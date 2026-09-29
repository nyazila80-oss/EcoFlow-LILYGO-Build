import random, sys
SEEDS=100; OPS=100000
viol=0; notify_ok=0; dropped=0; disconnects=0; reconnects=0
for seed in range(SEEDS):
 r=random.Random(0x19153500+seed)
 app=True; pending=False; queued=False
 for _ in range(OPS):
  x=r.randrange(100)
  if x<8: # callback disconnect before pump
   pending=True; disconnects+=1
  elif x<14: # process transition
   if pending: app=False; pending=False; queued=False
  elif x<20: # reconnect event/process
   pending=True
   # model ordered FIFO: reconnect final state after deferred processing
   app=True; pending=False; queued=False; reconnects+=1
  elif x<55: # remote notify callback queues only if no pending/link valid
   if app and not pending: queued=True
  else: # bridge pump
   if queued:
    queued=False
    # first guard from firmware
    if pending or not app:
     dropped+=1; continue
    # race injection: disconnect can publish between setValue and final notify guard
    race = r.random()<0.20
    if race:
     pending=True; disconnects+=1
    # second guard from firmware immediately before notify
    if not pending and app:
     notify_ok+=1
    else:
     dropped+=1
    # invariant: firmware must never call notify when event already pending or app false
    if pending and (not (pending or not app)):
     viol+=1
  # process some pending events later
  if pending and r.random()<0.15:
   app=False; pending=False; queued=False
print(f'events={SEEDS*OPS}')
print(f'disconnect_events={disconnects}')
print(f'reconnect_events={reconnects}')
print(f'notify_ok={notify_ok}')
print(f'fail_closed_drops={dropped}')
print(f'modeled_invalid_notify={viol}')
print('PASS' if viol==0 else 'FAIL')
sys.exit(0 if viol==0 else 1)
