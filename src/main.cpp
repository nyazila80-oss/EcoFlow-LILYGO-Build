#include <Arduino.h>
#include <Preferences.h>
#include <FS.h>
#include <SPIFFS.h>
#include <esp_heap_caps.h>
#include <atomic>

#include "config.h"
#include "time_ntp.h"
#include "wi-fi.h"
#include "mqtt.h"
#include "bms.h"
#include "can.h"
#include "ecoflow.h"
#include "web.h"
#include "ota.h"
#include "powerstream_api.h"
#include "jk_ble_proxy.h"
#include "low_soc_guard.h"
#include "powerstream_ble_lab.h"
#include "ble_boot_diag.h"
#include "cloud_boot_diag.h"

// 15AR controlled A/B: the stock Arduino loop task reserves 8192 bytes. The
// 15AN/15AO hardware run still had 3776 bytes unused when mbedTLS exhausted
// INTERNAL8 and failed a 4-byte allocation. Reclaim only 1024 bytes; hardware
// acceptance still requires at least 2048 bytes post-job stack margin.
static constexpr size_t TLS15AR_LOOP_STACK_BYTES = 7168;
static constexpr uint32_t TLS15AR_MIN_STACK_MARGIN_BYTES = 2048;
SET_LOOP_TASK_STACK_SIZE(TLS15AR_LOOP_STACK_BYTES);91

    Serial.printf("[15AR] loop stack A/B active: bytes=%u required_post_job_margin=%u\n",
                (unsigned)TLS15AR_LOOP_STACK_BYTES,
                (unsigned)TLS15AR_MIN_STACK_MARGIN_BYTES);
#include "diag_heartbeat.h"

#define SERIALDEBUG 0
#define CANDUMP 1
#define VERBOSE_BMS_PRINTS 0
#define DIAG_BLE_DISABLED 0

// 15AN hardware fix A/B: preserve the existing one-shot NimBLE lifecycle and
// keep BLE uninitialized until the first cloud/TLS job has actually completed.
// This gives verified TLS/X509 first ownership of INTERNAL8 without risky live
// NimBLE deinit/reinit. A bounded failsafe releases BLE if no cloud job is run.
static constexpr uint32_t TLS15AN_BLE_FAILSAFE_MS = 120000;
static bool s15anBleReleased = false;
static uint32_t s15anBootMs = 0;

AsyncWebServer server(80);
std::atomic<bool> canHealth{false};
static std::atomic<TaskHandle_t> sDiagHeartbeatHandle{nullptr};
uint32_t diagHeartbeatStackMinBytes() {
  TaskHandle_t handle=sDiagHeartbeatHandle.load(std::memory_order_acquire);
  return handle ? (uint32_t)uxTaskGetStackHighWaterMark(handle) : 0;
}

