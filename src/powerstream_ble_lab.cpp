#include "powerstream_ble_lab.h"
#include "jk_ble_proxy.h"
#include "bms.h"
#include "low_soc_guard.h"
#include "resource_gate.h"
#include "ps_probe_trace.h"
#include <Preferences.h>
#include <NimBLEDevice.h>
#include <WiFi.h>
#include <MD5Builder.h>
#include "mbedtls/aes.h"
#include <esp_heap_caps.h>
#include <atomic>

// AUDIT20.4.5.9.11 WRAP-APSTA-CROSSCORE-AUDIT-HARDENED
// One-shot/manual PowerStream BLE control only. No scanning, no periodic reconnect,
// no SOC automation. All synchronous GATT work runs in a dedicated low-priority task
// so WiFi/Web/CAN/RS485 main-loop service cannot be blocked by connect/auth waits.

static const char* SVC_UUID="00000001-0000-1000-8000-00805f9b34fb";
static const char* WRITE_UUID="00000002-0000-1000-8000-00805f9b34fb";
static const char* NOTIFY_UUID="00000003-0000-1000-8000-00805f9b34fb";
// 9.36.7.4: pre-task admission and in-worker reserve are deliberately separate.
// The 6144-byte FreeRTOS worker stack is allocated from heap. Requiring the old
// 18k again after task creation was contradictory and could self-block.
static constexpr uint32_t ADMIT_FREE_HEAP=18000;
static constexpr uint32_t ADMIT_LARGEST8=9000;
static constexpr uint32_t RUNTIME_FREE_HEAP=9000;
static constexpr uint32_t RUNTIME_LARGEST8=6000;
static constexpr uint32_t CONNECT_TIMEOUT_MS=1800;
static constexpr uint32_t AUTH_TIMEOUT_MS=10000;
static constexpr uint32_t VERIFY_TIMEOUT_MS=6000;
static constexpr uint32_t WIFI_STABLE_MS=5000;
static constexpr uint32_t COOLDOWN_MS=30000;
static constexpr uint32_t WORKER_STACK=6144;
static constexpr uint32_t PHYS_OBS_MS=3000;
static constexpr float PHYS_DISCHARGE_A=-0.50f; // diagnostic threshold only; not a safety guarantee

enum class PsState:uint8_t{OFF,IDLE,QUEUED,CONNECTING,DISCOVERING,AUTHENTICATING,SENDING,VERIFYING,CONFIRMED,FAILED,COOLDOWN};
static const char* stateName(PsState s){switch(s){case PsState::OFF:return"OFF";case PsState::IDLE:return"IDLE";case PsState::QUEUED:return"QUEUED";case PsState::CONNECTING:return"CONNECTING";case PsState::DISCOVERING:return"DISCOVERING";case PsState::AUTHENTICATING:return"AUTHENTICATING";case PsState::SENDING:return"SENDING";case PsState::VERIFYING:return"VERIFYING";case PsState::CONFIRMED:return"CONFIRMED";case PsState::FAILED:return"FAILED";case PsState::COOLDOWN:return"COOLDOWN";}return"?";}

static String sMac,sSn,sUid;
static std::atomic<int> sAddrType{0}; // 0 public, 1 random
static std::atomic<bool> sEnabled{false};
static std::atomic<bool> sConfigured{false};
static std::atomic<bool> sConfigGate{false};
static std::atomic<PsState> sState{PsState::OFF};
static std::atomic<bool> sCancel{false},sWorkerRunning{false},sAuthOk{false},sAuthFailed{false},sLinkUp{false};
// 9.36.6: stage diagnostics for the manual PowerStream BLE path. These contain
// no UID/key material; they only show how far the one-shot transaction got.
static std::atomic<bool> sDiagConnected{false},sDiagService{false},sDiagWrite{false},sDiagNotify{false},sDiagSubscribed{false},sDiagAuthStatusSent{false},sDiagAuthSent{false};
static std::atomic<int> sAuthResponse{-1};
// Acknowledge only metadata from the auth-status reply; never expose its payload.
static std::atomic<bool> sAuthStatusReplySeen{false};
static std::atomic<int> sAuthStatusReplyVersion{-1},sAuthReplyVersion{-1};
static std::atomic<uint32_t> sAuthStatusReplyPayloadLen{0};
static std::atomic<int> sLastPeerDisconnectReason{-1};
// Scalar-only C-probe diagnostics. Never record authentication payloads.
static std::atomic<uint32_t> sAuthStatusLen{0},sAuthFrameLen{0},sAuthMtu{0};
static std::atomic<bool> sAuthLinkBeforeWrite{false},sAuthLinkAfterWrite{false};
static std::atomic<int> sAuthDisconnectAtFailure{-1};
static std::atomic<int> sSupply{-1},sRequested{-1};
// 9.36.7.10: diagnostic transaction depth. FULL preserves the existing command path; AUTH_ONLY stops after verified auth.
enum class PsTxnDepth:uint8_t{FULL=0,AUTH_ONLY=1};
static std::atomic<PsTxnDepth> sTxnDepth{PsTxnDepth::FULL};
static std::atomic<uint32_t> sAuthOnlyOk{0},sAuthOnlyFail{0};
static std::atomic<uint32_t> sLastHeartbeat{0},sHeartbeatGeneration{0},sCommandEpoch{0},sLastHeartbeatEpoch{0},sTxOk{0},sTxFail{0},sLastOpMs{0},sCooldownUntil{0};
enum class EnforceObs:uint8_t{IDLE,REQUESTED,ACKNOWLEDGED,OBSERVING,OBSERVED_NO_DISCHARGE,OBSERVED_DISCHARGE,TELEMETRY_INVALID};
static std::atomic<EnforceObs> sEnforceObs{EnforceObs::IDLE};
static std::atomic<int32_t> sObsMinCurrentmA{0},sObsMaxCurrentmA{0};
static std::atomic<uint32_t> sObsSamples{0};
static const char* obsName(EnforceObs s){switch(s){case EnforceObs::IDLE:return"IDLE";case EnforceObs::REQUESTED:return"REQUESTED";case EnforceObs::ACKNOWLEDGED:return"ACKNOWLEDGED";case EnforceObs::OBSERVING:return"OBSERVING";case EnforceObs::OBSERVED_NO_DISCHARGE:return"OBSERVED_NO_DISCHARGE";case EnforceObs::OBSERVED_DISCHARGE:return"OBSERVED_DISCHARGE";case EnforceObs::TELEMETRY_INVALID:return"TELEMETRY_INVALID";}return"?";}
static std::atomic<uint32_t> sHeapPre{0},sHeapPost{0},sLargestPre{0},sLargestPost{0},sCleanupCount{0};
// 9.36.7.4: bounded scalar memory telemetry; no credentials/payloads.
static std::atomic<uint32_t> sMemRequestFree{0},sMemRequestLargest{0},sMemWorkerFree{0},sMemWorkerLargest{0};
// Capture the values used by the first failing runtime guard, across cleanup.
// Stage 0 means no guard failed in this boot; 1..6 identify the check site.
static std::atomic<uint32_t> sRuntimeGuardFree{0},sRuntimeGuardLargest8{0};
static std::atomic<bool> sRuntimeGuardIntegrity{true};
static std::atomic<uint8_t> sRuntimeGuardStage{0};
static std::atomic<uint32_t> sMemAuxFree{0},sMemAuxLargest{0},sMemClientFree{0},sMemClientLargest{0};
static std::atomic<uint32_t> sMemConnectFree{0},sMemConnectLargest{0},sMemGattFree{0},sMemGattLargest{0};
static std::atomic<uint32_t> sMemAuthFree{0},sMemAuthLargest{0},sMemCommandFree{0},sMemCommandLargest{0};
static std::atomic<int32_t> sCleanupDeltaFree{0},sCleanupDeltaLargest{0};
static std::atomic<uint32_t> sWorkerStackMinBytes{0},sWorkerStartedAt{0};
static std::atomic<uint32_t> sWifiStableSince{0};
static portMUX_TYPE sMux=portMUX_INITIALIZER_UNLOCKED;
static char sLastError[128]={0};
static NimBLEClient* sClient=nullptr;
static NimBLERemoteCharacteristic* sWrite=nullptr;
static NimBLERemoteCharacteristic* sNotify=nullptr;
static uint8_t sKey[16],sIv[16];

