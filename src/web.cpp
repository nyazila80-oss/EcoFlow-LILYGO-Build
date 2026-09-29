#include "web.h"
#include <atomic>
#include <cerrno>
#include <esp_heap_caps.h>

#include <Preferences.h>
#include <FS.h>
#include <SPIFFS.h>

#include "config.h"
#include "can.h"
#include "wi-fi.h"
#include "mqtt.h"
#include "bms.h"
#include "ecoflow.h"
#include "powerstream_api.h"
#include "low_soc_guard.h"
#include "powerstream_ble_lab.h"
#include "jk_ble_proxy.h"
#include "ble_boot_diag.h"
#include "cloud_boot_diag.h"
#include "ps_probe_trace.h"
struct CrashHttpScope {
  CrashHttpRoute route;
  explicit CrashHttpScope(CrashHttpRoute r):route(r){crashHttpEnter(route);}
  ~CrashHttpScope(){crashHttpLeave(route);}
};
#include "diag_heartbeat.h"
// AUDIT20.4.5.9.15: AsyncWebServer callbacks must not mutate the shared Config
// object. They publish a fixed-size pending transaction; webTick() (main-loop
// owner) applies it coherently. No Arduino String crosses the task boundary.
enum : uint16_t { P_VOLT=1u<<0, P_CHGVOLT=1u<<1, P_TEMP=1u<<2, P_SOC=1u<<3,
                  P_DISRUN=1u<<4, P_CHGRUN=1u<<5, P_UP=1u<<6, P_DN=1u<<7, P_SERIAL=1u<<8 };
struct PendingCoreUpdate {
  uint16_t mask=0, volt=0, chgvolt=0; uint8_t temp=0, soc=0, up=0, dn=0;
  uint32_t disrun=0, chgrun=0; char serial[17]{};
};
static PendingCoreUpdate sPendingCoreUpdate;
static portMUX_TYPE sPendingCoreMux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<uint8_t> sPendingCoreState{0}; // 0=FREE, 1=WRITING, 2=READY
struct PendingToggle { char key[24]{}; };
static PendingToggle sPendingToggle;
static portMUX_TYPE sPendingToggleMux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<uint8_t> sPendingToggleState{0}; // 0 FREE, 1 WRITING, 2 READY
static bool queueToggle(const String& key){
  if(key.length()==0 || key.length()>=sizeof(sPendingToggle.key)) return false;
  uint8_t expected=0; if(!sPendingToggleState.compare_exchange_strong(expected,1,std::memory_order_acq_rel)) return false;
  PendingToggle t{}; key.toCharArray(t.key,sizeof(t.key));
  portENTER_CRITICAL(&sPendingToggleMux); sPendingToggle=t; portEXIT_CRITICAL(&sPendingToggleMux);
  sPendingToggleState.store(2,std::memory_order_release); return true;
}
static void applyPendingToggle(){
  if(sPendingToggleState.load(std::memory_order_acquire)!=2) return;
  PendingToggle t{}; portENTER_CRITICAL(&sPendingToggleMux); t=sPendingToggle; portEXIT_CRITICAL(&sPendingToggleMux);
  bool nv=false; if(!toggleConfigMainOwner(t.key,nv)) Serial.printf("[WEB] rejected queued toggle %s\n",t.key);
  sPendingToggleState.store(0,std::memory_order_release);
}

static bool queueCoreUpdate(const PendingCoreUpdate& in){
  uint8_t expected=0;
  if(!sPendingCoreState.compare_exchange_strong(expected,1,std::memory_order_acq_rel)) return false;
  portENTER_CRITICAL(&sPendingCoreMux); sPendingCoreUpdate=in; portEXIT_CRITICAL(&sPendingCoreMux);
  sPendingCoreState.store(2,std::memory_order_release);
  return true;
}
static void applyPendingCoreUpdate(){
  if(sPendingCoreState.load(std::memory_order_acquire)!=2) return;
  PendingCoreUpdate u; portENTER_CRITICAL(&sPendingCoreMux); u=sPendingCoreUpdate; portEXIT_CRITICAL(&sPendingCoreMux);
  if(u.mask&P_VOLT) config.volt=u.volt; if(u.mask&P_CHGVOLT) config.chgvolt=u.chgvolt;
  if(u.mask&P_TEMP) config.temp=u.temp; if(u.mask&P_SOC) config.soc=u.soc;
  if(u.mask&P_DISRUN) config.disruntime=u.disrun; if(u.mask&P_CHGRUN) config.chgruntime=u.chgrun;
  if(u.mask&P_UP) config.bmsChgUp=u.up; if(u.mask&P_DN) config.bmsChgDn=u.dn;
  if(u.mask&P_SERIAL) memcpy(config.serialStr,u.serial,17);
  syncCanBatterySnapshotAtomic();
  if(u.mask&(P_CHGVOLT|P_SERIAL)) syncCanIdentitySnapshotAtomic();
  if(u.mask&(P_CHGVOLT|P_SERIAL|P_UP|P_DN)) saveCoreConfig();
  sPendingCoreState.store(0,std::memory_order_release);
}





struct PendingGuardUpdate { bool socEn=false; uint8_t stop=0,resume=0; bool hasSoh=false,sohEn=false; uint8_t sohMin=0; };
static PendingGuardUpdate sPendingGuard;
static portMUX_TYPE sPendingGuardMux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<uint8_t> sPendingGuardState{0};
static bool queueGuardUpdate(const PendingGuardUpdate& in){ uint8_t e=0; if(!sPendingGuardState.compare_exchange_strong(e,1,std::memory_order_acq_rel))return false; portENTER_CRITICAL(&sPendingGuardMux);sPendingGuard=in;portEXIT_CRITICAL(&sPendingGuardMux);sPendingGuardState.store(2,std::memory_order_release);return true; }
static void applyPendingGuardUpdate(){ if(sPendingGuardState.load(std::memory_order_acquire)!=2)return; PendingGuardUpdate u{};portENTER_CRITICAL(&sPendingGuardMux);u=sPendingGuard;portEXIT_CRITICAL(&sPendingGuardMux); if(setLowSocConfigAtomic(u.socEn,u.stop,u.resume)){if(u.hasSoh)setLowSohConfigAtomic(u.sohEn,u.sohMin); lowSocGuardTick(); syncCanBatterySnapshotAtomic(); saveCoreConfig();} sPendingGuardState.store(0,std::memory_order_release); }

static bool sFsReady = false;
static bool sFsVersionMatch = false;
static const char* FS_MANIFEST_PATH = "/fs_version.txt";

static String trimCopy(String v) { v.trim(); return v; }

void filesystemInitStatus() {
  sFsReady = SPIFFS.begin(false);
  sFsVersionMatch = false;
  if (!sFsReady) return;
  File f = SPIFFS.open(FS_MANIFEST_PATH, "r");
  if (!f) return;
  String v = trimCopy(f.readString());
  f.close();
  sFsVersionMatch = (v == String(FW_VERSION));
}

bool filesystemReady() { return sFsReady; }
bool filesystemVersionMatches() { return sFsReady && sFsVersionMatch; }
const char* filesystemStatusString() {
  if (!sFsReady) return "FS_MOUNT_FAILED";
  return sFsVersionMatch ? "FS_OK" : "FS_VERSION_MISMATCH";
}

static void sendProtectedFs(AsyncWebServerRequest* request, const char* path, const char* type) {
  if (!remoteAuthRequest(request)) return;
    CrashHttpScope crashScope(CRASH_HTTP_FS_PAGE);
  if (!sFsReady) {
    request->send(503, "text/plain", String("Filesystem unavailable: ") + filesystemStatusString());
    return;
  }
  if (!sFsVersionMatch) {
    request->send(503, "text/plain", String("Filesystem/Firmware version mismatch: ") + filesystemStatusString());
    return;
  }
  if (!SPIFFS.exists(path)) {
    request->send(404, "text/plain", "Filesystem file not found");
    return;
  }
  AsyncWebServerResponse* res = request->beginResponse(SPIFFS, path, type);
  res->addHeader("Cache-Control", "no-store");
  request->send(res);
}

// ----------------------------------------------------------------------------
// WebSockets
// ----------------------------------------------------------------------------
static AsyncWebSocket wsLog("/log");
static AsyncWebSocket wsBms("/bms");
static AsyncWebSocket wsDebug("/debug");
static std::atomic<bool> sCloudQuiesce{false};
// 9.36.7.5: lifecycle diagnostics. Stale BMS websocket clients were previously
// never passed through cleanupClients(); log/debug cleanup also shared one timer.
// That can retain dead AsyncTCP/WebSocket state across browser reconnects.
static std::atomic<uint32_t> sWsCleanupRuns{0};
static std::atomic<uint32_t> sWebLoopMaxGapMs{0};
static std::atomic<uint32_t> sWebLoopLastGapMs{0};
static std::atomic<uint32_t> sWebLowHeapCleanupCount{0};
// 9.36.7.7: callback/load diagnostics for the high-frequency /api/bms path.
// This does not retain request pointers and does not allocate in callbacks beyond existing JSON work.
static std::atomic<uint32_t> sBmsApiCalls{0}, sBmsApiInflight{0}, sBmsApiMaxInflight{0};
static std::atomic<uint32_t> sBmsApiMaxBuildUs{0}, sBmsApiLastBuildUs{0};
static std::atomic<uint32_t> sBmsApiMinHeap{0xFFFFFFFFu}, sBmsApiMinLargest{0xFFFFFFFFu};
static inline void atomicMaxU32(std::atomic<uint32_t>& a,uint32_t v){uint32_t p=a.load(std::memory_order_relaxed);while(v>p&&!a.compare_exchange_weak(p,v,std::memory_order_relaxed)){} }
static inline void atomicMinU32(std::atomic<uint32_t>& a,uint32_t v){uint32_t p=a.load(std::memory_order_relaxed);while(v<p&&!a.compare_exchange_weak(p,v,std::memory_order_relaxed)){} }
static std::atomic<bool> sRebootRequested{false};
// AUDIT20.4.5.9.17: JKPBBms is main-loop owned. AsyncWebServer callbacks may
// request an operation, but never call mutating BMS methods directly.
enum class PendingBmsOpType : uint8_t { NONE=0, SETUP_REFRESH=1, WRITE_U32=2 };
struct PendingBmsOp { PendingBmsOpType type=PendingBmsOpType::NONE; uint16_t reg=0; uint32_t value=0; };
static PendingBmsOp sPendingBmsOp;
static portMUX_TYPE sPendingBmsMux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<uint8_t> sPendingBmsState{0}; // 0 FREE, 1 WRITING, 2 READY
static bool queueBmsOp(PendingBmsOpType type,uint16_t reg=0,uint32_t value=0){
  uint8_t expected=0; if(!sPendingBmsState.compare_exchange_strong(expected,1,std::memory_order_acq_rel)) return false;
  PendingBmsOp op{}; op.type=type; op.reg=reg; op.value=value;
  portENTER_CRITICAL(&sPendingBmsMux); sPendingBmsOp=op; portEXIT_CRITICAL(&sPendingBmsMux);
  sPendingBmsState.store(2,std::memory_order_release); return true;
}
static void applyPendingBmsOp(){
  if(sPendingBmsState.load(std::memory_order_acquire)!=2) return;
  PendingBmsOp op{}; portENTER_CRITICAL(&sPendingBmsMux); op=sPendingBmsOp; portEXIT_CRITICAL(&sPendingBmsMux);
  bool accepted=false;
  bmsObjectLock();
  if(op.type==PendingBmsOpType::SETUP_REFRESH){ bms.queueSetupRequest(); accepted=true; }
  else if(op.type==PendingBmsOpType::WRITE_U32) accepted=bms.writeSettingU32(op.reg,op.value);
  bmsObjectUnlock();
  if(!accepted) Serial.printf("[WEB] queued BMS op rejected type=%u reg=%u\n",(unsigned)op.type,(unsigned)op.reg);
  sPendingBmsState.store(0,std::memory_order_release);
}


extern std::atomic<bool> canHealth;

