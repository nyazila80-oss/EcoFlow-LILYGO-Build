#include "powerstream_api.h"
#include "resource_gate.h"
#include "cloud_boot_diag.h"
#include <esp_heap_caps.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include "web.h"
#include <StreamString.h>
#include <mbedtls/md.h>
#include <time.h>
#include <freertos/FreeRTOS.h>
#include <freertos/semphr.h>
#include <atomic>
#include <limits.h>

PowerStreamApiState psApiState;

static String gSn, gAccess, gSecret;
static std::atomic<uint32_t> gCloudTraceJobId{0};
static StaticSemaphore_t gApiMutexBuf;
static SemaphoreHandle_t gApiMutex=xSemaphoreCreateRecursiveMutexStatic(&gApiMutexBuf);
static void ensureApiMutex(){}
struct ApiLock { bool held=false; ApiLock(TickType_t wait=0){ ensureApiMutex(); held=gApiMutex && xSemaphoreTakeRecursive(gApiMutex,wait)==pdTRUE; } ~ApiLock(){ if(held) xSemaphoreGiveRecursive(gApiMutex); } };
bool powerStreamApiBusy(){ ensureApiMutex(); if(!gApiMutex) return true; if(xSemaphoreTakeRecursive(gApiMutex,0)==pdTRUE){xSemaphoreGiveRecursive(gApiMutex);return false;} return true; }
// TLS memory-isolation trace. These are diagnostics only; no secrets or payloads.
static std::atomic<uint32_t> gTlsHeapClient{0}, gTlsLargestClient{0};
static std::atomic<uint32_t> gTlsHeapCa{0}, gTlsLargestCa{0};
static std::atomic<uint32_t> gTlsHeapBeginPre{0}, gTlsLargestBeginPre{0};
static std::atomic<uint32_t> gTlsHeapBeginPost{0}, gTlsLargestBeginPost{0};
static std::atomic<uint32_t> gTlsHeapGetPre{0}, gTlsLargestGetPre{0};
static std::atomic<uint32_t> gTlsHeapGetPost{0}, gTlsLargestGetPost{0};
// 9.36.7.13 transport diagnostics: distinguish DNS/TCP reachability from TLS.
static std::atomic<int32_t> gDnsOk{-1}, gTcp443Ok{-1};
static std::atomic<uint32_t> gDnsIp{0};
static std::atomic<uint32_t> gTlsInternalFreePre{0}, gTlsInternalLargestPre{0};
static std::atomic<uint32_t> gTlsInternalFreePost{0}, gTlsInternalLargestPost{0};
static inline void tlsMemSnap(std::atomic<uint32_t>& freeDst,std::atomic<uint32_t>& largestDst){
  freeDst.store(ESP.getFreeHeap(),std::memory_order_relaxed);
  largestDst.store(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),std::memory_order_relaxed);
}
static inline void tlsInternalSnap(std::atomic<uint32_t>& freeDst,std::atomic<uint32_t>& largestDst){
  const uint32_t caps=MALLOC_CAP_8BIT|MALLOC_CAP_INTERNAL;
  freeDst.store(heap_caps_get_free_size(caps),std::memory_order_relaxed);
  largestDst.store(heap_caps_get_largest_free_block(caps),std::memory_order_relaxed);
}

static const char* API_BASE = "https://api-e.ecoflow.com";
static const char* API_HOST = "api-e.ecoflow.com";

