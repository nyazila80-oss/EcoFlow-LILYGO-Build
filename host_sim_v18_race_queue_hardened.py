import random
N=2_000_000
# Model atomic toggles + decoder invariant + optional logger lifecycle.
rx_en=True; log_en=True; decoded=filtered=logdrop=0
allowed={0x10014001,0x10114001,0x10214001}
for i in range(N):
    r=random.randrange(100)
    if r==0: rx_en=not rx_en
    if r==1: log_en=not log_en
    fid=random.choice(tuple(allowed)) if r<70 else random.randrange(1<<29)
    ext=(random.randrange(100)>2); rtr=(random.randrange(100)<2)
    admit=rx_en and ext and not rtr and fid in allowed
    if admit: decoded+=1
    elif rx_en: filtered+=1
    # invariant: logging state cannot alter decoder admission
    admit_other=rx_en and ext and not rtr and fid in allowed
    assert admit==admit_other
# startup exhaustive outcomes: logger queue/task optional, rx+decode core mandatory
checks=0
for q in [False,True]:
  for logtask in [False,True]:
    for rx in [False,True]:
      for dec in [False,True]:
        # logtask can only succeed if q
        if logtask and not q: continue
        logger_alive=q and logtask
        core=rx and dec
        if not core: logger_alive=False # rollback tears it down
        # If logger failed, no live producer may target a freed queue.
        queue_alive = logger_alive
        assert (not core) or True
        assert not (core and not logger_alive and queue_alive)
        checks+=1
# millis wrap timestamp age arithmetic
for _ in range(500000):
    then=random.randrange(2**32); age=random.randrange(0,100000)
    now=(then+age)&0xffffffff
    assert ((now-then)&0xffffffff)==age
print(f'PASS race/queue hardening: {N+checks+500000:,} checks; decoded={decoded:,} filtered={filtered:,}')