// AUDIT20.0: Remote WebUI authentication. Remote access is intended only over
// a private VPN (WireGuard/Tailscale). HTTP Basic Auth is a second barrier;
// do not expose port 80 directly to the public Internet.
static String sRemotePassword;
static const char* REMOTE_USER = "admin";
// 9.36.2 AUTH-DIAG: count HTTP Basic-Auth outcomes without logging credentials.
// These counters are diagnostic only and never affect admission decisions.
static std::atomic<uint32_t> sAuthOk{0};
static std::atomic<uint32_t> sAuthChallenge{0};
static std::atomic<uint32_t> sAuthLastOkMs{0};
static std::atomic<uint32_t> sAuthLastChallengeMs{0};
static std::atomic<uint32_t> sWsConnects{0}, sWsDisconnects{0}, sWsErrors{0};

static void remoteAuthEnsure() {
  if (sRemotePassword.length()) return;
  Preferences ap;
  if (ap.begin("remoteauth", false)) {
    sRemotePassword = ap.getString("password", "");
    if (sRemotePassword.length() < 16) {
      static const char alphabet[] = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789";
      char pw[21];
      for (size_t i=0;i<20;i++) pw[i]=alphabet[esp_random() % (sizeof(alphabet)-1)];
      pw[20]='\0'; sRemotePassword=pw; ap.putString("password", sRemotePassword);
    }
    ap.end();
  }
  if (!sRemotePassword.length()) {
    // Fail closed if NVS is unavailable: random per boot is still preferable to no auth.
    char pw[21]; snprintf(pw,sizeof(pw),"%08lX%08lX",(unsigned long)esp_random(),(unsigned long)esp_random());
    sRemotePassword=pw;
  }
  Serial.printf("[REMOTE] WebUI user=%s password=<redacted> ota_password_configured=%s (VPN only; do NOT port-forward HTTP)\n",
                REMOTE_USER, sRemotePassword.length() ? "true" : "false");
}

bool remoteAuthRequest(AsyncWebServerRequest* r) {
  // 9.36.4 A/B diagnostic: local HTTP WebUI/API admission deliberately has no
  // Basic-Auth challenge. Same-origin mutation checks remain in force.
  // Keep the function so every existing route follows exactly the same code path
  // apart from Basic Auth, making 9.36.3 vs 9.36.4 a controlled comparison.
  (void)r;
  sAuthOk.fetch_add(1, std::memory_order_relaxed);
  sAuthLastOkMs.store(millis(), std::memory_order_relaxed);
  return true;
}

bool remoteOtaAuthRequest(AsyncWebServerRequest* r) {
  // OTA remains protected by the persistent remoteauth secret.
  remoteAuthEnsure();
  if (r->authenticate(REMOTE_USER, sRemotePassword.c_str())) return true;
  r->requestAuthentication();
  return false;
}

// Escape a string for JSON inclusion
bool remoteMutationAllowed(AsyncWebServerRequest* r) {
  // Browser-side CSRF guard: mutating PowerStream requests must originate from this device.
  // This is not a substitute for network isolation; it prevents cross-site browser requests.
  if (!r->hasHeader("Origin")) return false; // mutating browser/API requests must prove same origin
  String origin=r->getHeader("Origin")->value();
  String host=r->host();
  return origin == (String("http://")+host) || origin == (String("https://")+host);
}

static String jsonEscape(const String &s) {
  String out; out.reserve(s.length() + 4);
  for (size_t i = 0; i < s.length(); i++) {
    char c = s[i];
    if (c == '\"' || c == '\\') out += '\\';
    out += c;
  }
  return out;
}

const char* remoteAuthUser() { remoteAuthEnsure(); return REMOTE_USER; }
const char* remoteAuthPassword() { remoteAuthEnsure(); return sRemotePassword.c_str(); }

// 9.36.7.9: persisted legacy-like regression A/B mode.
// This is deliberately boot-applied: no live teardown of BLE/tasks.
static bool sRegressionCfgLoaded=false;
static bool sRegressionConfigured=false;
static bool sRegressionApplied=false;
static void loadRegressionCfgOnce(){
  if(sRegressionCfgLoaded) return;
  Preferences p; bool en=false;
  if(p.begin("regab",true)){ en=p.getBool("legacy",false); p.end(); }
  sRegressionConfigured=en; sRegressionApplied=en; sRegressionCfgLoaded=true;
  Serial.printf("[REG-A/B] legacy-like boot mode: %s (JK-BLE retained)\n",en?"ON":"OFF");
}
bool regressionLegacyConfigured(){loadRegressionCfgOnce();return sRegressionConfigured;}
bool regressionLegacyApplied(){loadRegressionCfgOnce();return false;} // 9.36.7.10 deprecated: never suppress runtime
bool regressionLegacySet(bool enabled){
  Preferences p; if(!p.begin("regab",false)) return false;
  const bool ok=p.putBool("legacy",enabled)==1; p.end();
  if(ok) sRegressionConfigured=enabled;
  return ok;
}

