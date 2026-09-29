#include "cloud_boot_diag.h"
#include <Arduino.h>
#include <WiFi.h>
#include <esp_attr.h>
#include <esp_heap_caps.h>

namespace {
constexpr uint32_t kMagic=0xC10D9361u;
struct StoredCloud { uint32_t magic, step, atMs, freeHeap, largest8, wifiStatus, jobId;
  int32_t httpCode, responseBytes; uint32_t resultOk, check; };
struct StoredLoop { uint32_t magic, atMs, count, freeHeap, largest8, wifiStatus, check; };
RTC_NOINIT_ATTR StoredCloud rtcCloud;
RTC_NOINIT_ATTR StoredLoop rtcLoop;
StoredCloud priorCloud{};
StoredLoop priorLoop{};
portMUX_TYPE mux=portMUX_INITIALIZER_UNLOCKED;
uint32_t checkCloud(const StoredCloud& v){return kMagic ^ v.step ^ v.atMs ^ v.freeHeap ^
  v.largest8 ^ v.wifiStatus ^ v.jobId ^ (uint32_t)v.httpCode ^
  (uint32_t)v.responseBytes ^ v.resultOk ^ 0x27B5E09Au;}
uint32_t checkLoop(const StoredLoop& v){return kMagic ^ v.atMs ^ v.count ^
  v.freeHeap ^ v.largest8 ^ v.wifiStatus ^ 0x5F0B391Cu;}
CloudDiagSnapshot snap(const StoredCloud& v){return {v.step,v.atMs,v.freeHeap,v.largest8,
  v.wifiStatus,v.jobId,v.httpCode,v.responseBytes,v.resultOk!=0};}
LoopDiagSnapshot snap(const StoredLoop& v){return {v.atMs,v.count,v.freeHeap,v.largest8,v.wifiStatus};}
}
void cloudDiagBegin(){
  if(rtcCloud.magic==kMagic && rtcCloud.step<=CLOUD_DIAG_FINISHED &&
     rtcCloud.check==checkCloud(rtcCloud)) priorCloud=rtcCloud;
  if(rtcLoop.magic==kMagic && rtcLoop.check==checkLoop(rtcLoop)) priorLoop=rtcLoop;
  portENTER_CRITICAL(&mux);
  rtcCloud={}; rtcCloud.magic=kMagic;rtcCloud.check=checkCloud(rtcCloud);
  rtcLoop={};rtcLoop.magic=kMagic;rtcLoop.check=checkLoop(rtcLoop);
  portEXIT_CRITICAL(&mux);
}
void cloudDiagMark(CloudDiagStep step,uint32_t id,int32_t code,int32_t bytes,bool ok){
  StoredCloud v{kMagic,(uint32_t)step,millis(),ESP.getFreeHeap(),
    (uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
    (uint32_t)WiFi.status(),id,code,bytes,ok?1u:0u,0};
  v.check=checkCloud(v);
  portENTER_CRITICAL(&mux);rtcCloud=v;portEXIT_CRITICAL(&mux);
}
void cloudDiagLoopTick(){
  static uint32_t last=0;
  const uint32_t now=millis();if((uint32_t)(now-last)<5000)return;last=now;
  StoredLoop v{kMagic,now,0,ESP.getFreeHeap(),
    (uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
    (uint32_t)WiFi.status(),0};
  portENTER_CRITICAL(&mux);v.count=rtcLoop.count+1;v.check=checkLoop(v);rtcLoop=v;portEXIT_CRITICAL(&mux);
}
CloudDiagSnapshot cloudDiagPrevious(){return snap(priorCloud);}
LoopDiagSnapshot cloudDiagLoopPrevious(){return snap(priorLoop);}
CloudDiagSnapshot cloudDiagCurrent(){portENTER_CRITICAL(&mux);auto v=rtcCloud;portEXIT_CRITICAL(&mux);return snap(v);}
LoopDiagSnapshot cloudDiagLoopCurrent(){portENTER_CRITICAL(&mux);auto v=rtcLoop;portEXIT_CRITICAL(&mux);return snap(v);}
