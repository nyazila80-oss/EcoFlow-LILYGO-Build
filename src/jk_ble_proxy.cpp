#include "jk_ble_proxy.h"
#include "ble_boot_diag.h"
#include <NimBLEDevice.h>
#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_heap_caps.h>
#include <atomic>
#include <Preferences.h>

// AUDIT19.15.16-LOG-HEAP-GUARD: no BLE scanning at all. The real JK address and address
// type were verified on hardware, so direct reconnect removes the most crash-
// prone/high-duty part of 19.6-19.8. BLE init is deferred until the network
// stack has had time to settle.
static constexpr const char* JK_TARGET_MAC = "A4:C1:38:09:4B:C2";
static constexpr uint8_t JK_TARGET_ADDR_TYPE = 0;
static constexpr const char* JK_PROXY_NAME = "603134845005019-00";
static constexpr const char* JK_SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb";
static constexpr const char* JK_CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb";
static constexpr uint32_t BLE_BOOT_GRACE_MS = 20000;
static constexpr uint32_t JK_RETRY_MS = 20000;
static constexpr uint32_t BLE_MIN_HEAP_BEFORE_INIT = 20000;
static constexpr uint32_t BLE_MIN_HEAP_BEFORE_CONNECT = 8000;
static constexpr uint32_t BLE_MIN_LARGEST8_BEFORE_INIT = 12000;
static constexpr uint32_t BLE_MIN_LARGEST8_BEFORE_CONNECT = 6000;

enum class BleState : uint8_t { NOT_STARTED, IDLE, CONNECTED, BACKOFF };
static BleState sState = BleState::NOT_STARTED;
static NimBLEServer* sServer = nullptr;
static NimBLECharacteristic* sLocalChar = nullptr;
static NimBLEClient* sClient = nullptr;
static NimBLERemoteCharacteristic* sRemoteChar = nullptr;
static std::atomic_bool sBmsConnected{false};
static std::atomic_bool sAppConnected{false};
static std::atomic_bool sAuxReserved{false};
static std::atomic_bool sInitialized{false};
static bool sInitAttempted = false;
static std::atomic_bool sSafeHold{false};
static std::atomic_bool sStartupEnabled{true};
static std::atomic_bool sStartupAppliedEnabled{true};
static bool sStartupCfgLoaded=false;
static JkBleMemoryDiag sMemDiag;
static inline void jkMemSnap(uint32_t &fr,uint32_t &lg){fr=ESP.getFreeHeap();lg=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);sMemDiag.minFree=ESP.getMinFreeHeap();}
static std::atomic_bool sRestartAdvertisingPending{false};
// AUDIT20.4.5.9.22: all advertising start/stop operations belong to the
// Arduino-loop JK BLE owner. Auxiliary workers only request a reservation and
// wait for the owner to close the connectable proxy window.
enum class AuxReserveState : uint8_t { IDLE=0, REQUESTED=1, PROCESSING=2, GRANTED=3, DENIED=4 };
static std::atomic<AuxReserveState> sAuxReserveState{AuxReserveState::IDLE};
static constexpr uint32_t AUX_RESERVE_OWNER_TIMEOUT_MS = 750;
static std::atomic<uint32_t> sAuxBeforeFree{0},sAuxBeforeLargest{0},sAuxAfterStopFree{0},sAuxAfterStopLargest{0},sAuxAfterDecisionFree{0},sAuxAfterDecisionLargest{0},sAuxDiagGeneration{0};
static void auxMemSnap(std::atomic<uint32_t>&f,std::atomic<uint32_t>&l){f=ESP.getFreeHeap();l=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);}

