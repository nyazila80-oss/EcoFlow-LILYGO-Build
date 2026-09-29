#pragma once
#include <stdint.h>

enum CloudDiagStep : uint32_t {
  CLOUD_DIAG_NONE=0, CLOUD_DIAG_QUEUED=1, CLOUD_DIAG_WORKER=2,
  CLOUD_DIAG_HTTP_BEGIN=3, CLOUD_DIAG_HTTP_GET=4,
  CLOUD_DIAG_HTTP_REPLY=5, CLOUD_DIAG_BODY=6,
  CLOUD_DIAG_PARSED=7, CLOUD_DIAG_FINISHED=8
};
struct CloudDiagSnapshot {
  uint32_t step, atMs, freeHeap, largest8, wifiStatus, jobId;
  int32_t httpCode, responseBytes;
  bool resultOk;
};
struct LoopDiagSnapshot {
  uint32_t atMs, count, freeHeap, largest8, wifiStatus;
};
void cloudDiagBegin();
void cloudDiagMark(CloudDiagStep step, uint32_t jobId, int32_t httpCode=0,
                   int32_t responseBytes=0, bool resultOk=false);
void cloudDiagLoopTick();
CloudDiagSnapshot cloudDiagPrevious();
CloudDiagSnapshot cloudDiagCurrent();
LoopDiagSnapshot cloudDiagLoopPrevious();
LoopDiagSnapshot cloudDiagLoopCurrent();