static void heapCheckpoint(const char* tag) {
  Serial.printf("[HEAP] %-18s free=%u largest8=%u min=%u\n", tag,
                (unsigned)ESP.getFreeHeap(),
                (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
                (unsigned)ESP.getMinFreeHeap());
}

static void diagHeartbeatTask(void*) {
  uint32_t seq = 0;
  for (;;) {
    const bool heapOk = heap_caps_check_integrity_all(false);
    const wl_status_t ws = WiFi.status();
    IPAddress ip = WiFi.localIP();
    const UBaseType_t selfHwm = uxTaskGetStackHighWaterMark(nullptr);
    const UBaseType_t rxHwm = canRxStackHighWater();
    const UBaseType_t decHwm = canDecodeStackHighWater();
    Serial.printf("[ALIVE] #%lu ms=%lu core=%d heap=%u largest8=%u min=%u heapOK=%u wifi=%d ip=%u.%u.%u.%u bmsLoop=%lu bmsTx=%lu/%lu canRx=%lu canFilt=%lu canDec=%lu canDrop=%lu stackRaw(diag/rx/dec)=%u/%u/%u\n",
      (unsigned long)++seq, (unsigned long)millis(), xPortGetCoreID(),
      (unsigned)ESP.getFreeHeap(),
      (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
      (unsigned)ESP.getMinFreeHeap(), heapOk ? 1u : 0u, (int)ws,
      (unsigned)ip[0], (unsigned)ip[1], (unsigned)ip[2], (unsigned)ip[3],
      (unsigned long)bmsDiagLoopTicks.load(std::memory_order_relaxed),
      (unsigned long)bmsDiagTxStarted.load(std::memory_order_relaxed), (unsigned long)bmsDiagTxAttempts.load(std::memory_order_relaxed),
      (unsigned long)can_rx_count, (unsigned long)can_rx_filtered, (unsigned long)can_decoded,
      (unsigned long)can_rx_dropped,
      (unsigned)selfHwm, (unsigned)rxHwm, (unsigned)decHwm);
    vTaskDelay(pdMS_TO_TICKS(5000));
  }
}

void setup() {
  Serial.begin(115200);
  s15anBootMs = millis();
  bleBootDiagBegin();
  cloudDiagBegin();
  delay(500);
  Serial.println("[DIAG] 15AN TLS-FIRST INTERNAL8 FIX A/B: BLE startup gated until first cloud job completes");
  heapCheckpoint("boot");

  pinMode(ME2107_EN, OUTPUT); digitalWrite(ME2107_EN, HIGH);
  pinMode(CAN_SPEED_MODE, OUTPUT); digitalWrite(CAN_SPEED_MODE, LOW);

  mqttInit(deviceId());
  loadCoreConfig();
  powerStreamBleLabInit();
  powerStreamApiLoad();
  bmsInit();
  heapCheckpoint("config+bms");

  filesystemInitStatus();
  Serial.printf("[FS] boot status=%s total=%u used=%u\n", filesystemStatusString(),
                filesystemReady() ? (unsigned)SPIFFS.totalBytes() : 0u,
                filesystemReady() ? (unsigned)SPIFFS.usedBytes() : 0u);
  heapCheckpoint("SPIFFS");

  wifiInstallEventDiagnostics();
  loadWiFiConfig();
  if (net.wifiSsid.isEmpty()) { Serial.println("No saved WiFi credentials -> starting setup AP"); startAP(); }
  else { startSTA(0); Serial.println("[WiFi] STA association started asynchronously"); }
  heapCheckpoint("WiFi kicked");

  ecoflowMessagesInit();
  canInitDriver();
  if (twai_ok) canStartTasks();
  else Serial.println("TWAI not ready; CAN tasks not started. Visit /can_try_init to retry later.");
  heapCheckpoint("CAN driver+tasks");

  initNTP();
  webInit(server); setupServerRoutes(server); otaInit(server); webSetupStaticRoutes(server);
  heapCheckpoint("web+OTA routes");
  server.begin();
  Serial.println("[WEB] HTTP server started on port 80");
  heapCheckpoint("HTTP started");
  Serial.println("[15AN] BLE/NimBLE startup held for TLS-first A/B; failsafe=120000ms");
}

void loop() {
  otaHandle();
  ensureWiFi();
  cloudDiagLoopTick();
  powerStreamApiLoopTick();

  // Release BLE only after the queued cloud operation has finished. This means
  // the complete verified TLS handshake and cleanup ran while NimBLE was still
  // uninitialized. If the operator never runs a cloud job, the failsafe keeps
  // normal JK functionality from being blocked indefinitely.
  if (!s15anBleReleased) {
    const String js = powerStreamApiJobStatusJson();
    const bool cloudCompleted = js.indexOf("\"done\":true") >= 0;
    const bool failsafe = (uint32_t)(millis() - s15anBootMs) >= TLS15AN_BLE_FAILSAFE_MS;
    if (cloudCompleted || failsafe) {
      s15anBleReleased = true;
      Serial.printf("[15AN] BLE startup released reason=%s free=%u largest8=%u\n",
                    cloudCompleted ? "cloud_done" : "failsafe",
                    (unsigned)heap_caps_get_free_size(MALLOC_CAP_8BIT),
                    (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    }
  }

  if (wifiConsumeWebRebindRequest()) {
    Serial.println("[WEB] legacy rebind request consumed; listener retained");
  }
  ntpTick();
  mqttLoopTick();
  applyBatteryMasterIfChanged();
  bmsLoopTick();
  lowSocGuardTick();
#if !DIAG_BLE_DISABLED
  if (s15anBleReleased) jkBleProxyTick();
#endif
  if (s15anBleReleased) powerStreamBleLabTick();
  webTick();
  canTxSequencerTick();
  ecoflowCbRecorderTick();
  delay(1);
}
