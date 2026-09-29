#include "can.h"
#include "ecoflow.h"
#include "bms.h"
#include "low_soc_guard.h"
#include "web.h"
#include "time_ntp.h"
#include <esp_err.h>
#include <atomic>

// --- CAN fast pipeline counters ---
std::atomic<uint32_t> can_rx_count{0};
std::atomic<uint32_t> can_rx_dropped{0};
std::atomic<uint32_t> can_rx_queue_overflow{0};
std::atomic<uint32_t> can_rx_epoch_dropped{0};
std::atomic<uint32_t> can_decoded{0};
std::atomic<uint32_t> can_rx_filtered{0};

// --- RX queue ---
QueueHandle_t canRxQ = nullptr;

// --- Driver status ---
bool twai_ok = false;
static bool canTasksStarted = false;

// AUDIT20.4.5.9.20: serialize late CAN init/task-start attempts. /can_try_init
// is an AsyncWebServer route and can be hit concurrently; startup may also call
// canStartTasks(). A recursive static mutex avoids duplicate queues/tasks and
// keeps initialization off the heap.
static StaticSemaphore_t g_canInitMutexBuf;
static SemaphoreHandle_t g_canInitMutex=xSemaphoreCreateRecursiveMutexStatic(&g_canInitMutexBuf);
struct CanInitLock {
  bool held=false;
  CanInitLock(){ held=g_canInitMutex && xSemaphoreTakeRecursive(g_canInitMutex,portMAX_DELAY)==pdTRUE; }
  ~CanInitLock(){ if(held) xSemaphoreGiveRecursive(g_canInitMutex); }
};
static TaskHandle_t canRxTaskHandle = nullptr;
static TaskHandle_t canDecodeTaskHandle = nullptr;
static TaskHandle_t canLogTaskHandle = nullptr;
static TaskHandle_t canAlertTaskHandle = nullptr;

// AUDIT20.4.5.9.31: runtime bus-state gate is independent from the legacy
// installed-driver flag. BUS-OFF closes TX/RX admission immediately; only a
// completed TWAI recovery followed by a successful twai_start() re-opens it.
static std::atomic_bool canBusReady{false};
static std::atomic<uint32_t> canBusEpoch{1};
struct CanRxEpochItem { twai_message_t msg; uint32_t epoch; };
static inline void closeCanBusBoundary() {
  if (canBusReady.exchange(false, std::memory_order_acq_rel))
    canBusEpoch.fetch_add(1, std::memory_order_acq_rel);
}

std::atomic<uint32_t> can_bus_off_count{0};
std::atomic<uint32_t> can_bus_recovered_count{0};
std::atomic<uint32_t> can_bus_recovery_fail{0};
struct __attribute__((packed)) CanLogItem { uint32_t id; uint32_t ms; uint8_t dlc; uint8_t data[8]; };
static QueueHandle_t canLogQ = nullptr;
std::atomic<uint32_t> can_log_dropped{0};

// ---------------- Driver init ----------------
void canInitDriver() {
  twai_general_config_t g =
      TWAI_GENERAL_CONFIG_DEFAULT((gpio_num_t)CAN_TX, (gpio_num_t)CAN_RX, TWAI_MODE_NORMAL);

  g.rx_queue_len = TWAI_RXQ;
  g.tx_queue_len = TWAI_TXQ;
  g.intr_flags   = 0;  // don't force IRAM

  twai_timing_config_t t = TWAI_TIMING_CONFIG_1MBITS();
  twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();

  Serial.printf("TWAI pins TX=%d RX=%d, rxQ=%d txQ=%d\n",
                (int)g.tx_io, (int)g.rx_io, g.rx_queue_len, g.tx_queue_len);

  esp_err_t err = twai_driver_install(&g, &t, &f);
  if (err != ESP_OK) {
    Serial.printf("TWAI install failed: %s (rxQ=%d txQ=%d) FreeHeap=%u\n",
                  esp_err_to_name(err), g.rx_queue_len, g.tx_queue_len, (unsigned)ESP.getFreeHeap());
    twai_ok = false;
    return;
  }

  err = twai_start();
  if (err != ESP_OK) {
    Serial.printf("TWAI start failed: %s\n", esp_err_to_name(err));
    twai_driver_uninstall();
    twai_ok = false;
    return;
  }

  uint32_t alerts = TWAI_ALERT_RX_DATA | TWAI_ALERT_RX_QUEUE_FULL |
                    TWAI_ALERT_RX_FIFO_OVERRUN | TWAI_ALERT_ERR_PASS |
                    TWAI_ALERT_BUS_ERROR | TWAI_ALERT_ARB_LOST |
                    TWAI_ALERT_TX_FAILED | TWAI_ALERT_TX_SUCCESS |
                    TWAI_ALERT_BUS_OFF | TWAI_ALERT_RECOVERY_IN_PROGRESS |
                    TWAI_ALERT_BUS_RECOVERED;
  twai_reconfigure_alerts(alerts, NULL);

  twai_ok = true;
  canBusReady.store(true, std::memory_order_release);
  Serial.println("TWAI CAN initialized (1Mbps)");
}

