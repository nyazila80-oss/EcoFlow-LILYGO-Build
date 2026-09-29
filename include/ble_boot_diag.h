#pragma once
#include <stdint.h>

// Fixed-size RTC breadcrumb: survives a software reset without flash writes.
void bleBootDiagBegin();
void bleBootDiagMark(uint32_t stage);
uint32_t bleBootDiagCurrent();
uint32_t bleBootDiagPrevious();
uint32_t bleBootDiagResetReason();

// Candidate: a bounded RTC breadcrumb for synchronous HTTP callback activity.
enum CrashHttpRoute : uint8_t { CRASH_HTTP_BMS=0, CRASH_HTTP_PS_STATUS=1,
  CRASH_HTTP_FS_PAGE=2, CRASH_HTTP_NET_HEALTH=3 };
struct CrashHttpSnapshot {
  uint32_t activeMask, lastRoute, freeHeap, largest8, atMs;
};
void crashHttpEnter(CrashHttpRoute route);
void crashHttpLeave(CrashHttpRoute route);
CrashHttpSnapshot crashHttpPrevious();
CrashHttpSnapshot crashHttpCurrent();

enum : uint32_t {
  BLE_BOOT_NOT_REACHED = 0,
  BLE_BOOT_PRE_INIT = 1,
  BLE_BOOT_WIFI_PS_OK = 2,
  BLE_BOOT_NIMBLE_ENTER = 3,
  BLE_BOOT_NIMBLE_RETURN = 4,
  BLE_BOOT_ADVERTISING = 5
};
