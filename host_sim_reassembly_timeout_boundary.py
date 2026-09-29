import random
TIMEOUT=300
random.seed(5933)
viol=0; checks=0; late_end_rejected=0
# Model the relevant admission ordering: timeout must reset before MID/END admission.
for _ in range(2_000_000):
    last=random.randrange(0,2**32)
    gap=random.randrange(0,700)
    now=(last+gap)&0xffffffff
    active=True
    # uint32 millis subtraction
    age=(now-last)&0xffffffff
    if active and age>TIMEOUT:
        active=False
    kind=random.choice(('MID','END','START'))
    if kind=='START': active=True
    elif kind=='END' and age>TIMEOUT:
        checks+=1
        if active: viol+=1
        else: late_end_rejected+=1
    elif kind=='MID' and age>TIMEOUT:
        checks+=1
        if active: viol+=1
assert viol==0
print({'iterations':2_000_000,'late_checks':checks,'late_frames_rejected':late_end_rejected,'violations':viol})