// Minimal verified trust store for the current EcoFlow public TLS chain: DigiCert Global Root G2.
// Peer verification remains mandatory; no insecure fallback is permitted.
static const char ECOFLOW_CA_BUNDLE[] PROGMEM = R"EOF(
-----BEGIN CERTIFICATE-----
MIIDjjCCAnagAwIBAgIQAzrx5qcRqaC7KGSxHQn65TANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xMzA4MDExMjAwMDBaFw0zODAxMTUxMjAwMDBaMGExCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xIDAeBgNVBAMTF0RpZ2lDZXJ0IEdsb2JhbCBSb290IEcyMIIBIjANBgkqhkiG
9w0BAQEFAAOCAQ8AMIIBCgKCAQEAuzfNNNx7a8myaJCtSnX/RrohCgiN9RlUyfuI
2/Ou8jqJkTx65qsGGmvPrC3oXgkkRLpimn7Wo6h+4FR1IAWsULecYxpsMNzaHxmx
1x7e/dfgy5SDN67sH0NO3Xss0r0upS/kqbitOtSZpLYl6ZtrAGCSYP9PIUkY92eQ
q2EGnI/yuum06ZIya7XzV+hdG82MHauVBJVJ8zUtluNJbd134/tJS7SsVQepj5Wz
tCO7TG1F8PapspUwtP1MVYwnSlcUfIKdzXOS0xZKBgyMUNGPHgm+F6HmIcr9g+UQ
vIOlCsRnKPZzFBQ9RnbDhxSJITRNrw9FDKZJobq7nMWxM4MphQIDAQABo0IwQDAP
BgNVHRMBAf8EBTADAQH/MA4GA1UdDwEB/wQEAwIBhjAdBgNVHQ4EFgQUTiJUIBiV
5uNu5g/6+rkS7QYXjzkwDQYJKoZIhvcNAQELBQADggEBAGBnKJRvDkhj6zHd6mcY
1Yl9PMWLSn/pvtsrF9+wX3N3KjITOYFnQoQj8kVnNeyIv/iPsGEMNKSuIEyExtv4
NeF22d+mQrvHRAiGfzZ0JFrabA0UWTW98kndth/Jsw1HKj2ZL7tcu7XUIOGZX1NG
Fdtom/DzMNU+MeKNhJ7jitralj41E6Vf8PlwUHBHQRFXGU7Aj64GxJUTFy8bJZ91
8rGOmaFvE7FBcf6IKshPECBV1/MUReXgRPTqh5Uykw7+U0b6LJ3/iyK5S9kJRaTe
pLiaWN0bfVKfjllDiIGknibVb63dDcY3fe0Dkhvld1927jyNxF1WW6LZZm6zNTfl
MrY=
-----END CERTIFICATE-----
)EOF";

static String maskKey(const String& s) {
  if (!s.length()) return "";
  if (s.length() <= 8) return "********";
  return s.substring(0,4) + "…" + s.substring(s.length()-4);
}

void powerStreamApiLoad() {
  ApiLock lk(pdMS_TO_TICKS(1000)); if(!lk.held) return;
  Preferences p; p.begin("psapi", true);
  gSn = p.getString("sn", "HW51ZEH49GB10829");
  gAccess = p.getString("access", "");
  gSecret = p.getString("secret", "");
  p.end();
  psApiState.configured = gSn.length() && gAccess.length() && gSecret.length();
}

bool powerStreamApiSave(const String& sn, const String& accessKey, const String& secretKey) {
  ApiLock lk(0); if(!lk.held) return false;
  String s=sn, a=accessKey, k=secretKey; s.trim(); a.trim(); k.trim();
  if (!s.length()) return false;
  if (a.length()) gAccess=a;
  if (k.length()) gSecret=k;
  gSn=s;
  Preferences p; p.begin("psapi", false);
  p.putString("sn", gSn);
  p.putString("access", gAccess);
  p.putString("secret", gSecret);
  p.end();
  psApiState.configured = gSn.length() && gAccess.length() && gSecret.length();
  return true;
}

bool powerStreamApiClear() {
  ApiLock lk(0); if(!lk.held) return false;
  Preferences p; p.begin("psapi", false); p.clear(); p.end();
  gAccess=""; gSecret=""; gSn="HW51ZEH49GB10829";
  psApiState = PowerStreamApiState();
  return true;
}
String powerStreamApiSerial(){ ApiLock lk(pdMS_TO_TICKS(50)); return lk.held?gSn:String(); }
String powerStreamApiAccessMasked(){ ApiLock lk(pdMS_TO_TICKS(50)); return lk.held?maskKey(gAccess):String(); }
bool powerStreamApiConfigured(){ ApiLock lk(pdMS_TO_TICKS(50)); return lk.held && psApiState.configured; }
PowerStreamApiState powerStreamApiStateSnapshot(){ ApiLock lk(pdMS_TO_TICKS(50)); return lk.held?psApiState:PowerStreamApiState(); }

