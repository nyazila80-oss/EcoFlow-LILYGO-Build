#include "mqtt.h"
#include "config.h"
#include "can.h"
#include "ecoflow.h"          // for getPeerSerial()

#include <WiFi.h>
#include <PubSubClient.h>
#include <Preferences.h>
#include <freertos/semphr.h>
#include "bms.h"
#include <atomic>

// Persistent config
extern std::atomic<bool> canHealth;        // from main/can layer

// ---------- MQTT + HA Discovery --------------------
struct MqttConfig {
  String host;
  uint16_t port = 1883;
  String user;
  String pass;
  String base = "ecoflow_bridge";
  bool enabled = false;
};

static MqttConfig mqttCfg;

static WiFiClient mqttNet;
static PubSubClient mqttClient(mqttNet);

static bool mqttDiscoverySent = false;
static bool mqttDiscoveryPublishing = false; // only touched from MQTT loop
static bool mqttDiscoveryPublishFailed = false;
static uint32_t mqttLastConnAttempt = 0;
static uint32_t mqttLastStatePub = 0;
static std::atomic<bool> mqttConfigReloadPending{false};
static uint32_t mqttNextReloadRetryMs=0; // main-loop only

static const uint32_t MQTT_RECONNECT_MS = 5000;
static const uint32_t MQTT_STATE_MS     = 2000; // publish state every 2s

static StaticSemaphore_t mqttCfgNvsMutexBuf;
static SemaphoreHandle_t mqttCfgNvsMutex=xSemaphoreCreateMutexStatic(&mqttCfgNvsMutexBuf);
static SemaphoreHandle_t mqttCfgNvsLock(){return mqttCfgNvsMutex;}

static String mqttDeviceId;
static String mqttDevName;

// AUDIT19.15.18: cache hot-path topics and reuse the state JSON capacity.
// This avoids repeated temporary String allocation every 2 seconds.
static String topicState, topicAvail;
static String topicBatteryState, topicMosChgState, topicMosDisState, topicCanTxState, topicCanRxState;
static String topicBatterySet, topicMosChgSet, topicMosDisSet, topicCanTxSet, topicCanRxSet;

bool mqttBaseValid(const String& base) {
  if(base.isEmpty() || base.length()>64 || base[0]=='/' || base[base.length()-1]=='/')return false;
  bool slash=false;
  for(size_t i=0;i<base.length();++i){
    const char c=base[i];
    if(c=='/'){if(slash)return false;slash=true;continue;}
    slash=false;
    const bool asciiAlnum=(c>='A'&&c<='Z')||(c>='a'&&c<='z')||(c>='0'&&c<='9');
    if(!asciiAlnum&&c!='_'&&c!='-'&&c!='.')return false;
  }
  return true;
}

static void rebuildHotTopics() {
  const String root = mqttCfg.base + "/" + mqttDeviceId;
  topicState = root + "/state";
  topicAvail = root + "/availability";
  const String sw = root + "/switch/";
  topicBatteryState = sw + "battery_master/state"; topicBatterySet = sw + "battery_master/set";
  topicMosChgState  = sw + "mos_chg/state";        topicMosChgSet  = sw + "mos_chg/set";
  topicMosDisState  = sw + "mos_dis/state";        topicMosDisSet  = sw + "mos_dis/set";
  topicCanTxState   = sw + "can_tx/state";         topicCanTxSet   = sw + "can_tx/set";
  topicCanRxState   = sw + "can_rx/state";         topicCanRxSet   = sw + "can_rx/set";
}


// topic helpers
static String t_state() {
  return mqttCfg.base + "/" + mqttDeviceId + "/state";
}
static String t_switch_state(const String& key) {
  return mqttCfg.base + "/" + mqttDeviceId + "/switch/" + key + "/state";
}
static String t_switch_set(const String& key) {
  return mqttCfg.base + "/" + mqttDeviceId + "/switch/" + key + "/set";
}
static String t_avail() {
  return mqttCfg.base + "/" + mqttDeviceId + "/availability";
}