uint32_t canCurrentBusEpoch() { return canBusEpoch.load(std::memory_order_acquire); }

// ---------------- TX primitive ----------------
bool sendCANFrame(uint32_t can_id, const uint8_t* data, uint8_t len) {
  // Runtime safety gate: when BMS-backed telemetry is selected, never transmit
  // EcoFlow CAN frames from stale/unvalidated JK data. User config remains untouched.
  if (!canBusReady.load(std::memory_order_acquire) || !bmsTelemetryValidForCan() || lowSocGuardRecoveryPending()) return false;
  if (!data || len == 0 || len > 8) {
    Serial.printf("sendCANFrame: bad args (data=%p len=%u)\n", data, len);
    return false;
  }
  twai_message_t msg = {};
  msg.identifier       = can_id & 0x1FFFFFFF;
  msg.extd             = 1;
  msg.rtr              = 0;
  msg.data_length_code = len;
  memcpy(msg.data, data, len);

  // AUDIT20.4.5.9.30: bound each fragment wait. A congested/bus-off TWAI
  // queue must not pin the CAN producer for 100 ms per fragment. Logical-message
  // code aborts on the first failed fragment, so this is also the maximum wait
  // before the message is abandoned.
  esp_err_t err = twai_transmit(&msg, pdMS_TO_TICKS(25));
  if (err != ESP_OK) {
    return false;
  }
  ecoflowCbRecorderRawFrame(true, msg.identifier, msg.extd, msg.rtr, msg.data, msg.data_length_code);
  return true;
}

// ---------------- Tasks ----------------
static void canAlertTask(void *arg) {
  (void)arg;
  // Close the startup window: BUS-OFF may have happened after twai_start() but
  // before this monitor task was scheduled. Synchronize from driver state once.
  twai_status_info_t initial{};
  if (twai_get_status_info(&initial) == ESP_OK) {
    if (initial.state == TWAI_STATE_BUS_OFF) {
      closeCanBusBoundary();
      can_bus_off_count.fetch_add(1, std::memory_order_relaxed);
      if (twai_initiate_recovery() != ESP_OK)
        can_bus_recovery_fail.fetch_add(1, std::memory_order_relaxed);
    } else if (initial.state == TWAI_STATE_RUNNING) {
      canBusReady.store(true, std::memory_order_release);
    } else {
      closeCanBusBoundary();
    }
  } else {
    closeCanBusBoundary();
  }

  for (;;) {
    uint32_t alerts = 0;
    const esp_err_t ar = twai_read_alerts(&alerts, pdMS_TO_TICKS(100));
    if (ar == ESP_ERR_TIMEOUT) {
      // Periodic state reconciliation makes recovery robust even if an alert was
      // missed/coalesced. There is no other intentional twai_stop() path.
      twai_status_info_t st{};
      if (twai_get_status_info(&st) == ESP_OK) {
        if (st.state == TWAI_STATE_RUNNING) {
          canBusReady.store(true, std::memory_order_release);
        } else if (st.state == TWAI_STATE_BUS_OFF) {
          closeCanBusBoundary();
          if (twai_initiate_recovery() != ESP_OK)
            can_bus_recovery_fail.fetch_add(1, std::memory_order_relaxed);
        } else if (st.state == TWAI_STATE_STOPPED) {
          closeCanBusBoundary();
          if (twai_start() == ESP_OK) {
            can_bus_recovered_count.fetch_add(1, std::memory_order_relaxed);
            canBusReady.store(true, std::memory_order_release);
          } else {
            can_bus_recovery_fail.fetch_add(1, std::memory_order_relaxed);
          }
        } else {
          closeCanBusBoundary();
        }
      } else {
        closeCanBusBoundary();
      }
      continue;
    }
    if (ar != ESP_OK) { closeCanBusBoundary(); vTaskDelay(pdMS_TO_TICKS(10)); continue; }

    if (alerts & TWAI_ALERT_BUS_OFF) {
      closeCanBusBoundary();
      can_bus_off_count.fetch_add(1, std::memory_order_relaxed);
      // Recovery is explicit in ESP-IDF. If initiation fails, remain fail-closed;
      // never pretend the bus is usable merely because the driver is installed.
      if (twai_initiate_recovery() != ESP_OK)
        can_bus_recovery_fail.fetch_add(1, std::memory_order_relaxed);
    }

    if (alerts & TWAI_ALERT_BUS_RECOVERED) {
      // After recovery TWAI is STOPPED. Re-start is required before TX/RX.
      if (twai_start() == ESP_OK) {
        can_bus_recovered_count.fetch_add(1, std::memory_order_relaxed);
        canBusReady.store(true, std::memory_order_release);
      } else {
        can_bus_recovery_fail.fetch_add(1, std::memory_order_relaxed);
        closeCanBusBoundary();
      }
    }
  }
}