static String hmac256(const String& msg, const String& key) {
  unsigned char out[32];
  const mbedtls_md_info_t* info = mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if (!info || mbedtls_md_hmac(info, (const unsigned char*)key.c_str(), key.length(),
      (const unsigned char*)msg.c_str(), msg.length(), out) != 0) return "";
  static const char hex[]="0123456789abcdef"; char buf[65];
  for(int i=0;i<32;i++){buf[i*2]=hex[out[i]>>4];buf[i*2+1]=hex[out[i]&15];} buf[64]=0;
  return String(buf);
}

static bool authHeaders(HTTPClient& http, const String& flattened, String& err) {
  time_t now=time(nullptr);
  if (now < 1700000000) { err="Systemzeit nicht synchronisiert (NTP erforderlich)"; return false; }
  String nonce=String(100000 + (esp_random()%900000));
  char tsBuf[24]; snprintf(tsBuf, sizeof(tsBuf), "%llu", (unsigned long long)((uint64_t)now * 1000ULL));
  String timestamp(tsBuf);
  String signBase = flattened.length() ? flattened + "&" : "";
  signBase += "accessKey="+gAccess+"&nonce="+nonce+"&timestamp="+timestamp;
  String sig=hmac256(signBase,gSecret);
  if(!sig.length()){err="HMAC-SHA256 fehlgeschlagen";return false;}
  http.addHeader("accessKey",gAccess); http.addHeader("nonce",nonce);
  http.addHeader("timestamp",timestamp); http.addHeader("sign",sig);
  return true;
}

class BoundedApiResponse : public StreamString {
 public:
  static constexpr size_t kMaxBytes = 8192;
  bool exceeded = false;
  size_t write(const uint8_t* bytes, size_t count) override {
    if (count > kMaxBytes - length()) { exceeded = true; return 0; }
    return StreamString::write(bytes, count);
  }
  size_t write(uint8_t byte) override { return write(&byte, 1); }
};

// Find an actual JSON member name, outside string values. Reject duplicates
// rather than silently accepting a nested or later conflicting field.
static bool findUniqueJsonMember(const String& json, const char* key, int depthWanted, int& valueAt) {
  const size_t keyLen=strlen(key);
  int depth=0; bool inString=false, escaped=false, found=false;
  bool started=false, ended=false; char containers[16]{};
  int stringStart=-1; valueAt=-1;
  for(int i=0;i<(int)json.length();++i){
    const char c=json[i];
    if(inString){
      if(escaped){escaped=false;continue;}
      if(c=='\\'){escaped=true;continue;}
      if(c=='"'){
        inString=false;
        int next=i+1;while(next<(int)json.length()&&isspace((unsigned char)json[next]))next++;
        if(next<(int)json.length()&&json[next]==':' &&
           (depthWanted<0||depth==depthWanted) &&
           (size_t)(i-stringStart-1)==keyLen &&
           strncmp(json.c_str()+stringStart+1,key,keyLen)==0){
          if(found)return false;
          found=true;valueAt=next+1;
        }
      }
      continue;
    }
    if(!started){if(isspace((unsigned char)c))continue;if(c!='{')return false;started=true;}
    if(ended){if(!isspace((unsigned char)c))return false;continue;}
    if(c=='"'){inString=true;stringStart=i;continue;}
    if(c=='{'||c=='['){if(depth==16)return false;containers[depth++]=c;}
    else if(c=='}'||c==']'){
      if(depth==0||containers[depth-1]!=(c=='}'?'{':'['))return false;
      if(--depth==0)ended=true;
    }
  }
  return found&&!inString&&ended&&depth==0;
}