static const char* onOff(bool v){ return v ? "ON" : "OFF"; }

static void mqttPublish(const String& topic, const String& payload, bool retain = false) {
  const bool ok=mqttClient.connected() && mqttClient.publish(topic.c_str(), payload.c_str(), retain);
  if(mqttDiscoveryPublishing && !ok)mqttDiscoveryPublishFailed=true;
}

static String haDeviceJson() {
  String d = "{";
  d += "\"identifiers\":[\"" + mqttDeviceId + "\"],";
  d += "\"name\":\"" + mqttDevName + "\",";
  d += "\"manufacturer\":\"RGarrett93\",";
  d += "\"model\":\"EcoFlow PowerStream CAN/BMS LFP Bridge\",";
  d += "\"sw_version\":\"";
  d += String(FW_VERSION);
  d += "\"";
  d += "}";
  return d;
}

static void haPublishSensor(const String& objId,
                            const String& name,
                            const String& unit,
                            const String& devClass,
                            const String& stateClass,
                            const String& valueTmpl) {
  String topic = "homeassistant/sensor/" + mqttDeviceId + "_" + objId + "/config";

  String payload = "{";
  payload += "\"name\":\"" + name + "\",";
  payload += "\"uniq_id\":\"" + mqttDeviceId + "_" + objId + "\",";
  payload += "\"stat_t\":\"" + t_state() + "\",";
  payload += "\"avty_t\":\"" + t_avail() + "\",";
  payload += "\"pl_avail\":\"online\",";
  payload += "\"pl_not_avail\":\"offline\",";
  payload += "\"val_tpl\":\"" + valueTmpl + "\",";
  if (unit.length())       payload += "\"unit_of_meas\":\"" + unit + "\",";
  if (devClass.length())   payload += "\"dev_cla\":\"" + devClass + "\",";
  if (stateClass.length()) payload += "\"stat_cla\":\"" + stateClass + "\",";
  payload += "\"dev\":" + haDeviceJson();
  payload += "}";

  mqttPublish(topic, payload, true);
}

static void haPublishSwitch(const String& key, const String& friendlyName) {
  String topic = "homeassistant/switch/" + mqttDeviceId + "_" + key + "/config";

  String payload = "{";
  payload += "\"name\":\"" + friendlyName + "\",";
  payload += "\"uniq_id\":\"" + mqttDeviceId + "_" + key + "\",";
  payload += "\"cmd_t\":\"" + t_switch_set(key) + "\",";
  payload += "\"stat_t\":\"" + t_switch_state(key) + "\",";
  payload += "\"avty_t\":\"" + t_avail() + "\",";
  payload += "\"pl_avail\":\"online\",";
  payload += "\"pl_not_avail\":\"offline\",";
  payload += "\"pl_on\":\"ON\",";
  payload += "\"pl_off\":\"OFF\",";
  payload += "\"dev\":" + haDeviceJson();
  payload += "}";

  mqttPublish(topic, payload, true);
}

