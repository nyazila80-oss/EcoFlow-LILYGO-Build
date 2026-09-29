#include "config.h"
#include "low_soc_guard.h"
#include <atomic>

// Define the global instance
Config config;
static std::atomic<bool> g_canRxEnabled{true};
static std::atomic<bool> g_rxLogging{true};
static std::atomic<bool> g_txLogging{true};
static std::atomic<bool> g_canTxEnabled{true};
static std::atomic<uint16_t> g_canMsgMask{0x03FFU};
static std::atomic<uint8_t> g_miscToggleMask{0}; // bit0 acout5C, bit1 flagCB
static std::atomic<uint8_t> g_mosStatus{0};
static std::atomic<uint16_t> g_configuredCanLimits{100U | (10U<<8)}; // bit0 charge, bit1 discharge
static std::atomic<bool> g_batteryMaster{true};
static std::atomic<bool> g_battSync{true};
// Coherent CAN battery telemetry snapshot using a 32-bit seqlock; avoids 64-bit atomic requirements on ESP32.
static std::atomic<uint32_t> g_canBattSeq{0};
static portMUX_TYPE g_canBattWriterMux=portMUX_INITIALIZER_UNLOCKED;
static std::atomic<uint32_t> g_canBattWord1{1U | (20U<<24)}; // soc[7:0], volt[23:8], temp[31:24]
static std::atomic<uint32_t> g_canBattWord2{100U | (10U<<8)}; // upper[7:0], lower[15:8]
static std::atomic<uint32_t> g_canBattChgRuntime{1};
static std::atomic<uint32_t> g_canBattDisRuntime{1};
static std::atomic<uint32_t> g_canPowerSeq{0};
static std::atomic<int32_t> g_canInputW{0};
static std::atomic<int32_t> g_canOutputW{0};
static std::atomic<uint32_t> g_canDerivedSeq{0};
static std::atomic<uint32_t> g_canCellMinMax{0};
static std::atomic<uint32_t> g_canDerived2{0};
static std::atomic<uint32_t> g_canIdentitySeq{0};
static std::atomic<uint32_t> g_canSerial0{0}, g_canSerial1{0}, g_canSerial2{0}, g_canSerial3{0};
static std::atomic<uint32_t> g_canChargeVolt{57600};
// Coherent cross-core snapshot: bit0 enabled, bits8..15 stop, bits16..23 resume.
static std::atomic<uint32_t> g_lowSocCfg{1U | (10U<<8) | (12U<<16)};
static std::atomic<uint16_t> g_lowSohCfg{70U<<8}; // bit0 enabled, bits8..15 minimum SOH