// AUDIT19.15.26: preserve callback event ordering across the NimBLE host task
// and Arduino loop task. Volatile flags can lose ordering (disconnect followed
// by reconnect before loop() runs). A fixed FIFO avoids allocation and keeps
// all session state changes serialized in jkBleProxyTick().
enum class BleEventType : uint8_t { APP_CONNECT, APP_DISCONNECT, BMS_CONNECT_FAIL, BMS_DISCONNECT };
struct BleEvent { BleEventType type; int reason; };
static constexpr uint8_t BLE_EVENT_QUEUE_DEPTH = 16;
static BleEvent sBleEvents[BLE_EVENT_QUEUE_DEPTH];
static uint8_t sBleEventHead=0, sBleEventTail=0, sBleEventCount=0, sBleEventHighWater=0;
static std::atomic_uint32_t sBleEventDrops{0};
static volatile bool sBleEventOverflowPending=false;
static portMUX_TYPE sBleEventMux = portMUX_INITIALIZER_UNLOCKED;
static bool enqueueBleEvent(BleEventType type, int reason=0){
  bool ok=false;
  portENTER_CRITICAL(&sBleEventMux);
  if(sBleEventCount < BLE_EVENT_QUEUE_DEPTH){
    sBleEvents[sBleEventHead] = {type, reason};
    sBleEventHead=(uint8_t)((sBleEventHead+1U)%BLE_EVENT_QUEUE_DEPTH);
    ++sBleEventCount; if(sBleEventCount>sBleEventHighWater)sBleEventHighWater=sBleEventCount;
    ok=true;
  } else { ++sBleEventDrops; sBleEventOverflowPending=true; }
  portEXIT_CRITICAL(&sBleEventMux);
  return ok;
}
static bool takeBleEvent(BleEvent& ev){
  bool ok=false;
  portENTER_CRITICAL(&sBleEventMux);
  if(sBleEventCount){ ev=sBleEvents[sBleEventTail]; sBleEventTail=(uint8_t)((sBleEventTail+1U)%BLE_EVENT_QUEUE_DEPTH); --sBleEventCount; ok=true; }
  portEXIT_CRITICAL(&sBleEventMux);
  return ok;
}
static bool bleEventsPending(){
  portENTER_CRITICAL(&sBleEventMux); const bool pending=(sBleEventCount!=0)||sBleEventOverflowPending; portEXIT_CRITICAL(&sBleEventMux); return pending;
}
// Keep BLE host callbacks short: they only copy one ATT-sized packet into a
// fixed buffer. Actual client write / server notify runs later from loop().
// No dynamic allocation is performed in the callbacks.
// ATT application payload is MTU-3. With MTU 247 the maximum characteristic
// value carried by one notification/write is 244 bytes. Keep staging buffers
// at the protocol payload limit rather than the full ATT MTU.
static constexpr size_t BLE_BRIDGE_MAX_PACKET = 244;
// AUDIT20.4.5.9.26: four slots absorb short host-callback bursts without
// turning the Arduino loop into an unbounded BLE drain loop. Cost is <2 KiB
// for both directions combined; stream loss is still session-fatal.
static constexpr uint8_t BLE_BRIDGE_QUEUE_DEPTH = 4;
static constexpr uint32_t BLE_BRIDGE_MAX_QUEUE_AGE_MS = 250;
// AUDIT20.4.5.9.24: every staged bridge packet is bound to the BLE session
// generation that existed in the host callback. Queue flushes remain the fast
// path, while the generation check is a second fail-closed barrier against a
// callback racing a disconnect/reconnect/overflow transition.
static std::atomic_uint32_t sBridgeSessionEpoch{1};
struct BridgePacket { size_t len=0; uint32_t epoch=0; uint32_t queuedMs=0; uint8_t data[BLE_BRIDGE_MAX_PACKET]; };
struct BridgeQueue {
  BridgePacket slot[BLE_BRIDGE_QUEUE_DEPTH];
  uint8_t head=0, tail=0, count=0, highWater=0;
};
static BridgeQueue sAppToBms, sBmsToApp;
static std::atomic_uint32_t sAppToBmsDrops{0}, sBmsToAppDrops{0};
static std::atomic_uint32_t sAppToBmsDropLogPending{0}, sBmsToAppDropLogPending{0};
static std::atomic_uint32_t sQueueFlushes{0};
// AUDIT20.4.5.9.25: the proxy transports a byte stream split across ATT packets.
// Losing one staged packet can leave either protocol parser in the middle of a
// frame. Treat every bridge queue/forwarding loss as a session-fatal condition:
// callbacks only publish the fault; the Arduino-loop owner invalidates the
// epoch, flushes both directions and tears down the real JK link. Forwarding
// remains latched off until the phone disconnects/reconnects, preventing a
// damaged stream from being silently continued.
static std::atomic_bool sBridgeFaultPending{false};
static std::atomic_bool sBridgeFaultLatched{false};
static std::atomic_uint32_t sBridgeFaults{0};
static std::atomic_uint32_t sForwardWriteFails{0};
static std::atomic_uint32_t sConnectAttempts{0}, sBridgeReadyCount{0};
static std::atomic_int sLastBmsDisconnectReason{0};
static void publishBridgeFault(){ sBridgeFaultPending.store(true,std::memory_order_release); }
static portMUX_TYPE sBridgeMux = portMUX_INITIALIZER_UNLOCKED;
static void clearQueue(BridgeQueue& q){
  portENTER_CRITICAL(&sBridgeMux);
  q.head=0; q.tail=0; q.count=0; q.highWater=0;
  for(uint8_t i=0;i<BLE_BRIDGE_QUEUE_DEPTH;++i){ q.slot[i].len=0; q.slot[i].epoch=0; q.slot[i].queuedMs=0; }
  ++sQueueFlushes;
  portEXIT_CRITICAL(&sBridgeMux);
}
static void clearBridgeQueues(){ clearQueue(sAppToBms); clearQueue(sBmsToApp); }
static bool queuePacket(BridgeQueue& q, std::atomic_uint32_t& drops, const uint8_t* data, size_t len){
  if(!data || !len || len > BLE_BRIDGE_MAX_PACKET){ ++drops; publishBridgeFault(); return false; }
  portENTER_CRITICAL(&sBridgeMux);
  if(q.count >= BLE_BRIDGE_QUEUE_DEPTH){ ++drops; portEXIT_CRITICAL(&sBridgeMux); publishBridgeFault(); return false; }
  BridgePacket& dst=q.slot[q.head];
  memcpy(dst.data,data,len); dst.len=len; dst.epoch=sBridgeSessionEpoch.load(std::memory_order_acquire); dst.queuedMs=millis();
  q.head=(uint8_t)((q.head+1U)%BLE_BRIDGE_QUEUE_DEPTH);
  ++q.count; if(q.count>q.highWater)q.highWater=q.count;
  portEXIT_CRITICAL(&sBridgeMux); return true;
}
static bool takePacket(BridgeQueue& q, uint8_t* out, size_t& len, bool& expired){
  bool ok=false; expired=false; portENTER_CRITICAL(&sBridgeMux);
  if(q.count){
    BridgePacket& src=q.slot[q.tail];
    const uint32_t currentEpoch=sBridgeSessionEpoch.load(std::memory_order_acquire);
    if(src.epoch==currentEpoch){
      const uint32_t age=(uint32_t)(millis()-src.queuedMs);
      if(age<=BLE_BRIDGE_MAX_QUEUE_AGE_MS){ len=src.len; memcpy(out,src.data,len); ok=true; }
      else { len=0; expired=true; }
    } else { len=0; } // stale packet from a previous BLE session: discard fail-closed
    src.len=0; src.epoch=0; src.queuedMs=0;
    q.tail=(uint8_t)((q.tail+1U)%BLE_BRIDGE_QUEUE_DEPTH); --q.count;
  }
  portEXIT_CRITICAL(&sBridgeMux); return ok;
}
static void advanceBridgeSessionEpoch(){
  // Zero is not special, but skip it to make diagnostics easier after wrap.
  uint32_t next=sBridgeSessionEpoch.fetch_add(1,std::memory_order_acq_rel)+1U;
  if(next==0) sBridgeSessionEpoch.store(1,std::memory_order_release);
}
static uint32_t sStateSinceMs = 0;
static uint32_t sWifiConnectedSinceMs = 0;
static NimBLEUUID sServiceUuid(JK_SERVICE_UUID), sCharUuid(JK_CHAR_UUID);
static void setState(BleState st){ sState=st; sStateSinceMs=millis(); }
static void bleHeap(const char* tag){
  Serial.printf("[JK-BLE][HEAP] %-14s free=%u largest8=%u min=%u\n", tag,
    (unsigned)ESP.getFreeHeap(),
    (unsigned)heap_caps_get_largest_free_block(MALLOC_CAP_8BIT),
    (unsigned)ESP.getMinFreeHeap());
}
static void backoff(const char* why){ sBmsConnected=false; sRemoteChar=nullptr; setState(BleState::BACKOFF);
  Serial.printf("[JK-BLE] Backoff %lu ms (%s), heap=%u\n",(unsigned long)JK_RETRY_MS,why,(unsigned)ESP.getFreeHeap()); }