static void setError(const char* x){
  portENTER_CRITICAL(&sMux);
  if(!x)x=""; size_t n=strnlen(x,sizeof(sLastError)-1); memcpy(sLastError,x,n); sLastError[n]='\0';
  portEXIT_CRITICAL(&sMux);
}
static String getError(){char tmp[sizeof(sLastError)];portENTER_CRITICAL(&sMux);memcpy(tmp,sLastError,sizeof(tmp));portEXIT_CRITICAL(&sMux);tmp[sizeof(tmp)-1]='\0';return String(tmp);}
static bool heapIntegrity(){return heap_caps_check_integrity_all(false);}
static bool heapAdmitSafe(){return ESP.getFreeHeap()>=ADMIT_FREE_HEAP && heap_caps_get_largest_free_block(MALLOC_CAP_8BIT)>=ADMIT_LARGEST8 && heapIntegrity();}
static const char* runtimeGuardStageName(uint8_t stage){
  switch(stage){case 1:return "worker_start";case 2:return "slot_reserved";case 3:return "client_alloc";case 4:return "connect";case 5:return "gatt";case 6:return "before_command";default:return "none";}
}
static bool runtimeGuard(uint8_t stage){
  const uint32_t freeHeap=ESP.getFreeHeap();
  const uint32_t largest8=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  const bool integrity=heapIntegrity();
  const bool safe=freeHeap>=RUNTIME_FREE_HEAP && largest8>=RUNTIME_LARGEST8 && integrity;
  if(!safe){
    sRuntimeGuardFree=freeHeap;
    sRuntimeGuardLargest8=largest8;
    sRuntimeGuardIntegrity=integrity;
    sRuntimeGuardStage=stage;
  }
  return safe;
}
static inline void memSnap(std::atomic<uint32_t>&f,std::atomic<uint32_t>&l){f=ESP.getFreeHeap();l=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);}
static void md5raw(const uint8_t*d,size_t n,uint8_t out[16]){MD5Builder b;b.begin();b.add((uint8_t*)d,n);b.calculate();b.getBytes(out);}
static void deriveCrypto(){md5raw((const uint8_t*)sSn.c_str(),sSn.length(),sKey);String r;for(int i=(int)sSn.length()-1;i>=0;--i)r+=sSn[(unsigned)i];md5raw((const uint8_t*)r.c_str(),r.length(),sIv);}
static void aes(bool enc,const uint8_t*in,uint8_t*out,size_t len){mbedtls_aes_context a;mbedtls_aes_init(&a);uint8_t iv[16];memcpy(iv,sIv,16);if(enc){mbedtls_aes_setkey_enc(&a,sKey,128);mbedtls_aes_crypt_cbc(&a,MBEDTLS_AES_ENCRYPT,len,iv,in,out);}else{mbedtls_aes_setkey_dec(&a,sKey,128);mbedtls_aes_crypt_cbc(&a,MBEDTLS_AES_DECRYPT,len,iv,in,out);}mbedtls_aes_free(&a);}
static uint8_t crc8(const uint8_t*d,size_t n){uint8_t c=0;for(size_t i=0;i<n;i++){c^=d[i];for(int b=0;b<8;b++)c=(c&0x80)?(uint8_t)((c<<1)^0x07):(uint8_t)(c<<1);}return c;}
static uint16_t crc16(const uint8_t*d,size_t n){uint16_t c=0;for(size_t i=0;i<n;i++){c^=d[i];for(int b=0;b<8;b++)c=(c&1)?(uint16_t)((c>>1)^0xA001):(uint16_t)(c>>1);}return c;}
static size_t packet(uint8_t*o,uint8_t src,uint8_t dst,uint8_t cs,uint8_t ci,const uint8_t*pl,size_t pn,uint8_t ver,uint8_t dsrc,uint8_t ddst){size_t i=0;o[i++]=0xAA;o[i++]=ver;o[i++]=pn&0xff;o[i++]=(pn>>8)&0xff;o[i++]=crc8(o,4);o[i++]=0x0D;for(int k=0;k<6;k++)o[i++]=0;o[i++]=src;o[i++]=dst;if(ver>=3){o[i++]=dsrc;o[i++]=ddst;}o[i++]=cs;o[i++]=ci;if(pn){memcpy(o+i,pl,pn);i+=pn;}uint16_t c=crc16(o,i);o[i++]=c&0xff;o[i++]=c>>8;return i;}
static size_t encrypt(const uint8_t*p,size_t pn,uint8_t*out){if(pn<5)return 0;memcpy(out,p,5);size_t bl=pn-5,pad=((bl+15)/16)*16;uint8_t buf[128]={0};if(pad>sizeof(buf))return 0;memcpy(buf,p+5,bl);aes(true,buf,out+5,pad);return 5+pad;}
static size_t varint(uint32_t n,uint8_t*o){size_t i=0;do{uint8_t b=n&0x7f;n>>=7;o[i++]=n?(b|0x80):b;}while(n);return i;}
static size_t authStatus(uint8_t*out){uint8_t p[64];return encrypt(p,packet(p,0x21,0x35,0x35,0x89,nullptr,0,3,1,1),out);}
static size_t autoAuth(uint8_t*out){uint8_t m[16];String x=sUid+sSn;md5raw((const uint8_t*)x.c_str(),x.length(),m);const char*H="0123456789ABCDEF";uint8_t hp[32];for(int i=0;i<16;i++){hp[2*i]=H[m[i]>>4];hp[2*i+1]=H[m[i]&15];}uint8_t p[80];return encrypt(p,packet(p,0x21,0x35,0x35,0x86,hp,32,3,1,1),out);}
static size_t supplyFrame(uint8_t*out,int mode){uint8_t pl[8];pl[0]=0x08;size_t pn=1+varint((uint32_t)mode,pl+1);uint8_t p[64];return encrypt(p,packet(p,0x21,0x35,0x14,0x82,pl,pn,0x13,0,0),out);}
static uint64_t pbv(const uint8_t*d,size_t len,size_t&i){uint64_t v=0;int sh=0;while(i<len){uint8_t b=d[i++];v|=(uint64_t)(b&0x7f)<<sh;if(!(b&0x80))break;sh+=7;if(sh>63)break;}return v;}
static int field50(const uint8_t*d,size_t len){size_t i=0;while(i<len){uint64_t t=pbv(d,len,i);uint32_t fn=t>>3,wt=t&7;if(wt==0){uint64_t v=pbv(d,len,i);if(fn==50)return(int)v;}else if(wt==1){if(i+8>len)return-1;i+=8;}else if(wt==2){uint64_t l=pbv(d,len,i);if(l>len-i)return-1;i+=(size_t)l;}else if(wt==5){if(i+4>len)return-1;i+=4;}else return-1;}return-1;}

