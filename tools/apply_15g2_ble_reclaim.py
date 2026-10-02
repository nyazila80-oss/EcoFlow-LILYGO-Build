from pathlib import Path

p=Path('src/powerstream_ble_lab.cpp')
s=p.read_text()
name='bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)'
if name in s:
    print('15G.2 reclaim implementation already present')
    raise SystemExit(0)

anchor='static bool wifiStaEnabled(){'
if anchor not in s:
    raise SystemExit('15G.2 anchor not found')

impl=r'''// 9.36.7.15G.2: release only the cached, disconnected PowerStream client
// before a cloud TLS allocation window. Never stop/deinit NimBLE and never touch
// the JK proxy/server. Fail closed if configuration or a BLE worker owns state.
bool powerStreamBleLabReclaimIdleClientForCloud(bool& released){
  released=false;
  bool expected=false;
  if(!sConfigGate.compare_exchange_strong(expected,true,std::memory_order_acq_rel)) return false;

  // sConfigGate serializes this handoff against configuration changes and new
  // one-shot admissions. An already-running worker is never interrupted here.
  if(sWorkerRunning.load(std::memory_order_acquire) || sLinkUp.load(std::memory_order_acquire)){
    sConfigGate.store(false,std::memory_order_release);
    return false;
  }

  if(!sClient){
    // No cached PowerStream client means there is nothing to reclaim.
    sWrite=nullptr;
    sNotify=nullptr;
    sConfigGate.store(false,std::memory_order_release);
    return true;
  }

  // Defensive second source of truth: never delete a connected/connecting client
  // merely to make room for TLS. Cloud must defer instead.
  if(sClient->isConnected()){
    sConfigGate.store(false,std::memory_order_release);
    return false;
  }

  NimBLEDevice::deleteClient(sClient);
  sClient=nullptr;
  sWrite=nullptr;
  sNotify=nullptr;
  clearNotifyQueue();
  released=true;
  sConfigGate.store(false,std::memory_order_release);
  return true;
}

'''
s=s.replace(anchor,impl+anchor,1)
p.write_text(s)
print('15G.2 reclaim implementation inserted')