static void mqttPublishDiscovery() {
  if (!mqttCfg.enabled) return;
  if (!mqttClient.connected()) return;
  mqttDiscoveryPublishFailed=false;
  mqttDiscoveryPublishing=true;

  // BMS metrics
  haPublishSensor("soc",         "BMS SoC",          "%",  "battery",    "measurement", "{{ value_json.soc }}");
  haPublishSensor("voltage",     "BMS Voltage",      "V",  "voltage",    "measurement", "{{ value_json.voltage }}");
  haPublishSensor("current",     "BMS Current",      "A",  "current",    "measurement", "{{ value_json.current }}");
  haPublishSensor("temp",        "BMS Temperature",  "°C", "temperature","measurement", "{{ value_json.temperature }}");
  haPublishSensor("chg_runtime", "Charge Runtime",   "min","",           "measurement", "{{ value_json.chgruntime }}");
  haPublishSensor("dis_runtime", "Discharge Runtime","min","",           "measurement", "{{ value_json.disruntime }}");

  // NEW: PS info from state JSON
  haPublishSensor("ps_serial", "PS Serial Number", "", "", "",
                  "{{ value_json.ps_serial_number }}");
  haPublishSensor("ps_online", "PS Online", "", "", "",
                  "{{ value_json.ps_online }}");

  // Switches
  haPublishSwitch("battery_master", "Battery Master Switch");
  haPublishSwitch("mos_chg",        "MOSFET Charge");
  haPublishSwitch("mos_dis",        "MOSFET Discharge");
  haPublishSwitch("can_tx",         "CAN TX Enabled");
  haPublishSwitch("can_rx",         "CAN RX Enabled");

  mqttDiscoveryPublishing=false;
  mqttDiscoverySent=!mqttDiscoveryPublishFailed;
  Serial.printf("[MQTT] Discovery %s\n",mqttDiscoverySent?"complete":"incomplete; retry pending");
}

static void mqttPublishStates() {
  if (!mqttCfg.enabled) return;
  if (!mqttClient.connected()) return;

  const BmsSafetySnapshot live = bmsSafetySnapshotAtomic();
  const int   soc     = (int)live.soc;
  const float voltage = live.voltageMilliV / 1000.0f;
  const float current = live.currentMilliA / 1000.0f;
  const int   temp    = live.tempDeciC / 10;
  const CanBatterySnapshot mqttBatt=canBatterySnapshotAtomic(); bool mqttMosChg=false,mqttMosDis=false; mosStatusAtomic(mqttMosChg,mqttMosDis);
  const int   chg     = (int)mqttBatt.chgruntime;
  const int   dis     = (int)mqttBatt.disruntime;
  const String psStr  = getPeerSerial();
  // C4 serial bytes are printable but may include JSON quote/backslash.
  // Escape them without allocating in this periodic publication path.
  char psJson[33]; size_t psLen=0;
  for(size_t i=0;i<psStr.length() && i<16;++i){
    const unsigned char c=(unsigned char)psStr[i];
    if(c=='"'||c=='\\')psJson[psLen++]='\\';
    psJson[psLen++]=(c<0x20)?'?':(char)c;
  }
  psJson[psLen]='\0';

  // Fixed stack buffer: no periodic Arduino String growth/fragmentation.
  char json[512];
  const int n = snprintf(json, sizeof(json),
    "{\"soc\":%d,\"voltage\":%.3f,\"current\":%.3f,\"temperature\":%d,"
    "\"chgruntime\":%d,\"disruntime\":%d,\"batteryMaster\":%s,"
    "\"chgMOSFET\":%s,\"disMOSFET\":%s,\"canTxEnabled\":%s,\"canRxEnabled\":%s,"
    "\"ps_serial_number\":\"%s\",\"ps_online\":\"%s\"}",
    soc, voltage, current, temp, chg, dis,
    batteryMasterAtomic() ? "true" : "false",
    mqttMosChg ? "true" : "false",
    mqttMosDis ? "true" : "false",
    canTxEnabledAtomic() ? "true" : "false",
    canRxEnabledAtomic() ? "true" : "false",
    psJson, canHealth.load(std::memory_order_acquire) ? "connected" : "disconnected");

  if (n <= 0 || (size_t)n >= sizeof(json)) {
    Serial.println("[MQTT] state JSON overflow prevented");
    return;
  }

  mqttClient.publish(topicState.c_str(), json, false);
  mqttClient.publish(topicBatteryState.c_str(), onOff(batteryMasterAtomic()), true);
  mqttClient.publish(topicMosChgState.c_str(), onOff(mqttMosChg), true);
  mqttClient.publish(topicMosDisState.c_str(), onOff(mqttMosDis), true);
  mqttClient.publish(topicCanTxState.c_str(), onOff(canTxEnabledAtomic()), true);
  mqttClient.publish(topicCanRxState.c_str(), onOff(canRxEnabledAtomic()), true);
  mqttClient.publish(topicAvail.c_str(), "online", true);
}