static bool apiRequest(const String& method, const String& path, const String& query,
                       const String& body, const String& flattened, String& response, String& err) {
  if(method!="GET"){err="Cloud-Schreiben in dieser Diagnose-Firmware gesperrt";return false;}
  if(!powerStreamApiConfigured()){err="EcoFlow API noch nicht konfiguriert";return false;}
  if(!WiFi.isConnected()){err="WLAN nicht verbunden";return false;}
  // 9.36.7.15C: do not open a throw-away TCP socket before TLS.
  // The diagnostic probe itself consumed/fragmented scarce internal DRAM.
  gDnsOk.store(-1,std::memory_order_relaxed);
  gDnsIp.store(0,std::memory_order_relaxed);
  gTcp443Ok.store(-1,std::memory_order_relaxed);
  tlsInternalSnap(gTlsInternalFreePre,gTlsInternalLargestPre);

  WiFiClientSecure client;
  tlsMemSnap(gTlsHeapClient,gTlsLargestClient);
  // Fail closed: validate EcoFlow's TLS chain against bundled DigiCert trust anchors.
  // Never fall back to setInsecure() because API secrets are sent in request headers.
  client.setCACert(ECOFLOW_CA_BUNDLE);
  tlsMemSnap(gTlsHeapCa,gTlsLargestCa);
  HTTPClient http; http.setTimeout(12000);
  String url=String(API_BASE)+path+(query.length()?"?"+query:"");
  cloudDiagMark(CLOUD_DIAG_HTTP_BEGIN,gCloudTraceJobId.load());
  tlsMemSnap(gTlsHeapBeginPre,gTlsLargestBeginPre);
  if(!http.begin(client,url)){err="HTTPS-Verbindung konnte nicht initialisiert werden";return false;}
  tlsMemSnap(gTlsHeapBeginPost,gTlsLargestBeginPost);
  if(!authHeaders(http,flattened,err)){http.end();return false;}
  if(body.length()) http.addHeader("Content-Type","application/json;charset=UTF-8");
  int httpCode=-1;
  cloudDiagMark(CLOUD_DIAG_HTTP_GET,gCloudTraceJobId.load());
  tlsMemSnap(gTlsHeapGetPre,gTlsLargestGetPre);
  // Do not enter mbedTLS when fragmentation is already below the configured
  // receive-buffer requirement plus modest allocator/record overhead.
  // This is fail-closed and preserves the existing JK/BLE session.
  static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 10240;
  if(gTlsLargestGetPre.load(std::memory_order_relaxed) < TLS_GET_MIN_LARGEST8){
    err="TLS preflight: largest8 zu klein ("+String(gTlsLargestGetPre.load())+
        ", Minimum "+String(TLS_GET_MIN_LARGEST8)+")";
    http.end();
    return false;
  }
  if(method=="GET") httpCode=http.GET(); else if(method=="PUT") httpCode=http.PUT(body); else {err="Interner HTTP-Methodenfehler";http.end();return false;}
  tlsMemSnap(gTlsHeapGetPost,gTlsLargestGetPost);
  tlsInternalSnap(gTlsInternalFreePost,gTlsInternalLargestPost);
  cloudDiagMark(CLOUD_DIAG_HTTP_REPLY,gCloudTraceJobId.load(),httpCode);
  if(httpCode<0){
    // A failed GET has no HTTP response stream. Reading it would replace the
    // original transport error with HTTPClient's secondary stream error -4.
    const uint32_t freeAtGet=ESP.getFreeHeap();
    const uint32_t largestAtGet=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    const String transportReason=http.errorToString(httpCode);
    char tlsReason[96]={0};
    const int tlsCode=client.lastError(tlsReason,sizeof(tlsReason));
    const int wifiAtGet=(int)WiFi.status();
    { ApiLock dl(pdMS_TO_TICKS(50)); if(dl.held){psApiState.lastHttpCode=httpCode;psApiState.lastResponseBytes=0;} }
    http.end();
    err="EcoFlow HTTPS GET fehlgeschlagen (Code "+String(httpCode)+", "+transportReason+
        ", TLS "+String(tlsCode)+": "+String(tlsReason)+
        ", heap "+String(freeAtGet)+", largest8 "+String(largestAtGet)+
        ", WLAN "+String(wifiAtGet)+")";
    return false;
  }
  // Bound both declared and chunked/unknown-length replies before any large
  // String allocation. HTTPClient reports a short Stream write as an error.
  const int contentLength=http.getSize();
  if(contentLength>(int)BoundedApiResponse::kMaxBytes){
    { ApiLock dl(pdMS_TO_TICKS(50)); if(dl.held){psApiState.lastHttpCode=httpCode;psApiState.lastResponseBytes=0;} }
    err="EcoFlow API-Antwort zu gross (HTTP "+String(httpCode)+", Content-Length "+String(contentLength)+", Limit 8192)";
    http.end();return false;
  }
  BoundedApiResponse bounded;
  if(!bounded.reserve(contentLength>0 ? contentLength+1 : 512)){
    err="Zu wenig Speicher fuer EcoFlow API-Antwort";http.end();return false;
  }
  const int readResult=http.writeToStream(&bounded);
  response=static_cast<const String&>(bounded);
  cloudDiagMark(CLOUD_DIAG_BODY,gCloudTraceJobId.load(),httpCode,(int32_t)response.length());
  { ApiLock dl(pdMS_TO_TICKS(50)); if(dl.held){ psApiState.lastHttpCode=httpCode; psApiState.lastResponseBytes=(int)response.length(); } }
  http.end();
  if(bounded.exceeded){err="EcoFlow API-Antwort zu gross (HTTP "+String(httpCode)+", gelesen "+String(response.length())+", Limit 8192)";return false;}
  if(readResult<0){
    err="EcoFlow Transportfehler "+String(readResult)+" (HTTP "+String(httpCode)+", bytes "+String(response.length());
    if(contentLength>=0) err += "/"+String(contentLength);
    err += ")";
    if(response.length()) err += ": "+response.substring(0,220);
    return false;
  }
  if(httpCode<200 || httpCode>=300){err="EcoFlow HTTP "+String(httpCode)+": "+response.substring(0,220);return false;}
  // EcoFlow success code is exactly 0 (number or string). Reject any explicit non-zero code.
  int i=-1;
  if(!findUniqueJsonMember(response,"code",1,i)){err="EcoFlow API-Antwort ohne eindeutiges code-Feld: "+response.substring(0,260);return false;}
  while(i<(int)response.length() && isspace((unsigned char)response[i])) i++;
  bool quoted=(i<(int)response.length() && response[i]=='\"'); if(quoted) i++;
  bool neg=(i<(int)response.length() && response[i]=='-'); if(neg) i++;
  int j=i; while(j<(int)response.length() && isDigit(response[j])) j++;
  if(j==i){err="EcoFlow API-Antwort mit nichtnumerischem code-Feld: "+response.substring(0,260);return false;}
  String apiCode=response.substring(i,j);
  if(quoted){if(j>=(int)response.length()||response[j]!='"'){err="EcoFlow API-code ungültig";return false;}j++;}
  if(j<(int)response.length()&&!isspace((unsigned char)response[j])&&response[j]!=','&&response[j]!='}'){
    err="EcoFlow API-code ungültig";return false;
  }
  if(neg || apiCode != "0"){err="EcoFlow API meldet Fehler: "+response.substring(0,260);return false;}
  cloudDiagMark(CLOUD_DIAG_PARSED,gCloudTraceJobId.load(),httpCode,(int32_t)response.length(),true);
  return true;
}