void setupServerRoutes(AsyncWebServer &server) {


  // 9.36.2 AUTH-DIAG: authenticated self-observation endpoint. A normal browser
  // session may produce an initial 401 challenge; repeated growth during an already
  // authenticated session is what matters diagnostically.
  server.on("/api/remote/auth-status", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    char j[320];
    uint32_t now=millis(), lok=sAuthLastOkMs.load(std::memory_order_relaxed), lch=sAuthLastChallengeMs.load(std::memory_order_relaxed);
    snprintf(j,sizeof(j),"{\"web_auth_enabled\":false,\"user\":\"%s\",\"ok\":%lu,\"challenges\":%lu,\"password_len\":%u,\"last_ok_age_ms\":%lu,\"last_challenge_age_ms\":%lu,\"ws_connects\":%lu,\"ws_disconnects\":%lu,\"ws_errors\":%lu}",
      REMOTE_USER,
      (unsigned long)sAuthOk.load(std::memory_order_relaxed),
      (unsigned long)sAuthChallenge.load(std::memory_order_relaxed),
      (unsigned)sRemotePassword.length(),
      (unsigned long)(lok?now-lok:0), (unsigned long)(lch?now-lch:0),
      (unsigned long)sWsConnects.load(), (unsigned long)sWsDisconnects.load(), (unsigned long)sWsErrors.load());
    r->send(200,"application/json",j);
  });

  // 9.36.7.9: regression isolation keeps JK-BLE active while removing later auxiliary load.
  server.on("/api/diag/regression-ab", HTTP_GET, [](AsyncWebServerRequest* r){
    String j=String("{\"ok\":true,\"configured_legacy\":")+(regressionLegacyConfigured()?"true":"false")+
      ",\"boot_applied_legacy\":"+(regressionLegacyApplied()?"true":"false")+
      ",\"jk_ble_retained\":true,\"ps_ble_runtime\":"+(regressionLegacyApplied()?"false":"true")+
      ",\"ws_bms_push\":"+(regressionLegacyApplied()?"false":"true")+
      ",\"reboot_required\":"+((regressionLegacyConfigured()!=regressionLegacyApplied())?"true":"false")+"}";
    r->send(200,"application/json",j);
  });
  server.on("/api/diag/regression-ab", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!r->hasParam("legacy",true)){r->send(400,"application/json","{\"ok\":false,\"error\":\"legacy required\"}");return;}
    String v=r->getParam("legacy",true)->value(); bool en=(v=="1"||v=="true"||v=="on");
    if(!regressionLegacySet(en)){r->send(500,"application/json","{\"ok\":false,\"error\":\"NVS write failed\"}");return;}
    r->send(200,"application/json",String("{\"ok\":true,\"configured_legacy\":")+(en?"true":"false")+",\"reboot_required\":true}");
  });
  // AUDIT20.4.5.9.1 PS-PRIORITY-LAB2-HARDENED: manual-only BLE control. No SOC automation.
  // 9.36.7.8: controlled boot-time BLE isolation A/B test.
  server.on("/api/diag/ble-isolation", HTTP_GET, [](AsyncWebServerRequest* r){
    String j=String("{\"ok\":true,\"configured_enabled\":")+(jkBleStartupEnabled()?"true":"false")+
      ",\"boot_applied_enabled\":"+(jkBleStartupAppliedEnabled()?"true":"false")+
      ",\"nimble_initialized\":"+(jkBleProxyInitialized()?"true":"false")+
      ",\"reboot_required\":"+((jkBleStartupEnabled()!=jkBleStartupAppliedEnabled())?"true":"false")+"}";
    r->send(200,"application/json",j);
  });
  server.on("/api/diag/ble-isolation", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!r->hasParam("enabled",true)){r->send(400,"application/json","{\"ok\":false,\"error\":\"enabled required\"}");return;}
    String v=r->getParam("enabled",true)->value(); bool en=(v=="1"||v=="true"||v=="on");
    if(!jkBleSetStartupEnabled(en)){r->send(500,"application/json","{\"ok\":false,\"error\":\"NVS write failed\"}");return;}
    String j=String("{\"ok\":true,\"configured_enabled\":")+(en?"true":"false")+",\"reboot_required\":true}";
    r->send(200,"application/json",j);
  });
  server.on("/api/powerstream/ble-lab/status", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    CrashHttpScope crashScope(CRASH_HTTP_PS_STATUS);
    r->send(200,"application/json",powerStreamBleLabStatusJson());
  });
  server.on("/api/powerstream/ble-lab/config", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    String mac=r->hasParam("mac",true)?r->getParam("mac",true)->value():String();
    String sn=r->hasParam("sn",true)?r->getParam("sn",true)->value():String();
    String uid=r->hasParam("uid",true)?r->getParam("uid",true)->value():String();
    String ev=r->hasParam("enabled",true)?r->getParam("enabled",true)->value():String("0");
    bool en=(ev=="1"||ev=="true"||ev=="on");
    int at=r->hasParam("addr_type",true)?r->getParam("addr_type",true)->value().toInt():0;
    if(!powerStreamBleLabSaveConfig(mac,sn,uid,en,at)){r->send(400,"application/json","{\"ok\":false,\"err\":\"invalid/incomplete config\"}");return;}
    r->send(200,"application/json","{\"ok\":true,\"note\":\"saved; credentials are write-only\"}");
  });
  server.on("/api/powerstream/ble-lab/identity", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r))return;
    Preferences p;if(!p.begin("psblelab",true)){r->send(503,"application/json","{\"ok\":false,\"err\":\"NVS unavailable\"}");return;}
    String bleSn=p.getString("sn","");String bleMac=p.getString("mac","");p.end();
    String cloudSn=powerStreamApiSerial();
    String j="{\"ok\":true,\"ble_sn\":\""+jsonEscape(bleSn)+"\",\"ble_mac\":\""+jsonEscape(bleMac)+"\",\"cloud_sn\":\""+jsonEscape(cloudSn)+"\",\"sn_equal\":"+String(bleSn.length()&&bleSn==cloudSn?"true":"false")+",\"scan_used\":false}";
    r->send(200,"application/json",j);
  });
  server.on("/api/powerstream/ble-lab/verify-user-id", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r))return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    if(!r->hasParam("user_id",true)){r->send(400,"application/json","{\"ok\":false,\"err\":\"user_id required\"}");return;}
    bool matches=false;
    if(!powerStreamBleLabVerifyUserId(r->getParam("user_id",true)->value(),matches)){r->send(400,"application/json","{\"ok\":false,\"err\":\"invalid input or NVS unavailable\"}");return;}
    r->send(200,"application/json",String("{\"ok\":true,\"matches\":")+(matches?"true":"false")+"}");
  });
  // 9.36.7.10 phase-C diagnostic: connect/GATT/subscribe/auth, then disconnect. Never writes priority command.
  server.on("/api/powerstream/ble-lab/auth-probe", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    String m; bool ok=powerStreamBleLabProbeAuth(m);
    r->send(ok?200:409,"application/json","{\"ok\":"+String(ok?"true":"false")+",\"message\":\""+jsonEscape(m)+"\"}");
  });
  server.on("/api/powerstream/ble-lab/supply", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    if(!r->hasParam("mode",true)){r->send(400,"application/json","{\"ok\":false,\"err\":\"mode required: 0=supply, 1=storage\"}");return;}
    String mv=r->getParam("mode",true)->value(); if(mv!="0"&&mv!="1"){r->send(400,"application/json","{\"ok\":false,\"err\":\"mode must be exactly 0 or 1\"}");return;} int mode=(mv=="1")?1:0; String m; bool ok=powerStreamBleLabSetSupplyMode(mode,m);
    r->send(ok?200:409,"application/json","{\"ok\":"+String(ok?"true":"false")+",\"message\":\""+jsonEscape(m)+"\"}");
  });

  // EcoFlow Open API / PowerStream HW51. Secrets are write-only: never returned by GET.
  server.on("/api/powerstream/config", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    PowerStreamApiState st=powerStreamApiStateSnapshot();
    String j="{\"configured\":"+String(st.configured?"true":"false")+
      ",\"sn\":\""+jsonEscape(powerStreamApiSerial())+"\",\"access_masked\":\""+
      jsonEscape(powerStreamApiAccessMasked())+"\",\"upper\":"+String(st.upperLimit)+
      ",\"lower\":"+String(st.lowerLimit)+",\"busy\":"+String(powerStreamApiBusy()?"true":"false")+"}";
    r->send(200,"application/json",j);
  });

  server.on("/api/powerstream/config", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"message\":\"Origin nicht erlaubt\"}");return;}
    if(powerStreamApiBusy()){r->send(409,"application/json","{\"ok\":false,\"message\":\"EcoFlow API busy\"}");return;}
    String sn=r->hasParam("sn",true)?r->getParam("sn",true)->value():String();
    String ak=r->hasParam("access",true)?r->getParam("access",true)->value():String();
    String sk=r->hasParam("secret",true)?r->getParam("secret",true)->value():String();
    if(!powerStreamApiSave(sn,ak,sk)){r->send(400,"application/json","{\"ok\":false,\"message\":\"Seriennummer fehlt\"}");return;}
    r->send(200,"application/json","{\"ok\":true}");
  });

  server.on("/api/powerstream/clear", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"message\":\"Origin nicht erlaubt\"}");return;}
    bool ok=powerStreamApiClear(); r->send(ok?200:409,"application/json",ok?"{\"ok\":true}":"{\"ok\":false,\"message\":\"EcoFlow API busy\"}");
  });

  server.on("/api/powerstream/job", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    r->send(200,"application/json",powerStreamApiJobStatusJson());
  });
  server.on("/api/powerstream/test", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"message\":\"Origin nicht erlaubt\"}");return;}
    uint32_t id=0; bool ok=powerStreamApiQueueTest(id);
    r->send(ok?202:409,"application/json",ok?(String("{\"ok\":true,\"queued\":true,\"job_id\":")+id+"}"):"{\"ok\":false,\"message\":\"EcoFlow API job already active\"}");
  });
  server.on("/api/powerstream/limits", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return; uint32_t id=0; bool ok=powerStreamApiQueueRead(id);
    r->send(ok?202:409,"application/json",ok?(String("{\"ok\":true,\"queued\":true,\"job_id\":")+id+"}"):"{\"ok\":false,\"message\":\"EcoFlow API job already active\"}");
  });
  server.on("/api/powerstream/limits", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    r->send(403,"application/json","{\"ok\":false,\"message\":\"Cloud-Schreiben in dieser Diagnose-Firmware gesperrt\"}");
  });


  // AUDIT18.7: cloud-independent limits advertised by the emulated EcoFlow battery
  // in the 3C CAN payload. CB/2031 and CB/2033 are sniffed separately and never
  // overwrite these local limits.
  server.on("/api/powerstream/can-limits", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    uint8_t cfgUp=0,cfgDn=0; configuredCanLimitsAtomic(cfgUp,cfgDn);
    String j="{\"ok\":true,\"upper\":"+String((unsigned)cfgUp)+
      ",\"lower\":"+String((unsigned)cfgDn)+
      ",\"observed_upper\":"+String(ecoflowObservedUpperLimit())+
      ",\"observed_lower\":"+String(ecoflowObservedLowerLimit())+
      ",\"observed_upper_age_ms\":"+String(ecoflowObservedUpperAgeMs())+
      ",\"observed_lower_age_ms\":"+String(ecoflowObservedLowerAgeMs())+"}";
    r->send(200,"application/json",j);
  });

  server.on("/api/powerstream/can-limits", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"message\":\"Origin nicht erlaubt\"}");return;}
    if(!r->hasParam("upper",true)||!r->hasParam("lower",true)){r->send(400,"application/json","{\"ok\":false,\"message\":\"upper/lower fehlen\"}");return;}
    int u=r->getParam("upper",true)->value().toInt(), l=r->getParam("lower",true)->value().toInt();
    if(u<50||u>100||l<0||l>50||l>=u){r->send(400,"application/json","{\"ok\":false,\"message\":\"Bereich: upper 50-100, lower 0-50, lower < upper\"}");return;}
    PendingCoreUpdate pu; pu.mask=P_UP|P_DN; pu.up=(uint8_t)u; pu.dn=(uint8_t)l;
    if(!queueCoreUpdate(pu)){r->send(409,"application/json","{\"ok\":false,\"message\":\"core config update already pending\"}");return;}
    r->send(202,"application/json","{\"ok\":true,\"queued\":true,\"message\":\"Lokale CAN-Grenzen werden im Mainloop atomar uebernommen\"}");
  });

  // AUDIT20.4.4: configurable low-SOC guard. This state machine does NOT write JK MOS
  // and does NOT invent an unverified PowerStream DCL command. It exposes a verified
  // block request for the future DCL mapping while keeping BMS communications alive.
  server.on("/api/bms/low-soc-guard", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    bool lsgEnabled; uint8_t lsgStop,lsgResume; lowSocConfigSnapshot(lsgEnabled,lsgStop,lsgResume);
    bool lshEnabled; uint8_t lshMin; lowSohConfigSnapshot(lshEnabled,lshMin);
    const BmsSafetySnapshot bs=bmsSafetySnapshotAtomic();
    String j="{\"ok\":true,\"enabled\":"+String(lsgEnabled?"true":"false")+
      ",\"stop\":"+String((unsigned)lsgStop)+",\"resume\":"+String((unsigned)lsgResume)+
      ",\"soh_enabled\":"+String(lshEnabled?"true":"false")+",\"soh_min\":"+String((unsigned)lshMin)+",\"soc\":"+String((unsigned)bs.soc)+",\"soh\":"+String((unsigned)bs.soh)+
      ",\"bms_valid\":"+String(bs.valid?"true":"false")+",\"block_requested\":"+String(lowSocGuardBlockRequested()?"true":"false")+
      ",\"state\":\""+String(lowSocGuardState())+"\",\"transitions\":"+String((unsigned long)lowSocGuardTransitions())+
      ",\"enforcement\":\"SOC_LATCHED_CAN_FLOOR; SOH_BLOCK_REQUEST_ONLY; BMS_STALE_FAIL_CLOSED_TX_SUPPRESS; VERIFY_POWERSTREAM_RESPONSE_ON_HARDWARE\"}";
    r->send(200,"application/json",j);
  });
  server.on("/api/bms/low-soc-guard", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    if(!r->hasParam("enabled",true)||!r->hasParam("stop",true)||!r->hasParam("resume",true)){r->send(400,"application/json","{\"ok\":false,\"err\":\"enabled/stop/resume required\"}");return;}
    int stop=r->getParam("stop",true)->value().toInt(), resume=r->getParam("resume",true)->value().toInt();
    String ev=r->getParam("enabled",true)->value();
    if(stop<0||stop>99||resume<1||resume>100||resume<=stop){r->send(400,"application/json","{\"ok\":false,\"err\":\"resume must be greater than stop; range 0..100\"}");return;}
    if(!(ev=="0"||ev=="1"||ev=="true"||ev=="false"||ev=="on"||ev=="off")){r->send(400,"application/json","{\"ok\":false,\"err\":\"enabled invalid\"}");return;}
    const bool en=(ev=="1"||ev=="true"||ev=="on"); PendingGuardUpdate gu{}; gu.socEn=en;gu.stop=(uint8_t)stop;gu.resume=(uint8_t)resume; bool curEn;uint8_t curMin;lowSohConfigSnapshot(curEn,curMin);gu.sohEn=curEn;gu.sohMin=curMin; if(r->hasParam("soh_enabled",true)||r->hasParam("soh_min",true)){gu.hasSoh=true;if(r->hasParam("soh_enabled",true)){String sv=r->getParam("soh_enabled",true)->value();if(!(sv=="0"||sv=="1"||sv=="true"||sv=="false"||sv=="on"||sv=="off")){r->send(400,"application/json","{\"ok\":false,\"err\":\"soh_enabled invalid\"}");return;}gu.sohEn=(sv=="1"||sv=="true"||sv=="on");}if(r->hasParam("soh_min",true)){int sm=r->getParam("soh_min",true)->value().toInt();if(sm<0||sm>100){r->send(400,"application/json","{\"ok\":false,\"err\":\"soh_min range 0..100\"}");return;}gu.sohMin=(uint8_t)sm;}} if(!queueGuardUpdate(gu)){r->send(409,"application/json","{\"ok\":false,\"err\":\"guard update busy\"}");return;}
    r->send(200,"application/json","{\"ok\":true,\"note\":\"saved; SOC floor follows the hysteresis block state on CAN; SOH remains a block request only until a verified PowerStream command exists\"}");
  });

  // AUDIT20.4.3: passive raw-CAN CB forensic recorder. Read-only dump plus explicit clear.
  server.on("/api/powerstream/cb-recorder/status", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    r->send(200,"application/json",ecoflowCbRecorderStatusJson());
  });
  server.on("/api/powerstream/cb-recorder/dump", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    uint16_t offset=r->hasParam("offset")?(uint16_t)r->getParam("offset")->value().toInt():0;
    uint8_t limit=r->hasParam("limit")?(uint8_t)r->getParam("limit")->value().toInt():32;
    r->send(200,"text/plain; charset=utf-8",ecoflowCbRecorderDumpPage(offset,limit));
  });
  server.on("/api/powerstream/cb-recorder/clear", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"message\":\"Origin nicht erlaubt\"}");return;}
    ecoflowCbRecorderClear();
    r->send(200,"application/json","{\"ok\":true}");
  });

  server.on("/api/wifi", HTTP_POST, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    auto getS = [&](const char* n)->String{
      return r->hasParam(n, true) ? r->getParam(n, true)->value() : String();
    };

    String ssid = getS("ssid");
    String pass = getS("pass");

    if (ssid.isEmpty()) { r->send(400, "application/json", "{\"ok\":false,\"err\":\"ssid required\"}"); return; }
    if (!wifiSaveCredentialsDeferred(ssid, pass)) { r->send(500, "application/json", "{\"ok\":false,\"err\":\"wifi NVS write/readback failed\"}"); return; }
    r->send(202, "application/json", "{\"ok\":true,\"wifi_reconnect_queued\":true}");
  });

  server.on("/api/state", HTTP_GET, [](AsyncWebServerRequest *request) {
    if(!remoteAuthRequest(request)) return;

    const bool staConnected = WiFi.isConnected();
    const String staIp = staConnected ? WiFi.localIP().toString() : String("-");
    const String apIp  = WiFi.softAPIP().toString();
    Preferences netp; netp.begin("net", true); const String stateSsid=netp.getString("ssid", ""); const bool statePassSet=netp.getString("pass", "").length()>0; netp.end();

    // Load MQTT config
    Preferences p; p.begin("mqtt", true);
    String   mHost    = p.getString("host", "");
    uint16_t mPort    = p.getUShort("port", 1883);
    String   mUser    = p.getString("user", "");
    bool     mPassSet = p.getString("pass", "").length()>0;
    String   mBase    = p.getString("base", "ecoflow_bridge");
    bool     mEnabled = p.getBool("enabled", false);
    p.end();

    String json; json.reserve(2048); json = "{";

    // Firmware / UI version
    const CanBatterySnapshot webBatt=canBatterySnapshotAtomic(); const CanIdentitySnapshot webId=canIdentitySnapshotAtomic(); bool webMosChg=false,webMosDis=false; mosStatusAtomic(webMosChg,webMosDis); uint8_t webCfgUp=0,webCfgDn=0; configuredCanLimitsAtomic(webCfgUp,webCfgDn);
    json += "\"version\":\"" + String(FW_VERSION) + "\",";

    json += "\"deviceId\":\"" + deviceId() + "\",";

    // Core parameter values
    json += "\"volt\":" + String((unsigned)webBatt.volt) + ",";
    json += "\"chgvolt\":" + String((unsigned)webId.chgvolt) + ",";
    json += "\"temp\":" + String((unsigned)webBatt.temp) + ",";
    json += "\"soc\":" + String((unsigned)webBatt.soc) + ",";
    json += "\"disruntime\":" + String((unsigned)webBatt.disruntime) + ",";
    json += "\"chgruntime\":" + String((unsigned)webBatt.chgruntime) + ",";
    json += "\"bmsChgUp\":" + String((unsigned)webCfgUp) + ",";
    json += "\"bmsChgDn\":" + String((unsigned)webCfgDn) + ",";
    json += "\"serial\":\"" + jsonEscape(webId.serial) + "\",";

    // Toggles
    json += "\"batteryMaster\":" + String(batteryMasterAtomic() ? "true" : "false") + ",";
    json += "\"batt\":" + String(battSyncAtomic() ? "true" : "false") + ",";
    json += "\"canTxEnabled\":" + String(canTxEnabledAtomic() ? "true" : "false") + ",";
    json += "\"canRxEnabled\":" + String(canRxEnabledAtomic() ? "true" : "false") + ",";
    json += "\"txlogging\":" + String(txLoggingAtomic() ? "true" : "false") + ",";
    json += "\"rxlogging\":" + String(rxLoggingAtomic() ? "true" : "false") + ",";

    json += "\"message3C\":" + String(canMessageEnabledAtomic("message3C") ? "true" : "false") + ",";
    json += "\"message13\":" + String(canMessageEnabledAtomic("message13") ? "true" : "false") + ",";
    json += "\"messageCB\":" + String(canMessageEnabledAtomic("messageCB") ? "true" : "false") + ",";
    json += "\"message70\":" + String(canMessageEnabledAtomic("message70") ? "true" : "false") + ",";
    json += "\"message0B\":" + String(canMessageEnabledAtomic("message0B") ? "true" : "false") + ",";
    json += "\"message5C\":" + String(canMessageEnabledAtomic("message5C") ? "true" : "false") + ",";
    json += "\"message68\":" + String(canMessageEnabledAtomic("message68") ? "true" : "false") + ",";
    json += "\"message4F\":" + String(canMessageEnabledAtomic("message4F") ? "true" : "false") + ",";
    json += "\"message8C\":" + String(canMessageEnabledAtomic("message8C") ? "true" : "false") + ",";
    json += "\"message24\":" + String(canMessageEnabledAtomic("message24") ? "true" : "false") + ",";
    json += "\"acout5C\":" + String(acout5CAtomic() ? "true" : "false") + ",";
    json += "\"flagCB\":" + String(flagCBAtomic() ? "true" : "false") + ",";
    json += "\"moschg\":" + String(webMosChg ? "true" : "false") + ",";
    json += "\"mosdis\":" + String(webMosDis ? "true" : "false") + ",";

    // CAN Health
    json += "\"canHealth\":" + String(canHealth.load(std::memory_order_acquire) ? "true" : "false") + ",";
    // EcoFlow PowerStream Serial
    json += "\"peerSerial\":\"" + jsonEscape(getPeerSerial()) + "\",";
    // WiFi object
    json += "\"wifi\":{";
    json += "\"connected\":" + String(staConnected ? "true" : "false") + ",";
    json += "\"mode\":\"" + wifiModeToString(WiFi.getMode()) + "\",";
    json += "\"ip\":\"" + staIp + "\",";
    json += "\"ap_ip\":\"" + apIp + "\",";
    json += "\"ssid\":\"" + jsonEscape(stateSsid) + "\",";
    json += "\"pass_set\":" + String(statePassSet ? "true" : "false");
    json += "},";

    // MQTT object
    json += "\"mqtt\":{";
    json += "\"host\":\"" + jsonEscape(mHost) + "\",";
    json += "\"port\":" + String(mPort) + ",";
    json += "\"user\":\"" + jsonEscape(mUser) + "\",";
    json += "\"pass_set\":" + String(mPassSet ? "true" : "false") + ",";
    json += "\"base\":\"" + jsonEscape(mBase) + "\",";
    json += "\"enabled\":" + String(mEnabled ? "true" : "false");
    json += "}";

    json += "}";

    request->send(200, "application/json", json);
  });

  server.on("/api/bms", HTTP_GET, [](AsyncWebServerRequest *request) {
    CrashHttpScope crashScope(CRASH_HTTP_BMS);
    const uint32_t apiT0=micros();
    const uint32_t inNow=sBmsApiInflight.fetch_add(1,std::memory_order_acq_rel)+1;
    atomicMaxU32(sBmsApiMaxInflight,inNow); sBmsApiCalls.fetch_add(1,std::memory_order_relaxed);
    struct ApiExit{~ApiExit(){sBmsApiInflight.fetch_sub(1,std::memory_order_acq_rel);}} apiExit;
    atomicMinU32(sBmsApiMinHeap,ESP.getFreeHeap());
    atomicMinU32(sBmsApiMinLargest,heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    if(!remoteAuthRequest(request)) return;
    const JKPBBms snap = bmsDiagnosticSnapshot();
    // AUDIT18.7: /api/bms is the canonical dashboard endpoint.  Keep the
    // original fields for backwards compatibility and add the validated live
    // fields here so the UI does not depend on a second /full route.
    const bool live = snap.valid();
    const int soc = (int)snap.get_state_of_charge();
    const float v = snap.get_voltage();
    const float c = snap.get_current();
    const float t = snap.get_ntc_temperature(0);
    const int n = (int)snap.get_num_cells();

    uint16_t minMv = 0, maxMv = 0;
    for (int i = 0; i < n; i++) {
      const uint16_t mv = (uint16_t)lround(snap.get_cell_voltage(i) * 1000.0f);
      if (i == 0 || mv < minMv) minMv = mv;
      if (i == 0 || mv > maxMv) maxMv = mv;
    }

    String json; json.reserve(4096); json = "{";
    json += "\"fw\":\"" + String(FW_VERSION) + "\",";
    json += "\"web_api_schema\":\"AUDIT18.7-BMS-2\",";
    json += "\"uptime_ms\":" + String((unsigned long)millis()) + ",";
    json += "\"valid\":" + String(live ? "true" : "false") + ",";
    json += "\"setup_valid\":" + String(snap.setup_valid() ? "true" : "false") + ",";
    json += "\"soc\":" + String(soc) + ",";
    json += "\"voltage\":" + String(v, 3) + ",";
    json += "\"current\":" + String(c, 3) + ",";
    json += "\"temperature\":" + String(t, 1) + ",";
    json += "\"min_cell_mv\":" + String(minMv) + ",";
    json += "\"max_cell_mv\":" + String(maxMv) + ",";
    json += "\"power\":" + String(snap.get_power(), 1) + ",";
    json += "\"remain_ah\":" + String(snap.get_balance_capacity(), 2) + ",";
    json += "\"capacity_ah\":" + String(snap.get_rate_capacity(), 2) + ",";
    json += "\"mos_temp\":" + String(snap.get_mos_temperature(), 1) + ",";
    json += "\"alarm\":" + String((unsigned long)snap.get_alarm_bits()) + ",";
    json += "\"charge_mos\":" + String(snap.get_charge_mosfet_status()?"true":"false") + ",";
    json += "\"discharge_mos\":" + String(snap.get_discharge_mosfet_status()?"true":"false") + ",";
    json += "\"balance_mos\":" + String(snap.get_balance_status(0)?"true":"false") + ",";
    json += "\"balance_current\":" + String(snap.get_balance_current(),3) + ",";
    json += "\"soh\":" + String((unsigned long)snap.get_soh()) + ",";
    json += "\"cycles\":" + String((unsigned long)snap.get_cycle_count()) + ",";
    json += "\"bms_runtime_s\":" + String((unsigned long)snap.get_bms_runtime_s()) + ",";
    json += "\"precharge\":" + String(snap.get_precharge_status()?"true":"false") + ",";
    json += "\"heating\":" + String(snap.get_heating_status()?"true":"false") + ",";
    json += "\"charger_plugged\":" + String(snap.get_charger_plugged()?"true":"false") + ",";
    json += "\"runtime_charge_min\":" + String((unsigned long)canBatterySnapshotAtomic().chgruntime) + ",";
    json += "\"runtime_discharge_min\":" + String((unsigned long)canBatterySnapshotAtomic().disruntime) + ",";
    json += "\"temps\":[";
    for(int i=0;i<5;i++){ if(i)json+=","; json+=String(snap.get_ntc_temperature(i),1); }
    json += "],\"cells\":[";
    for(int i=0;i<n;i++){ if(i)json+=","; json+=String(snap.get_cell_voltage(i),3); }
    json += "],\"wire\":[";
    for(int i=0;i<n;i++){ if(i)json+=","; json+=String(snap.get_wire_resistance(i),3); }
    json += "],\"cfg\":{";
    json += "\"cell_count\":"+String((unsigned long)snap.cfg_cell_count())+",\"capacity_ah\":"+String(snap.cfg_capacity_ah(),1)+",\"sleep_entry_v\":"+String(snap.cfg_sleep_entry_v(),3);
    json += ",\"uvp\":"+String(snap.cfg_cell_uvp(),3)+",\"uvpr\":"+String(snap.cfg_cell_uvpr(),3)+",\"ovp\":"+String(snap.cfg_cell_ovp(),3)+",\"ovpr\":"+String(snap.cfg_cell_ovpr(),3);
    json += ",\"soc100\":"+String(snap.cfg_soc100_v(),3)+",\"soc0\":"+String(snap.cfg_soc0_v(),3)+",\"rcv\":"+String(snap.cfg_rcv_v(),3)+",\"float_v\":"+String(snap.cfg_float_v(),3)+",\"poweroff\":"+String(snap.cfg_poweroff_v(),3);
    json += ",\"bal_delta\":"+String(snap.cfg_balance_delta_v(),3)+",\"bal_start\":"+String(snap.cfg_balance_start_v(),3)+",\"bal_max_a\":"+String(snap.cfg_max_balance_a(),2);
    json += ",\"charge_a\":"+String(snap.cfg_charge_a(),1)+",\"discharge_a\":"+String(snap.cfg_discharge_a(),1)+",\"chg_delay\":"+String((unsigned long)snap.cfg_charge_ocp_delay())+",\"chg_release\":"+String((unsigned long)snap.cfg_charge_ocpr())+",\"dsg_delay\":"+String((unsigned long)snap.cfg_discharge_ocp_delay())+",\"dsg_release\":"+String((unsigned long)snap.cfg_discharge_ocpr());
    json += ",\"scp_release\":"+String((unsigned long)snap.cfg_scp_release())+",\"scp_delay_us\":"+String((unsigned long)snap.cfg_scp_delay_us());
    json += ",\"chg_otp\":"+String(snap.cfg_charge_otp(),1)+",\"chg_otpr\":"+String(snap.cfg_charge_otpr(),1)+",\"chg_utp\":"+String(snap.cfg_charge_utp(),1)+",\"chg_utpr\":"+String(snap.cfg_charge_utpr(),1);
    json += ",\"dsg_otp\":"+String(snap.cfg_discharge_otp(),1)+",\"dsg_otpr\":"+String(snap.cfg_discharge_otpr(),1)+",\"mos_otp\":"+String(snap.cfg_mos_otp(),1)+",\"mos_otpr\":"+String(snap.cfg_mos_otpr(),1);
    json += ",\"charge_en\":"+String(snap.cfg_charge_enabled()?"true":"false")+",\"discharge_en\":"+String(snap.cfg_discharge_enabled()?"true":"false")+",\"balance_en\":"+String(snap.cfg_balance_enabled()?"true":"false");
    json += ",\"device_address\":"+String((unsigned long)snap.cfg_device_address())+",\"precharge_s\":"+String((unsigned long)snap.cfg_precharge_s())+",\"function_bits\":"+String((unsigned long)snap.cfg_function_bits())+",\"smart_sleep_h\":"+String((unsigned long)snap.cfg_smart_sleep_h())+"}";
    json += ",\"diag\":{";
    json += "\"waiting\":"+String(snap.waiting()?"true":"false")+",\"setup_pending\":"+String(snap.setup_request_pending()?"true":"false");
    json += ",\"request_reg\":"+String((unsigned long)snap.active_request_register())+",\"frame_pos\":"+String((unsigned long)snap.frame_pos())+",\"raw_rx\":"+String((unsigned long)snap.raw_rx_pos());
    json += ",\"last_valid_age_ms\":"+String((unsigned long)snap.last_valid_age_ms())+",\"ok_status\":"+String((unsigned long)snap.ok_status_frames())+",\"ok_setup\":"+String((unsigned long)snap.ok_setup_frames());
    json += ",\"rejected\":"+String((unsigned long)snap.rejected_frames())+",\"timeouts\":"+String((unsigned long)snap.timeout_count());
    json += ",\"loop_ticks\":"+String((unsigned long)bmsDiagLoopTicks.load(std::memory_order_relaxed))+",\"tx_attempts\":"+String((unsigned long)bmsDiagTxAttempts.load(std::memory_order_relaxed))+",\"tx_started\":"+String((unsigned long)bmsDiagTxStarted.load(std::memory_order_relaxed))+",\"init_count\":"+String((unsigned long)bmsDiagInitCount.load(std::memory_order_relaxed))+"}";
    json += "}";
    
    const uint32_t apiUs=micros()-apiT0; sBmsApiLastBuildUs.store(apiUs,std::memory_order_relaxed); atomicMaxU32(sBmsApiMaxBuildUs,apiUs);
    atomicMinU32(sBmsApiMinHeap,ESP.getFreeHeap()); atomicMinU32(sBmsApiMinLargest,heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    request->send(200, "application/json", json);
  });

  server.on("/api/bms/full", HTTP_GET, [](AsyncWebServerRequest *request) {
    if(!remoteAuthRequest(request)) return;
    const JKPBBms snap = bmsDiagnosticSnapshot();
    String j; j.reserve(4096); j = "{";
    j += "\"fw\":\"" + String(FW_VERSION) + "\"";
    j += ",\"web_api_schema\":\"AUDIT18.7-BMS-DIAG-1\"";
    j += ",\"uptime_ms\":" + String((unsigned long)millis());
    j += ",\"valid\":" + String(snap.valid()?"true":"false") + ",\"setup_valid\":" + String(snap.setup_valid()?"true":"false");
    j += ",\"setup_age_ms\":" + String((unsigned long)snap.setup_age_ms());
    j += ",\"diag\":{";
    j += "\"waiting\":"+String(snap.waiting()?"true":"false")+",\"setup_pending\":"+String(snap.setup_request_pending()?"true":"false");
    j += ",\"request_reg\":"+String((unsigned long)snap.active_request_register())+",\"frame_pos\":"+String((unsigned long)snap.frame_pos())+",\"raw_rx\":"+String((unsigned long)snap.raw_rx_pos());
    j += ",\"last_valid_age_ms\":"+String((unsigned long)snap.last_valid_age_ms())+",\"ok_status\":"+String((unsigned long)snap.ok_status_frames())+",\"ok_setup\":"+String((unsigned long)snap.ok_setup_frames());
    j += ",\"rejected\":"+String((unsigned long)snap.rejected_frames())+",\"timeouts\":"+String((unsigned long)snap.timeout_count());
    j += ",\"write_pending\":"+String(snap.write_pending()?"true":"false")+",\"write_ack_ok\":"+String(snap.last_write_ack_ok()?"true":"false")+",\"write_verified\":"+String(snap.last_write_verified()?"true":"false");
    j += ",\"write_reg\":"+String((unsigned)snap.last_write_register())+",\"write_value\":"+String((unsigned long)snap.last_write_value())+",\"write_ack_count\":"+String((unsigned long)snap.write_ack_ok_count())+",\"write_verify_count\":"+String((unsigned long)snap.write_verify_ok_count())+",\"write_fail_count\":"+String((unsigned long)snap.write_fail_count());
    j += ",\"loop_ticks\":"+String((unsigned long)bmsDiagLoopTicks.load(std::memory_order_relaxed))+",\"tx_attempts\":"+String((unsigned long)bmsDiagTxAttempts.load(std::memory_order_relaxed))+",\"tx_started\":"+String((unsigned long)bmsDiagTxStarted.load(std::memory_order_relaxed))+",\"init_count\":"+String((unsigned long)bmsDiagInitCount.load(std::memory_order_relaxed))+"}";
    j += ",\"address\":"+String(snap.detected_address())+",\"soc\":"+String(snap.get_state_of_charge());
    j += ",\"voltage\":"+String(snap.get_voltage(),3)+",\"current\":"+String(snap.get_current(),3)+",\"power\":"+String(snap.get_power(),1);
    j += ",\"status\":"+String(snap.get_battery_status())+",\"soh\":"+String(snap.get_soh())+",\"precharge\":"+String(snap.get_precharge_status()?"true":"false")+",\"bms_runtime_s\":"+String((unsigned long)snap.get_bms_runtime_s())+",\"heating\":"+String(snap.get_heating_status()?"true":"false")+",\"charger_plugged\":"+String(snap.get_charger_plugged()?"true":"false")+",\"balance_current\":"+String(snap.get_balance_current(),3);
    j += ",\"remain_ah\":"+String(snap.get_balance_capacity(),2)+",\"capacity_ah\":"+String(snap.get_rate_capacity(),2);
    j += ",\"cycles\":"+String((unsigned long)snap.get_cycle_count())+",\"cycle_mah\":"+String((unsigned long)snap.get_cycle_capacity_mah());
    j += ",\"alarm\":"+String((unsigned long)snap.get_alarm_bits())+",\"charge_mos\":"+String(snap.get_charge_mosfet_status()?"true":"false")+",\"discharge_mos\":"+String(snap.get_discharge_mosfet_status()?"true":"false")+",\"balance_mos\":"+String(snap.get_balance_status(0)?"true":"false");
    j += ",\"mos_temp\":"+String(snap.get_mos_temperature(),1)+",\"temps\":[";
    for(int i=0;i<5;i++){ if(i)j+=","; j+=String(snap.get_ntc_temperature(i),1); } j+="]";
    j += ",\"cells\":["; for(int i=0;i<snap.get_num_cells();i++){if(i)j+=",";j+=String(snap.get_cell_voltage(i),3);} j+="]";
    j += ",\"wire\":["; for(int i=0;i<snap.get_num_cells();i++){if(i)j+=",";j+=String(snap.get_wire_resistance(i),3);} j+="]";
    j += ",\"runtime_charge_min\":"+String((unsigned long)canBatterySnapshotAtomic().chgruntime)+",\"runtime_discharge_min\":"+String((unsigned long)canBatterySnapshotAtomic().disruntime);
    j += ",\"cfg\":{";
    j += "\"cell_count\":"+String((unsigned long)snap.cfg_cell_count())+",\"capacity_ah\":"+String(snap.cfg_capacity_ah(),1)+",\"sleep_entry_v\":"+String(snap.cfg_sleep_entry_v(),3);
    j += ",\"uvp\":"+String(snap.cfg_cell_uvp(),3)+",\"uvpr\":"+String(snap.cfg_cell_uvpr(),3)+",\"ovp\":"+String(snap.cfg_cell_ovp(),3)+",\"ovpr\":"+String(snap.cfg_cell_ovpr(),3);
    j += ",\"soc100\":"+String(snap.cfg_soc100_v(),3)+",\"soc0\":"+String(snap.cfg_soc0_v(),3)+",\"rcv\":"+String(snap.cfg_rcv_v(),3)+",\"float_v\":"+String(snap.cfg_float_v(),3)+",\"poweroff\":"+String(snap.cfg_poweroff_v(),3);
    j += ",\"bal_delta\":"+String(snap.cfg_balance_delta_v(),3)+",\"bal_start\":"+String(snap.cfg_balance_start_v(),3)+",\"bal_max_a\":"+String(snap.cfg_max_balance_a(),2);
    j += ",\"charge_a\":"+String(snap.cfg_charge_a(),1)+",\"discharge_a\":"+String(snap.cfg_discharge_a(),1)+",\"chg_delay\":"+String((unsigned long)snap.cfg_charge_ocp_delay())+",\"chg_release\":"+String((unsigned long)snap.cfg_charge_ocpr())+",\"dsg_delay\":"+String((unsigned long)snap.cfg_discharge_ocp_delay())+",\"dsg_release\":"+String((unsigned long)snap.cfg_discharge_ocpr());
    j += ",\"scp_release\":"+String((unsigned long)snap.cfg_scp_release())+",\"scp_delay_us\":"+String((unsigned long)snap.cfg_scp_delay_us());
    j += ",\"chg_otp\":"+String(snap.cfg_charge_otp(),1)+",\"chg_otpr\":"+String(snap.cfg_charge_otpr(),1)+",\"chg_utp\":"+String(snap.cfg_charge_utp(),1)+",\"chg_utpr\":"+String(snap.cfg_charge_utpr(),1);
    j += ",\"dsg_otp\":"+String(snap.cfg_discharge_otp(),1)+",\"dsg_otpr\":"+String(snap.cfg_discharge_otpr(),1)+",\"mos_otp\":"+String(snap.cfg_mos_otp(),1)+",\"mos_otpr\":"+String(snap.cfg_mos_otpr(),1);
    j += ",\"charge_en\":"+String(snap.cfg_charge_enabled()?"true":"false")+",\"discharge_en\":"+String(snap.cfg_discharge_enabled()?"true":"false")+",\"balance_en\":"+String(snap.cfg_balance_enabled()?"true":"false");
    j += ",\"device_address\":"+String((unsigned long)snap.cfg_device_address())+",\"precharge_s\":"+String((unsigned long)snap.cfg_precharge_s())+",\"function_bits\":"+String(snap.cfg_function_bits())+",\"smart_sleep_h\":"+String(snap.cfg_smart_sleep_h());
    j += "}}";  request->send(200,"application/json",j);
  });

  server.on("/api/bms/setup_refresh", HTTP_POST, [](AsyncWebServerRequest *r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    if(!queueBmsOp(PendingBmsOpType::SETUP_REFRESH)){r->send(409,"application/json","{\"ok\":false,\"err\":\"BMS command queue busy\"}");return;}
    r->send(202,"application/json","{\"ok\":true,\"queued\":true}");
  });

  // AUDIT18.5: safe allow-list for JK-PB V19 RW settings. Values are supplied
  // as raw integer units from the documented register map (mV, mA, 0.1 C, etc).
  server.on("/api/bms/setting", HTTP_POST, [](AsyncWebServerRequest *r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    if (!r->hasParam("key", true) || !r->hasParam("value", true)) { r->send(400,"application/json","{\"ok\":false,\"err\":\"key/value required\"}"); return; }
    const String key=r->getParam("key",true)->value();
    const String rawValue=r->getParam("value",true)->value();
    char* valueEnd=nullptr;
    errno=0;
    const long long sv=strtoll(rawValue.c_str(),&valueEnd,10);
    if(errno==ERANGE || valueEnd==rawValue.c_str() || *valueEnd!='\0'){
      r->send(400,"application/json","{\"ok\":false,\"err\":\"invalid integer value\"}");return;
    }
    struct E { const char* k; uint16_t off; uint32_t lo,hi; bool sign; };
    // AUDIT20.4.1: REMOTE endpoint is intentionally narrower than the internal
    // JK-PB writer. Only settings already exposed as safe controls in /remote
    // are accepted here. Critical protection, MOS/function, address, cell-count,
    // capacity and current-limit settings remain read-only remotely.
    static const E m[] = {
      {"bal_delta",20,1,500,false},
      {"soc100",24,2000,5000,false},
      {"soc0",28,1200,4500,false},
      {"rcv",32,2000,5000,false},
      {"float",36,2000,5000,false},
      {"bal_start",132,1500,5000,false},
      {"smart_sleep",280,0,255,false}
    };
    const E* e=nullptr; for (auto &x:m) if(key==x.k){e=&x;break;}
    if(!e){r->send(400,"application/json","{\"ok\":false,\"err\":\"unsupported setting\"}");return;}
    if((!e->sign && (sv < (long long)e->lo || sv > (long long)e->hi)) || (e->sign && (sv < -400 || sv > (long long)e->hi))){r->send(422,"application/json","{\"ok\":false,\"err\":\"value outside safety range\"}");return;}
    if(!queueBmsOp(PendingBmsOpType::WRITE_U32,e->off,(uint32_t)(int32_t)sv)){r->send(409,"application/json","{\"ok\":false,\"err\":\"BMS command queue busy\"}");return;}
    r->send(202,"application/json","{\"ok\":true,\"queued\":true}");
  });


  // AUDIT20.0 remote write status: lets the authenticated dashboard confirm
  // ACK + 0x161E read-back rather than treating HTTP 202 as success.
  server.on("/api/remote/write-status", HTTP_GET, [](AsyncWebServerRequest *r){
    if(!remoteAuthRequest(r)) return;
    const JKPBBms snap = bmsDiagnosticSnapshot();
    char j[256];
    snprintf(j,sizeof(j),"{\"pending\":%s,\"ack_ok\":%s,\"verified\":%s,\"reg\":%u,\"value\":%lu,\"ack_ok_count\":%lu,\"verify_ok_count\":%lu,\"fail_count\":%lu}",
      snap.write_pending()?"true":"false", snap.last_write_ack_ok()?"true":"false", snap.last_write_verified()?"true":"false",
      (unsigned)snap.last_write_register(), (unsigned long)snap.last_write_value(),
      (unsigned long)snap.write_ack_ok_count(), (unsigned long)snap.write_verify_ok_count(), (unsigned long)snap.write_fail_count());
    
    r->send(200,"application/json",j);
  });

  server.on("/api/remote/info", HTTP_GET, [](AsyncWebServerRequest *r){
    if(!remoteAuthRequest(r)) return;
    r->send(200,"application/json","{\"ok\":true,\"transport\":\"VPN+HTTP-Basic\",\"direct_public_internet\":false,\"writes\":\"ACK+readback\"}");
  });

  server.on(AsyncURIMatcher::exact("/api/net"), HTTP_GET, [](AsyncWebServerRequest *request) {
    if(!remoteAuthRequest(request)) return;

    const bool staConnected = WiFi.isConnected();
    String mode = wifiModeToString(WiFi.getMode());
    String ip   = staConnected ? WiFi.localIP().toString() : WiFi.softAPIP().toString();
    String ssid = staConnected ? WiFi.SSID() : WiFi.softAPSSID();

    String json = "{";
    json += "\"mode\":\"" + mode + "\",";
    json += "\"ip\":\"" + ip + "\",";
    json += "\"ssid\":\"" + jsonEscape(ssid) + "\"";
    json += "}";

    request->send(200, "application/json", json);
  });

  server.on(AsyncURIMatcher::exact("/api/net/health"), HTTP_GET, [](AsyncWebServerRequest *request) {
    CrashHttpScope crashScope(CRASH_HTTP_NET_HEALTH);
    // 9.36.7 intentionally lightweight and read-only: usable even while diagnosing auth/UI issues.
    String j="{";
    j += "\"ok\":true,";
    j += "\"ms\":"+String(millis())+",";
    j += "\"wifi_status\":"+String((int)WiFi.status())+",";
    j += "\"mode\":\""+wifiModeToString(WiFi.getMode())+"\",";
    j += "\"ip\":\""+WiFi.localIP().toString()+"\",";
    j += "\"rssi\":"+String(WiFi.status()==WL_CONNECTED?WiFi.RSSI():0)+",";
    j += "\"heap\":"+String(ESP.getFreeHeap())+",";
    j += "\"largest8\":"+String(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT))+",";
    j += "\"reconnects\":"+String(wifiReconnectCounter())+",";
    j += "\"full_restarts\":"+String(wifiFullRestartCounter())+",";
    j += "\"previous_wifi_auto_reset\":"+String(wifiPreviousAutoReset()?"true":"false")+",";
    j += "\"wifi_auto_reset_attempts\":"+String(wifiAutoResetAttempts())+",";
    j += "\"recovery_ap\":"+String(wifiRecoveryApCounter())+",";
    j += "\"sta_up_count\":"+String(wifiStaUpCounter())+",";
    j += "\"last_up_ms\":"+String(wifiLastStaUpMs())+",";
    j += "\"last_down_ms\":"+String(wifiLastStaDownMs())+",";
    j += "\"wifi_evt_connected\":"+String(wifiEventStaConnectedCount())+",";
    j += "\"wifi_evt_disconnected\":"+String(wifiEventStaDisconnectedCount())+",";
    j += "\"wifi_evt_got_ip\":"+String(wifiEventGotIpCount())+",";
    j += "\"wifi_evt_lost_ip\":"+String(wifiEventLostIpCount())+",";
    j += "\"wifi_last_disc_reason\":"+String(wifiLastDisconnectReason())+",";
    j += "\"wifi_last_disc_rssi\":"+String(wifiLastDisconnectRssi())+",";
    j += "\"wifi_last_event_ms\":"+String(wifiLastEventMs())+",";
    j += "\"web_rebind_suppressed\":"+String(wifiWebRebindSuppressedCount())+",";
    j += "\"ws_log\":"+String(webWsLogClients())+",";
    j += "\"ws_bms\":"+String(webWsBmsClients())+",";
    j += "\"ws_debug\":"+String(webWsDebugClients())+",";
    j += "\"ws_cleanup_runs\":"+String(webWsCleanupRuns())+",";
    j += "\"ws_lowheap_cleanup\":"+String(webLowHeapCleanupCount())+",";
    j += "\"loop_last_gap_ms\":"+String(webLoopLastGapMs())+",";
    j += "\"loop_max_gap_ms\":"+String(webLoopMaxGapMs())+",";
    j += "\"bms_api_calls\":"+String(sBmsApiCalls.load(std::memory_order_relaxed))+",";
    j += "\"bms_api_inflight\":"+String(sBmsApiInflight.load(std::memory_order_relaxed))+",";
    j += "\"bms_api_max_inflight\":"+String(sBmsApiMaxInflight.load(std::memory_order_relaxed))+",";
    j += "\"bms_api_last_us\":"+String(sBmsApiLastBuildUs.load(std::memory_order_relaxed))+",";
    j += "\"bms_api_max_us\":"+String(sBmsApiMaxBuildUs.load(std::memory_order_relaxed))+",";
    j += "\"bms_api_min_heap\":"+String(sBmsApiMinHeap.load(std::memory_order_relaxed))+",";
    j += "\"bms_api_min_largest\":"+String(sBmsApiMinLargest.load(std::memory_order_relaxed))+",";
    j += "\"min_heap\":"+String(ESP.getMinFreeHeap());
    j += "}";
    AsyncWebServerResponse* res=request->beginResponse(200,"application/json",j);
    res->addHeader("Cache-Control","no-store");
    res->addHeader("Connection","close");
    request->send(res);
  });

  server.on(AsyncURIMatcher::exact("/api/net"), HTTP_POST, [](AsyncWebServerRequest *request) {
    if(!remoteAuthRequest(request)) return;
    if(!remoteMutationAllowed(request)){request->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}

    // Validate both halves of the form before persisting either one.
    const String mbase=request->arg("mbase"), mport=request->arg("mport");
    if(!mqttBaseValid(mbase)){request->send(400,"application/json","{\"ok\":false,\"err\":\"invalid mqtt base topic\"}");return;}
    uint32_t portLong=0; bool portValid=!mport.isEmpty();
    for(size_t i=0;i<mport.length();++i){
      const char c=mport[i];
      if(c<'0'||c>'9'){portValid=false;break;}
      portLong=portLong*10U+(uint32_t)(c-'0');
      if(portLong>65535U){portValid=false;break;}
    }
    if(!portValid||portLong==0){request->send(400,"application/json","{\"ok\":false,\"err\":\"mqtt port range 1..65535\"}");return;}

    // --- WiFi fields ---
    String ssid = request->arg("ssid");
    String pass = request->arg("pass");

    bool   wifiChanged = false;
    bool   staOk       = false;
    String staIp;   // new

    if (ssid.length()) {
      // Never mutate global Arduino String WiFi state from the AsyncWebServer task.
      // Persist here; main-loop ensureWiFi() atomically notices the request and reloads/applies it.
      Preferences np; np.begin("net", true);
      const String oldSsid=np.getString("ssid", ""), oldPass=np.getString("pass", ""); np.end();
      // 9.36.7.11: credentials are write-only. An empty password field means
      // "keep the stored password" so merely saving the page cannot erase it.
      if (pass.isEmpty() && oldPass.length()) pass = oldPass;
      wifiChanged = (ssid != oldSsid) || (pass != oldPass);
      if (wifiChanged) {
        if (!wifiSaveCredentialsDeferred(ssid, pass)) {
          request->send(500, "application/json", "{\"ok\":false,\"err\":\"wifi NVS write/readback failed\"}");
          return;
        }
        staOk = false; // apply is intentionally deferred to the main loop
      }
    }

    // --- MQTT fields (always saved) ---
    String mhost = request->arg("mhost");
    String muser = request->arg("muser");
    String mpass = request->arg("mpass");
    if (mpass.isEmpty()) {
      Preferences mp; mp.begin("mqtt", true); mpass=mp.getString("pass", ""); mp.end();
    }
    bool men = request->arg("men") == "on" || request->arg("men") == "true";
    if(!mqttSaveConfigDeferred(mhost,(uint16_t)portLong,muser,mpass,mbase,men)){request->send(500,"application/json","{\"ok\":false,\"err\":\"mqtt NVS write/readback failed\"}");return;}

    // JSON response so the UI knows what happened
    String json = "{";
    json += "\"ok\":true";
    json += ",\"wifi_changed\":"; json += (wifiChanged ? "true" : "false");
    if (wifiChanged) {
      json += ",\"sta_ok\":"; json += (staOk ? "true" : "false");
      if (staOk && staIp.length()) {
        json += ",\"sta_ip\":\"";
        json += staIp;
        json += "\"";
      }
    }
    json += "}";

    request->send(200, "application/json", json);
  });

  server.on("/api/toggle", HTTP_POST, [](AsyncWebServerRequest* request) {
    if(!remoteAuthRequest(request)) return;
    if(!remoteMutationAllowed(request)){request->send(403,"application/json","{\"ok\":false,\"err\":\"same-origin required\"}");return;}
    String k; if(request->hasParam("k",true)) k=request->getParam("k",true)->value(); else if(request->hasParam("key",true)) k=request->getParam("key",true)->value();
    if(!k.length()){request->send(400,"application/json","{\"ok\":false,\"err\":\"missing key\"}");return;}
    if(k=="moschg"||k=="mosdis"){request->send(409,"application/json","{\"ok\":false,\"err\":\"JK-PB MOS control disabled (read-only)\"}");return;}
    bool cur=false; if(!configToggleValueAtomic(k.c_str(),cur)){request->send(404,"application/json",String("{\"ok\":false,\"err\":\"unknown key\",\"k\":\"")+k+"\"}");return;}
    if(!queueToggle(k)){request->send(409,"application/json","{\"ok\":false,\"err\":\"toggle update busy\"}");return;}
    request->send(202,"application/json",String("{\"ok\":true,\"queued\":true,\"k\":\"")+k+"\",\"current\":"+(cur?"true":"false")+"}");
  });

}


