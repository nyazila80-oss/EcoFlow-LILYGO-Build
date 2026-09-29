import random, json, time, os, sys

# Combined recovery model for AUDIT19.15.31. Models the firmware's documented
# fail-closed rules under simultaneous RS485 truncation, BLE lifecycle churn,
# WiFi loss/recovery and CAN traffic. It does NOT emulate ESP32/NimBLE timing.

class System:
    def __init__(self):
        self.now=0; self.last_bms=0; self.bms_valid=True; self.power=True
        self.rs=bytearray(); self.rs_target=random.choice((308,310,332))
        self.ble_fifo=[]; self.ble_overflow=False; self.appq=[]; self.bmsq=[]
        self.app=True; self.ble=True; self.wifi=True; self.adv=False
        self.can_tx=0; self.can_block=0; self.cross_session=0; self.rs_false_valid=0
        self.recoveries=0; self.events=0; self.fifo_overflows=0
    def flush(self): self.appq.clear(); self.bmsq.clear()
    def ble_event(self,e):
        if len(self.ble_fifo)>=16:
            self.ble_fifo.clear(); self.ble_overflow=True; self.fifo_overflows+=1
        else:self.ble_fifo.append(e)
    def process_ble(self):
        if self.ble_overflow:
            self.ble_overflow=False; self.ble_fifo.clear(); self.app=False; self.ble=False; self.flush(); self.adv=True
        while self.ble_fifo:
            e=self.ble_fifo.pop(0)
            if e=='bd': self.ble=False; self.flush()
            elif e=='bc': self.ble=True; self.flush()
            elif e=='ad': self.app=False; self.flush(); self.adv=True
            elif e=='ac': self.app=True; self.bmsq.clear(); self.adv=False
    def power_off(self):
        self.power=False; self.rs.clear(); self.ble_event('bd')
    def power_on(self):
        self.power=True; self.rs.clear()
    def rs_chunk(self,n):
        if not self.power:return
        # Random bytes cannot make telemetry valid: model requires complete expected transaction.
        take=min(n,self.rs_target-len(self.rs)); self.rs.extend(b'X'*take)
        if len(self.rs)==self.rs_target:
            self.bms_valid=True; self.last_bms=self.now; self.rs.clear(); self.recoveries+=1
    def tick(self,dt=1):
        self.now+=dt; self.process_ble()
        # Firmware stale window: bms.valid() eventually goes false after lost telemetry.
        if (not self.power) and self.now-self.last_bms>3000:self.bms_valid=False
        # CAN TX primitive is gated by bmsTelemetryValidForCan().
        if self.bms_valid:self.can_tx+=1
        else:self.can_block+=1
        assert len(self.ble_fifo)<=16 and len(self.appq)<=2 and len(self.bmsq)<=2
        if not self.ble and (self.appq or self.bmsq): self.cross_session+=1

def run(seed,steps):
    random.seed(seed); s=System()
    for _ in range(steps):
        op=random.randrange(100)
        if op<4:s.power_off()
        elif op<8:s.power_on()
        elif op<35:s.rs_chunk(random.randrange(1,80))
        elif op<42:s.ble_event(random.choice(('ad','ac','bd','bc')))
        elif op<48:s.wifi=not s.wifi
        elif op<65:
            if random.randrange(2)==0:
                if s.ble and len(s.appq)<2:s.appq.append((seed,s.events))
            else:
                if s.ble and s.app and len(s.bmsq)<2:s.bmsq.append((seed,s.events))
        elif op<75:
            if s.appq:s.appq.pop(0)
            if s.bmsq:s.bmsq.pop(0)
        # Force occasional callback storms, including overflow path.
        elif op==99:
            for _ in range(random.randrange(17,40)):s.ble_event(random.choice(('ad','ac','bd','bc')))
        s.events+=1; s.tick(random.randrange(1,15))
        assert s.cross_session==0
    return {'events':s.events,'can_tx':s.can_tx,'can_blocked':s.can_block,'recoveries':s.recoveries,'fifo_overflows':s.fifo_overflows,'cross_session_violations':s.cross_session}

if __name__=='__main__':
    t=time.time(); total={k:0 for k in ('events','can_tx','can_blocked','recoveries','fifo_overflows','cross_session_violations')}
    seeds=100; steps=100000
    for seed in range(seeds):
        r=run(seed,steps)
        for k,v in r.items():total[k]+=v
    total['seeds']=seeds; total['seconds']=round(time.time()-t,3)
    print(json.dumps(total,indent=2,sort_keys=True))