static bool extractNumber(const String& json, const char* key, int& value) {
  int p=-1;if(!findUniqueJsonMember(json,key,-1,p))return false;
  while(p<(int)json.length() && isspace((unsigned char)json[p]))p++;
  const bool quoted=p<(int)json.length()&&json[p]=='"';if(quoted)p++;
  bool neg=false;if(p<(int)json.length()&&json[p]=='-'){neg=true;p++;}
  if(p>=(int)json.length()||!isDigit(json[p]))return false;
  int64_t v=0;while(p<(int)json.length()&&isDigit(json[p])){int digit=json[p]-'0';if(v>(INT64_MAX-digit)/10)return false;v=v*10+digit;p++;}
  if((!neg&&v>INT_MAX)||(neg&&v>(int64_t)INT_MAX+1))return false;
  if(quoted){if(p>=(int)json.length()||json[p]!='"')return false;p++;}
  if(p<(int)json.length()&&!isspace((unsigned char)json[p])&&json[p]!=','&&json[p]!='}')return false;
  value=(int)(neg?-v:v);return true;
}

bool powerStreamApiTest(String& message) {
  ApiLock txn(0); if(!txn.held){ message="EcoFlow API busy; parallel request rejected"; return false; }
  String resp,err;
  if(!apiRequest("GET","/iot-open/sign/device/list","","","",resp,err)){message=err;psApiState.lastOk=false;return false;}
  if(resp.indexOf(gSn)<0){message="API erreichbar, aber konfigurierte PowerStream-SN wurde in der Geräteliste nicht gefunden";psApiState.lastOk=false;return false;}
  message="EcoFlow API verbunden; PowerStream in Geräteliste gefunden"; psApiState.lastOk=true; psApiState.lastMessage=message; return true;
}