class ServerCB : public NimBLEServerCallbacks {
  void onConnect(NimBLEServer*, NimBLEConnInfo&) override {
    // Host callback only publishes state; queue/session cleanup is deferred.
    enqueueBleEvent(BleEventType::APP_CONNECT);
  }
  void onDisconnect(NimBLEServer*, NimBLEConnInfo&, int reason) override {
    // Host callback only publishes state. Queue cleanup and advertising restart
    // are serialized later from jkBleProxyTick().
    enqueueBleEvent(BleEventType::APP_DISCONNECT, reason);
  }
};
class ClientCB : public NimBLEClientCallbacks {
  void onConnect(NimBLEClient*) override {
    // Keep the host callback allocation-free and side-effect free.
    // Discovery/logging is performed by startConnectReal() after synchronous connect() returns.
  }
  void onConnectFail(NimBLEClient*, int reason) override {
    // Do not mutate bridge pointers/state from the NimBLE host callback.
    enqueueBleEvent(BleEventType::BMS_CONNECT_FAIL, reason);
  }
  void onDisconnect(NimBLEClient*, int reason) override {
    // Do not invalidate remote characteristic pointers or mutate queues from
    // the NimBLE host callback while bridgePump() may be returning from a
    // client operation on the Arduino loop task. Defer all cleanup.
    enqueueBleEvent(BleEventType::BMS_DISCONNECT, reason);
  }
};
class CharCB : public NimBLECharacteristicCallbacks {
  void onWrite(NimBLECharacteristic* c, NimBLEConnInfo&) override {
    NimBLEAttValue v=c->getValue(); if(!v.size() || sBridgeFaultLatched.load(std::memory_order_acquire) || sBridgeFaultPending.load(std::memory_order_acquire) || !sAppConnected.load(std::memory_order_acquire) || !sBmsConnected.load(std::memory_order_acquire) || bleEventsPending()) return;
    if(!queuePacket(sAppToBms,sAppToBmsDrops,(const uint8_t*)v.data(),v.size()))
      ++sAppToBmsDropLogPending;
  }
};
static ServerCB serverCB; static ClientCB clientCB; static CharCB charCB;
static void remoteNotify(NimBLERemoteCharacteristic*,uint8_t* data,size_t len,bool){
  // The real JK may notify while no phone is attached. Such packets have no
  // consumer and must not fill the forwarding queue or latch a bridge fault.
  if(!sAppConnected.load(std::memory_order_acquire) || !sBmsConnected.load(std::memory_order_acquire) || sBridgeFaultLatched.load(std::memory_order_acquire) || sBridgeFaultPending.load(std::memory_order_acquire) || bleEventsPending() || !data || !len)return;
  if(!queuePacket(sBmsToApp,sBmsToAppDrops,data,len)) ++sBmsToAppDropLogPending;
}
static void bridgePump(){
  // Never begin a new bridge operation once either disconnect callback or a
  // stream-integrity fault has published a pending session transition.
  if(bleEventsPending() || sBridgeFaultPending.load(std::memory_order_acquire) || sBridgeFaultLatched.load(std::memory_order_acquire)) return;
  uint8_t buf[BLE_BRIDGE_MAX_PACKET]; size_t len=0; bool expired=false;
  if(sBmsConnected && sClient && sClient->isConnected() && sRemoteChar && takePacket(sAppToBms,buf,len,expired)){
    // AUDIT19.15.36: re-check the physical client link after dequeue and
    // immediately before touching the cached remote characteristic. A NimBLE
    // disconnect callback can be published between the first gate and this
    // point; in that case fail closed and let processDeferredTransitions()
    // serialize teardown on the next loop pass.
    if(bleEventsPending() || sBridgeFaultPending.load(std::memory_order_acquire) || sBridgeFaultLatched.load(std::memory_order_acquire) || !sBmsConnected || !sClient || !sClient->isConnected() || !sRemoteChar) return;
    const bool response=sRemoteChar->canWrite()&&!sRemoteChar->canWriteNoResponse();
    if(!sRemoteChar->writeValue(buf,len,response)) {
      ++sForwardWriteFails; publishBridgeFault();
      Serial.println("[JK-BLE] Forward write failed; session fault queued");
      return;
    }
  }
  if(expired){ publishBridgeFault(); Serial.println("[JK-BLE] App->BMS queued packet expired; session fault queued"); return; }
  len=0; expired=false;
  if(sLocalChar && takePacket(sBmsToApp,buf,len,expired)){
    if(bleEventsPending() || sBridgeFaultPending.load(std::memory_order_acquire) || sBridgeFaultLatched.load(std::memory_order_acquire) || !sAppConnected) return;
    sLocalChar->setValue(buf,len);
    if(!bleEventsPending() && !sBridgeFaultPending.load(std::memory_order_acquire) && !sBridgeFaultLatched.load(std::memory_order_acquire) && sAppConnected) sLocalChar->notify();
  }
  if(expired){ publishBridgeFault(); Serial.println("[JK-BLE] BMS->App queued packet expired; session fault queued"); }
}

