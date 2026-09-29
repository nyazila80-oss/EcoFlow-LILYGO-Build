#pragma once
#include <Arduino.h>

void recordNtpSync();
double now_seconds();

// Non-blocking NTP: initNTP() only starts SNTP when WiFi is available.
// ntpTick() completes/retries synchronization from loop().
bool initNTP(uint32_t timeoutMs = 10000);
void ntpTick();

inline bool due(uint32_t now, uint32_t &next_deadline) {
  return (int32_t)(now - next_deadline) >= 0;
}