bool powerStreamApiReadLimits(int& upper, int& lower, String& message) {
  ApiLock txn(0); if(!txn.held){ message="EcoFlow API busy; parallel request rejected"; return false; }
  String resp,err,q="sn="+gSn;
  if(!apiRequest("GET","/iot-open/sign/device/quota/all",q,"",q,resp,err)){message=err;psApiState.lastOk=false;return false;}
  int u=-1,l=-1;
  // PowerStream GetAllQuotaResponse uses qualified member names such as
  // "20_1.upperLimit" and "20_1.lowerLimit". Keep a bare-name fallback
  // only for compatibility with older/alternate EcoFlow responses.
  bool haveU=extractNumber(resp,"20_1.upperLimit",u) || extractNumber(resp,"upperLimit",u);
  bool haveL=extractNumber(resp,"20_1.lowerLimit",l) || extractNumber(resp,"lowerLimit",l);
  if(!haveU||!haveL){
    message="quota/all erfolgreich, aber 20_1.upperLimit/lowerLimit fehlen"; psApiState.lastOk=false; return false;
  }
  PowerStreamApiState next=psApiState;
  next.upperLimit=u; next.lowerLimit=l;
  extractNumber(resp,"20_1.batSoc",next.batSoc);
  extractNumber(resp,"20_1.batInputVolt",next.batInputVolt);
  extractNumber(resp,"20_1.batInputCur",next.batInputCur);
  extractNumber(resp,"20_1.batTemp",next.batTemp);
  extractNumber(resp,"20_1.bpType",next.bpType);
  extractNumber(resp,"20_1.interfaceConnFlag",next.interfaceConnFlag);
  extractNumber(resp,"20_1.supplyPriority",next.supplyPriority);
  extractNumber(resp,"20_1.bmsReqChgVol",next.bmsReqChgVol);
  extractNumber(resp,"20_1.bmsReqChgAmp",next.bmsReqChgAmp);
  extractNumber(resp,"20_1.invOnOff",next.invOnOff);
  extractNumber(resp,"20_1.wifiRssi",next.wifiRssi);
  next.lastReadMs=millis(); next.lastOk=true; next.lastMessage="PowerStream quota/all gelesen";
  psApiState=next; upper=u; lower=l; message=next.lastMessage; return true;
}

bool powerStreamApiSetLimits(int, int, String& message) {
  // Read-only diagnostic build: direct callers cannot issue a Cloud PUT.
  message="Cloud-Schreiben in dieser Diagnose-Firmware gesperrt";
  return false;
}