static void processDeferredTransitions(){
  // A dropped/failed ATT fragment is stream-fatal. Do not attempt to continue
  // with the next fragment: invalidate the generation and tear down the real
  // link. Keep the latch set until APP_DISCONNECT establishes a clean phone
  // session boundary.
  if(sBridgeFaultPending.exchange(false,std::memory_order_acq_rel)){
    sBridgeFaultLatched.store(true,std::memory_order_release);
    ++sBridgeFaults;
    sBmsConnected.store(false,std::memory_order_release);
    advanceBridgeSessionEpoch(); sRemoteChar=nullptr; clearBridgeQueues();
    if(sClient && sClient->isConnected()) sClient->disconnect();
    setState(BleState::BACKOFF);
    Serial.printf("[JK-BLE] FAIL-CLOSED bridge stream fault total=%lu; waiting for app reconnect\n",(unsigned long)sBridgeFaults.load(std::memory_order_relaxed));
  }
  // If the fixed callback FIFO ever overflows, fail closed instead of silently
  // losing a disconnect/reconnect transition and bridging across sessions.
  bool overflow=false;
  portENTER_CRITICAL(&sBleEventMux);
  overflow=sBleEventOverflowPending;
  sBleEventOverflowPending=false;
  if(overflow){
    // Once an event was lost, the ordering of every event already queued is
    // unknowable. Close callback admission before exposing an empty event FIFO:
    // otherwise a host callback could observe overflow=false/pending=false in
    // the tiny window before the owner invalidates the old session.
    sBmsConnected.store(false,std::memory_order_release);
    sAppConnected.store(false,std::memory_order_release);
    sBleEventHead=0; sBleEventTail=0; sBleEventCount=0;
  }
  portEXIT_CRITICAL(&sBleEventMux);
  if(overflow){
    advanceBridgeSessionEpoch(); sRemoteChar=nullptr; clearBridgeQueues();
    if(sClient && sClient->isConnected()) sClient->disconnect();
    sRestartAdvertisingPending.store(true,std::memory_order_release); setState(BleState::BACKOFF);
    Serial.printf("[JK-BLE] FAIL-CLOSED callback FIFO overflow total=%lu; sessions reset\n",(unsigned long)sBleEventDrops.load(std::memory_order_relaxed));
  }
  // Logging is deferred: never call Serial from NimBLE host callbacks.
  if(sAppToBmsDropLogPending.load(std::memory_order_relaxed)){ const uint32_t n=sAppToBmsDropLogPending.exchange(0, std::memory_order_relaxed); Serial.printf("[JK-BLE] App->BMS bridge busy/drop x%lu\n",(unsigned long)n); }
  if(sBmsToAppDropLogPending.load(std::memory_order_relaxed)){ const uint32_t n=sBmsToAppDropLogPending.exchange(0, std::memory_order_relaxed); Serial.printf("[JK-BLE] BMS->App bridge busy/drop x%lu\n",(unsigned long)n); }

  // FIFO processing preserves the actual callback order. This specifically
  // fixes disconnect->reconnect occurring before the next Arduino loop tick.
  BleEvent ev;
  while(takeBleEvent(ev)){
    switch(ev.type){
      case BleEventType::BMS_CONNECT_FAIL:
        sLastBmsDisconnectReason.store(ev.reason,std::memory_order_relaxed);
        sBmsConnected.store(false,std::memory_order_release); advanceBridgeSessionEpoch(); sRemoteChar=nullptr; clearBridgeQueues(); setState(BleState::BACKOFF);
        Serial.printf("[JK-BLE] Real JK connect failed reason=%d; deferred FIFO cleanup complete\n",ev.reason);
        break;
      case BleEventType::BMS_DISCONNECT:
        sLastBmsDisconnectReason.store(ev.reason,std::memory_order_relaxed);
        sBmsConnected.store(false,std::memory_order_release); advanceBridgeSessionEpoch(); sRemoteChar=nullptr; clearBridgeQueues(); setState(BleState::BACKOFF);
        Serial.printf("[JK-BLE] Real JK disconnected reason=%d; deferred FIFO cleanup complete\n",ev.reason);
        break;
      case BleEventType::APP_CONNECT:
        advanceBridgeSessionEpoch(); sAppConnected=true;
        // A DISCONNECT->CONNECT pair can be queued before loop() runs. The
        // CONNECT is the final state, so cancel an advertising restart that
        // the preceding DISCONNECT requested. This avoids advertising a second
        // app slot after the original app has already reconnected.
        sRestartAdvertisingPending.store(false,std::memory_order_release);
        clearQueue(sBmsToApp);
        Serial.println("[JK-BLE] JK app connected; deferred FIFO stale queue flush complete");
        break;
      case BleEventType::APP_DISCONNECT:
        sAppConnected.store(false,std::memory_order_release); advanceBridgeSessionEpoch(); clearBridgeQueues();
        sBridgeFaultLatched.store(false,std::memory_order_release); sBridgeFaultPending.store(false,std::memory_order_release);
        sRestartAdvertisingPending.store(true,std::memory_order_release);
        Serial.printf("[JK-BLE] JK app disconnected reason=%d; deferred FIFO cleanup complete\n",ev.reason);
        break;
    }
  }
  static uint32_t lastEventDrops=0;
  const uint32_t drops=sBleEventDrops.load(std::memory_order_relaxed);
  if(drops!=lastEventDrops){ Serial.printf("[JK-BLE] WARNING callback event FIFO overflow total=%lu\n",(unsigned long)drops); lastEventDrops=drops; }
}

