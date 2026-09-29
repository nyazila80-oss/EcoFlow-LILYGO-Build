#include "wi-fi.h"
#include <Preferences.h>
#include <freertos/semphr.h>
#include <atomic>
#include <esp_system.h>
#include "resource_gate.h"
#include "web.h"

extern String deviceId();
static StaticSemaphore_t netNvsMutexBuf;
static SemaphoreHandle_t netNvsMutex=xSemaphoreCreateMutexStatic(&netNvsMutexBuf);
static SemaphoreHandle_t netNvsLock(){return netNvsMutex;}
NetConfig net;
static bool apMode = false;
static bool hadStaConnection = false;
static uint32_t wifiNextRetryMs = 0;
static uint32_t wifiDisconnectedSinceMs = 0;
static uint32_t wifiLastFullRestartMs = 0;
static uint32_t wifiReconnectCount = 0;
static uint32_t wifiFullRestartCount = 0;
static uint32_t wifiRecoveryApCount = 0;
static bool recoveryApActive = false;
static std::atomic<bool> wifiCredReloadPending{false};
static uint32_t wifiCredNextReloadRetryMs=0; // main-loop only
static std::atomic<bool> webRebindPending{false};
static uint32_t wifiStaUpCount = 0;
static uint32_t wifiLastUpMs = 0;
static uint32_t wifiLastDownMs = 0;
static std::atomic<uint32_t> wifiEvtStaConnected{0}, wifiEvtStaDisconnected{0}, wifiEvtGotIp{0}, wifiEvtLostIp{0};
static std::atomic<uint32_t> wifiEvtLastReason{0}, wifiEvtLastMs{0}, wifiWebRebindSuppressed{0};
static std::atomic<int32_t> wifiEvtLastRssi{0};
static std::atomic<bool> wifiEvtInstalled{false};
// RTC state survives ESP.restart(). An outage that persists across the reboot
// must leave the recovery AP available instead of causing a reboot loop.
static RTC_NOINIT_ATTR uint32_t rtcWifiResetMagic;
static RTC_NOINIT_ATTR uint32_t rtcWifiResetAttempts;
static constexpr uint32_t WIFI_RESET_MAGIC = 0x57465231;
static bool previousWifiAutoReset = false;
static std::atomic<uint32_t> wifiAutoResetAttemptsDiag{0};

static constexpr uint32_t WIFI_SOFT_RETRY_MS = 10000;
static constexpr uint32_t WIFI_FULL_RESTART_AFTER_MS = 30000;
static constexpr uint32_t WIFI_FULL_RESTART_COOLDOWN_MS = 30000;
static constexpr uint32_t WIFI_RECOVERY_AP_AFTER_MS = 120000;
static constexpr uint32_t WIFI_DEVICE_RESET_AFTER_MS = 300000;
static constexpr uint32_t WIFI_STABLE_CLEAR_MS = 180000;

void wifiInstallEventDiagnostics(){
  if(wifiEvtInstalled.exchange(true,std::memory_order_acq_rel)) return;
  previousWifiAutoReset = rtcWifiResetMagic == WIFI_RESET_MAGIC &&
                          rtcWifiResetAttempts == 1 && esp_reset_reason() == ESP_RST_SW;
  if(rtcWifiResetMagic != WIFI_RESET_MAGIC || rtcWifiResetAttempts > 1 ||
     esp_reset_reason() != ESP_RST_SW) {
    rtcWifiResetMagic = WIFI_RESET_MAGIC;
    rtcWifiResetAttempts = 0;
  }
  wifiAutoResetAttemptsDiag.store(rtcWifiResetAttempts,std::memory_order_relaxed);
  WiFi.onEvent([](arduino_event_id_t event, arduino_event_info_t info){
    wifiEvtLastMs.store(millis(),std::memory_order_relaxed);
    switch(event){
      case ARDUINO_EVENT_WIFI_STA_CONNECTED: wifiEvtStaConnected.fetch_add(1,std::memory_order_relaxed); break;
      case ARDUINO_EVENT_WIFI_STA_DISCONNECTED:
        wifiEvtStaDisconnected.fetch_add(1,std::memory_order_relaxed);
        wifiEvtLastReason.store((uint32_t)info.wifi_sta_disconnected.reason,std::memory_order_relaxed);
        wifiEvtLastRssi.store((int32_t)info.wifi_sta_disconnected.rssi,std::memory_order_relaxed);
        break;
      case ARDUINO_EVENT_WIFI_STA_GOT_IP: wifiEvtGotIp.fetch_add(1,std::memory_order_relaxed); break;
      case ARDUINO_EVENT_WIFI_STA_LOST_IP: wifiEvtLostIp.fetch_add(1,std::memory_order_relaxed); break;
      default: break;
    }
  });
}

