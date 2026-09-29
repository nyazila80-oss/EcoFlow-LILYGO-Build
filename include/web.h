#pragma once

#include <Arduino.h>
#include <ESPAsyncWebServer.h>

// WebSocket + ring-buffer logging service
void webInit(AsyncWebServer& server);

// Static pages + utility endpoints (SPIFFS, CAN stats, reboot, update_param, 404)
void webSetupStaticRoutes(AsyncWebServer& server);

void setupServerRoutes(AsyncWebServer &server);

// Call from loop() (replaces the old inline flush/ping/BMS push block)
void webTick();

// Logging APIs used by CAN/EcoFlow modules
void streamCanLog(const char* message);
void streamDebug(const char* message);

// AUDIT20.1 shared remote-auth helpers (used by OTA and WebSocket setup).
const char* remoteAuthUser();
const char* remoteAuthPassword();
bool remoteAuthRequest(AsyncWebServerRequest* request);
// 9.36.4: OTA stays password-protected while local WebUI/API auth is disabled for A/B diagnosis.
bool remoteOtaAuthRequest(AsyncWebServerRequest* request);
bool remoteMutationAllowed(AsyncWebServerRequest* request);

// Mount filesystem once and initialize release diagnostics.
void filesystemInitStatus();

// Filesystem release diagnostics.
bool filesystemReady();
bool filesystemVersionMatches();
const char* filesystemStatusString();

// 9.36.7.5 WebSocket/Web lifecycle diagnostics.
uint32_t webWsLogClients();
uint32_t webWsBmsClients();
uint32_t webWsDebugClients();
uint32_t webWsCleanupRuns();
uint32_t webLoopMaxGapMs();
uint32_t webLoopLastGapMs();
uint32_t webLowHeapCleanupCount();

// 9.36.7.9 regression isolation: legacy-like runtime A/B (JK-BLE remains available).
bool regressionLegacyConfigured();
bool regressionLegacyApplied();
bool regressionLegacySet(bool enabled);

void webCloudQuiesceBegin();
void webCloudQuiesceEnd();