bool canRxEnabledAtomic(){ return g_canRxEnabled.load(std::memory_order_acquire); }
bool rxLoggingAtomic(){ return g_rxLogging.load(std::memory_order_acquire); }
bool txLoggingAtomic(){ return g_txLogging.load(std::memory_order_acquire); }
void setCanRxEnabledAtomic(bool v){ config.canRxEnabled=v; g_canRxEnabled.store(v,std::memory_order_release); }
void setRxLoggingAtomic(bool v){ config.rxlogging=v; g_rxLogging.store(v,std::memory_order_release); }
void setTxLoggingAtomic(bool v){ config.txlogging=v; g_txLogging.store(v,std::memory_order_release); }
bool canTxEnabledAtomic(){ return g_canTxEnabled.load(std::memory_order_acquire); }
void setCanTxEnabledAtomic(bool v){ config.canTxEnabled=v; g_canTxEnabled.store(v,std::memory_order_release); }
void syncCanMessageFlagsAtomic(){
  uint16_t m=0; const bool v[]={config.message3C,config.message13,config.messageCB,config.message70,config.message0B,config.message5C,config.message68,config.message4F,config.message8C,config.message24};
  for(unsigned i=0;i<10;i++) if(v[i]) m|=(uint16_t)(1U<<i); g_canMsgMask.store(m,std::memory_order_release);
}
bool canMessageEnabledAtomic(const char* k){
  int i=-1; if(!strcmp(k,"message3C"))i=0; else if(!strcmp(k,"message13"))i=1; else if(!strcmp(k,"messageCB"))i=2; else if(!strcmp(k,"message70"))i=3; else if(!strcmp(k,"message0B"))i=4; else if(!strcmp(k,"message5C"))i=5; else if(!strcmp(k,"message68"))i=6; else if(!strcmp(k,"message4F"))i=7; else if(!strcmp(k,"message8C"))i=8; else if(!strcmp(k,"message24"))i=9;
  return i>=0 && (g_canMsgMask.load(std::memory_order_acquire)&(uint16_t)(1U<<i));
}
bool configToggleValueAtomic(const char* k, bool &value){
  if(!k) return false;
  if(!strcmp(k,"canTxEnabled")){ value=canTxEnabledAtomic(); return true; }
  if(!strcmp(k,"canRxEnabled")){ value=canRxEnabledAtomic(); return true; }
  if(!strcmp(k,"rxlogging")){ value=rxLoggingAtomic(); return true; }
  if(!strcmp(k,"txlogging")){ value=txLoggingAtomic(); return true; }
  if(!strcmp(k,"batteryMaster")){ value=batteryMasterAtomic(); return true; }
  if(!strcmp(k,"batt")){ value=battSyncAtomic(); return true; }
  if(!strncmp(k,"message",7)){ value=canMessageEnabledAtomic(k); return true; }
  const uint8_t m=g_miscToggleMask.load(std::memory_order_acquire);
  if(!strcmp(k,"acout5C")){ value=(m&1U)!=0; return true; }
  if(!strcmp(k,"flagCB")){ value=(m&2U)!=0; return true; }
  return false;
}
bool toggleConfigMainOwner(const char* k, bool &newValue){
  bool cur=false; if(!configToggleValueAtomic(k,cur)) return false; newValue=!cur;
  if(!strcmp(k,"canTxEnabled")) setCanTxEnabledAtomic(newValue);
  else if(!strcmp(k,"canRxEnabled")) setCanRxEnabledAtomic(newValue);
  else if(!strcmp(k,"rxlogging")) setRxLoggingAtomic(newValue);
  else if(!strcmp(k,"txlogging")) setTxLoggingAtomic(newValue);
  else if(!strcmp(k,"batteryMaster")) setBatteryMasterAtomic(newValue);
  else if(!strcmp(k,"batt")) setBattSyncAtomic(newValue);
  else if(!strncmp(k,"message",7)){ bool* p=getTogglePtrByKey(String(k)); if(!p) return false; *p=newValue; syncCanMessageFlagsAtomic(); }
  else if(!strcmp(k,"acout5C")){ config.acout5C=newValue; uint8_t m=g_miscToggleMask.load(); g_miscToggleMask.store(newValue?(m|1U):(m&~1U),std::memory_order_release); }
  else if(!strcmp(k,"flagCB")){ config.flagCB=newValue; uint8_t m=g_miscToggleMask.load(); g_miscToggleMask.store(newValue?(m|2U):(m&~2U),std::memory_order_release); }
  else return false;
  return true;
}
void setMosStatusAtomic(bool chg,bool dis){ config.moschg=chg; config.mosdis=dis; g_mosStatus.store((chg?1U:0U)|(dis?2U:0U),std::memory_order_release); }
void mosStatusAtomic(bool &chg,bool &dis){ const uint8_t m=g_mosStatus.load(std::memory_order_acquire); chg=(m&1U)!=0; dis=(m&2U)!=0; }
bool acout5CAtomic(){ return (g_miscToggleMask.load(std::memory_order_acquire)&1U)!=0; }
bool flagCBAtomic(){ return (g_miscToggleMask.load(std::memory_order_acquire)&2U)!=0; }
void configuredCanLimitsAtomic(uint8_t &upper,uint8_t &lower){ const uint16_t v=g_configuredCanLimits.load(std::memory_order_acquire); upper=(uint8_t)v; lower=(uint8_t)(v>>8); }
void lowSocConfigSnapshot(bool &enabled, uint8_t &stop, uint8_t &resume){
  const uint32_t v=g_lowSocCfg.load(std::memory_order_acquire); enabled=(v&1U)!=0; stop=(uint8_t)((v>>8)&0xFFU); resume=(uint8_t)((v>>16)&0xFFU);
}
bool setLowSocConfigAtomic(bool enabled, uint8_t stop, uint8_t resume){
  if(stop>99 || resume>100 || resume<=stop) return false;
  const uint32_t v=(enabled?1U:0U)|((uint32_t)stop<<8)|((uint32_t)resume<<16); g_lowSocCfg.store(v,std::memory_order_release); return true;
}
void lowSohConfigSnapshot(bool &enabled, uint8_t &minSoh){ const uint16_t v=g_lowSohCfg.load(std::memory_order_acquire); enabled=(v&1U)!=0; minSoh=(uint8_t)(v>>8); }
bool setLowSohConfigAtomic(bool enabled, uint8_t minSoh){ if(minSoh>100) return false; g_lowSohCfg.store((uint16_t)((enabled?1U:0U)|((uint16_t)minSoh<<8)),std::memory_order_release); return true; }

