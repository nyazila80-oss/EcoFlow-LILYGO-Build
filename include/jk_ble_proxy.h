#pragma once
#include <Arduino.h>

// Experimental JK-BMS BLE transparent proxy.
// Phase 1: local BLE repeater only. No Internet/BLE tunnelling.
void jkBleProxyInit();
void jkBleProxyTick();
bool jkBleProxyBmsConnected();
bool jkBleProxyAppConnected();
bool jkBleProxyInitialized();
// Read-only scalar snapshot for the network boot/bridge diagnostic.
struct JkBleStatusDiag {
  bool appConnected=false, bmsConnected=false, initialized=false;
  bool auxReserved=false, bridgeFault=false, eventsPending=false;
  bool safeHold=false, startupEnabled=false;
  uint32_t appToBmsDrops=0, bmsToAppDrops=0, eventDrops=0;
  uint32_t bridgeFaults=0, forwardWriteFails=0, queueFlushes=0;
  uint32_t connectAttempts=0, bridgeReadyCount=0;
  int lastBmsDisconnectReason=0;
};
JkBleStatusDiag jkBleProxyStatusDiag();
// 9.36.7.8: boot-time isolation switch for controlled A/B testing.
// Changing the persisted value requires reboot; no live NimBLE deinit is attempted.
bool jkBleStartupEnabled();
bool jkBleStartupAppliedEnabled();
bool jkBleSetStartupEnabled(bool enabled);

// Shared BLE arbitration for short-lived auxiliary central connections (e.g. PowerStream).
// Reservation suppresses JK-proxy advertising/reconnect contention; caller must release.
bool jkBleProxyReserveAuxConnection();
void jkBleProxyReleaseAuxConnection();
bool jkBleProxyAuxReserved();
bool jkBleProxyAuxSlotReady();
// True when a NimBLE callback has published a JK session transition that the main loop has not serialized yet.
bool jkBleProxyEventsPending();

// Last owner-side auxiliary slot handoff. Zero means no snapshot in this boot.
struct JkBleAuxMemoryDiag {
  uint32_t beforeStopFree=0, beforeStopLargest=0;
  uint32_t afterStopFree=0, afterStopLargest=0;
  uint32_t afterDecisionFree=0, afterDecisionLargest=0;
  uint32_t generation=0;
};
JkBleAuxMemoryDiag jkBleProxyAuxMemoryDiag();

// 9.36.7.4: bounded memory-lifecycle diagnostics; scalar snapshots only.
struct JkBleMemoryDiag {
  uint32_t preInitFree=0, preInitLargest=0;
  uint32_t postNimbleFree=0, postNimbleLargest=0;
  uint32_t postServerFree=0, postServerLargest=0;
  uint32_t postGattFree=0, postGattLargest=0;
  uint32_t postClientFree=0, postClientLargest=0;
  uint32_t postAdvFree=0, postAdvLargest=0;
  uint32_t minFree=0;
};
JkBleMemoryDiag jkBleProxyMemoryDiag();