// ---- WiFi mode helper ----
static void wsAttachHandlers(const char* name, AsyncWebSocket& ws) {
  ws.onEvent([name](AsyncWebSocket * server,
                    AsyncWebSocketClient * client,
                    AwsEventType type,
                    void * arg,
                    uint8_t * data,
                    size_t len) {
    switch (type) {
      case WS_EVT_CONNECT: {
        if(sCloudQuiesce.load(std::memory_order_acquire)){ client->close(); break; }
        sWsConnects.fetch_add(1, std::memory_order_relaxed);
        IPAddress ip = client->remoteIP();
        Serial.printf("[%s] #%u CONNECTED from %s\n", name, client->id(), ip.toString().c_str());
        client->text(String("[") + name + "] hello from ESP32");
        break;
      }
      case WS_EVT_DISCONNECT:
        sWsDisconnects.fetch_add(1, std::memory_order_relaxed);
        Serial.printf("[%s] #%u DISCONNECTED\n", name, client->id());
        break;
      case WS_EVT_DATA:
        Serial.printf("[%s] #%u TEXT %u bytes\n", name, client->id(), (unsigned)len);
        break;
      case WS_EVT_PONG:
        Serial.printf("[%s] #%u PONG\n", name, client->id());
        break;
      case WS_EVT_ERROR:
        sWsErrors.fetch_add(1, std::memory_order_relaxed);
        Serial.printf("[%s] #%u ERROR\n", name, client->id());
        break;
    }
  });
}