static void mqttOnMessage(char* topic, byte* payload, unsigned int length) {
  String t(topic);
  String p;
  p.reserve(length + 1);
  for (unsigned int i = 0; i < length; i++) p += (char)payload[i];
  p.trim();

  auto isOn  = [&](const String& s){ return s == "ON"  || s == "on"  || s == "1" || s == "true"; };
  auto isOff = [&](const String& s){ return s == "OFF" || s == "off" || s == "0" || s == "false"; };

  if (t == t_switch_set("battery_master")) {
    if (isOn(p))  setBatteryMasterAtomic(true);
    if (isOff(p)) setBatteryMasterAtomic(false);
    return;
  }

  if (t == t_switch_set("mos_chg") || t == t_switch_set("mos_dis")) {
    // JK-PB adapter is intentionally telemetry-only. Never mutate the displayed
    // MOS state from MQTT; it is refreshed only from validated BMS telemetry.
    Serial.printf("[MQTT] Ignored %s: JK-PB MOS control is read-only\n", t.c_str());
    return;
  }

  if (t == t_switch_set("can_tx")) {
    if (isOn(p))  setCanTxEnabledAtomic(true);
    if (isOff(p)) setCanTxEnabledAtomic(false);
    return;
  }

  if (t == t_switch_set("can_rx")) {
    if (isOn(p))  setCanRxEnabledAtomic(true);
    if (isOff(p)) setCanRxEnabledAtomic(false);
    return;
  }
}

static bool mqttSubscribeTopics() {
  bool ok=mqttClient.subscribe(topicBatterySet.c_str());
  ok=mqttClient.subscribe(topicMosChgSet.c_str()) && ok;
  ok=mqttClient.subscribe(topicMosDisSet.c_str()) && ok;
  ok=mqttClient.subscribe(topicCanTxSet.c_str()) && ok;
  ok=mqttClient.subscribe(topicCanRxSet.c_str()) && ok;
  return ok;
}

void mqttDisconnectClean() {
  if (mqttClient.connected()) {
    mqttPublish(topicAvail, "offline", true);
    mqttClient.disconnect();
  }
}

bool loadMqttConfig() {
  SemaphoreHandle_t m=mqttCfgNvsLock(); if(!m || xSemaphoreTake(m,pdMS_TO_TICKS(250))!=pdTRUE)return false;
  struct Unlock{SemaphoreHandle_t m;~Unlock(){xSemaphoreGive(m);}} unlock{m};
  Preferences p;
  // A fresh device has no MQTT namespace yet; open once read/write to create
  // it, then use normal read-only opens on later reloads.
  if(!p.begin("mqtt", true) && !p.begin("mqtt", false))return false;
  mqttCfg.host    = p.getString("host", "");
  mqttCfg.port    = p.getUShort("port", 1883);
  mqttCfg.user    = p.getString("user", "");
  mqttCfg.pass    = p.getString("pass", "");
  mqttCfg.base    = p.getString("base", "ecoflow_bridge");
  mqttCfg.enabled = p.getBool("enabled", false);
  p.end();

  if (mqttCfg.base.length() == 0) mqttCfg.base = "ecoflow_bridge";
  if(!mqttBaseValid(mqttCfg.base))mqttCfg.enabled=false;
  rebuildHotTopics();
  return true;
}

