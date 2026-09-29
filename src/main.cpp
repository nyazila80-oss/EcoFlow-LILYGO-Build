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
#include "diag_heartbeat.h"

#define SERIALDEBUG 0
#define CANDUMP 1
#define VERBOSE_BMS_PRINTS 0

// AUDIT19.15.19 STACK-WATERMARK-DIAG: keep the bounded RS485 + independent heartbeat
// diagnostics from 19.15.3, but exercise the complete BLE proxy path as well.
#define DIAG_BLE_DISABLED 0

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
  bleBootDiagBegin();
  cloudDiagBegin();
  delay(500);
  Serial.println("[DIAG] AUDIT20.4.4 RX-DECOUPLED + LOW-SOC-GUARD: BLE enabled");
  heapCheckpoint("boot");

  pinMode(ME2107_EN, OUTPUT); digitalWrite(ME2107_EN, HIGH);
  pinMode(CAN_SPEED_MODE, OUTPUT); digitalWrite(CAN_SPEED_MODE, LOW);

  mqttInit(deviceId());
  loadCoreConfig();
  powerStreamBleLabInit();
  Serial.println("[COEX-A/B] 9.36.7.11 security-hardened staged JK/PowerStream BLE diagnostics active; no legacy runtime suppression");
  powerStreamApiLoad();
  bmsInit();
  heapCheckpoint("config+bms");

  // FINAL-HARDENED: one authoritative SPIFFS mount/status initialization.
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

  // FINAL-AUDIT: initialize TX serialization/XOR state before any CAN task can decode and reply.
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

  Serial.println("[DIAG] dedicated heartbeat task disabled in TLS RAM reclaim build");
}

void loop() {
  otaHandle();
  ensureWiFi();
  cloudDiagLoopTick();
  powerStreamApiLoopTick();
  if (wifiConsumeWebRebindRequest()) {
    // 9.36.7.6: intentionally do NOT end()/begin() the AsyncServer on STA/IP changes.
    // The listener is wildcard-bound; LwIP invalidates stale TCP sockets on disconnect.
    // Rebinding can itself race active AsyncTCP clients and is not needed for DHCP recovery.
    Serial.println("[WEB] legacy rebind request consumed; listener retained");
  }
  ntpTick();
  mqttLoopTick();
  applyBatteryMasterIfChanged();
  bmsLoopTick();
  lowSocGuardTick();
#if !DIAG_BLE_DISABLED
  jkBleProxyTick();
#endif
  powerStreamBleLabTick();
  webTick();
  canTxSequencerTick();
  ecoflowCbRecorderTick();
  // Explicit scheduler handoff; prevents a hot main loop from starving lower-priority work.
  delay(1);
}