bool loadWiFiConfig() {
  SemaphoreHandle_t m=netNvsLock(); if(!m || xSemaphoreTake(m,pdMS_TO_TICKS(250))!=pdTRUE)return false;
  struct Unlock{SemaphoreHandle_t m;~Unlock(){xSemaphoreGive(m);}} unlock{m};
  Preferences p;
  if(!p.begin("net", true) && !p.begin("net", false))return false;
  net.wifiSsid = p.getString("ssid", "");
  net.wifiPass = p.getString("pass", ""); p.end();
  return true;
}
void saveWiFiConfig() {
  Preferences p; p.begin("net", false); p.putString("ssid", net.wifiSsid);
  p.putString("pass", net.wifiPass); p.end();
}

bool wifiSaveCredentialsDeferred(const String& ssid, const String& pass) {
  SemaphoreHandle_t mtx=netNvsLock();
  if(!mtx || xSemaphoreTake(mtx,pdMS_TO_TICKS(250))!=pdTRUE) return false;
  struct Unlock{SemaphoreHandle_t m;~Unlock(){xSemaphoreGive(m);}} unlock{mtx};
  Preferences p;
  if (!p.begin("net", false)) return false;
  const String oldSsid = p.getString("ssid", "");
  const String oldPass = p.getString("pass", "");
  const bool changed = oldSsid != ssid || oldPass != pass;
  const bool ok1 = p.putString("ssid", ssid) == ssid.length();
  const bool ok2 = p.putString("pass", pass) == pass.length();
  const bool rb = p.getString("ssid", "") == ssid && p.getString("pass", "") == pass;
  p.end();
  if (ok1 && ok2 && rb && changed) wifiCredReloadPending.store(true, std::memory_order_release);
  return ok1 && ok2 && rb;
}

String wifiModeToString(wifi_mode_t m) {
  switch(m){case WIFI_MODE_NULL:return "NULL";case WIFI_MODE_STA:return "STA";
    case WIFI_MODE_AP:return "AP";case WIFI_MODE_APSTA:return "AP+STA";default:return "UNKNOWN";}
}
static bool staHasUsableIp() {
  if (WiFi.status() != WL_CONNECTED) return false;
  const IPAddress ip = WiFi.localIP();
  return (uint32_t)ip != 0u;
}


static void startRecoveryAPSTA() {
  if (net.wifiSsid.isEmpty()) { startAP(); return; }
  String ssid="EcoFlowBridge-"+deviceId(); String pass=String(remoteAuthPassword());
  WiFi.mode(WIFI_AP_STA);
  WiFi.setSleep(true); // ESP32 Wi-Fi/BLE coexistence requires modem sleep.
  WiFi.setAutoReconnect(true);
  if (!recoveryApActive) {
    if (WiFi.softAP(ssid.c_str(), pass.c_str())) {
      recoveryApActive=true; apMode=true; ++wifiRecoveryApCount;
      Serial.printf("[WiFi] Recovery AP+STA: %s IP=%s count=%lu\n", ssid.c_str(),
                    WiFi.softAPIP().toString().c_str(), (unsigned long)wifiRecoveryApCount);
    }
  }
  WiFi.begin(net.wifiSsid.c_str(),net.wifiPass.c_str());
}

void startAP() {
  if (apMode && (WiFi.getMode()==WIFI_MODE_AP || WiFi.getMode()==WIFI_MODE_APSTA)) return;
  apMode=true; recoveryApActive=false;
  String ssid="EcoFlowBridge-"+deviceId(); String pass=String(remoteAuthPassword());
  WiFi.mode(WIFI_AP);
  WiFi.softAP(ssid.c_str(),pass.c_str());
  Serial.printf("[WiFi] Setup AP: %s IP=%s\n", ssid.c_str(),WiFi.softAPIP().toString().c_str());
}

