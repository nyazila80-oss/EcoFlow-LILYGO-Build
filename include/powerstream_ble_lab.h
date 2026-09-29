#pragma once
#include <Arduino.h>

void powerStreamBleLabInit();
void powerStreamBleLabTick();
bool powerStreamBleLabConfigured();
bool powerStreamBleLabEnabled();
bool powerStreamBleLabSaveConfig(const String& mac,const String& sn,const String& uid,bool enabled,int addrType=0);
bool powerStreamBleLabVerifyUserId(const String& candidate, bool& matches);
String powerStreamBleLabStatusJson();
bool powerStreamBleLabSetSupplyMode(int mode,String& message); // queues one-shot operation; 0=supply, 1=storage

bool powerStreamBleLabProbeAuth(String& message); // 9.36.7.10 diagnostic: connect/GATT/auth only, never sends supply/storage