void syncCanIdentitySnapshotAtomic(){
  uint32_t w[4]={0,0,0,0}; memcpy(w,config.serialStr,16);
  g_canIdentitySeq.fetch_add(1,std::memory_order_acq_rel);
  g_canSerial0.store(w[0],std::memory_order_relaxed); g_canSerial1.store(w[1],std::memory_order_relaxed);
  g_canSerial2.store(w[2],std::memory_order_relaxed); g_canSerial3.store(w[3],std::memory_order_relaxed);
  g_canChargeVolt.store(config.chgvolt,std::memory_order_relaxed);
  g_canIdentitySeq.fetch_add(1,std::memory_order_release);
}
CanIdentitySnapshot canIdentitySnapshotAtomic(){
  for(;;){
    const uint32_t a=g_canIdentitySeq.load(std::memory_order_acquire); if(a&1U) continue;
    uint32_t w[4]={g_canSerial0.load(std::memory_order_relaxed),g_canSerial1.load(std::memory_order_relaxed),g_canSerial2.load(std::memory_order_relaxed),g_canSerial3.load(std::memory_order_relaxed)};
    const uint16_t cv=(uint16_t)g_canChargeVolt.load(std::memory_order_relaxed);
    const uint32_t b=g_canIdentitySeq.load(std::memory_order_acquire);
    if(a==b && !(b&1U)){ CanIdentitySnapshot out{}; memcpy(out.serial,w,16); out.serial[16]='\0'; out.chgvolt=cv; return out; }
  }
}

