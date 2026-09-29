#pragma once
#include <Arduino.h>

class JKPBBms;

struct Config;
extern Config config;

// BMS instance exposed for MQTT/CAN/Web
extern JKPBBms bms;

// Public API
void mqttInit(const String& devId);
void mqttLoopTick();
void mqttMarkDiscoveryDirty();
// Safe from AsyncWebServer: actual String/config reload is performed by mqttLoopTick().
void mqttRequestConfigReload();
bool mqttSaveConfigDeferred(const String& host,uint16_t port,const String& user,const String& pass,const String& base,bool enabled);
bool mqttBaseValid(const String& base);
bool loadMqttConfig();
void mqttDisconnectClean();