bool startSTA(uint32_t timeoutMs) {
  if(net.wifiSsid.isEmpty()) return false;
  if (apMode) { WiFi.softAPdisconnect(true); apMode=false; recoveryApActive=false; }
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(true); // Keep coexistence valid before delayed NimBLE init.
  WiFi.setAutoReconnect(true);
  WiFi.begin(net.wifiSsid.c_str(),net.wifiPass.c_str());
  wifiDisconnectedSinceMs = millis();
  wifiNextRetryMs = millis()+WIFI_SOFT_RETRY_MS;
  if (timeoutMs==0) return staHasUsableIp();
  uint32_t start=millis();
  while(!staHasUsableIp() && millis()-start<timeoutMs) delay(50);
  if(staHasUsableIp()){
    hadStaConnection=true;
    Serial.printf("WiFi connected. IP: %s RSSI=%d\n",WiFi.localIP().toString().c_str(),WiFi.RSSI());
    return true;
  }
  return false;
}

void ensureWiFi() {
  if (wifiCredReloadPending.load(std::memory_order_acquire) &&
      (int32_t)(millis()-wifiCredNextReloadRetryMs)>=0 &&
      wifiCredReloadPending.exchange(false, std::memory_order_acq_rel)) {
    if(loadWiFiConfig()){
      wifiCredNextReloadRetryMs=0;
      wifiCredsUpdatedKick();
    } else {
      wifiCredNextReloadRetryMs=millis()+1000;
      wifiCredReloadPending.store(true, std::memory_order_release);
    }
  }
  const uint32_t now=millis();
  if(staHasUsableIp()){
    if(!hadStaConnection) {
      ++wifiStaUpCount; wifiLastUpMs=now;
      // AsyncTCP was started during setup, often before DHCP completed. Rebind once
      // after every genuine STA/IP recovery so port 80 is attached to the healthy netif.
      wifiWebRebindSuppressed.fetch_add(1,std::memory_order_relaxed);
      Serial.printf("[WiFi] STA connected. IP=%s RSSI=%d mode=%s up#=%lu -> listener retained (rebind suppressed)\n",
        WiFi.localIP().toString().c_str(), WiFi.RSSI(), wifiModeToString(WiFi.getMode()).c_str(),
        (unsigned long)wifiStaUpCount);
    }
    hadStaConnection=true; wifiDisconnectedSinceMs=0;
    if(rtcWifiResetAttempts && (uint32_t)(now-wifiLastUpMs)>=WIFI_STABLE_CLEAR_MS) {
      rtcWifiResetAttempts=0;
      wifiAutoResetAttemptsDiag.store(0,std::memory_order_relaxed);
    }
    // Once STA is healthy again, remove the temporary recovery AP to reduce radio load.
    if (recoveryApActive) {
      WiFi.softAPdisconnect(true); recoveryApActive=false; apMode=false;
      WiFi.mode(WIFI_STA); WiFi.setSleep(true);
  WiFi.setAutoReconnect(true);
      Serial.println("[WiFi] Recovery complete; AP disabled, STA retained");
    }
    return;
  }
  if (wifiDisconnectedSinceMs==0) { wifiDisconnectedSinceMs=now; wifiLastDownMs=now; hadStaConnection=false; }
  if(net.wifiSsid.isEmpty()) { if(!apMode) startAP(); return; }

  const uint32_t offlineMs = now - wifiDisconnectedSinceMs; // wrap-safe unsigned delta

  if (offlineMs >= WIFI_RECOVERY_AP_AFTER_MS) {
    if (!recoveryApActive) startRecoveryAPSTA();
    if ((int32_t)(now-wifiNextRetryMs)>=0) {
      ++wifiReconnectCount;
      WiFi.reconnect();
      wifiNextRetryMs=now+WIFI_SOFT_RETRY_MS;
    }
    // Only reboot after a real STA/IP connection was seen in this boot. Do
    // not reboot during first setup, while someone uses the recovery AP, or
    // while a PowerStream BLE/Cloud operation owns the heavy-operation gate.
    if (offlineMs >= WIFI_DEVICE_RESET_AFTER_MS && wifiStaUpCount > 0 &&
        wifiFullRestartCount > 0 && recoveryApActive &&
        WiFi.softAPgetStationNum() == 0 &&
        heavyOpOwner() == HeavyOpOwner::NONE && rtcWifiResetAttempts == 0) {
      rtcWifiResetAttempts=1;
      wifiAutoResetAttemptsDiag.store(1,std::memory_order_relaxed);
      Serial.printf("[WiFi] STA offline %lums after prior IP; automatic ESP software reset (recovery AP attempted)\n",
                    (unsigned long)offlineMs);
      Serial.flush();
      ESP.restart();
    }
    return;
  }

  if (offlineMs >= WIFI_FULL_RESTART_AFTER_MS &&
      (wifiLastFullRestartMs==0 || (uint32_t)(now-wifiLastFullRestartMs)>=WIFI_FULL_RESTART_COOLDOWN_MS)) {
    ++wifiFullRestartCount; wifiLastFullRestartMs=now;
    Serial.printf("[WiFi] STA offline %lums; full restart #%lu (status=%d heap=%u)\n",
                  (unsigned long)offlineMs, (unsigned long)wifiFullRestartCount,
                  (int)WiFi.status(), (unsigned)ESP.getFreeHeap());
    WiFi.disconnect(false, false); // keep persisted credentials/config intact
    delay(20);
    WiFi.mode(WIFI_STA); WiFi.setSleep(true);
  WiFi.setAutoReconnect(true);
    WiFi.begin(net.wifiSsid.c_str(),net.wifiPass.c_str());
    wifiNextRetryMs=now+WIFI_SOFT_RETRY_MS;
    return;
  }

  if((int32_t)(now-wifiNextRetryMs)<0) return;
  ++wifiReconnectCount;
  Serial.printf("[WiFi] STA offline status=%d; reconnect #%lu (offline=%lums heap=%u)\n",
                (int)WiFi.status(), (unsigned long)wifiReconnectCount,
                (unsigned long)offlineMs, (unsigned)ESP.getFreeHeap());
  WiFi.reconnect();
  wifiNextRetryMs=now+WIFI_SOFT_RETRY_MS;
}

