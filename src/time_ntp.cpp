#include "time_ntp.h"
#include <WiFi.h>
#include <time.h>
#include <esp_timer.h>

static time_t ntp_sec = 0;
static int64_t ntp_micros = 0; // esp_timer_get_time(): monotonic 64-bit microseconds
static bool ntpStarted = false;
static bool ntpSynced = false;
static uint32_t ntpStartedMs = 0;
static uint32_t ntpNextRetryMs = 0;
static uint32_t ntpTimeoutMs = 10000;

void recordNtpSync() {
  ntp_sec = time(nullptr);
  ntp_micros = esp_timer_get_time();
}

double now_seconds() {
  if (!ntpSynced || ntp_sec < 24L * 3600L) return 0.0;
  const int64_t delta_us = esp_timer_get_time() - ntp_micros;
  return double(ntp_sec) + double(delta_us) * 1e-6;
}

bool initNTP(uint32_t timeoutMs) {
  ntpTimeoutMs = timeoutMs;
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[NTP] deferred until WiFi is connected");
    ntpNextRetryMs = millis() + 1000;
    return false;
  }
  configTime(0, 3600, "pool.ntp.org");
  ntpStarted = true;
  ntpStartedMs = millis();
  Serial.println("[NTP] sync started asynchronously");
  return false;
}

void ntpTick() {
  const uint32_t nowMs = millis();
  if (ntpSynced) return;

  if (WiFi.status() != WL_CONNECTED) {
    ntpStarted = false;
    ntpNextRetryMs = nowMs + 5000;
    return;
  }

  if (!ntpStarted) {
    if ((int32_t)(nowMs - ntpNextRetryMs) < 0) return;
    configTime(0, 3600, "pool.ntp.org");
    ntpStarted = true;
    ntpStartedMs = nowMs;
    Serial.println("[NTP] sync started asynchronously");
    return;
  }

  const time_t t = time(nullptr);
  if (t >= 24L * 3600L) {
    recordNtpSync();
    ntpSynced = true;
    Serial.printf("[NTP] synced: %ld\n", (long)ntp_sec);
    return;
  }

  if (nowMs - ntpStartedMs >= ntpTimeoutMs) {
    ntpStarted = false;
    ntpNextRetryMs = nowMs + 60000;
    Serial.println("[NTP] timeout; retry scheduled in 60 s");
  }
}