// ----------------------------------------------------------------------------
// Ring buffers (CAN + DEBUG)
// ----------------------------------------------------------------------------
static constexpr size_t WSBUF_SZ       = 4096;     // per channel; AUDIT19.15.17 saves 8 KiB internal RAM total
static constexpr size_t WSFLUSH_SLICE  = 1024;     // bytes per burst (tune)

struct WsRing {
  char buf[WSBUF_SZ];
  size_t head = 0, tail = 0;
  SemaphoreHandle_t mtx = nullptr;
  inline size_t used() const { return (head + WSBUF_SZ - tail) % WSBUF_SZ; }
  inline size_t free() const { return WSBUF_SZ - 1 - used(); } // keep 1 byte gap
  inline void   pushByte(char c){
    buf[head] = c;
    head = (head + 1) % WSBUF_SZ;
    if (head == tail) tail = (tail + 1) % WSBUF_SZ;
  }
  inline bool   popByte(char &out){
    if (tail == head) return false;
    out = buf[tail];
    tail = (tail + 1) % WSBUF_SZ;
    return true;
  }
};

static WsRing ringCan, ringDbg;
static StaticSemaphore_t ringCanMutexBuf, ringDbgMutexBuf;

static void wsbuf_init(){
  ringCan.mtx = xSemaphoreCreateMutexStatic(&ringCanMutexBuf);
  ringDbg.mtx = xSemaphoreCreateMutexStatic(&ringDbgMutexBuf);
  if (!ringCan.mtx) Serial.println("[WEB] WARN: CAN log ring mutex allocation failed; CAN WebSocket logging disabled");
  if (!ringDbg.mtx) Serial.println("[WEB] WARN: DEBUG ring mutex allocation failed; DEBUG WebSocket logging disabled");
}