bool batteryMasterAtomic(){ return g_batteryMaster.load(std::memory_order_acquire); }
void setBatteryMasterAtomic(bool v){ config.batteryMaster=v; g_batteryMaster.store(v,std::memory_order_release); }
bool battSyncAtomic(){ return g_battSync.load(std::memory_order_acquire); }
void setBattSyncAtomic(bool v){ config.batt=v; g_battSync.store(v,std::memory_order_release); }
void syncCanBatterySnapshotAtomic(){
  // Seqlocks require a single writer at a time. This snapshot can be published
  // both by the BMS/main path and by AsyncWebServer configuration callbacks.
  // Serialize writers so the sequence can never become even while another writer
  // is still updating the payload words.
  portENTER_CRITICAL(&g_canBattWriterMux);
  g_canBattSeq.fetch_add(1,std::memory_order_acq_rel); // odd = writer active
  const uint32_t w1=(uint32_t)config.soc | ((uint32_t)config.volt<<8) | ((uint32_t)config.temp<<24);
  g_configuredCanLimits.store((uint16_t)config.bmsChgUp|((uint16_t)config.bmsChgDn<<8),std::memory_order_release);
  uint8_t effectiveLower=config.bmsChgDn; bool lsgEn=false; uint8_t lsgStop=0,lsgResume=0; lowSocConfigSnapshot(lsgEn,lsgStop,lsgResume); /* Hardened: advertise the SOC floor only while the SOC hysteresis latch is actually blocking. SOH is intentionally not mapped to an invented CAN command. */ if(lsgEn && lowSocGuardSocBlocked() && lsgStop>effectiveLower) effectiveLower=lsgStop; const uint32_t w2=(uint32_t)config.bmsChgUp | ((uint32_t)effectiveLower<<8);
  g_canBattWord1.store(w1,std::memory_order_relaxed); g_canBattWord2.store(w2,std::memory_order_relaxed);
  g_canBattChgRuntime.store(config.chgruntime,std::memory_order_relaxed); g_canBattDisRuntime.store(config.disruntime,std::memory_order_relaxed);
  g_canBattSeq.fetch_add(1,std::memory_order_release); // even = stable snapshot
  portEXIT_CRITICAL(&g_canBattWriterMux);
}
CanBatterySnapshot canBatterySnapshotAtomic(){
  for(;;){
    const uint32_t a=g_canBattSeq.load(std::memory_order_acquire); if(a&1U) continue;
    const uint32_t w1=g_canBattWord1.load(std::memory_order_relaxed), w2=g_canBattWord2.load(std::memory_order_relaxed);
    const uint32_t cr=g_canBattChgRuntime.load(std::memory_order_relaxed), dr=g_canBattDisRuntime.load(std::memory_order_relaxed);
    const uint32_t b=g_canBattSeq.load(std::memory_order_acquire); if(a==b && !(b&1U)) return {(uint8_t)w1,(uint16_t)(w1>>8),(uint8_t)(w1>>24),(uint8_t)w2,(uint8_t)(w2>>8),cr,dr};
  }
}
void setCanPowerSnapshotAtomic(int32_t inputW, int32_t outputW){
  g_canPowerSeq.fetch_add(1,std::memory_order_acq_rel);
  g_canInputW.store(inputW,std::memory_order_relaxed); g_canOutputW.store(outputW,std::memory_order_relaxed);
  g_canPowerSeq.fetch_add(1,std::memory_order_release);
}
void canPowerSnapshotAtomic(int32_t &inputW, int32_t &outputW){
  for(;;){ const uint32_t a=g_canPowerSeq.load(std::memory_order_acquire); if(a&1U) continue;
    const int32_t in=g_canInputW.load(std::memory_order_relaxed), out=g_canOutputW.load(std::memory_order_relaxed);
    const uint32_t b=g_canPowerSeq.load(std::memory_order_acquire); if(a==b && !(b&1U)){ inputW=in; outputW=out; return; } }
}
void setCanDerivedSnapshotAtomic(uint16_t minMv,uint16_t maxMv,uint16_t balMilli,uint16_t fullMv){
  g_canDerivedSeq.fetch_add(1,std::memory_order_acq_rel);
  g_canCellMinMax.store((uint32_t)minMv|((uint32_t)maxMv<<16),std::memory_order_relaxed);
  g_canDerived2.store((uint32_t)balMilli|((uint32_t)fullMv<<16),std::memory_order_relaxed);
  g_canDerivedSeq.fetch_add(1,std::memory_order_release);
}
CanDerivedSnapshot canDerivedSnapshotAtomic(){ for(;;){ const uint32_t a=g_canDerivedSeq.load(std::memory_order_acquire); if(a&1U)continue; const uint32_t mm=g_canCellMinMax.load(std::memory_order_relaxed),d2=g_canDerived2.load(std::memory_order_relaxed); const uint32_t b=g_canDerivedSeq.load(std::memory_order_acquire); if(a==b && !(b&1U)) return {(uint16_t)mm,(uint16_t)(mm>>16),(uint16_t)d2,(uint16_t)(d2>>16)}; } }

// Returns pointer to a config boolean by key name, or nullptr if unknown
bool* getTogglePtrByKey(const String& k) {
  if (k == "canTxEnabled") return &config.canTxEnabled;
  if (k == "txlogging")    return &config.txlogging;

  if (k == "batteryMaster") return &config.batteryMaster;
  if (k == "batt")         return &config.batt;

  if (k == "message3C")    return &config.message3C;
  if (k == "message13")    return &config.message13;
  if (k == "messageCB")    return &config.messageCB;
  if (k == "message70")    return &config.message70;
  if (k == "message0B")    return &config.message0B;
  if (k == "message5C")    return &config.message5C;
  if (k == "message68")    return &config.message68;
  if (k == "message4F")    return &config.message4F;
  if (k == "message24")    return &config.message24;
  if (k == "message8C")    return &config.message8C;

  if (k == "acout5C")      return &config.acout5C;
  if (k == "flagCB")       return &config.flagCB;
  if (k == "moschg")       return &config.moschg;
  if (k == "mosdis")       return &config.mosdis;
  return nullptr;
}