void wifiCredsUpdatedKick(){
  hadStaConnection=false; wifiNextRetryMs=0; wifiDisconnectedSinceMs=millis();
  wifiLastFullRestartMs=0;
  if (!net.wifiSsid.isEmpty()) startSTA(0);
}


bool wifiConsumeWebRebindRequest(){ return webRebindPending.exchange(false, std::memory_order_acq_rel); }
uint32_t wifiReconnectCounter(){ return wifiReconnectCount; }
uint32_t wifiFullRestartCounter(){ return wifiFullRestartCount; }
uint32_t wifiRecoveryApCounter(){ return wifiRecoveryApCount; }
uint32_t wifiStaUpCounter(){ return wifiStaUpCount; }
uint32_t wifiLastStaUpMs(){ return wifiLastUpMs; }
uint32_t wifiLastStaDownMs(){ return wifiLastDownMs; }

uint32_t wifiEventStaConnectedCount(){return wifiEvtStaConnected.load(std::memory_order_relaxed);}
uint32_t wifiEventStaDisconnectedCount(){return wifiEvtStaDisconnected.load(std::memory_order_relaxed);}
uint32_t wifiEventGotIpCount(){return wifiEvtGotIp.load(std::memory_order_relaxed);}
uint32_t wifiEventLostIpCount(){return wifiEvtLostIp.load(std::memory_order_relaxed);}
uint32_t wifiLastDisconnectReason(){return wifiEvtLastReason.load(std::memory_order_relaxed);}
int32_t wifiLastDisconnectRssi(){return wifiEvtLastRssi.load(std::memory_order_relaxed);}
uint32_t wifiLastEventMs(){return wifiEvtLastMs.load(std::memory_order_relaxed);}
uint32_t wifiWebRebindSuppressedCount(){return wifiWebRebindSuppressed.load(std::memory_order_relaxed);}
bool wifiPreviousAutoReset(){return previousWifiAutoReset;}
uint32_t wifiAutoResetAttempts(){return wifiAutoResetAttemptsDiag.load(std::memory_order_relaxed);}