// Shared-BLE hardening: mirror the proven JK proxy rule: NimBLE host callbacks
// only copy bounded data into a fixed queue. Crypto/protobuf parsing runs in
// the PS worker task, never in the NimBLE host callback.
static constexpr size_t PS_NOTIFY_MAX=244;
static constexpr uint8_t PS_NOTIFY_QDEPTH=4;
struct PsNotifyPacket { uint16_t len; uint32_t rxAt; uint32_t commandEpoch; uint8_t data[PS_NOTIFY_MAX]; };
static PsNotifyPacket sNq[PS_NOTIFY_QDEPTH];
static uint8_t sNqHead=0,sNqTail=0,sNqCount=0;
static std::atomic<uint32_t> sNqDrops{0};
static portMUX_TYPE sNqMux=portMUX_INITIALIZER_UNLOCKED;
static void clearNotifyQueue(){portENTER_CRITICAL(&sNqMux);sNqHead=sNqTail=sNqCount=0;portEXIT_CRITICAL(&sNqMux);}
static void notifyCb(NimBLERemoteCharacteristic*,uint8_t*data,size_t len,bool){
  if(!data||!len||len>PS_NOTIFY_MAX){sNqDrops++;return;}
  portENTER_CRITICAL(&sNqMux);
  if(sNqCount>=PS_NOTIFY_QDEPTH){sNqDrops++;portEXIT_CRITICAL(&sNqMux);return;}
  PsNotifyPacket& p=sNq[sNqHead];p.len=(uint16_t)len;p.rxAt=millis();p.commandEpoch=sCommandEpoch.load(std::memory_order_acquire);memcpy(p.data,data,len);
  sNqHead=(uint8_t)((sNqHead+1U)%PS_NOTIFY_QDEPTH);++sNqCount;
  portEXIT_CRITICAL(&sNqMux);
}
static bool takeNotify(PsNotifyPacket& out){bool ok=false;portENTER_CRITICAL(&sNqMux);if(sNqCount){out=sNq[sNqTail];sNqTail=(uint8_t)((sNqTail+1U)%PS_NOTIFY_QDEPTH);--sNqCount;ok=true;}portEXIT_CRITICAL(&sNqMux);return ok;}
static void processNotifyFrame(const uint8_t*data,size_t len,uint32_t rxAt,uint32_t packetEpoch){
  if(len<21||data[0]!=0xAA||sCancel.load())return;
  uint8_t ver=data[1];uint16_t pay=data[2]|(data[3]<<8);size_t bl=len-5,al=bl-(bl%16);if(!al||al>512)return;
  // Validate the plaintext header CRC before spending crypto work. BLE already has
  // link-layer integrity, but protocol-level confirmation must not trust a corrupt
  // application frame.
  if(data[4]!=crc8(data,4))return;
  uint8_t dec[512];aes(false,data+5,dec,al);if(al<13)return;
  const size_t hdr=(ver>=3)?18U:16U;
  const size_t expected=hdr+(size_t)pay+2U;
  if(expected<7U || expected>5U+al || expected>517U)return;
  uint8_t plain[517];memcpy(plain,data,5);memcpy(plain+5,dec,expected-5);
  const uint16_t gotCrc=(uint16_t)plain[expected-2] | ((uint16_t)plain[expected-1]<<8);
  if(crc16(plain,expected-2)!=gotCrc)return;
  uint8_t src=dec[7],cs,ci;size_t po;if(ver>=3){cs=dec[11];ci=dec[12];po=13;}else{cs=dec[9];ci=dec[10];po=11;}
  if(src==0x35&&cs==0x35&&ci==0x89){sAuthStatusReplySeen=true;sAuthStatusReplyVersion=ver;sAuthStatusReplyPayloadLen=pay;return;}
  if(src==0x35&&cs==0x35&&ci==0x86){
    sAuthReplyVersion=ver;
    if(pay>=1&&po<al){sAuthResponse=(int)dec[po];if(dec[po]==0){sAuthOk=true;sAuthFailed=false;}else{sAuthFailed=true;}}
    else{sAuthResponse=-2;sAuthFailed=true;}
    return;
  }
  if(src==0x35&&cs==0x14&&ci==0x01){size_t avail=al>po?al-po:0,n=pay<avail?pay:avail;if(!n)return;uint8_t pl[512];memcpy(pl,dec+po,n);uint8_t x=dec[1];if(x)for(size_t k=0;k<n;k++)pl[k]^=x;int v=field50(pl,n);if(v==0||v==1){sSupply=v;sLastHeartbeat=rxAt;sLastHeartbeatEpoch=packetEpoch;sHeartbeatGeneration.fetch_add(1,std::memory_order_release);}}
}
static void pumpNotify(){PsNotifyPacket p;while(takeNotify(p))processNotifyFrame(p.data,p.len,p.rxAt,p.commandEpoch);}
class PsCB:public NimBLEClientCallbacks{void onConnect(NimBLEClient*)override{sLinkUp=true;}void onDisconnect(NimBLEClient*,int reason)override{sLastPeerDisconnectReason=reason;sLinkUp=false;sAuthOk=false;}};
static PsCB sCallbacks;

