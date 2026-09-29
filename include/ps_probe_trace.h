#pragma once
#include <stdint.h>

// Persistent, scalar-only checkpoints for manually triggered PowerStream BLE probes.
// Flash writes are bounded to one-shot attempts, never used by the periodic loop.
enum PsProbeStep : uint32_t {
  PS_PROBE_NONE=0, PS_PROBE_WORKER=1, PS_PROBE_SLOT_REQUEST=2,
  PS_PROBE_SLOT_GRANTED=3, PS_PROBE_CLIENT=4, PS_PROBE_CONNECT=5,
  PS_PROBE_GATT=6, PS_PROBE_AUTH=7, PS_PROBE_CLEANUP=8,
  PS_PROBE_FINISHED=9
};
struct PsProbeTrace { uint32_t step, atMs, freeHeap, largest8, sequence; };
void psProbeTraceBegin();
bool psProbeTraceMark(PsProbeStep step);
PsProbeTrace psProbeTracePrevious();
PsProbeTrace psProbeTraceCurrent();
bool psProbeTraceWriteOk();
uint32_t psProbeTraceWriteAttemptsThisBoot();
uint32_t psProbeTraceWriteFailuresThisBoot();
