#pragma once
#include <Arduino.h>
#include <WiFi.h>


struct NetConfig {
  String wifiSsid;
  String wifiPass;
};

extern NetConfig net;

// ---- WiFi mode helper ----
String wifiModeToString(wifi_mode_t m);

// Persistent config
bool loadWiFiConfig();
void saveWiFiConfig();
// Async-safe control-plane update: persist credentials and defer String mutation/WiFi apply to main loop.
bool wifiSaveCredentialsDeferred(const String& ssid, const String& pass);

// AP/STA control
void startAP();
bool startSTA(uint32_t timeoutMs = 15000);
void ensureWiFi();

// Helper used by web routes after saving creds
void wifiCredsUpdatedKick();

// 9.36.7 WEB/WIFI stability diagnostics.
// A web-server rebind is requested only after a real STA/IP transition, never merely because the UI is idle.
bool wifiConsumeWebRebindRequest();
uint32_t wifiReconnectCounter();
uint32_t wifiFullRestartCounter();
uint32_t wifiRecoveryApCounter();
uint32_t wifiStaUpCounter();
uint32_t wifiLastStaUpMs();
uint32_t wifiLastStaDownMs();

// 9.36.7.6 event-level WiFi diagnostics (callback writes atomics only).
void wifiInstallEventDiagnostics();
uint32_t wifiEventStaConnectedCount();
uint32_t wifiEventStaDisconnectedCount();
uint32_t wifiEventGotIpCount();
uint32_t wifiEventLostIpCount();
uint32_t wifiLastDisconnectReason();
int32_t wifiLastDisconnectRssi();
uint32_t wifiLastEventMs();
uint32_t wifiWebRebindSuppressedCount();
bool wifiPreviousAutoReset();
uint32_t wifiAutoResetAttempts();