// Drop exactly ONE whole line (until and including the next '\n')
static void rb_drop_one_line(WsRing &rb){
  char c;
  while (rb.tail != rb.head) {
    if (rb.popByte(c) && c == '\n') break;
  }
}

// Enqueue a full line (adds '\n'); if not enough space, drop oldest whole lines first
static void rb_enqueue_line(WsRing &rb, const char* s){
  if (!s || !*s || !rb.mtx) return;
  if (xSemaphoreTake(rb.mtx, 0) != pdTRUE) return;
  size_t need = strlen(s) + 1;
  // Fail closed for an oversized line. Without this guard, need > ring capacity
  // would make the drop loop spin forever because free() can never reach need.
  if (need > (WSBUF_SZ - 1)) { xSemaphoreGive(rb.mtx); return; }
  while (rb.free() < need) rb_drop_one_line(rb);
  while (*s) rb.pushByte(*s++);
  rb.pushByte('\n');
  xSemaphoreGive(rb.mtx);
}

static void ws_flush_ring(AsyncWebSocket &ws, WsRing &rb){
  if (ws.count() == 0 || !rb.mtx) return;
  if (xSemaphoreTake(rb.mtx, 0) != pdTRUE) return;
  const size_t used = rb.used();
  const size_t limit = (used < WSFLUSH_SLICE ? used : (size_t)WSFLUSH_SLICE);
  if (limit == 0) { xSemaphoreGive(rb.mtx); return; }

  size_t idx = rb.tail;
  ssize_t last_nl = -1;
  for (size_t i = 0; i < limit; ++i) {
    if (rb.buf[idx] == '\n') last_nl = (ssize_t)i;
    idx = (idx + 1) % WSBUF_SZ;
  }

  if (last_nl < 0 && used < (WSBUF_SZ - 64)) {
    xSemaphoreGive(rb.mtx);
    return;
  }

  size_t to_send = (last_nl >= 0) ? ((size_t)last_nl + 1) : limit;

  static char out[WSFLUSH_SLICE + 1];
  for (size_t i = 0; i < to_send; ++i) rb.popByte(out[i]);
  xSemaphoreGive(rb.mtx);

  if (auto *mb = ws.makeBuffer(to_send)) {
    memcpy(mb->get(), out, to_send);
    ws.textAll(mb);
  } else {
    // AUDIT19.15.33: fail closed under heap pressure. Calling the raw-data
    // textAll() fallback can allocate internally again after makeBuffer() has
    // already told us allocation failed. Logging is non-critical, so drop it.
    static uint32_t wsLogAllocDrops = 0;
    ++wsLogAllocDrops;
  }
}

