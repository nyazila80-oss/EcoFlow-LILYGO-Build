#pragma once
#include <Arduino.h>
#include <Preferences.h>
#include <atomic>

#define FW_VERSION "2.4.5.9.36.7.15I-X509-ROOTCAUSE"

// RS485
#define RS485_TX 22
#define RS485_RX 21
#define RS485_CALLBACK 17
#define RS485_EN 19
#define BOOST_ENABLE_PIN 16

// WS2812B
#define WS2812B_DATA 4

// CAN
#define CAN_TX 27
#define CAN_RX 26
#define CAN_SPEED_MODE 23

// RS485 and CAN Boost power supply
#define ME2107_EN 16 

// SD
#define SD_MISO 2
#define SD_MOSI 15
#define SD_SCLK 14
#define SD_CS 13

// ---- Global configuration structure ----
struct Config {
  uint8_t soc = 1;
  uint16_t volt = 0;
  uint16_t chgvolt = 57600;
  uint8_t temp = 20;
  uint32_t disruntime = 1;
  uint32_t chgruntime = 1;
  uint8_t bmsChgUp = 100;
  uint8_t bmsChgDn = 10;
  bool flagCB = false;
  char serialStr[17] = "M102Z3B4ZE5H1234";
  bool txlogging = true;
  bool rxlogging = true;
  bool canTxEnabled = true;
  bool canRxEnabled = true;
  bool message3C = true;
  bool message13 = true;
  bool messageCB = true;
  bool message70 = true;
  bool message0B = true;
  bool message5C = true;
  bool message68 = true;
  bool message4F = true;
  bool message8C = true;
  bool message24 = true;
  bool acout5C = false;
  bool moschg = false;
  bool mosdis = false;
  bool batt = true; // Auto-sync BMS values form battery
  bool batteryMaster = true; // Master battery disconnect (separate from 'batt' auto-sync)
  bool lowSocGuardEnabled = true;
  uint8_t lowSocStop = 10;
  uint8_t lowSocResume = 12;
  bool lowSohGuardEnabled = false;
  uint8_t lowSohMin = 70;
};

// Global config instance
extern Config config;
extern std::atomic<bool> canHealth;

// Returns pointer to a config boolean by key name, or nullptr if unknown
bool* getTogglePtrByKey(const String& k);

// Cross-core-safe mirrors for hot CAN task gates.
bool canRxEnabledAtomic();
bool rxLoggingAtomic();
bool txLoggingAtomic();
void setCanRxEnabledAtomic(bool v);
void setRxLoggingAtomic(bool v);
void setTxLoggingAtomic(bool v);
bool canTxEnabledAtomic();
void setCanTxEnabledAtomic(bool v);
void syncCanMessageFlagsAtomic();
bool canMessageEnabledAtomic(const char* key);
bool configToggleValueAtomic(const char* key, bool &value);
bool toggleConfigMainOwner(const char* key, bool &newValue);
void setMosStatusAtomic(bool chg, bool dis);
void mosStatusAtomic(bool &chg, bool &dis);
bool acout5CAtomic();
bool flagCBAtomic();
void configuredCanLimitsAtomic(uint8_t &upper,uint8_t &lower);
void lowSocConfigSnapshot(bool &enabled, uint8_t &stop, uint8_t &resume);
bool setLowSocConfigAtomic(bool enabled, uint8_t stop, uint8_t resume);
void lowSohConfigSnapshot(bool &enabled, uint8_t &minSoh);
bool setLowSohConfigAtomic(bool enabled, uint8_t minSoh);
struct CanIdentitySnapshot { char serial[17]; uint16_t chgvolt; };
void syncCanIdentitySnapshotAtomic();
CanIdentitySnapshot canIdentitySnapshotAtomic();
struct CanBatterySnapshot {
  uint8_t soc; uint16_t volt; uint8_t temp; uint8_t upper; uint8_t lower;
  uint32_t chgruntime; uint32_t disruntime;
};
bool batteryMasterAtomic();
void setBatteryMasterAtomic(bool v);
bool battSyncAtomic();
void setBattSyncAtomic(bool v);
void syncCanBatterySnapshotAtomic();
CanBatterySnapshot canBatterySnapshotAtomic();
void setCanPowerSnapshotAtomic(int32_t inputW, int32_t outputW);
void canPowerSnapshotAtomic(int32_t &inputW, int32_t &outputW);
struct CanDerivedSnapshot { uint16_t minCellMv, maxCellMv, balanceCapMilli, fullChargeMv; };
void setCanDerivedSnapshotAtomic(uint16_t minMv,uint16_t maxMv,uint16_t balMilli,uint16_t fullMv);
CanDerivedSnapshot canDerivedSnapshotAtomic();


// ---- Storing core fields ----
void loadCoreConfig();
void saveCoreConfig();

String deviceId();
