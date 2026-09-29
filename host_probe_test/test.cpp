#include "ps_probe_trace.h"
#include "Arduino.h"
#include "Preferences.h"
#include <cassert>
#include <iostream>
EspStub ESP;
bool failNextPut=false;
std::map<std::string,std::vector<uint8_t>> fakeNvs;
uint32_t millis() { static uint32_t t=100; return t+=10; }
int main() {
  assert(fakeNvs.empty());
  psProbeTraceBegin();
  assert(fakeNvs.count("psprobe")==1); // first-use namespace created
  assert(psProbeTraceWriteOk());
  assert(psProbeTraceWriteAttemptsThisBoot()==0);
  assert(psProbeTraceMark(PS_PROBE_WORKER));
  assert(psProbeTraceCurrent().step==PS_PROBE_WORKER);
  assert(psProbeTraceWriteAttemptsThisBoot()==1);
  assert(psProbeTraceWriteFailuresThisBoot()==0);
  failNextPut=true;
  assert(!psProbeTraceMark(PS_PROBE_CONNECT));
  assert(!psProbeTraceWriteOk());
  assert(psProbeTraceCurrent().step==PS_PROBE_WORKER);
  assert(psProbeTraceWriteAttemptsThisBoot()==2);
  assert(psProbeTraceWriteFailuresThisBoot()==1);
  assert(psProbeTraceMark(PS_PROBE_GATT));
  assert(psProbeTraceWriteOk());
  assert(psProbeTraceCurrent().step==PS_PROBE_GATT);
  assert(psProbeTraceWriteAttemptsThisBoot()==3);
  assert(psProbeTraceWriteFailuresThisBoot()==1);
  std::cout << "PASS: first-use, failed write, recovery, counters\n";
}