// ----------------------------------------------------------------------------
// Public logging APIs
// ----------------------------------------------------------------------------
void streamCanLog(const char* message) {
  if (wsLog.count())
    rb_enqueue_line(ringCan, message);
}

void streamDebug(const char* message) {
  if (wsDebug.count())
    rb_enqueue_line(ringDbg, message);
}

// ----------------------------------------------------------------------------
// BMS WebSocket JSON push
// ----------------------------------------------------------------------------
static void sendBMSReadings() {
  if (wsBms.count() == 0) return;

  #ifdef ASYNC_WEBSOCKET_FEATURES
  if (!wsBms.availableForWriteAll()) return;
  #endif

  const BmsSafetySnapshot live = bmsSafetySnapshotAtomic();
  const float voltage = live.voltageMilliV / 1000.0f;
  const float current = live.currentMilliA / 1000.0f;
  const int   soc     = live.soc;
  const int   temp    = live.tempDeciC / 10;
  const int   chg     = (int)canBatterySnapshotAtomic().chgruntime;
  const int   dis     = (int)canBatterySnapshotAtomic().disruntime;

  char json[160];
  snprintf(json, sizeof(json),
    "{\"soc\":%d,\"voltage\":%.2f,\"current\":%.2f,\"temperature\":%d,\"chgruntime\":%d,\"disruntime\":%d}",
    soc, voltage, current, temp, chg, dis);

  size_t n = strlen(json);
  if (auto *mb = wsBms.makeBuffer(n)) {
    memcpy(mb->get(), json, n);
    wsBms.textAll(mb);
  } else {
    // Telemetry WebSocket is optional. Do not attempt a second allocation
    // path when the heap has already refused makeBuffer().
    static uint32_t wsBmsAllocDrops = 0;
    ++wsBmsAllocDrops;
  }
}


// ----------------------------------------------------------------------------
// Init + tick
// ----------------------------------------------------------------------------
void webInit(AsyncWebServer& server) {
  remoteAuthEnsure();
  wsbuf_init();

  wsAttachHandlers("LOG",   wsLog);
  wsAttachHandlers("BMS",   wsBms);
  wsAttachHandlers("DEBUG", wsDebug);

  // 9.36.4 A/B diagnostic: WebSockets intentionally have no Basic Auth.
  // OTA and recovery-AP credentials remain protected and unchanged.

  server.addHandler(&wsLog);
  server.addHandler(&wsBms);
  server.addHandler(&wsDebug);
}


void webCloudQuiesceBegin() {
  sCloudQuiesce.store(true,std::memory_order_release);
  wsLog.closeAll(); wsBms.closeAll(); wsDebug.closeAll();
  wsLog.cleanupClients(); wsBms.cleanupClients(); wsDebug.cleanupClients();
  delay(20);
}
void webCloudQuiesceEnd() {
  sCloudQuiesce.store(false,std::memory_order_release);
}

void webTick() {
  static uint32_t lastTickMs=0;
  const uint32_t tickNow=millis();
  if(lastTickMs){ const uint32_t gap=tickNow-lastTickMs; sWebLoopLastGapMs.store(gap,std::memory_order_relaxed); uint32_t prev=sWebLoopMaxGapMs.load(std::memory_order_relaxed); while(gap>prev && !sWebLoopMaxGapMs.compare_exchange_weak(prev,gap,std::memory_order_relaxed)){} }
  lastTickMs=tickNow;
  if(sRebootRequested.exchange(false)){ mqttDisconnectClean(); delay(50); ESP.restart(); return; }
  applyPendingCoreUpdate();
  applyPendingGuardUpdate();
  applyPendingToggle();
  applyPendingBmsOp();
  static uint32_t lastBmsPush = 0;
  static const  uint32_t BMS_PUSH_MS = 250;

  static uint32_t lastFlush = 0;
  static uint32_t lastPing  = 0;

  uint32_t now = millis();

  if (now - lastBmsPush >= BMS_PUSH_MS) {
    lastBmsPush = now;
    sendBMSReadings();
  }

  if (now - lastFlush >= 50) {
    lastFlush = now;
    ws_flush_ring(wsLog,   ringCan);
    ws_flush_ring(wsDebug, ringDbg);
  }

  // 9.36.7.5: clean ALL websocket endpoints independently of traffic.
  // Previously wsBms was never cleaned, and log/debug shared one cleanup timer.
  // Browser reconnects can therefore leave stale AsyncTCP clients and consume heap.
  static uint32_t lastWsCleanup=0;
  if(now-lastWsCleanup>=1000){
    lastWsCleanup=now;
    wsLog.cleanupClients();
    wsBms.cleanupClients();
    wsDebug.cleanupClients();
    sWsCleanupRuns.fetch_add(1,std::memory_order_relaxed);
    // Under pressure, perform one extra bounded cleanup pass; never reboot here.
    if(ESP.getFreeHeap()<14000 || heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)<7000){
      wsLog.cleanupClients(); wsBms.cleanupClients(); wsDebug.cleanupClients();
      sWebLowHeapCleanupCount.fetch_add(1,std::memory_order_relaxed);
    }
  }

  if (now - lastPing >= 15000) {
    lastPing = now;
    wsLog.pingAll();
    wsBms.pingAll();
    wsDebug.pingAll();
  }
}