static void mqttEnsureConnected() {
  if (!mqttCfg.enabled) {
    mqttDisconnectClean();
    return;
  }

  if (WiFi.status() != WL_CONNECTED) return;
  if (mqttCfg.host.length() == 0) return;

  if (mqttClient.connected()) return;

  uint32_t now = millis();
  if (now - mqttLastConnAttempt < MQTT_RECONNECT_MS) return;
  mqttLastConnAttempt = now;

  mqttClient.setServer(mqttCfg.host.c_str(), mqttCfg.port);
  mqttClient.setCallback(mqttOnMessage);

  String cid = mqttDeviceId + "_bridge";

  bool ok;
  if (mqttCfg.user.length()) {
    ok = mqttClient.connect(cid.c_str(), mqttCfg.user.c_str(), mqttCfg.pass.c_str(),
                            topicAvail.c_str(), 1, true, "offline");
  } else {
    ok = mqttClient.connect(cid.c_str(), topicAvail.c_str(), 1, true, "offline");
  }

  if (ok) {
    mqttDiscoverySent = false;
    if(!mqttSubscribeTopics()){
      Serial.println("[MQTT] Subscribe failed; retrying connection");
      mqttClient.disconnect();
      return;
    }
    mqttPublish(topicAvail, "online", true);
    mqttPublishDiscovery();
    mqttPublishStates();
    Serial.println("[MQTT] Connected");
  } else {
    Serial.printf("[MQTT] Connect failed rc=%d\n", mqttClient.state());
  }
}


bool mqttSaveConfigDeferred(const String& host,uint16_t port,const String& user,const String& pass,const String& base,bool enabled){
  if(!mqttBaseValid(base))return false;
  SemaphoreHandle_t mtx=mqttCfgNvsLock();
  if(!mtx || xSemaphoreTake(mtx,pdMS_TO_TICKS(250))!=pdTRUE)return false;
  struct Unlock{SemaphoreHandle_t m;~Unlock(){xSemaphoreGive(m);}} unlock{mtx};
  Preferences p;if(!p.begin("mqtt",false))return false;
  p.putString("host",host);p.putUShort("port",port);p.putString("user",user);p.putString("pass",pass);p.putString("base",base);p.putBool("enabled",enabled);p.end();
  Preferences r;if(!r.begin("mqtt",true))return false;
  bool ok=r.getString("host","")==host && r.getUShort("port",0)==port && r.getString("user","")==user && r.getString("pass","")==pass && r.getString("base","")==base && r.getBool("enabled",!enabled)==enabled;r.end();
  if(ok)mqttRequestConfigReload();return ok;
}

void mqttRequestConfigReload() { mqttConfigReloadPending.store(true, std::memory_order_release); }

void mqttMarkDiscoveryDirty() {
  mqttDiscoverySent = false;
  mqttLastConnAttempt = 0;
}

void mqttInit(const String& devId) {
  mqttDeviceId = devId;
  mqttDevName  = "EcoFlow Bridge " + mqttDeviceId;

  if(!loadMqttConfig())mqttRequestConfigReload();

  mqttClient.setBufferSize(1024);
  mqttDiscoverySent     = false;
  mqttLastConnAttempt   = 0;
  mqttLastStatePub      = 0;
}

void mqttLoopTick() {
  if (mqttConfigReloadPending.load(std::memory_order_acquire) &&
      (int32_t)(millis()-mqttNextReloadRetryMs)>=0 &&
      mqttConfigReloadPending.exchange(false, std::memory_order_acq_rel)) {
    const String previousAvailability=topicAvail;
    if(!loadMqttConfig()){
      // A concurrent NVS write or transient NVS error must not consume the
      // reload request or needlessly disconnect the existing broker.
      mqttRequestConfigReload();
      mqttNextReloadRetryMs=millis()+1000;
      return;
    }
    if(mqttClient.connected()){
      mqttClient.publish(previousAvailability.c_str(),"offline",true);
      mqttClient.disconnect();
    }
    mqttNextReloadRetryMs=0;
    mqttMarkDiscoveryDirty();
  }
  mqttEnsureConnected();

  if (mqttClient.connected()) {
    mqttClient.loop();

    uint32_t nowMs = millis();
    if (nowMs - mqttLastStatePub >= MQTT_STATE_MS) {
      mqttLastStatePub = nowMs;
      mqttPublishStates();
      if (!mqttDiscoverySent) mqttPublishDiscovery();
    }
  }
}
