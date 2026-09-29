import random
IDS=(0x10014001,0x10114001,0x10214001)
def accept(fid,extd=True,rtr=False,rxlogging=False):
    if rxlogging: return True
    return extd and not rtr and (fid & 0x1fffffff) in IDS
random.seed(203)
for _ in range(1_000_000):
    fid=random.randrange(1<<29); extd=random.choice((True,False)); rtr=random.choice((True,False))
    got=accept(fid,extd,rtr,False)
    exp=extd and not rtr and fid in IDS
    assert got==exp
for fid in IDS:
    assert accept(fid,True,False,False)
    assert accept(fid,True,False,True)
for _ in range(100000):
    assert accept(random.randrange(1<<29),random.choice((True,False)),random.choice((True,False)),True)
print('PASS CAN prefilter model: 1,100,003 checks')