// AUDIT20.4.5.9.13: dedicated cloud worker. AsyncWebServer must never perform
// blocking TLS/HTTP or the ~15 s device-propagation verification loop.
enum class CloudJobType:uint8_t{NONE,TEST,READ,SET};
static std::atomic<bool> gJobPending{false}, gJobRunning{false}, gJobReserved{false};
static std::atomic<uint32_t> gJobId{0}, gJobSeq{0};
static std::atomic<int> gJobUpper{-1}, gJobLower{-1};
static std::atomic<uint32_t> gCloudStackMinBytes{0}, gCloudHeapBefore{0}, gCloudLargestBefore{0};
static std::atomic<CloudJobType> gJobType{CloudJobType::NONE};
static StaticSemaphore_t gJobMutexBuf;
static SemaphoreHandle_t gJobMutex=xSemaphoreCreateMutexStatic(&gJobMutexBuf);
static String gJobMessage;
static bool gJobOk=false;
static void ensureJobMutex(){}
static void setJobResult(bool ok,const String&m){ensureJobMutex();if(gJobMutex&&xSemaphoreTake(gJobMutex,pdMS_TO_TICKS(100))==pdTRUE){gJobOk=ok;gJobMessage=m;xSemaphoreGive(gJobMutex);}}
static void runCloudJobOnLoopTask(){
  if(!gJobPending.exchange(false,std::memory_order_acq_rel)) return;
  gJobRunning=true;
  // Close WebSockets and reject reconnects while mbedTLS owns the scarce internal DRAM.
  webCloudQuiesceBegin();
  delay(20);
  gCloudHeapBefore=ESP.getFreeHeap();
  gCloudLargestBefore=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  cloudDiagMark(CLOUD_DIAG_WORKER,gJobId.load());
  String m; bool ok=false; int u=-1,l=-1; CloudJobType t=gJobType.load();
  if(t==CloudJobType::TEST) ok=powerStreamApiTest(m);
  else if(t==CloudJobType::READ){ ok=powerStreamApiReadLimits(u,l,m); if(ok){gJobUpper=u;gJobLower=l;} }
  else if(t==CloudJobType::SET){ m="Cloud-Schreiben in dieser Diagnose-Firmware gesperrt"; ok=false; }
  gCloudStackMinBytes=(uint32_t)uxTaskGetStackHighWaterMark(nullptr);
  setJobResult(ok,m);
  PowerStreamApiState endState=powerStreamApiStateSnapshot();
  cloudDiagMark(CLOUD_DIAG_FINISHED,gJobId.load(),endState.lastHttpCode,endState.lastResponseBytes,ok);
  gJobRunning=false; gJobReserved=false; heavyOpRelease(HeavyOpOwner::POWERSTREAM_CLOUD);
  webCloudQuiesceEnd();
}
void powerStreamApiLoopTick(){ if(gJobPending.load(std::memory_order_acquire)) runCloudJobOnLoopTask(); }
static bool queueJob(CloudJobType t,int u,int l,uint32_t &id){bool expected=false;if(!gJobReserved.compare_exchange_strong(expected,true,std::memory_order_acq_rel))return false;if(!heavyOpTryAcquire(HeavyOpOwner::POWERSTREAM_CLOUD)){gJobReserved.store(false,std::memory_order_release);return false;}uint32_t n=gJobSeq.fetch_add(1)+1;gJobType=t;gJobUpper=u;gJobLower=l;setJobResult(false,"queued");gJobId=n;gCloudTraceJobId=n;cloudDiagMark(CLOUD_DIAG_QUEUED,n);gJobPending=true;id=n;return true;}
bool powerStreamApiQueueTest(uint32_t&id){return queueJob(CloudJobType::TEST,-1,-1,id);}
bool powerStreamApiQueueRead(uint32_t&id){return queueJob(CloudJobType::READ,-1,-1,id);}
bool powerStreamApiQueueSetLimits(int,int,uint32_t&){return false;}
String powerStreamApiJobStatusJson(){ensureJobMutex();String m;bool ok=false;if(gJobMutex&&xSemaphoreTake(gJobMutex,pdMS_TO_TICKS(50))==pdTRUE){m=gJobMessage;ok=gJobOk;xSemaphoreGive(gJobMutex);}m.replace("\\","\\\\");m.replace("\"","\\\"");const bool running=gJobRunning.load(),pending=gJobPending.load(),reserved=gJobReserved.load();PowerStreamApiState st=powerStreamApiStateSnapshot();return String("{\"ok\":true,\"job_id\":")+String(gJobId.load())+",\"pending\":"+(pending?"true":"false")+",\"running\":"+(running?"true":"false")+",\"done\":"+((!reserved&&gJobId.load())?"true":"false")+",\"result_ok\":"+(ok?"true":"false")+",\"upper\":"+String(gJobUpper.load())+",\"lower\":"+String(gJobLower.load())+",\"bat_soc\":"+String(st.batSoc)+",\"bat_input_volt_raw\":"+String(st.batInputVolt)+",\"bat_input_cur_raw\":"+String(st.batInputCur)+",\"bat_temp_raw\":"+String(st.batTemp)+",\"bp_type\":"+String(st.bpType)+",\"interface_conn_flag\":"+String(st.interfaceConnFlag)+",\"supply_priority\":"+String(st.supplyPriority)+",\"bms_req_chg_vol\":"+String(st.bmsReqChgVol)+",\"bms_req_chg_amp\":"+String(st.bmsReqChgAmp)+",\"inv_on_off\":"+String(st.invOnOff)+",\"wifi_rssi\":"+String(st.wifiRssi)+",\"last_http_code\":"+String(st.lastHttpCode)+",\"last_response_bytes\":"+String(st.lastResponseBytes)+",\"cloud_stack_min_bytes\":"+String(gCloudStackMinBytes.load())+",\"heap_before\":"+String(gCloudHeapBefore.load())+",\"largest_before\":"+String(gCloudLargestBefore.load())+",\"tls_heap_client\":"+String(gTlsHeapClient.load())+",\"tls_largest_client\":"+String(gTlsLargestClient.load())+",\"tls_heap_ca\":"+String(gTlsHeapCa.load())+",\"tls_largest_ca\":"+String(gTlsLargestCa.load())+",\"tls_heap_begin_pre\":"+String(gTlsHeapBeginPre.load())+",\"tls_largest_begin_pre\":"+String(gTlsLargestBeginPre.load())+",\"tls_heap_begin_post\":"+String(gTlsHeapBeginPost.load())+",\"tls_largest_begin_post\":"+String(gTlsLargestBeginPost.load())+",\"tls_heap_get_pre\":"+String(gTlsHeapGetPre.load())+",\"tls_largest_get_pre\":"+String(gTlsLargestGetPre.load())+",\"tls_heap_get_post\":"+String(gTlsHeapGetPost.load())+",\"tls_largest_get_post\":"+String(gTlsLargestGetPost.load())+",\"dns_ok\":"+String(gDnsOk.load())+",\"dns_ip_u32\":"+String(gDnsIp.load())+",\"tcp_443_ok\":"+String(gTcp443Ok.load())+",\"internal_free_pre\":"+String(gTlsInternalFreePre.load())+",\"internal_largest_pre\":"+String(gTlsInternalLargestPre.load())+",\"internal_free_post\":"+String(gTlsInternalFreePost.load())+",\"internal_largest_post\":"+String(gTlsInternalLargestPost.load())+",\"heavy_owner\":\""+String(heavyOpOwnerName())+"\",\"heavy_age_ms\":"+String(heavyOpAgeMs())+",\"heavy_acquires\":"+String(heavyOpAcquireCount())+",\"heavy_release_mismatch\":"+String(heavyOpReleaseMismatchCount())+",\"message\":\""+m+"\"}";}
