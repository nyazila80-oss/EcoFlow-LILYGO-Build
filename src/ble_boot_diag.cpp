#include <Arduino.h>
#include <esp_attr.h>
#include <esp_system.h>
#include <esp_heap_caps.h>
#include "ble_boot_diag.h"

static constexpr uint32_t kMagic = 0xB1E93611u;
struct Breadcrumb { uint32_t magic, stage, check; };
RTC_NOINIT_ATTR static Breadcrumb sRtc;
static constexpr uint32_t kHttpMagic=0xC1A93611u;
struct HttpBreadcrumb {
  uint32_t magic, active[4], lastRoute, freeHeap, largest8, atMs, check;
};
RTC_NOINIT_ATTR static HttpBreadcrumb sHttpRtc;
static CrashHttpSnapshot sPrevHttp{};
static uint32_t sPrevious = 0;
static uint32_t sReset = 0;
static portMUX_TYPE sMux = portMUX_INITIALIZER_UNLOCKED;

void bleBootDiagBegin() {
  sReset = static_cast<uint32_t>(esp_reset_reason());
  sPrevHttp={};
  uint32_t check=kHttpMagic;
  for(uint32_t v:sHttpRtc.active) check ^= v;
  check ^= sHttpRtc.lastRoute ^ sHttpRtc.freeHeap ^ sHttpRtc.largest8 ^ sHttpRtc.atMs;
  if(sHttpRtc.magic==kHttpMagic && sHttpRtc.check==check) {
    for(uint32_t i=0;i<4;i++) if(sHttpRtc.active[i]) sPrevHttp.activeMask |= 1u<<i;
    sPrevHttp.lastRoute=sHttpRtc.lastRoute;
    sPrevHttp.freeHeap=sHttpRtc.freeHeap;
    sPrevHttp.largest8=sHttpRtc.largest8;
    sPrevHttp.atMs=sHttpRtc.atMs;
  }
  sHttpRtc={}; sHttpRtc.magic=kHttpMagic;
  sHttpRtc.check=kHttpMagic;
  if (sRtc.magic == kMagic && sRtc.check == (sRtc.stage ^ kMagic) && sRtc.stage <= BLE_BOOT_ADVERTISING)
    sPrevious = sRtc.stage;
  else sPrevious = BLE_BOOT_NOT_REACHED;
  bleBootDiagMark(BLE_BOOT_NOT_REACHED);
}
void bleBootDiagMark(uint32_t stage) {
  portENTER_CRITICAL(&sMux);
  sRtc.magic = kMagic;
  sRtc.stage = stage;
  sRtc.check = stage ^ kMagic;
  portEXIT_CRITICAL(&sMux);
}
uint32_t bleBootDiagCurrent() {
  portENTER_CRITICAL(&sMux);
  const uint32_t stage = sRtc.stage;
  portEXIT_CRITICAL(&sMux);
  return stage;
}
uint32_t bleBootDiagPrevious() { return sPrevious; }
uint32_t bleBootDiagResetReason() { return sReset; }

static void updateHttpCheck() {
  uint32_t check=kHttpMagic;
  for(uint32_t v:sHttpRtc.active) check ^= v;
  sHttpRtc.check=check ^ sHttpRtc.lastRoute ^ sHttpRtc.freeHeap ^ sHttpRtc.largest8 ^ sHttpRtc.atMs;
}
void crashHttpEnter(CrashHttpRoute route) {
  const unsigned i=static_cast<unsigned>(route); if(i>=4)return;
  const uint32_t freeHeap=heap_caps_get_free_size(MALLOC_CAP_8BIT);
  const uint32_t largest=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  portENTER_CRITICAL(&sMux);
  if(sHttpRtc.active[i]<UINT32_MAX) ++sHttpRtc.active[i];
  sHttpRtc.lastRoute=i+1; sHttpRtc.freeHeap=freeHeap;
  sHttpRtc.largest8=largest; sHttpRtc.atMs=millis(); updateHttpCheck();
  portEXIT_CRITICAL(&sMux);
}
void crashHttpLeave(CrashHttpRoute route) {
  const unsigned i=static_cast<unsigned>(route); if(i>=4)return;
  portENTER_CRITICAL(&sMux);
  if(sHttpRtc.active[i]) --sHttpRtc.active[i];
  updateHttpCheck(); portEXIT_CRITICAL(&sMux);
}
CrashHttpSnapshot crashHttpCurrent() {
  CrashHttpSnapshot out{};
  portENTER_CRITICAL(&sMux);
  for(uint32_t i=0;i<4;i++) if(sHttpRtc.active[i]) out.activeMask |= 1u<<i;
  out.lastRoute=sHttpRtc.lastRoute; out.freeHeap=sHttpRtc.freeHeap;
  out.largest8=sHttpRtc.largest8; out.atMs=sHttpRtc.atMs;
  portEXIT_CRITICAL(&sMux);
  return out;
}
CrashHttpSnapshot crashHttpPrevious() { return sPrevHttp; }