static void initBleOnce(){
  if(sInitialized.load(std::memory_order_acquire) || sInitAttempted) return;
  bleBootDiagMark(BLE_BOOT_PRE_INIT);
  const uint32_t heapBefore = ESP.getFreeHeap();
  const uint32_t largestBefore = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  bleHeap("pre-init"); sMemDiag.preInitFree=heapBefore;sMemDiag.preInitLargest=largestBefore;sMemDiag.minFree=ESP.getMinFreeHeap();
  if(heapBefore < BLE_MIN_HEAP_BEFORE_INIT || largestBefore < BLE_MIN_LARGEST8_BEFORE_INIT){
    // 9.36.7.3: low pre-init heap is an admission deferral, not a permanent fault.
    // Web/AsyncTCP activity can temporarily depress free heap. Retry on a later tick;
    // actual partial NimBLE allocation failures still latch SAFE HOLD below.
    Serial.printf("[JK-BLE] init deferred: low memory (free=%u, largest8=%u; need >=%u/%u)\n",
      (unsigned)heapBefore, (unsigned)largestBefore,
      (unsigned)BLE_MIN_HEAP_BEFORE_INIT, (unsigned)BLE_MIN_LARGEST8_BEFORE_INIT);
    return;
  }
  // The Wi-Fi driver, rather than WiFi.getSleep()'s cached value, decides
  // whether Bluetooth coexistence can start safely on this ESP32 build.
  if((WiFi.getMode() & WIFI_MODE_STA) != 0) {
    wifi_ps_type_t ps = WIFI_PS_NONE;
    const esp_err_t psErr = esp_wifi_get_ps(&ps);
    if(psErr != ESP_OK || ps == WIFI_PS_NONE) {
      static uint32_t lastPsWarnMs = 0;
      const uint32_t now = millis();
      if(lastPsWarnMs == 0 || now - lastPsWarnMs >= 5000) {
        Serial.printf("[JK-BLE] init deferred: WiFi modem sleep driver err=%d ps=%d (need modem sleep)\n", (int)psErr, (int)ps);
        lastPsWarnMs = now;
      }
      return;
    }
    Serial.printf("[JK-BLE] WiFi modem sleep driver ps=%d\n", (int)ps);
  }
  bleBootDiagMark(BLE_BOOT_WIFI_PS_OK);
  sInitAttempted = true; // never repeatedly re-initialize NimBLE after a partial allocation failure
  Serial.println("[JK-BLE] AUDIT19.15.29-EVENT-ORDER-GUARD direct-connect proxy init");
  static_assert(MYNEWT_VAL(BLE_MAX_CONNECTIONS) == 2, "NimBLE connection limit changed");
  static_assert(MYNEWT_VAL(BLE_ROLE_OBSERVER) == 0, "NimBLE observer unexpectedly enabled");
  static_assert(MYNEWT_VAL(BLE_ATT_PREFERRED_MTU) == 247, "NimBLE preferred MTU changed");
  bleBootDiagMark(BLE_BOOT_NIMBLE_ENTER);
  NimBLEDevice::init(JK_PROXY_NAME);
  bleBootDiagMark(BLE_BOOT_NIMBLE_RETURN);
  NimBLEDevice::setPower(9); NimBLEDevice::setMTU(247); Serial.printf("[JK-BLE] compiled config maxConn=%d observer=%d mtu=%d\n", (int)MYNEWT_VAL(BLE_MAX_CONNECTIONS), (int)MYNEWT_VAL(BLE_ROLE_OBSERVER), (int)MYNEWT_VAL(BLE_ATT_PREFERRED_MTU)); bleHeap("nimble init"); jkMemSnap(sMemDiag.postNimbleFree,sMemDiag.postNimbleLargest);
  sServer=NimBLEDevice::createServer(); bleHeap("server alloc"); jkMemSnap(sMemDiag.postServerFree,sMemDiag.postServerLargest); if(!sServer){Serial.println("[JK-BLE] server alloc failed");sSafeHold=true;Serial.println("[JK-BLE] SAFE HOLD LATCHED: partial BLE init failure");return;}
  sServer->setCallbacks(&serverCB);
  auto* svc=sServer->createService(sServiceUuid); bleHeap("service alloc"); if(!svc){Serial.println("[JK-BLE] service alloc failed");sSafeHold=true;Serial.println("[JK-BLE] SAFE HOLD LATCHED: partial BLE init failure");return;}
  sLocalChar=svc->createCharacteristic(sCharUuid,NIMBLE_PROPERTY::READ|NIMBLE_PROPERTY::WRITE|NIMBLE_PROPERTY::WRITE_NR|NIMBLE_PROPERTY::NOTIFY);
  bleHeap("char alloc");
  if(!sLocalChar){Serial.println("[JK-BLE] char alloc failed");sSafeHold=true;Serial.println("[JK-BLE] SAFE HOLD LATCHED: partial BLE init failure");return;}
  sLocalChar->setCallbacks(&charCB);
  if(!sServer->start()){Serial.println("[JK-BLE] GATT start failed");sSafeHold=true;Serial.println("[JK-BLE] SAFE HOLD LATCHED: partial BLE init failure");return;}
  bleHeap("gatt started"); jkMemSnap(sMemDiag.postGattFree,sMemDiag.postGattLargest);
  // AUDIT20.4.5.9.23: do NOT advertise the virtual JK until every resource needed
  // for a functional proxy has been allocated and the post-allocation heap guard
  // has passed. In 9.22 advertising started before createClient(); a client
  // allocation/heap failure then latched SAFE HOLD while leaving a dead proxy
  // connectable for the phone app for the rest of the boot.
  // Allocate the central/client object while we still have the guarded init budget.
  sClient=NimBLEDevice::createClient();
  bleHeap("client alloc"); jkMemSnap(sMemDiag.postClientFree,sMemDiag.postClientLargest);
  if(!sClient){ Serial.println("[JK-BLE] client alloc failed"); sSafeHold=true; Serial.println("[JK-BLE] SAFE HOLD LATCHED: client allocation failure"); return; }
  sClient->setClientCallbacks(&clientCB,false);
  sClient->setConnectTimeout(1500);
  sClient->setConnectRetries(0);
  const uint32_t postClientFree=ESP.getFreeHeap();
  const uint32_t postClientLargest=heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  if(postClientFree < BLE_MIN_HEAP_BEFORE_CONNECT || postClientLargest < BLE_MIN_LARGEST8_BEFORE_CONNECT){
    sSafeHold=true;
    Serial.printf("[JK-BLE] SAFE HOLD LATCHED: low memory after client alloc (free=%u, largest8=%u); proxy NOT advertised\n", (unsigned)postClientFree, (unsigned)postClientLargest);
    return;
  }
  auto* adv=NimBLEDevice::getAdvertising();
  if(!adv){ sSafeHold=true; Serial.println("[JK-BLE] SAFE HOLD LATCHED: advertising object missing; proxy NOT advertised"); return; }
  adv->setName(JK_PROXY_NAME); adv->addServiceUUID(sServiceUuid); adv->enableScanResponse(true);
  uint8_t md[]={0x65,0x0B}; adv->setManufacturerData(md,sizeof(md)); NimBLEDevice::startAdvertising();
  bleHeap("advertising"); jkMemSnap(sMemDiag.postAdvFree,sMemDiag.postAdvLargest);
  sInitialized.store(true,std::memory_order_release); setState(BleState::IDLE); Serial.printf("[JK-BLE] Virtual JK advertising as %s\n",JK_PROXY_NAME); bleHeap("after server");
  bleBootDiagMark(BLE_BOOT_ADVERTISING);
}