void webSetupStaticRoutes(AsyncWebServer& server) {
  server.on("/api/diag/cloud-boot", HTTP_GET, [](AsyncWebServerRequest* r) {
    const auto p=cloudDiagPrevious(), c=cloudDiagCurrent();
    const auto lp=cloudDiagLoopPrevious(), lc=cloudDiagLoopCurrent();
    String j="{\"ok\":true,\"ms\":"+String(millis());
    j+=",\"previous_cloud_step\":"+String(p.step)+",\"previous_cloud_at_ms\":"+String(p.atMs);
    j+=",\"previous_cloud_job_id\":"+String(p.jobId)+",\"previous_cloud_http_code\":"+String(p.httpCode);
    j+=",\"previous_cloud_bytes\":"+String(p.responseBytes)+",\"previous_cloud_result_ok\":"+String(p.resultOk?"true":"false");
    j+=",\"previous_cloud_heap\":"+String(p.freeHeap)+",\"previous_cloud_largest8\":"+String(p.largest8);
    j+=",\"previous_cloud_wifi_status\":"+String(p.wifiStatus);
    j+=",\"current_cloud_step\":"+String(c.step)+",\"current_cloud_at_ms\":"+String(c.atMs);
    j+=",\"current_cloud_job_id\":"+String(c.jobId)+",\"current_cloud_http_code\":"+String(c.httpCode);
    j+=",\"current_cloud_bytes\":"+String(c.responseBytes)+",\"current_cloud_result_ok\":"+String(c.resultOk?"true":"false");
    j+=",\"current_cloud_heap\":"+String(c.freeHeap)+",\"current_cloud_largest8\":"+String(c.largest8);
    j+=",\"current_cloud_wifi_status\":"+String(c.wifiStatus);
    j+=",\"previous_loop_at_ms\":"+String(lp.atMs)+",\"previous_loop_count\":"+String(lp.count);
    j+=",\"previous_loop_heap\":"+String(lp.freeHeap)+",\"previous_loop_largest8\":"+String(lp.largest8);
    j+=",\"previous_loop_wifi_status\":"+String(lp.wifiStatus);
    j+=",\"current_loop_at_ms\":"+String(lc.atMs)+",\"current_loop_count\":"+String(lc.count);
    j+=",\"current_loop_heap\":"+String(lc.freeHeap)+",\"current_loop_largest8\":"+String(lc.largest8);
    j+=",\"current_loop_wifi_status\":"+String(lc.wifiStatus)+"}";
    auto* res=r->beginResponse(200,"application/json",j);
    res->addHeader("Cache-Control","no-store");r->send(res);
  });
  server.on("/api/diag/ble-boot", HTTP_GET, [](AsyncWebServerRequest* request) {
    const JkBleStatusDiag d=jkBleProxyStatusDiag();
    String j = "{\"ok\":true,\"diag_version\":\"9.36.7.15C-TLS-RAM-RECLAIM-FIX\",\"ms\":" + String(millis());
    const PsProbeTrace prior=psProbeTracePrevious(), now=psProbeTraceCurrent();
    j += ",\"previous_ps_step\":" + String(prior.step);
    j += ",\"previous_ps_at_ms\":" + String(prior.atMs);
    j += ",\"previous_ps_free_heap\":" + String(prior.freeHeap);
    j += ",\"previous_ps_largest8\":" + String(prior.largest8);
    j += ",\"current_ps_step\":" + String(now.step);
    j += ",\"current_ps_at_ms\":" + String(now.atMs);
    j += ",\"ps_trace_write_ok\":" + String(psProbeTraceWriteOk()?"true":"false");
    j += ",\"ps_trace_write_attempts_this_boot\":" + String(psProbeTraceWriteAttemptsThisBoot());
    j += ",\"ps_trace_write_failures_this_boot\":" + String(psProbeTraceWriteFailuresThisBoot());
    j += ",\"reset_reason\":" + String(bleBootDiagResetReason());
    j += ",\"previous_stage\":" + String(bleBootDiagPrevious());
    j += ",\"current_stage\":" + String(bleBootDiagCurrent());
    const CrashHttpSnapshot prev=crashHttpPrevious(), curr=crashHttpCurrent();
    j += ",\"previous_http_active_mask\":" + String(prev.activeMask);
    j += ",\"previous_http_last_route\":" + String(prev.lastRoute);
    j += ",\"previous_http_free_heap\":" + String(prev.freeHeap);
    j += ",\"previous_http_largest8\":" + String(prev.largest8);
    j += ",\"previous_http_at_ms\":" + String(prev.atMs);
    j += ",\"current_http_active_mask\":" + String(curr.activeMask);
    j += ",\"free_heap\":" + String(ESP.getFreeHeap());
    j += ",\"largest8\":" + String(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT));
    j += ",\"min_heap\":" + String(ESP.getMinFreeHeap());
    j += ",\"diag_stack_min_bytes\":" + String(diagHeartbeatStackMinBytes());
    j += ",\"ble_initialized\":" + String(d.initialized?"true":"false");
    j += ",\"app_connected\":" + String(d.appConnected?"true":"false");
    j += ",\"real_jk_connected\":" + String(d.bmsConnected?"true":"false");
    j += ",\"bridge_ready\":" + String((d.appConnected && d.bmsConnected && !d.bridgeFault && !d.eventsPending)?"true":"false");
    j += ",\"aux_reserved\":" + String(d.auxReserved?"true":"false");
    j += ",\"bridge_fault\":" + String(d.bridgeFault?"true":"false");
    j += ",\"events_pending\":" + String(d.eventsPending?"true":"false");
    j += ",\"safe_hold\":" + String(d.safeHold?"true":"false");
    j += ",\"ble_startup_enabled\":" + String(d.startupEnabled?"true":"false");
    j += ",\"connect_attempts\":" + String(d.connectAttempts);
    j += ",\"bridge_ready_count\":" + String(d.bridgeReadyCount);
    j += ",\"last_bms_disconnect_reason\":" + String(d.lastBmsDisconnectReason);
    j += ",\"app_to_bms_drops\":" + String(d.appToBmsDrops);
    j += ",\"bms_to_app_drops\":" + String(d.bmsToAppDrops);
    j += ",\"event_drops\":" + String(d.eventDrops);
    j += ",\"bridge_faults\":" + String(d.bridgeFaults);
    j += ",\"forward_write_fails\":" + String(d.forwardWriteFails);
    j += ",\"queue_flushes\":" + String(d.queueFlushes) + "}";
    request->send(200, "application/json", j);
  });

  Serial.printf("[FS] status=%s total=%u used=%u\n", filesystemStatusString(),
                sFsReady ? (unsigned)SPIFFS.totalBytes() : 0u,
                sFsReady ? (unsigned)SPIFFS.usedBytes() : 0u);

  // Serve SPIFFS pages
  server.on("/", HTTP_GET, [](AsyncWebServerRequest* request){
    sendProtectedFs(request, "/index.html", "text/html");
  });

  server.on("/log", HTTP_GET, [](AsyncWebServerRequest* request){
    sendProtectedFs(request, "/canlog_streaming.html", "text/html");
  });

  server.on("/debug", HTTP_GET, [](AsyncWebServerRequest* request){
    sendProtectedFs(request, "/debug_streaming.html", "text/html");
  });

  server.on("/bms", HTTP_GET, [](AsyncWebServerRequest* request){
    sendProtectedFs(request, "/bms_dashboard.html", "text/html");
  });

  server.on("/bms_readings", HTTP_GET, [](AsyncWebServerRequest* request){
    sendProtectedFs(request, "/bms_readings.html", "text/html");
  });

  server.on("/remote", HTTP_GET, [](AsyncWebServerRequest* request){
    sendProtectedFs(request, "/remote.html", "text/html");
  });

  // Direct filenames are explicitly protected; do not expose SPIFFS through a catch-all.
  server.on("/index.html", HTTP_GET, [](AsyncWebServerRequest* r){ sendProtectedFs(r,"/index.html","text/html"); });
  server.on("/canlog_streaming.html", HTTP_GET, [](AsyncWebServerRequest* r){ sendProtectedFs(r,"/canlog_streaming.html","text/html"); });
  server.on("/debug_streaming.html", HTTP_GET, [](AsyncWebServerRequest* r){ sendProtectedFs(r,"/debug_streaming.html","text/html"); });
  server.on("/bms_dashboard.html", HTTP_GET, [](AsyncWebServerRequest* r){ sendProtectedFs(r,"/bms_dashboard.html","text/html"); });
  server.on("/bms_readings.html", HTTP_GET, [](AsyncWebServerRequest* r){ sendProtectedFs(r,"/bms_readings.html","text/html"); });
  server.on("/remote.html", HTTP_GET, [](AsyncWebServerRequest* r){ sendProtectedFs(r,"/remote.html","text/html"); });
  server.on("/ota_update.html", HTTP_GET, [](AsyncWebServerRequest* r){ sendProtectedFs(r,"/ota_update.html","text/html"); });
  server.on("/api/fs/status", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    String j = String("{\"status\":\"") + filesystemStatusString() +
      "\",\"fw\":\"" + FW_VERSION + "\",\"total\":" +
      String(sFsReady ? SPIFFS.totalBytes() : 0) + ",\"used\":" +
      String(sFsReady ? SPIFFS.usedBytes() : 0) + "}";
    r->send(200,"application/json",j);
  });

  // CAN stats
  server.on("/can_stats", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    twai_status_info_t st{};
    const bool driverStatusOk = twai_get_status_info(&st) == ESP_OK;

    char buf[384];
    snprintf(buf, sizeof(buf),
      "rx_cnt=%lu\nrx_sw_drop=%lu\nrx_queue_overflow=%lu\nrx_epoch_drop=%lu\nrx_log_drop=%lu\ndecoded=%lu\nrx_missed=%u\nrx_overrun=%u\ndriver_status_ok=%u\nstate=%d\nbus_off=%lu\nbus_recovered=%lu\nrecovery_fail=%lu\n",
      (unsigned long)can_rx_count, 
      (unsigned long)can_rx_dropped, 
      (unsigned long)can_rx_queue_overflow.load(),
      (unsigned long)can_rx_epoch_dropped.load(),
      (unsigned long)can_log_dropped,
      (unsigned long)can_decoded,
      st.rx_missed_count, 
      st.rx_overrun_count, 
      driverStatusOk ? 1U : 0U,
      st.state,
      (unsigned long)can_bus_off_count.load(),
      (unsigned long)can_bus_recovered_count.load(),
      (unsigned long)can_bus_recovery_fail.load()
    );

    r->send(200, "text/plain", buf);
  });

  // Try late CAN init
  server.on("/can_try_init", HTTP_GET, [](AsyncWebServerRequest* r){
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"text/plain","same-origin required");return;}
    if (canTryInitAndStart()) {
      r->send(200, "text/plain", "TWAI init OK; tasks started");
    } else {
      r->send(500, "text/plain", "TWAI still not ready (see Serial for reason)");
    }
  });

  // Reboot
  server.on("/reboot", HTTP_GET, [](AsyncWebServerRequest* r){ 
    if(!remoteAuthRequest(r)) return;
    if(!remoteMutationAllowed(r)){r->send(403,"text/plain","same-origin required");return;}
    r->send(200, "text/plain", "Reboot scheduled...");
    sRebootRequested.store(true); 
  });

  // Form POST: update parameters
  server.on("/update_param", HTTP_POST, [](AsyncWebServerRequest* request){
    if(!remoteAuthRequest(request)) return;
    if(!remoteMutationAllowed(request)){request->send(403,"text/plain","same-origin required");return;}
    auto getS = [&](const char* n)->String{
      return request->hasParam(n, true) ? request->getParam(n, true)->value() : String();
    };

    PendingCoreUpdate pu;
    { String sv=getS("volt"); if(sv.length()){ float f=sv.toFloat(); long mv=(sv.indexOf('.')>=0||f<=1000.0f)?lroundf(f*1000.0f):strtol(sv.c_str(),nullptr,10); pu.volt=(uint16_t)constrain(mv,0L,65535L); pu.mask|=P_VOLT; } }
    { String v=getS("chgvolt"); if(v.length()){ pu.chgvolt=(uint16_t)constrain(strtol(v.c_str(),nullptr,10),0L,65535L); pu.mask|=P_CHGVOLT; } }
    { String v=getS("temp"); if(v.length()){ long x=constrain(strtol(v.c_str(),nullptr,10),-40L,125L); pu.temp=(uint8_t)x; pu.mask|=P_TEMP; } }
    { String v=getS("soc"); if(v.length()){ pu.soc=(uint8_t)constrain(strtol(v.c_str(),nullptr,10),0L,100L); pu.mask|=P_SOC; } }
    { String v=getS("runtime"); if(v.length()){ pu.disrun=(uint32_t)max(0L,strtol(v.c_str(),nullptr,10)); pu.mask|=P_DISRUN; } }
    { String v=getS("chgtime"); if(v.length()){ pu.chgrun=(uint32_t)max(0L,strtol(v.c_str(),nullptr,10)); pu.mask|=P_CHGRUN; } }
    { String v=getS("bmschgup"); if(v.length()){ pu.up=(uint8_t)constrain(strtol(v.c_str(),nullptr,10),0L,100L); pu.mask|=P_UP; } }
    { String v=getS("bmschgdn"); if(v.length()){ pu.dn=(uint8_t)constrain(strtol(v.c_str(),nullptr,10),0L,100L); pu.mask|=P_DN; } }
    { String v=getS("serial"); if(v.length()){ if(v.length()!=16){request->send(400,"application/json","{\"ok\":false,\"err\":\"serial must be exactly 16 chars\"}");return;} memcpy(pu.serial,v.c_str(),16); pu.serial[16]='\0'; pu.mask|=P_SERIAL; } }
    if(!pu.mask){request->send(400,"application/json","{\"ok\":false,\"err\":\"no valid fields\"}");return;}
    if(!queueCoreUpdate(pu)){request->send(409,"application/json","{\"ok\":false,\"err\":\"core config update already pending\"}");return;}
    request->send(202, "application/json", "{\"ok\":true,\"queued\":true}");
  });

  // 404 handler
  server.onNotFound([](AsyncWebServerRequest *req){
    Serial.printf("[HTTP 404] %s %s\n",
                  req->method()==HTTP_GET?"GET": req->method()==HTTP_POST?"POST":"OTHER",
                  req->url().c_str());
    req->send(404, "text/plain", String("Not found: ")+req->url());
  });
}


uint32_t webWsLogClients(){return (uint32_t)wsLog.count();}
uint32_t webWsBmsClients(){return (uint32_t)wsBms.count();}
uint32_t webWsDebugClients(){return (uint32_t)wsDebug.count();}
uint32_t webWsCleanupRuns(){return sWsCleanupRuns.load(std::memory_order_relaxed);}
uint32_t webLoopMaxGapMs(){return sWebLoopMaxGapMs.load(std::memory_order_relaxed);}
uint32_t webLoopLastGapMs(){return sWebLoopLastGapMs.load(std::memory_order_relaxed);}
uint32_t webLowHeapCleanupCount(){return sWebLowHeapCleanupCount.load(std::memory_order_relaxed);}
