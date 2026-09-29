#pragma once
#include <Arduino.h>

struct PowerStreamApiState {
  bool configured = false;
  bool lastOk = false;
  int upperLimit = -1;
  int lowerLimit = -1;
  int batSoc = -1;
  int batInputVolt = INT32_MIN;
  int batInputCur = INT32_MIN;
  int batTemp = INT32_MIN;
  int bpType = -1;
  int interfaceConnFlag = -1;
  int supplyPriority = -1;
  int bmsReqChgVol = INT32_MIN;
  int bmsReqChgAmp = INT32_MIN;
  int invOnOff = -1;
  int wifiRssi = INT32_MIN;
  int lastHttpCode = 0;
  int lastResponseBytes = 0;
  String lastMessage;
  unsigned long lastReadMs = 0;
};

extern PowerStreamApiState psApiState;

void powerStreamApiLoad();
bool powerStreamApiSave(const String& sn, const String& accessKey, const String& secretKey);
bool powerStreamApiClear();
String powerStreamApiSerial();
String powerStreamApiAccessMasked();
bool powerStreamApiConfigured();
PowerStreamApiState powerStreamApiStateSnapshot();
bool powerStreamApiBusy();

bool powerStreamApiTest(String& message);
bool powerStreamApiReadLimits(int& upper, int& lower, String& message);
bool powerStreamApiSetLimits(int upper, int lower, String& message);

// Non-blocking web-facing queue API. HTTPS runs later from the pre-existing Arduino loop task.
void powerStreamApiLoopTick();
bool powerStreamApiQueueTest(uint32_t &jobId);
bool powerStreamApiQueueRead(uint32_t &jobId);
bool powerStreamApiQueueSetLimits(int upper,int lower,uint32_t &jobId);
String powerStreamApiJobStatusJson();