static void discoverReal();
static void startConnectReal(){
  const uint32_t heapNow = ESP.getFreeHeap();
  const uint32_t largestNow = heap_caps_get_largest_free_block(MALLOC_CAP_8BIT);
  bleHeap("pre-connect");
  if(!heap_caps_check_integrity_all(false)){ sSafeHold=true; Serial.println("[JK-BLE] SAFE HOLD LATCHED: heap integrity failed before connect"); return; }
  if(heapNow < BLE_MIN_HEAP_BEFORE_CONNECT || largestNow < BLE_MIN_LARGEST8_BEFORE_CONNECT){ backoff("low/fragmented heap before connect"); return; }
  if(!sClient){ backoff("client missing"); return; }
  if(sClient->isConnected()){
    // Never reconnect on top of a link whose disconnect callback is still
    // queued. Close it and let the next loop tick serialize that transition.
    sClient->disconnect();
    backoff("stale client link closing");
    return;
  }
  NimBLEAddress target(JK_TARGET_MAC,JK_TARGET_ADDR_TYPE);
  Serial.printf("[JK-BLE] Direct connect %s type=%u heap=%u ...\n",JK_TARGET_MAC,(unsigned)JK_TARGET_ADDR_TYPE,(unsigned)heapNow);
  ++sConnectAttempts;
  // AUDIT19.15.34: keep the discovered attribute database across reconnects to
  // the same fixed JK BMS. NimBLE documents deleteAttributes=false for this
  // use case; it avoids repeated service/characteristic allocation, reduces
  // heap fragmentation, and keeps reconnects lighter. Connection remains
  // synchronous (asyncConnect=false) and MTU exchange remains disabled.
  if(!sClient->connect(target, false, false, false)){backoff("connect failed");return;}
  discoverReal();
}

static void discoverReal(){
  if(!sClient || !sClient->isConnected()){backoff("link lost before discovery");return;}
  auto* svc=sClient->getService(sServiceUuid);
  if(!svc){sClient->disconnect();backoff("FFE0 missing");return;}
  sRemoteChar=svc->getCharacteristic(sCharUuid);
  if(!sRemoteChar){sClient->disconnect();backoff("FFE1 missing");return;}
  if(!sRemoteChar->canNotify()||!sRemoteChar->subscribe(true,remoteNotify)){sClient->disconnect();backoff("subscribe failed");return;}
  // New BMS session: invalidate all packets from the preceding physical link, then discard staged data.
  advanceBridgeSessionEpoch(); clearBridgeQueues(); sBmsConnected=true; setState(BleState::CONNECTED);
  ++sBridgeReadyCount;
  Serial.printf("[JK-BLE] Bridge ready callbackGuard=ON ring2 sessionGuard=ON drops=%lu/%lu flushes=%lu\n",(unsigned long)sAppToBmsDrops.load(std::memory_order_relaxed),(unsigned long)sBmsToAppDrops.load(std::memory_order_relaxed),(unsigned long)sQueueFlushes.load(std::memory_order_relaxed)); bleHeap("bridge ready");
}