static void canRxTask(void *arg) {
  twai_message_t msg;
  for (;;) {
    if (!twai_ok || !canBusReady.load(std::memory_order_acquire)) { vTaskDelay(pdMS_TO_TICKS(10)); continue; }

    // Capture the fault generation BEFORE blocking in twai_receive(). If BUS-OFF
    // occurs while receive is waiting, a frame returned from that call remains
    // tagged with the pre-fault generation and cannot cross the boundary.
    const uint32_t rxEpoch = canBusEpoch.load(std::memory_order_acquire);
    esp_err_t r = twai_receive(&msg, pdMS_TO_TICKS(20));

    if (r == ESP_OK) {
      can_rx_count++;
      // Forensic tap is before config/rxlogging prefilters so RX Logging may stay OFF.
      ecoflowCbRecorderRawFrame(false, msg.identifier, msg.extd, msg.rtr, msg.data, msg.data_length_code);

      // AUDIT20.4.4: copy raw RX frames into an independent best-effort log
      // queue. The hot TWAI receive task never formats strings or touches WebSocket.
      // If logging cannot keep up, only log frames are dropped; decoder admission
      // and the forensic recorder remain independent.
      if (rxLoggingAtomic() && canLogQ) {
        CanLogItem li{}; li.id=msg.identifier & 0x1FFFFFFFUL; li.ms=millis(); li.dlc=msg.data_length_code>8?8:msg.data_length_code; memcpy(li.data,msg.data,li.dlc);
        if (xQueueSend(canLogQ,&li,0)!=pdTRUE) can_log_dropped++;
      }

      // RX enabled gate (identical logic)
      if (!canRxEnabledAtomic()) {
        continue;
      }

      // AUDIT20.4.4: decoder admission is independent of RX Logging.
      // Raw logging/forensics taps happen before this point; the decoder queue
      // always receives only the three EcoFlow 0x14001 fragmentation IDs.
      const uint32_t fid = msg.identifier & 0x1FFFFFFFUL;
      const bool eco14001 = msg.extd && !msg.rtr &&
          (fid == 0x10014001UL || fid == 0x10114001UL || fid == 0x10214001UL);
      if (!eco14001) {
        can_rx_filtered++;
        continue;
      }

      CanRxEpochItem qi{msg, rxEpoch};
      if (canRxQ && xQueueSend(canRxQ, &qi, 0) != pdTRUE) {
        CanRxEpochItem dump{};
        xQueueReceive(canRxQ, &dump, 0);
        xQueueSend(canRxQ, &qi, 0);
        can_rx_dropped++;
        can_rx_queue_overflow++;
      }

    } else if (r == ESP_ERR_TIMEOUT) {
      // idle
    } else {
      vTaskDelay(pdMS_TO_TICKS(2));
    }
  }
}

static void canLogTask(void *arg) {
  CanLogItem li;
  for (;;) {
    if (xQueueReceive(canLogQ,&li,portMAX_DELAY)==pdTRUE) {
      // Drop queued raw-log work immediately when the user turns logging off.
      if (!rxLoggingAtomic()) continue;
      char logBuffer[96];
      const uint32_t ageMs=(uint32_t)(millis()-li.ms);
      const double ts=now_seconds() - ((double)ageMs/1000.0);
      int n=snprintf(logBuffer,sizeof(logBuffer),"(%012.6f) vcanRx %08lX#",ts,(unsigned long)li.id);
      for(uint8_t i=0;i<li.dlc && n<(int)sizeof(logBuffer)-3;++i) n+=snprintf(logBuffer+n,sizeof(logBuffer)-n,"%02X",li.data[i]);
      streamCanLog(logBuffer);
    }
  }
}

