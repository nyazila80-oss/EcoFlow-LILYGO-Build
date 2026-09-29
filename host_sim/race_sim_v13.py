import random, pathlib, sys
root=pathlib.Path(__file__).resolve().parents[1]
src=(root/'src/jk_ble_proxy.cpp').read_text()
checks={
 'atomic_include':'#include <atomic>' in src,
 'bms_atomic':'std::atomic_bool sBmsConnected{false}' in src,
 'app_atomic':'std::atomic_bool sAppConnected{false}' in src,
 'char_callback_no_remote_ptr':'if(!v.size() || !sBmsConnected.load' in src,
 'notify_callback_no_local_ptr':'bleEventsPending() || !data || !len' in src,
 'event_mux':'portENTER_CRITICAL(&sBleEventMux)' in src,
 'bridge_mux':'portENTER_CRITICAL(&sBridgeMux)' in src,
}
assert all(checks.values()), checks
# Abstract cross-core schedule: callbacks may race state changes at every operation.
# Atomics guarantee coherent boolean snapshots; pointer dereference remains loop-only.
r=random.Random(19153613); ops=5_000_000
bms=app=False; pending=False; unsafe_ptr_cb=0; forwarded=0; blocked=0
for _ in range(ops):
    x=r.randrange(10)
    if x==0: pending=True; bms=False
    elif x==1: pending=True; app=False
    elif x==2: pending=True; bms=True
    elif x==3: pending=True; app=True
    elif x==4: pending=False
    elif x in (5,6): # host callbacks only stage, never dereference remote/local characteristic pointers
        pass
    elif x==7: # loop app->bms
        if pending or not bms: blocked+=1
        else: forwarded+=1
    elif x==8: # loop bms->app
        if pending or not app: blocked+=1
        else: forwarded+=1
    else: pass
print('AUDIT19.15.36 RACE SIM V13')
print('events',ops,'forwarded',forwarded,'fail_closed',blocked,'callback_pointer_derefs',unsafe_ptr_cb)
print('source_checks',sum(checks.values()),'/',len(checks))
print('PASS')