static void loadStartupCfgOnce(){
  if(sStartupCfgLoaded) return;
  Preferences p;
  bool en=true;
  if(p.begin("jkbleiso", true)){ en=p.getBool("startup",true); p.end(); }
  sStartupEnabled.store(en,std::memory_order_release);
  sStartupAppliedEnabled.store(en,std::memory_order_release);
  sStartupCfgLoaded=true;
  Serial.printf("[JK-BLE] startup isolation: %s\n",en?"ENABLED":"DISABLED (baseline: no NimBLE init)");
}
void jkBleProxyInit(){ loadStartupCfgOnce(); /* deliberately deferred; tick initializes safely */ }
bool jkBleStartupEnabled(){ loadStartupCfgOnce(); return sStartupEnabled.load(std::memory_order_acquire); }
bool jkBleStartupAppliedEnabled(){ loadStartupCfgOnce(); return sStartupAppliedEnabled.load(std::memory_order_acquire); }
bool jkBleSetStartupEnabled(bool enabled){
  Preferences p; if(!p.begin("jkbleiso",false)) return false;
  const bool ok=p.putBool("startup",enabled)==1; p.end();
  if(ok) sStartupEnabled.store(enabled,std::memory_order_release);
  return ok;
}
void jkBleProxyTick(){
  loadStartupCfgOnce();
  if(!sStartupAppliedEnabled.load(std::memory_order_acquire)) return;
  const uint32_t now=millis();
  if(sSafeHold) return;
  if(sInitialized.load(std::memory_order_acquire)) {
    processDeferredTransitions();
    // Serialize NimBLE advertising ownership here. A PowerStream worker may
    // request the spare connection, but it never calls start/stopAdvertising().
    AuxReserveState requested=AuxReserveState::REQUESTED;
    // Claim ownership before any synchronous NimBLE call. The waiting worker
    // may withdraw REQUESTED on timeout, but cannot withdraw PROCESSING.
    if(sAuxReserveState.compare_exchange_strong(requested,AuxReserveState::PROCESSING,
                                                 std::memory_order_acq_rel)) {
      sAuxDiagGeneration.fetch_add(1,std::memory_order_acq_rel); // odd: snapshot in progress
      auxMemSnap(sAuxBeforeFree,sAuxBeforeLargest);
      sAuxAfterStopFree=0;sAuxAfterStopLargest=0;
      bool grant = !sAppConnected.load(std::memory_order_acquire) &&
                   !bleEventsPending();
      if(grant) {
        NimBLEDevice::stopAdvertising();
        auxMemSnap(sAuxAfterStopFree,sAuxAfterStopLargest);
        // Re-check after closing the advertising window. A connection callback
        // may have won immediately before stopAdvertising() took effect.
        grant = (sServer && sServer->getConnectedCount()==0) &&
                !sAppConnected.load(std::memory_order_acquire) &&
                !bleEventsPending();
      }
      if(grant) {
        auxMemSnap(sAuxAfterDecisionFree,sAuxAfterDecisionLargest);
        sAuxDiagGeneration.fetch_add(1,std::memory_order_release); // even: complete
        sAuxReserved.store(true,std::memory_order_release);
        sAuxReserveState.store(AuxReserveState::GRANTED,std::memory_order_release);
      } else {
        auxMemSnap(sAuxAfterDecisionFree,sAuxAfterDecisionLargest);
        sAuxDiagGeneration.fetch_add(1,std::memory_order_release); // even: complete
        sAuxReserved.store(false,std::memory_order_release);
        sAuxReserveState.store(AuxReserveState::DENIED,std::memory_order_release);
        if(sServer && sServer->getConnectedCount()==0 && !sAppConnected.load(std::memory_order_acquire))
          NimBLEDevice::startAdvertising();
      }
    }
    if(sRestartAdvertisingPending.load(std::memory_order_acquire) && !sAuxReserved.load(std::memory_order_acquire)) {
      sRestartAdvertisingPending.store(false,std::memory_order_release);
      NimBLEDevice::startAdvertising();
      Serial.println("[JK-BLE] Advertising restarted from main loop");
    }
    bridgePump();
  }
  if(!sInitialized.load(std::memory_order_acquire)){
    // Keep the first 20 s of boot BLE-free. With saved WiFi credentials, also
    // require 5 s of continuous STA connectivity before NimBLE is initialized.
    if(now < BLE_BOOT_GRACE_MS) return;
    if(WiFi.getMode() == WIFI_STA || WiFi.getMode() == WIFI_AP_STA) {
      if(WiFi.status() != WL_CONNECTED) { sWifiConnectedSinceMs = 0; return; }
      if(sWifiConnectedSinceMs == 0) { sWifiConnectedSinceMs = now; return; }
      if(now - sWifiConnectedSinceMs < 5000) return;
    }
    initBleOnce(); return;
  }
  if(!sInitialized.load(std::memory_order_acquire)) return; // fail closed after a one-time BLE init failure; reboot is the recovery path
  if(sBmsConnected&&sClient&&sClient->isConnected()){sState=BleState::CONNECTED;return;}
  // An auxiliary BLE transaction owns the spare connection slot. Do not start a
  // JK reconnect attempt until it releases the reservation.
  if(sAuxReserved.load(std::memory_order_acquire)) return;
  if(sBridgeFaultLatched.load(std::memory_order_acquire)) return;
  if(sState==BleState::CONNECTED){backoff("link lost");return;}
  if(sState==BleState::BACKOFF&&now-sStateSinceMs<JK_RETRY_MS) return;
  // Avoid starting a BLE connection attempt while STA is still associating.
  if((WiFi.getMode()==WIFI_STA || WiFi.getMode()==WIFI_AP_STA) && WiFi.status()!=WL_CONNECTED){ if(sState!=BleState::BACKOFF)setState(BleState::BACKOFF); return; }
  startConnectReal();
}
bool jkBleProxyBmsConnected(){return sBmsConnected.load(std::memory_order_acquire);}
bool jkBleProxyAppConnected(){return sAppConnected.load(std::memory_order_acquire);}
bool jkBleProxyInitialized(){return sInitialized.load(std::memory_order_acquire);}
JkBleStatusDiag jkBleProxyStatusDiag(){
  JkBleStatusDiag d;
  d.appConnected=sAppConnected.load(std::memory_order_acquire);
  d.bmsConnected=sBmsConnected.load(std::memory_order_acquire);
  d.initialized=sInitialized.load(std::memory_order_acquire);
  d.auxReserved=sAuxReserved.load(std::memory_order_acquire);
  d.bridgeFault=sBridgeFaultLatched.load(std::memory_order_acquire) || sBridgeFaultPending.load(std::memory_order_acquire);
  d.eventsPending=bleEventsPending();
  d.safeHold=sSafeHold.load(std::memory_order_acquire);
  d.startupEnabled=sStartupAppliedEnabled.load(std::memory_order_acquire);
  d.appToBmsDrops=sAppToBmsDrops.load(std::memory_order_relaxed);
  d.bmsToAppDrops=sBmsToAppDrops.load(std::memory_order_relaxed);
  d.eventDrops=sBleEventDrops.load(std::memory_order_relaxed);
  d.bridgeFaults=sBridgeFaults.load(std::memory_order_relaxed);
  d.forwardWriteFails=sForwardWriteFails.load(std::memory_order_relaxed);
  d.queueFlushes=sQueueFlushes.load(std::memory_order_relaxed);
  d.connectAttempts=sConnectAttempts.load(std::memory_order_relaxed);
  d.bridgeReadyCount=sBridgeReadyCount.load(std::memory_order_relaxed);
  d.lastBmsDisconnectReason=sLastBmsDisconnectReason.load(std::memory_order_relaxed);
  return d;
}


