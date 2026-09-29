#include "resource_gate.h"
#include <Arduino.h>
#include <atomic>
static std::atomic<uint8_t> gHeavyOwner{0};
static std::atomic<uint32_t> gHeavySinceMs{0};
static std::atomic<uint32_t> gHeavyAcquireCount{0};
static std::atomic<uint32_t> gHeavyReleaseMismatch{0};
bool heavyOpTryAcquire(HeavyOpOwner owner){
  uint8_t expected=0; const uint8_t wanted=(uint8_t)owner;
  if(!wanted) return false;
  if(!gHeavyOwner.compare_exchange_strong(expected,wanted,std::memory_order_acq_rel)) return false;
  // Publish the lease start only after ownership is committed. Age is diagnostic only;
  // it is NEVER used to steal a live owner because that would re-introduce overlap.
  gHeavySinceMs.store(millis(),std::memory_order_release);
  gHeavyAcquireCount.fetch_add(1,std::memory_order_relaxed);
  return true;
}
void heavyOpRelease(HeavyOpOwner owner){
  uint8_t expected=(uint8_t)owner;
  if(gHeavyOwner.compare_exchange_strong(expected,0,std::memory_order_acq_rel)){
    gHeavySinceMs.store(0,std::memory_order_release);
  } else if(owner!=HeavyOpOwner::NONE){
    gHeavyReleaseMismatch.fetch_add(1,std::memory_order_relaxed);
  }
}
HeavyOpOwner heavyOpOwner(){ return (HeavyOpOwner)gHeavyOwner.load(std::memory_order_acquire); }
const char* heavyOpOwnerName(){ switch(heavyOpOwner()){case HeavyOpOwner::POWERSTREAM_BLE:return "powerstream_ble";case HeavyOpOwner::POWERSTREAM_CLOUD:return "powerstream_cloud";default:return "none";} }
uint32_t heavyOpAgeMs(){
  if(heavyOpOwner()==HeavyOpOwner::NONE) return 0;
  const uint32_t since=gHeavySinceMs.load(std::memory_order_acquire);
  return since ? (uint32_t)(millis()-since) : 0;
}
uint32_t heavyOpAcquireCount(){ return gHeavyAcquireCount.load(std::memory_order_relaxed); }
uint32_t heavyOpReleaseMismatchCount(){ return gHeavyReleaseMismatch.load(std::memory_order_relaxed); }
