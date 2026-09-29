#include "ps_probe_trace.h"
#include <Arduino.h>
#include <Preferences.h>
#include <esp_heap_caps.h>
#include <freertos/FreeRTOS.h>
#include <atomic>

namespace {
constexpr uint32_t kMagic=0x50535431u;
struct Stored { uint32_t magic, step, atMs, freeHeap, largest8, sequence, check; };
Stored previous{}, current{};
std::atomic<bool> writeOk{true};
std::atomic<uint32_t> writeAttemptsThisBoot{0}, writeFailuresThisBoot{0};
portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
uint32_t checksum(const Stored& v) {
  return v.magic ^ v.step ^ v.atMs ^ v.freeHeap ^ v.largest8 ^ v.sequence ^ 0x7A91C053u;
}
PsProbeTrace snapshot(const Stored& v) {
  return {v.step,v.atMs,v.freeHeap,v.largest8,v.sequence};
}
}
void psProbeTraceBegin() {
  writeOk.store(true);
  writeAttemptsThisBoot.store(0);
  writeFailuresThisBoot.store(0);
  Preferences p;
  // The namespace may not exist on first boot; read/write opens or creates it.
  if(!p.begin("psprobe",false)){writeOk=false;return;}
  Stored saved{};
  if(p.getBytesLength("last")==sizeof(saved) &&
     p.getBytes("last",&saved,sizeof(saved))==sizeof(saved) &&
     saved.magic==kMagic && saved.step<=PS_PROBE_FINISHED &&
     saved.check==checksum(saved)) previous=saved;
  p.end();
  portENTER_CRITICAL(&mux);current=previous;portEXIT_CRITICAL(&mux);
}
bool psProbeTraceMark(PsProbeStep step) {
  writeAttemptsThisBoot.fetch_add(1);
  const uint32_t sequence=psProbeTraceCurrent().sequence+1;
  Stored next{kMagic,(uint32_t)step,millis(),ESP.getFreeHeap(),
    (uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),sequence,0};
  next.check=checksum(next);
  Preferences p;
  if(!p.begin("psprobe",false)){writeOk=false;writeFailuresThisBoot.fetch_add(1);return false;}
  const bool ok=p.putBytes("last",&next,sizeof(next))==sizeof(next);
  p.end();
  if(ok){portENTER_CRITICAL(&mux);current=next;portEXIT_CRITICAL(&mux);writeOk=true;}
  else {writeOk=false;writeFailuresThisBoot.fetch_add(1);}
  return ok;
}
PsProbeTrace psProbeTracePrevious(){return snapshot(previous);}
PsProbeTrace psProbeTraceCurrent(){portENTER_CRITICAL(&mux);const auto v=snapshot(current);portEXIT_CRITICAL(&mux);return v;}
bool psProbeTraceWriteOk(){return writeOk;}
uint32_t psProbeTraceWriteAttemptsThisBoot(){return writeAttemptsThisBoot.load();}
uint32_t psProbeTraceWriteFailuresThisBoot(){return writeFailuresThisBoot.load();}