bool jkBleProxyReserveAuxConnection(){
  if(!sInitialized.load(std::memory_order_acquire) || sAppConnected.load(std::memory_order_acquire)) return false;
  AuxReserveState expected=AuxReserveState::IDLE;
  if(!sAuxReserveState.compare_exchange_strong(expected,AuxReserveState::REQUESTED,std::memory_order_acq_rel)) return false;

  const uint32_t started=millis();
  for(;;){
    const AuxReserveState st=sAuxReserveState.load(std::memory_order_acquire);
    if(st==AuxReserveState::GRANTED) return true;
    if(st==AuxReserveState::DENIED){
      sAuxReserveState.store(AuxReserveState::IDLE,std::memory_order_release);
      return false;
    }
    if((uint32_t)(millis()-started)>=AUX_RESERVE_OWNER_TIMEOUT_MS){
      // Withdraw only while the owner has not claimed the request. PROCESSING
      // must finish in the owner; returning now could leak a later GRANTED slot.
      AuxReserveState req=AuxReserveState::REQUESTED;
      if(sAuxReserveState.compare_exchange_strong(req,AuxReserveState::IDLE,std::memory_order_acq_rel)) return false;
      if(req==AuxReserveState::GRANTED) return true;
      if(req==AuxReserveState::DENIED){ sAuxReserveState.store(AuxReserveState::IDLE,std::memory_order_release); return false; }
    }
    vTaskDelay(pdMS_TO_TICKS(5));
  }
}
void jkBleProxyReleaseAuxConnection(){
  const bool was=sAuxReserved.exchange(false,std::memory_order_acq_rel);
  sAuxReserveState.store(AuxReserveState::IDLE,std::memory_order_release);
  if(was && sInitialized.load(std::memory_order_acquire) && !sAppConnected.load(std::memory_order_acquire)){
    sRestartAdvertisingPending.store(true,std::memory_order_release); // owner performs NimBLE call in jkBleProxyTick()
  }
}
bool jkBleProxyAuxReserved(){return sAuxReserved.load(std::memory_order_acquire);}

bool jkBleProxyEventsPending(){return bleEventsPending();}
bool jkBleProxyAuxSlotReady(){
  // Worker-visible readiness is snapshot/atomic only. The owner already checked
  // NimBLEServer::getConnectedCount() after stopAdvertising() before GRANTED.
  return sAuxReserved.load(std::memory_order_acquire) &&
         sAuxReserveState.load(std::memory_order_acquire)==AuxReserveState::GRANTED &&
         !bleEventsPending() &&
         !sAppConnected.load(std::memory_order_acquire);
}

JkBleMemoryDiag jkBleProxyMemoryDiag(){JkBleMemoryDiag d=sMemDiag;d.minFree=ESP.getMinFreeHeap();return d;}
JkBleAuxMemoryDiag jkBleProxyAuxMemoryDiag(){
  for(int i=0;i<3;i++){
    const uint32_t before=sAuxDiagGeneration.load(std::memory_order_acquire);
    if(before&1U)continue;
    JkBleAuxMemoryDiag d;d.beforeStopFree=sAuxBeforeFree.load();d.beforeStopLargest=sAuxBeforeLargest.load();
    d.afterStopFree=sAuxAfterStopFree.load();d.afterStopLargest=sAuxAfterStopLargest.load();
    d.afterDecisionFree=sAuxAfterDecisionFree.load();d.afterDecisionLargest=sAuxAfterDecisionLargest.load();
    const uint32_t after=sAuxDiagGeneration.load(std::memory_order_acquire);
    if(before==after){d.generation=after/2U;return d;}
  }
  return {};
}