static void cleanupClient(){
  // Keep the dedicated PowerStream client object for reuse. NimBLE-Arduino 2.5.1
  // explicitly recommends retaining a client when reconnecting to the same peer
  // frequently: cached attributes avoid repeated discovery and reduce heap churn.
  // The client is DISCONNECTED before the shared second connection slot is released.
  if(sClient && sClient->isConnected()){
    sClient->disconnect();
    const uint32_t t0=millis();
    while(sClient->isConnected() && millis()-t0<1200U){
      vTaskDelay(pdMS_TO_TICKS(20));
    }
    // If the graceful disconnect did not complete, deleteClient() is the documented
    // hard cleanup path: it stops an active/connecting client before deletion.
    if(sClient->isConnected()){
      NimBLEDevice::deleteClient(sClient);
      sClient=nullptr;
    }
  }
  sWrite=nullptr;sNotify=nullptr;
  sLinkUp=false;sAuthOk=false;clearNotifyQueue();
  sCleanupCount++;
  sHeapPost=ESP.getFreeHeap();
  sLargestPost=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  sCleanupDeltaFree=sHeapPre.load()?(int32_t)sHeapPost.load()-(int32_t)sHeapPre.load():0;
  sCleanupDeltaLargest=sLargestPre.load()?(int32_t)sLargestPost.load()-(int32_t)sLargestPre.load():0;
}
static bool wifiStaEnabled(){
  const wifi_mode_t m=WiFi.getMode();
  return m==WIFI_STA || m==WIFI_AP_STA;
}
static bool coreHealthy(){
  // Fail closed on pending BLE ownership transitions and require fresh validated
  // RS485 BMS telemetry. PowerStream BLE safety must not depend on a physical JK-BLE link.
  if(jkBleProxyEventsPending()) return false;
  if(!bmsTelemetryValidForCan()) return false;
  if(jkBleProxyAuxReserved() && !jkBleProxyAuxSlotReady()) return false;
  if(wifiStaEnabled() && WiFi.status()!=WL_CONNECTED) return false;
  return true;
}
static bool cancelled(){return sCancel.load()||!sEnabled||!coreHealthy();}
static bool waitFlag(std::atomic<bool>&flag,uint32_t timeout){uint32_t t=millis();while(!flag.load()&&!sAuthFailed.load()&&!cancelled()&&millis()-t<timeout){pumpNotify();vTaskDelay(pdMS_TO_TICKS(20));}pumpNotify();return flag.load()&&!cancelled();}
static bool waitSupplyFresh(int mode,uint32_t generationBefore,uint32_t commandEpoch,uint32_t timeout){
  const uint32_t t=millis();
  while(!cancelled()&&millis()-t<timeout){
    pumpNotify();
    const uint32_t g=sHeartbeatGeneration.load(std::memory_order_acquire);
    // Callback-stamped command epoch is the primary freshness barrier. A packet
    // received before writeValue() returned carries the previous epoch even when
    // millis() has the same 1-ms value, so it cannot acknowledge this command.
    if(g!=generationBefore && sSupply.load()==mode && sLastHeartbeatEpoch.load()==commandEpoch)return true;
    vTaskDelay(pdMS_TO_TICKS(25));
  }
  pumpNotify();
  const uint32_t g=sHeartbeatGeneration.load(std::memory_order_acquire);
  return !cancelled() && g!=generationBefore && sSupply.load()==mode && sLastHeartbeatEpoch.load()==commandEpoch;
}
static void observePhysicalAfterAck(int mode){
  sObsSamples=0;sObsMinCurrentmA=0;sObsMaxCurrentmA=0;
  if(mode!=1){sEnforceObs=EnforceObs::ACKNOWLEDGED;return;} // Supply mode has no no-discharge claim.
  sEnforceObs=EnforceObs::OBSERVING;
  const uint32_t t0=millis();bool first=true;bool invalid=false;bool discharge=false;
  int32_t minmA=0,maxmA=0;uint32_t samples=0;
  uint32_t lastFrame=bmsSafetySnapshotAtomic().okStatusFrames;
  while(!cancelled() && millis()-t0<PHYS_OBS_MS){
    pumpNotify();
    const BmsSafetySnapshot bs=bmsSafetySnapshotAtomic();
    if(!bs.valid){invalid=true;break;}
    // Count only a newly validated JK status frame. Re-reading the same cached
    // current value every 100 ms must never masquerade as 30 independent samples.
    if(bs.okStatusFrames!=lastFrame){
      lastFrame=bs.okStatusFrames; const int32_t mA=bs.currentMilliA;
      if(first){minmA=maxmA=mA;first=false;}else{if(mA<minmA)minmA=mA;if(mA>maxmA)maxmA=mA;}
      ++samples; if(mA<(int32_t)lroundf(PHYS_DISCHARGE_A*1000.0f))discharge=true;
    }
    vTaskDelay(pdMS_TO_TICKS(50));
  }
  sObsSamples=samples;sObsMinCurrentmA=minmA;sObsMaxCurrentmA=maxmA;
  if(invalid||cancelled()||samples<2)sEnforceObs=EnforceObs::TELEMETRY_INVALID;
  else if(discharge)sEnforceObs=EnforceObs::OBSERVED_DISCHARGE;
  else sEnforceObs=EnforceObs::OBSERVED_NO_DISCHARGE;
}

static bool validMac(const String& m);
static bool saneToken(const String& x,size_t lo,size_t hi);