static void canDecodeTask(void *arg) {
  CanRxEpochItem qi{};
  for (;;) {
    if (xQueueReceive(canRxQ, &qi, portMAX_DELAY) == pdTRUE) {
      // AUDIT20.4.5.9.33: never decode a frame captured before the latest
      // BUS-OFF boundary. This prevents pre-fault queue contents from being
      // combined with post-recovery fragments.
      if (qi.epoch != canBusEpoch.load(std::memory_order_acquire)) {
        can_rx_dropped.fetch_add(1, std::memory_order_relaxed);
        can_rx_epoch_dropped.fetch_add(1, std::memory_order_relaxed);
        continue;
      }
      processEcoFlowCAN(qi.msg);
      can_decoded++;
    }
  }
}

// ---------------- Start helpers ----------------
void canStartTasks() {
  CanInitLock initLock; if(!initLock.held) return;
  if (!twai_ok || canTasksStarted) return;

  if (!canRxQ) {
    canRxQ = xQueueCreate(24, sizeof(CanRxEpochItem));
    if (!canRxQ) {
      Serial.println("CAN RX queue allocation failed; tasks not started");
      return;
    }
  }

  // Raw logging is diagnostic only. Create it BEFORE the core RX task so a
  // failed optional logger can be torn down without racing a live producer.
  if (!canLogQ) canLogQ=xQueueCreate(48,sizeof(CanLogItem));
  BaseType_t logOk = pdFAIL;
  if (canLogQ) {
    logOk=xTaskCreatePinnedToCore(canLogTask, "canLog", 2560, nullptr, 3, &canLogTaskHandle, 1);
    if (logOk != pdPASS) {
      vQueueDelete(canLogQ); canLogQ=nullptr; canLogTaskHandle=nullptr;
      can_log_dropped++;
    }
  }

  // Bus-off recovery is a core safety task, not optional diagnostics.
  BaseType_t alertOk = xTaskCreatePinnedToCore(canAlertTask, "canAlert", 2560, nullptr, 9, &canAlertTaskHandle, 0);
  BaseType_t rxOk = xTaskCreatePinnedToCore(canRxTask, "canRx", 3072, nullptr, 8, &canRxTaskHandle, 0);
  BaseType_t decOk = xTaskCreatePinnedToCore(canDecodeTask, "canDecode", 4096, nullptr, 7, &canDecodeTaskHandle, 0);

  if (alertOk == pdPASS && rxOk == pdPASS && decOk == pdPASS) {
    canTasksStarted = true;
    Serial.printf("CAN RX/decode tasks started; appQ=24 rawLog=%s heap=%u\n",
                  logOk == pdPASS ? "ON" : "UNAVAILABLE", (unsigned)ESP.getFreeHeap());
    return;
  }

  // Only a core RX/decode failure rolls the core pipeline back. Also tear down
  // the optional logger because no producer will remain after rollback.
  if (alertOk == pdPASS && canAlertTaskHandle) { vTaskDelete(canAlertTaskHandle); canAlertTaskHandle = nullptr; }
  if (rxOk == pdPASS && canRxTaskHandle) { vTaskDelete(canRxTaskHandle); canRxTaskHandle = nullptr; }
  if (decOk == pdPASS && canDecodeTaskHandle) { vTaskDelete(canDecodeTaskHandle); canDecodeTaskHandle = nullptr; }
  if (logOk == pdPASS && canLogTaskHandle) { vTaskDelete(canLogTaskHandle); canLogTaskHandle = nullptr; }
  if (canLogQ) { vQueueDelete(canLogQ); canLogQ=nullptr; }
  canTasksStarted = false;
  closeCanBusBoundary();
  Serial.printf("CAN core task creation incomplete alert=%ld rx=%ld decode=%ld; core tasks removed, retry allowed (log=%ld)\n",
                (long)alertOk, (long)rxOk, (long)decOk, (long)logOk);
}

bool canTryInitAndStart() {
  CanInitLock initLock; if(!initLock.held) return false;
  if (!twai_ok) {
    canInitDriver();
  }
  if (twai_ok) {
    canStartTasks();
    return canTasksStarted;
  }
  return false;
}

UBaseType_t canRxStackHighWater() {
  CanInitLock initLock;
  if(!initLock.held || !canRxTaskHandle) return 0;
  return uxTaskGetStackHighWaterMark(canRxTaskHandle);
}

UBaseType_t canDecodeStackHighWater() {
  CanInitLock initLock;
  if(!initLock.held || !canDecodeTaskHandle) return 0;
  return uxTaskGetStackHighWaterMark(canDecodeTaskHandle);
}
