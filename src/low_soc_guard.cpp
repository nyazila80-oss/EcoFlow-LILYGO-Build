#include "low_soc_guard.h"
#include "config.h"
#include "bms.h"
#include "web.h"
#include <cstdio>
#include <atomic>
enum : uint8_t { LSG_INIT=0, LSG_DISABLED, LSG_ALLOW, LSG_BLOCK_SOC, LSG_BLOCK_SOH, LSG_BLOCK_BOTH, LSG_STALE_BLOCK };
static std::atomic<bool> blockRequested{false};
static std::atomic<bool> socLatched{false};
static std::atomic<uint32_t> transitions{0};
static std::atomic<uint8_t> stateCode{LSG_INIT};
static std::atomic<bool> recoveryPending{false};
static std::atomic<uint32_t> recoveryBaseFrames{0};
static std::atomic<uint32_t> staleEvents{0};
static constexpr uint32_t RECOVERY_VALID_FRAMES = 2;
static uint32_t staleEnterMs=0;
static uint32_t recoveryFirstMs=0;
static uint32_t recoveryLastReported=0;
static void guardDiag(const char* fmt, uint32_t a=0, uint32_t b=0){
  char line[180]; snprintf(line,sizeof(line),fmt,(unsigned long)a,(unsigned long)b);
  Serial.println(line); streamDebug(line);
}
void lowSocGuardTick(){
  bool socEn; uint8_t stop,resume; lowSocConfigSnapshot(socEn,stop,resume);
  bool sohEn; uint8_t minSoh; lowSohConfigSnapshot(sohEn,minSoh);
  // Fail-safe priority: BMS validity is safety-critical and must be evaluated
  // before optional SOC/SOH policy switches. A stale BMS therefore blocks even
  // when both user-configurable guards are disabled.
  const BmsSafetySnapshot bs=bmsSafetySnapshotAtomic();
  if(!bs.valid){
    const bool wasRecovery=recoveryPending.exchange(true,std::memory_order_acq_rel);
    if(!wasRecovery){
      const uint32_t base=bs.okStatusFrames;
      recoveryBaseFrames.store(base,std::memory_order_release); staleEvents.fetch_add(1,std::memory_order_relaxed);
      staleEnterMs=millis(); recoveryFirstMs=0; recoveryLastReported=0;
      guardDiag("[BMS-GUARD] ENTER BMS_STALE_BLOCK t=%lu ms last_valid_age=%lu ms", staleEnterMs, bs.lastValidMs ? (uint32_t)(millis()-bs.lastValidMs) : 0xFFFFFFFFUL);
      guardDiag("[BMS-GUARD] ECOFLOW_TX_SUPPRESSED reason=BMS_STALE t=%lu ms", staleEnterMs);
    }
    if(!blockRequested.exchange(true,std::memory_order_acq_rel)) transitions.fetch_add(1);
    stateCode.store(LSG_STALE_BLOCK,std::memory_order_release); return;
  }
  // Fail-closed recovery: after a stale interval, one good frame is not enough.
  // Require two newly validated JK status frames before normal guard evaluation resumes.
  if(recoveryPending.load(std::memory_order_acquire)){
    const uint32_t base=recoveryBaseFrames.load(std::memory_order_acquire);
    const uint32_t now=bs.okStatusFrames;
    const uint32_t recovered=(uint32_t)(now-base);
    if(recovered < RECOVERY_VALID_FRAMES){
      if(recovered>0 && recovered!=recoveryLastReported){
        recoveryLastReported=recovered;
        if(!recoveryFirstMs) recoveryFirstMs=millis();
        guardDiag("[BMS-GUARD] RECOVERY %lu/2 t=%lu ms; TX remains suppressed", recovered, millis());
      }
      if(!blockRequested.exchange(true,std::memory_order_acq_rel)) transitions.fetch_add(1);
      stateCode.store(LSG_STALE_BLOCK,std::memory_order_release); return;
    }
    const uint32_t nowMs=millis();
    guardDiag("[BMS-GUARD] RECOVERY 2/2 t=%lu ms; stale_duration=%lu ms", nowMs, (uint32_t)(nowMs-staleEnterMs));
    recoveryPending.store(false,std::memory_order_release);
    guardDiag("[BMS-GUARD] EXIT BMS_STALE_BLOCK t=%lu ms; ECOFLOW_TX_RELEASED", nowMs);
  }
  // Only after BMS validity/recovery has been established may the optional
  // policy guards disable themselves. This preserves fail-closed behavior.
  if(!socEn && !sohEn){
    socLatched.store(false,std::memory_order_release);
    if(blockRequested.exchange(false,std::memory_order_acq_rel)) transitions.fetch_add(1);
    stateCode.store(LSG_DISABLED,std::memory_order_release);
    return;
  }
  const uint8_t soc=bs.soc, soh=bs.soh;
  const bool sohBlock=sohEn && soh<=minSoh;
  bool prev=blockRequested.load(std::memory_order_acquire);
  bool socBlock=false;
  if(socEn){
    // SOC hysteresis survives while another reason (SOH) is also active.
    bool lat=socLatched.load(std::memory_order_acquire);
    const bool oldLat=lat;
    if(!lat && soc<=stop) lat=true; else if(lat && soc>=resume) lat=false;
    socLatched.store(lat,std::memory_order_release); socBlock=lat;
    if(oldLat!=lat) syncCanBatterySnapshotAtomic();
  } else {
    // Disabling only the SOC guard must clear its hysteresis latch immediately.
    const bool wasLatched=socLatched.exchange(false,std::memory_order_acq_rel);
    if(wasLatched) syncCanBatterySnapshotAtomic();
  }
  const bool block=socBlock||sohBlock;
  if(prev!=block){ blockRequested.store(block,std::memory_order_release); transitions.fetch_add(1); }
  stateCode.store(block?(socBlock?(sohBlock?LSG_BLOCK_BOTH:LSG_BLOCK_SOC):LSG_BLOCK_SOH):LSG_ALLOW,std::memory_order_release);
}
bool lowSocGuardBlockRequested(){return blockRequested.load(std::memory_order_acquire);}
bool lowSocGuardSocBlocked(){return socLatched.load(std::memory_order_acquire);}
const char* lowSocGuardState(){switch(stateCode.load(std::memory_order_acquire)){case LSG_DISABLED:return "DISABLED";case LSG_ALLOW:return "ALLOW";case LSG_BLOCK_SOC:return "BLOCK_SOC";case LSG_BLOCK_SOH:return "BLOCK_SOH";case LSG_BLOCK_BOTH:return "BLOCK_SOC_SOH";case LSG_STALE_BLOCK:return "BMS_STALE_BLOCK";default:return "INIT";}}
uint32_t lowSocGuardTransitions(){return transitions.load(std::memory_order_acquire);}

bool lowSocGuardRecoveryPending(){return recoveryPending.load(std::memory_order_acquire);}
uint32_t lowSocGuardStaleEvents(){return staleEvents.load(std::memory_order_acquire);}