static void worker(void*){
  memSnap(sMemWorkerFree,sMemWorkerLargest);
  sRuntimeGuardStage=0;sRuntimeGuardFree=0;sRuntimeGuardLargest8=0;sRuntimeGuardIntegrity=true;
  psProbeTraceMark(PS_PROBE_WORKER);
  const uint32_t started=millis();sWorkerStartedAt=started;const int mode=sRequested.load();bool ok=false;bool auxReserved=false;
  // Reset attempt-specific fields before any admission or reservation can fail.
  sDiagConnected=false;sDiagService=false;sDiagWrite=false;sDiagNotify=false;sDiagSubscribed=false;sDiagAuthStatusSent=false;sDiagAuthSent=false;sAuthResponse=-1;sLastPeerDisconnectReason=-1;
  sAuthStatusReplySeen=false;sAuthStatusReplyVersion=-1;sAuthReplyVersion=-1;sAuthStatusReplyPayloadLen=0;
  sAuthStatusLen=0;sAuthFrameLen=0;sAuthMtu=0;sAuthLinkBeforeWrite=false;sAuthLinkAfterWrite=false;sAuthDisconnectAtFailure=-1;
  sHeapPre=0;sLargestPre=0;sCleanupDeltaFree=0;sCleanupDeltaLargest=0;
  sMemAuxFree=0;sMemAuxLargest=0;sMemClientFree=0;sMemClientLargest=0;sMemConnectFree=0;sMemConnectLargest=0;sMemGattFree=0;sMemGattLargest=0;sMemAuthFree=0;sMemAuthLargest=0;sMemCommandFree=0;sMemCommandLargest=0;
  do{
    if(cancelled()){setError("cancelled");break;}
    if(!jkBleProxyInitialized()){setError("JK/NimBLE not initialized");break;}
    if(!runtimeGuard(1)){setError("runtime heap guard at worker start");break;}
    psProbeTraceMark(PS_PROBE_SLOT_REQUEST);
    if(!jkBleProxyReserveAuxConnection()){setError("shared BLE slot unavailable");break;}
    psProbeTraceMark(PS_PROBE_SLOT_GRANTED);
    auxReserved=true;memSnap(sMemAuxFree,sMemAuxLargest);
    // Give any in-flight JK-app connection callback one scheduler turn to publish.
    vTaskDelay(pdMS_TO_TICKS(50));
    if(!jkBleProxyAuxSlotReady()){setError("shared BLE slot race/core link changed");break;}
    // Reserving the slot can coincide with advertising teardown and transient
    // allocations. Check the actual post-reservation heap before createClient().
    if(!runtimeGuard(2)){setError("runtime heap guard after BLE slot reservation");break;}
    psProbeTraceMark(PS_PROBE_CLIENT);
    sHeapPre=ESP.getFreeHeap();sLargestPre=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
    clearNotifyQueue();deriveCrypto();
    sState=PsState::CONNECTING;
    NimBLEAddress a(sMac.c_str(),sAddrType?BLE_ADDR_RANDOM:BLE_ADDR_PUBLIC);
    if(!sClient){
      sClient=NimBLEDevice::createClient(a);memSnap(sMemClientFree,sMemClientLargest);
      if(!sClient){setError("createClient failed");break;}
      if(!runtimeGuard(3)){
        // This client never connected, so retaining it cannot improve reuse.
        NimBLEDevice::deleteClient(sClient);sClient=nullptr;
        setError("runtime heap guard after client alloc");break;
      }
      sClient->setClientCallbacks(&sCallbacks,false);
      sClient->setConnectTimeout(CONNECT_TIMEOUT_MS);
      sClient->setConnectRetries(0);
    }else if(!sClient->setPeerAddress(a)){setError("setPeerAddress failed");break;}
    // deleteAttributes=false intentionally reuses the cached PowerStream GATT database.
    // Exchange MTU so the auth frame can use one Write Without Response.
    psProbeTraceMark(PS_PROBE_CONNECT);
    if(!sClient->connect(a,false,false,true)){setError("connect failed");break;}sLinkUp=true;sDiagConnected=true;memSnap(sMemConnectFree,sMemConnectLargest);if(!runtimeGuard(4)){setError("runtime heap guard after connect");break;}
    if(cancelled()||!sLinkUp.load()){setError("link lost after connect");break;}
    psProbeTraceMark(PS_PROBE_GATT);
    sState=PsState::DISCOVERING;auto*svc=sClient->getService(SVC_UUID);if(!svc){setError("service 0001 missing");break;}sDiagService=true;
    sWrite=svc->getCharacteristic(WRITE_UUID);sNotify=svc->getCharacteristic(NOTIFY_UUID);
    sDiagWrite=(sWrite!=nullptr);sDiagNotify=(sNotify!=nullptr);
    if(!sWrite){setError("write characteristic 0002 missing");break;}
    if(!sNotify){setError("notify characteristic 0003 missing");break;}
    if(!sNotify->subscribe(true,notifyCb)){setError("notify subscribe failed");break;}sDiagSubscribed=true;memSnap(sMemGattFree,sMemGattLargest);
    if(!runtimeGuard(5)){setError("runtime heap guard after GATT");break;}
    psProbeTraceMark(PS_PROBE_AUTH);
    sState=PsState::AUTHENTICATING;sAuthOk=false;sAuthFailed=false;uint8_t f[128];vTaskDelay(pdMS_TO_TICKS(300));size_t n=authStatus(f);
    sAuthStatusLen=n;sAuthMtu=sClient->getMTU();
    if(!n||!sLinkUp.load()||!sWrite||!sWrite->writeValue(f,n,false)){setError("auth-status write failed/link lost");break;}sDiagAuthStatusSent=true;
    vTaskDelay(pdMS_TO_TICKS(400));n=autoAuth(f);
    sAuthFrameLen=n;sAuthMtu=sClient->getMTU();
    if(!n){setError("auth frame construction failed");break;}
    // At MTU 23 NimBLE turns this no-response write into a prepared long
    // write. Wait briefly for the asynchronous exchange, then fail closed.
    const uint32_t mtuWaitStart=millis();
    while(sLinkUp.load() && sClient->getMTU() < n+3 && millis()-mtuWaitStart < 1500){vTaskDelay(pdMS_TO_TICKS(25));}
    sAuthMtu=sClient->getMTU();
    if(sAuthMtu.load() < n+3){setError("MTU too small for single auth write");break;}
    if(!sLinkUp.load()){setError("peer disconnected before auth write");break;}
    if(!sWrite){setError("auth write characteristic missing");break;}
    sAuthLinkBeforeWrite=sLinkUp.load();
    const bool authWriteOk=sWrite->writeValue(f,n,false);
    sAuthLinkAfterWrite=sLinkUp.load();
    if(!authWriteOk){sAuthDisconnectAtFailure=sLastPeerDisconnectReason.load();setError(sLinkUp.load()?"auth writeValue returned false":"peer disconnected during auth write");break;}
    sDiagAuthSent=true;
    memSnap(sMemAuthFree,sMemAuthLargest);
    if(!waitFlag(sAuthOk,AUTH_TIMEOUT_MS)){
      if(sAuthFailed.load()){
        const int ar=sAuthResponse.load();char eb[64];
        if(ar>=0)snprintf(eb,sizeof(eb),"authentication rejected code 0x%02X",ar&0xff);else snprintf(eb,sizeof(eb),"authentication rejected/no code");
        setError(eb);
      }else setError("authentication timeout/no 0x35/0x86 response");
      break;
    }
    if(cancelled()||!runtimeGuard(6)){setError(cancelled()?"cancelled":"runtime heap guard before command");break;}
    // 9.36.7.10 stage-C probe: connect + GATT + subscribe + authentication only.
    // It deliberately exits before constructing/writing a supply-priority frame.
    if(sTxnDepth.load()==PsTxnDepth::AUTH_ONLY){
      sAuthOnlyOk++; ok=true; sState=PsState::CONFIRMED; setError(""); break;
    }
#if PS_AUTH_V3_PROBE_ONLY
    // Diagnostic image never emits a priority command, even if a caller bypasses the HTTP gate.
    setError("v3 auth-only diagnostic blocks priority commands"); break;
#endif
    memSnap(sMemCommandFree,sMemCommandLargest);
    sState=PsState::SENDING;sEnforceObs=EnforceObs::REQUESTED;
    // Commit-point guard: never start/restore Supply while SOC is latched or BMS recovery is pending.
    if(mode==0 && (lowSocGuardSocBlocked()||lowSocGuardRecoveryPending())){setError("Supply commit blocked by SOC/BMS recovery guard");break;}
    n=supplyFrame(f,mode);
    if(!n||!sLinkUp.load()||!sWrite||!sWrite->writeValue(f,n,false)){setError("supply write failed/link lost");break;}sTxOk++;
    // ACK barrier is established only AFTER writeValue() returns. Drop any notification
    // already queued before that barrier; each queued packet carries callback rxAt so a
    // late parser run cannot make a pre-command heartbeat look fresh.
    clearNotifyQueue();
    const uint32_t hbGenerationBefore=sHeartbeatGeneration.load(std::memory_order_acquire);
    const uint32_t commandEpoch=sCommandEpoch.fetch_add(1,std::memory_order_acq_rel)+1U;
    sState=PsState::VERIFYING;if(!waitSupplyFresh(mode,hbGenerationBefore,commandEpoch,VERIFY_TIMEOUT_MS)){setError("fresh heartbeat confirmation timeout");break;}
    sEnforceObs=EnforceObs::ACKNOWLEDGED;
    observePhysicalAfterAck(mode);
    ok=true;sState=PsState::CONFIRMED;setError("");
  }while(false);
  // ESP-IDF's FreeRTOS port reports uxTaskGetStackHighWaterMark() in BYTES on ESP32.
  // Do not multiply by sizeof(StackType_t): doing so can over-report the real
  // safety margin by 4x and hide a near-overflow condition.
  sWorkerStackMinBytes=(uint32_t)uxTaskGetStackHighWaterMark(nullptr);
  psProbeTraceMark(PS_PROBE_CLEANUP);
  cleanupClient();if(auxReserved)jkBleProxyReleaseAuxConnection();sLastOpMs=millis()-started;sWorkerStartedAt=0;
  if(!ok){if(sTxnDepth.load()==PsTxnDepth::AUTH_ONLY)sAuthOnlyFail++;sTxFail++;sState=PsState::FAILED;sCooldownUntil=millis()+COOLDOWN_MS;}else{sCooldownUntil=millis()+2000;}
  sTxnDepth=PsTxnDepth::FULL;
  psProbeTraceMark(PS_PROBE_FINISHED);
  heavyOpRelease(HeavyOpOwner::POWERSTREAM_BLE);sWorkerRunning=false;vTaskDelete(nullptr);
}

