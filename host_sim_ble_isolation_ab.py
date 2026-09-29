import random
N=2_000_000
viol=0
for _ in range(N):
    stored=random.choice([0,1]); boot=stored
    initialized=False
    # after boot, random web writes must not alter boot-applied state
    for __ in range(random.randint(0,4)):
        stored=random.choice([0,1])
        if boot and random.random()<.5: initialized=True
        # invariants: disabled-at-boot never initializes; runtime config cannot deinit/init itself
        if not boot and initialized: viol+=1
        if boot != (not not boot): viol+=1
    # reboot applies latest persisted value
    boot2=stored; initialized2=False
    if boot2 and random.random()<.5: initialized2=True
    if not boot2 and initialized2: viol+=1
print({'states':N,'violations':viol})
assert viol==0