// ---------- Core Config Load ----------
void loadCoreConfig() {
  Preferences p; p.begin("core", true);
  String s = p.getString("serial", "");
  uint16_t cv = p.getUShort("chgvolt", 0);
  uint8_t cu = p.getUChar("can_up", config.bmsChgUp);
  uint8_t cd = p.getUChar("can_dn", config.bmsChgDn);
  bool lsg = p.getBool("lsg_en", config.lowSocGuardEnabled);
  uint8_t lss = p.getUChar("lsg_stop", config.lowSocStop);
  uint8_t lsr = p.getUChar("lsg_resume", config.lowSocResume);
  bool lsh = p.getBool("lsh_en", config.lowSohGuardEnabled);
  uint8_t lshm = p.getUChar("lsh_min", config.lowSohMin);
  p.end();

  if (s.length() == 16) {
    s.toCharArray(config.serialStr, 17);
  }
  if (cv != 0) {
    config.chgvolt = cv;
  }
  if (cu <= 100) config.bmsChgUp = cu;
  if (cd <= 100) config.bmsChgDn = cd;
  config.lowSocGuardEnabled = lsg;
  if (lss <= 99 && lsr <= 100 && lsr > lss) { config.lowSocStop=lss; config.lowSocResume=lsr; }
  config.lowSohGuardEnabled=lsh; if(lshm<=100) config.lowSohMin=lshm;
  g_canRxEnabled.store(config.canRxEnabled, std::memory_order_release);
  g_rxLogging.store(config.rxlogging, std::memory_order_release);
  g_txLogging.store(config.txlogging, std::memory_order_release);
  g_canTxEnabled.store(config.canTxEnabled, std::memory_order_release);
  syncCanMessageFlagsAtomic();
  setLowSocConfigAtomic(config.lowSocGuardEnabled, config.lowSocStop, config.lowSocResume);
  setLowSohConfigAtomic(config.lowSohGuardEnabled, config.lowSohMin);
  g_batteryMaster.store(config.batteryMaster,std::memory_order_release);
  g_battSync.store(config.batt,std::memory_order_release);
  g_miscToggleMask.store((config.acout5C?1U:0U)|(config.flagCB?2U:0U),std::memory_order_release);
  g_mosStatus.store((config.moschg?1U:0U)|(config.mosdis?2U:0U),std::memory_order_release);
  syncCanBatterySnapshotAtomic();
  syncCanIdentitySnapshotAtomic();
}

// ---------- Core Config Save ----------
void saveCoreConfig() {
  // Persist only published cross-core snapshots; callers may run outside the main loop.
  const CanIdentitySnapshot ident=canIdentitySnapshotAtomic();
  uint8_t configuredUp=100, configuredDn=10; configuredCanLimitsAtomic(configuredUp,configuredDn);
  Preferences p; p.begin("core", false);
  p.putString("serial", String(ident.serial));
  p.putUShort("chgvolt", ident.chgvolt);
  p.putUChar("can_up", configuredUp);
  p.putUChar("can_dn", configuredDn);
  bool lsgEnabled; uint8_t lsgStop,lsgResume; lowSocConfigSnapshot(lsgEnabled,lsgStop,lsgResume);
  p.putBool("lsg_en", lsgEnabled);
  p.putUChar("lsg_stop", lsgStop);
  p.putUChar("lsg_resume", lsgResume);
  bool lshEnabled; uint8_t lshMin; lowSohConfigSnapshot(lshEnabled,lshMin); p.putBool("lsh_en",lshEnabled); p.putUChar("lsh_min",lshMin);
  p.end();
}

// ---------- Device ID (from MAC) ----------
String deviceId() {
  uint64_t mac = ESP.getEfuseMac();
  uint16_t last16 = (uint16_t)(mac & 0xFFFF);   // lowest 16 bits

  char buf[5];                                  // 4 hex chars + NUL
  snprintf(buf, sizeof(buf), "%04X", last16);   // zero-padded, uppercase
  return String(buf);
}