void powerStreamBleLabInit(){psProbeTraceBegin();Preferences p;p.begin("psblelab",true);sMac=p.getString("mac","");sSn=p.getString("sn","");sUid=p.getString("uid","");sEnabled=p.getBool("en",false);sAddrType=p.getInt("atype",0);p.end();sConfigured=validMac(sMac)&&saneToken(sSn,8,64)&&saneToken(sUid,6,64)&&(sAddrType==0||sAddrType==1);sState=sEnabled?PsState::IDLE:PsState::OFF;Serial.printf("[PS-BLE-LAB2] enabled=%u configured=%u one-shot=1\n",sEnabled?1:0,powerStreamBleLabConfigured()?1:0);}
void powerStreamBleLabTick(){const uint32_t now=millis();if(WiFi.status()==WL_CONNECTED){if(!sWifiStableSince)sWifiStableSince=now;}else sWifiStableSince=0;PsState st=sState.load();if(!sEnabled){sState=PsState::OFF;return;}if((st==PsState::FAILED||st==PsState::CONFIRMED||st==PsState::COOLDOWN)&&!sWorkerRunning.load()){if((int32_t)(now-sCooldownUntil.load())>=0)sState=PsState::IDLE;else sState=PsState::COOLDOWN;}}
bool powerStreamBleLabVerifyUserId(const String& candidate, bool& matches){
  matches=false;
  if(candidate.length()<6 || candidate.length()>64)return false;
  Preferences p;if(!p.begin("psblelab",true))return false;
  String stored=p.getString("uid","");p.end();
  unsigned diff=(unsigned)(candidate.length()^stored.length());
  for(size_t i=0;i<64;i++){
    const uint8_t a=i<candidate.length()?(uint8_t)candidate[i]:0;
    const uint8_t b=i<stored.length()?(uint8_t)stored[i]:0;
    diff|=(unsigned)(a^b);
  }
  matches=stored.length()>0 && diff==0;
  return true;
}
static bool validMac(const String& m){if(m.length()!=17)return false;for(size_t i=0;i<17;i++){if((i%3)==2){if(m[i]!=':')return false;}else if(!isxdigit((unsigned char)m[i]))return false;}return true;}
static bool saneToken(const String& x,size_t lo,size_t hi){if(x.length()<lo||x.length()>hi)return false;for(size_t i=0;i<x.length();++i){unsigned char c=(unsigned char)x[i];if(c<0x21||c>0x7e)return false;}return true;}
bool powerStreamBleLabConfigured(){return sConfigured.load();}
bool powerStreamBleLabEnabled(){return sEnabled;}
bool powerStreamBleLabSaveConfig(const String&mac,const String&sn,const String&uid,bool en,int addrType){
  // 9.36.5: UID is write-only in the UI. An empty POST therefore means KEEP the
  // previously stored UID, never erase it. This also makes enable/disable safe.
  String effectiveUid = uid.length() ? uid : sUid;
  if(en&&(!validMac(mac)||!saneToken(sn,8,64)||!saneToken(effectiveUid,6,64)||(addrType!=0&&addrType!=1)))return false;
  bool gate=false;if(!sConfigGate.compare_exchange_strong(gate,true))return false;
  if(sWorkerRunning.load()){sConfigGate=false;return false;}
  sCancel=true; Preferences p; if(!p.begin("psblelab",false)){sCancel=false;sConfigGate=false;return false;}
  bool wr=true; wr &= p.putString("mac",mac)==mac.length(); wr &= p.putString("sn",sn)==sn.length(); wr &= p.putString("uid",effectiveUid)==effectiveUid.length();
  p.putBool("en",en); p.putInt("atype",addrType);
  const bool rb = p.getString("mac","")==mac && p.getString("sn","")==sn && p.getString("uid","")==effectiveUid && p.getBool("en",!en)==en && p.getInt("atype",-1)==addrType; p.end();
  if(!wr||!rb){sCancel=false;sConfigGate=false;setError("NVS write/readback failed");return false;}
  // Configuration identity changed: cached GATT attributes belong to the old peer.
  // No worker can be active while sConfigGate is held, so invalidation is serialized.
  if(sClient){NimBLEDevice::deleteClient(sClient);sClient=nullptr;sWrite=nullptr;sNotify=nullptr;}
  sMac=mac;sSn=sn;sUid=effectiveUid;sEnabled=en;sAddrType=addrType;sConfigured=validMac(mac)&&saneToken(sn,8,64)&&saneToken(effectiveUid,6,64)&&(addrType==0||addrType==1);sSupply=-1;sRequested=-1;sHeartbeatGeneration=0;sCommandEpoch=0;sLastHeartbeatEpoch=0;sEnforceObs=EnforceObs::IDLE;sObsSamples=0;sCancel=false;sState=sEnabled?PsState::IDLE:PsState::OFF;sConfigGate=false;return true;
}
bool powerStreamBleLabSetSupplyMode(int mode,String&msg){
#if PS_AUTH_V3_PROBE_ONLY
  (void)mode; msg="v3 auth-only diagnostic: priority commands disabled"; return false;
#endif
  if(mode!=0&&mode!=1){msg="mode must be 0 or 1";return false;}
  bool gate=false;if(!sConfigGate.compare_exchange_strong(gate,true)){msg="configuration busy";return false;}
  auto reject=[&](const String& m){msg=m;setError(m.c_str());sConfigGate=false;return false;};
  if(!sEnabled||!powerStreamBleLabConfigured())return reject("PowerStream BLE disabled/not configured");
  if(sWorkerRunning.load())return reject("BLE operation already running");
  if((int32_t)(millis()-sCooldownUntil.load())<0)return reject("BLE cooldown active");
  if(!jkBleProxyInitialized())return reject("NimBLE/JK proxy not initialized yet");
  if(!bmsTelemetryValidForCan())return reject("BMS telemetry stale/invalid; fresh RS485 safety data required");
  if(mode==0 && (lowSocGuardSocBlocked()||lowSocGuardRecoveryPending()))return reject("Supply blocked by SOC/BMS recovery guard");
  if(jkBleProxyAppConnected())return reject("JK app/proxy client connected; disconnect JK app before PowerStream BLE one-shot");
  const uint32_t ws=sWifiStableSince.load(); if(wifiStaEnabled() && (WiFi.status()!=WL_CONNECTED || !ws || millis()-ws<WIFI_STABLE_MS))return reject("WiFi STA not stable for 5s; BLE operation deferred");
  if(!heapAdmitSafe())return reject("pre-task heap admission blocks BLE operation");
  bool expected=false;if(!sWorkerRunning.compare_exchange_strong(expected,true))return reject("BLE operation already running");
  if(!heavyOpTryAcquire(HeavyOpOwner::POWERSTREAM_BLE)){ sWorkerRunning=false; return reject(String("resource gate busy: ")+heavyOpOwnerName()); }
  memSnap(sMemRequestFree,sMemRequestLargest);sRequested=mode;sEnforceObs=EnforceObs::REQUESTED;sObsSamples=0;sCancel=false;sState=PsState::QUEUED;BaseType_t rc=xTaskCreatePinnedToCore(worker,"psBleOneShot",WORKER_STACK,nullptr,1,nullptr,1);
  if(rc!=pdPASS){heavyOpRelease(HeavyOpOwner::POWERSTREAM_BLE);sWorkerRunning=false;sState=PsState::FAILED;sTxFail++;setError("worker allocation failed");msg="worker allocation failed";sConfigGate=false;return false;}
  setError("");sConfigGate=false;msg="queued one-shot BLE operation; no automatic reconnect";return true;
}
bool powerStreamBleLabProbeAuth(String& msg){
  bool gate=false;if(!sConfigGate.compare_exchange_strong(gate,true)){msg="configuration busy";return false;}
  auto reject=[&](const String& m){msg=m;setError(m.c_str());sConfigGate=false;return false;};
  if(!sEnabled||!powerStreamBleLabConfigured())return reject("PowerStream BLE disabled/not configured");
  if(sWorkerRunning.load())return reject("BLE operation already running");
  if((int32_t)(millis()-sCooldownUntil.load())<0)return reject("BLE cooldown active");
  if(!jkBleProxyInitialized())return reject("NimBLE/JK proxy not initialized yet");
  if(!bmsTelemetryValidForCan())return reject("BMS telemetry stale/invalid; fresh RS485 safety data required");
  if(jkBleProxyAppConnected())return reject("JK app/proxy client connected; disconnect JK app before PowerStream BLE auth probe");
  const uint32_t ws=sWifiStableSince.load();if(wifiStaEnabled()&&(WiFi.status()!=WL_CONNECTED||!ws||millis()-ws<WIFI_STABLE_MS))return reject("WiFi STA not stable for 5s; BLE operation deferred");
  if(!heapAdmitSafe())return reject("pre-task heap admission blocks BLE operation");
  bool expected=false;if(!sWorkerRunning.compare_exchange_strong(expected,true))return reject("BLE operation already running");
  if(!heavyOpTryAcquire(HeavyOpOwner::POWERSTREAM_BLE)){sWorkerRunning=false;return reject(String("resource gate busy: ")+heavyOpOwnerName());}
  memSnap(sMemRequestFree,sMemRequestLargest);sRequested=-1;sEnforceObs=EnforceObs::IDLE;sCancel=false;sTxnDepth=PsTxnDepth::AUTH_ONLY;sState=PsState::QUEUED;
  BaseType_t rc=xTaskCreatePinnedToCore(worker,"psBleAuthProbe",WORKER_STACK,nullptr,1,nullptr,1);
  if(rc!=pdPASS){sTxnDepth=PsTxnDepth::FULL;heavyOpRelease(HeavyOpOwner::POWERSTREAM_BLE);sWorkerRunning=false;sState=PsState::FAILED;sTxFail++;setError("auth-probe worker allocation failed");msg="auth-probe worker allocation failed";sConfigGate=false;return false;}
  setError("");sConfigGate=false;msg="queued connect/GATT/auth-only probe; no supply/storage command will be written";return true;
}
String powerStreamBleLabStatusJson(){const JkBleMemoryDiag jm=jkBleProxyMemoryDiag();const JkBleAuxMemoryDiag am=jkBleProxyAuxMemoryDiag();const uint32_t ws=sWifiStableSince.load();const bool preJkInit=jkBleProxyInitialized();const bool preBms=bmsTelemetryValidForCan();const bool preApp=!jkBleProxyAppConnected();const bool preWifi=!wifiStaEnabled()||(WiFi.status()==WL_CONNECTED&&ws&&(millis()-ws>=WIFI_STABLE_MS));const bool preHeap=heapAdmitSafe();const bool preCooldown=((int32_t)(millis()-sCooldownUntil.load())>=0);const bool preHeavy=(String(heavyOpOwnerName())=="none");String err=getError();err.replace("\\","\\\\");err.replace("\"","\\\"");return String("{\"ok\":true,\"lab_only\":true,\"enabled\":")+(sEnabled.load()?"true":"false")+",\"configured\":"+(powerStreamBleLabConfigured()?"true":"false")+",\"state\":\""+stateName(sState.load())+"\",\"worker\":"+(sWorkerRunning.load()?"true":"false")+",\"address_type\":\""+(sAddrType?"random":"public")+"\",\"supply_prio\":"+String(sSupply.load())+",\"requested\":"+String(sRequested.load())+",\"heartbeat_age_ms\":"+String(sLastHeartbeat.load()?millis()-sLastHeartbeat.load():0)+",\"heartbeat_generation\":"+String(sHeartbeatGeneration.load())+",\"command_epoch\":"+String(sCommandEpoch.load())+",\"heartbeat_epoch\":"+String(sLastHeartbeatEpoch.load())+",\"enforcement_observation\":\""+obsName(sEnforceObs.load())+"\",\"obs_samples\":"+String(sObsSamples.load())+",\"obs_min_current_a\":"+String(sObsMinCurrentmA.load()/1000.0f,3)+",\"obs_max_current_a\":"+String(sObsMaxCurrentmA.load()/1000.0f,3)+",\"acknowledged\":"+((sEnforceObs.load()==EnforceObs::ACKNOWLEDGED||sEnforceObs.load()==EnforceObs::OBSERVING||sEnforceObs.load()==EnforceObs::OBSERVED_NO_DISCHARGE||sEnforceObs.load()==EnforceObs::OBSERVED_DISCHARGE)?"true":"false")+",\"physical_no_discharge_observed\":"+(sEnforceObs.load()==EnforceObs::OBSERVED_NO_DISCHARGE?"true":"false")+",\"last_operation_ms\":"+String(sLastOpMs.load())+",\"tx_ok\":"+String(sTxOk.load())+",\"tx_fail\":"+String(sTxFail.load())+",\"heap\":"+String(ESP.getFreeHeap())+",\"largest8\":"+String(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT))+",\"heap_pre\":"+String(sHeapPre.load())+",\"heap_post\":"+String(sHeapPost.load())+",\"largest_pre\":"+String(sLargestPre.load())+",\"largest_post\":"+String(sLargestPost.load())+",\"cleanup_count\":"+String(sCleanupCount.load())+",\"worker_stack_min_bytes\":"+String(sWorkerStackMinBytes.load())+",\"worker_age_ms\":"+String(sWorkerStartedAt.load()?millis()-sWorkerStartedAt.load():0)+",\"jk_events_pending\":"+(jkBleProxyEventsPending()?"true":"false")+",\"notify_drops\":"+String(sNqDrops.load())+",\"created_clients\":"+String((unsigned)NimBLEDevice::getCreatedClientCount())+",\"aux_reserved\":"+(jkBleProxyAuxReserved()?"true":"false")+",\"heavy_owner\":\""+String(heavyOpOwnerName())+"\",\"heavy_age_ms\":"+String(heavyOpAgeMs())+",\"heavy_release_mismatch\":"+String(heavyOpReleaseMismatchCount())+",\"cfg_mac_valid\":"+(validMac(sMac)?"true":"false")+",\"cfg_sn_valid\":"+(saneToken(sSn,8,64)?"true":"false")+",\"cfg_uid_present\":"+(sUid.length()?"true":"false")+",\"cfg_uid_len\":"+String(sUid.length())+",\"cfg_addr_valid\":"+((sAddrType==0||sAddrType==1)?"true":"false")+",\"diag_connected\":"+(sDiagConnected.load()?"true":"false")+",\"diag_service\":"+(sDiagService.load()?"true":"false")+",\"diag_write\":"+(sDiagWrite.load()?"true":"false")+",\"diag_notify\":"+(sDiagNotify.load()?"true":"false")+",\"diag_subscribed\":"+(sDiagSubscribed.load()?"true":"false")+",\"diag_auth_status_sent\":"+(sDiagAuthStatusSent.load()?"true":"false")+",\"diag_auth_sent\":"+(sDiagAuthSent.load()?"true":"false")+",\"auth_status_reply_seen\":"+(sAuthStatusReplySeen.load()?"true":"false")+",\"auth_status_reply_version\":"+String(sAuthStatusReplyVersion.load())+",\"auth_status_reply_payload_len\":"+String(sAuthStatusReplyPayloadLen.load())+",\"auth_request_version\":3,\"auth_reply_version\":"+String(sAuthReplyVersion.load())+",\"auth_response\":"+String(sAuthResponse.load())+",\"last_peer_disconnect_reason\":"+String(sLastPeerDisconnectReason.load())+",\"auth_status_len\":"+String(sAuthStatusLen.load())+",\"auth_frame_len\":"+String(sAuthFrameLen.load())+",\"auth_mtu\":"+String(sAuthMtu.load())+",\"auth_link_before_write\":"+(sAuthLinkBeforeWrite.load()?"true":"false")+",\"auth_link_after_write\":"+(sAuthLinkAfterWrite.load()?"true":"false")+",\"auth_disconnect_at_failure\":"+String(sAuthDisconnectAtFailure.load())+",\"pre_jk_init\":"+(preJkInit?"true":"false")+",\"pre_bms_link\":"+(preBms?"true":"false")+",\"pre_jk_app_free\":"+(preApp?"true":"false")+",\"pre_wifi_stable\":"+(preWifi?"true":"false")+",\"pre_heap_ok\":"+(preHeap?"true":"false")+",\"pre_cooldown_ok\":"+(preCooldown?"true":"false")+",\"pre_heavy_free\":"+(preHeavy?"true":"false")+",\"aux_diag_generation\":"+String(am.generation)+",\"aux_before_stop_free\":"+String(am.beforeStopFree)+",\"aux_before_stop_largest\":"+String(am.beforeStopLargest)+",\"aux_after_stop_free\":"+String(am.afterStopFree)+",\"aux_after_stop_largest\":"+String(am.afterStopLargest)+",\"aux_after_decision_free\":"+String(am.afterDecisionFree)+",\"aux_after_decision_largest\":"+String(am.afterDecisionLargest)+",\"jk_mem_preinit_free\":"+String(jm.preInitFree)+",\"jk_mem_preinit_largest\":"+String(jm.preInitLargest)+",\"jk_mem_postnimble_free\":"+String(jm.postNimbleFree)+",\"jk_mem_postnimble_largest\":"+String(jm.postNimbleLargest)+",\"jk_mem_postserver_free\":"+String(jm.postServerFree)+",\"jk_mem_postserver_largest\":"+String(jm.postServerLargest)+",\"jk_mem_postgatt_free\":"+String(jm.postGattFree)+",\"jk_mem_postgatt_largest\":"+String(jm.postGattLargest)+",\"jk_mem_postclient_free\":"+String(jm.postClientFree)+",\"jk_mem_postclient_largest\":"+String(jm.postClientLargest)+",\"jk_mem_postadv_free\":"+String(jm.postAdvFree)+",\"jk_mem_postadv_largest\":"+String(jm.postAdvLargest)+",\"runtime_guard_stage\":\""+runtimeGuardStageName(sRuntimeGuardStage.load())+"\",\"runtime_guard_free\":"+String(sRuntimeGuardFree.load())+",\"runtime_guard_largest8\":"+String(sRuntimeGuardLargest8.load())+",\"runtime_guard_integrity\":"+(sRuntimeGuardIntegrity.load()?"true":"false")+",\"mem_request_free\":"+String(sMemRequestFree.load())+",\"mem_request_largest\":"+String(sMemRequestLargest.load())+",\"mem_worker_free\":"+String(sMemWorkerFree.load())+",\"mem_worker_largest\":"+String(sMemWorkerLargest.load())+",\"mem_aux_free\":"+String(sMemAuxFree.load())+",\"mem_aux_largest\":"+String(sMemAuxLargest.load())+",\"mem_client_free\":"+String(sMemClientFree.load())+",\"mem_client_largest\":"+String(sMemClientLargest.load())+",\"mem_connect_free\":"+String(sMemConnectFree.load())+",\"mem_connect_largest\":"+String(sMemConnectLargest.load())+",\"mem_gatt_free\":"+String(sMemGattFree.load())+",\"mem_gatt_largest\":"+String(sMemGattLargest.load())+",\"mem_auth_free\":"+String(sMemAuthFree.load())+",\"mem_auth_largest\":"+String(sMemAuthLargest.load())+",\"mem_command_free\":"+String(sMemCommandFree.load())+",\"mem_command_largest\":"+String(sMemCommandLargest.load())+",\"cleanup_delta_free\":"+String(sCleanupDeltaFree.load())+",\"cleanup_delta_largest\":"+String(sCleanupDeltaLargest.load())+",\"esp_min_free\":"+String(ESP.getMinFreeHeap())+",\"last_error\":\""+err+"\",\"auth_only_active\":"+(sTxnDepth.load()==PsTxnDepth::AUTH_ONLY?"true":"false")+",\"auth_only_ok\":"+String(sAuthOnlyOk.load())+",\"auth_only_fail\":"+String(sAuthOnlyFail.load())+",\"automatic_reconnect\":false,\"automatic_soc_control\":false}";}
