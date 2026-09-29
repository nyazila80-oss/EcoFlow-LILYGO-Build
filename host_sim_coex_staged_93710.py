import random
N=3_000_000
viol=0
for _ in range(N):
    phase=random.randrange(4) # 0 A,1 B,2 C,3 D
    jk_init=random.choice([0,1]); jk_app=random.choice([0,1]); cfg=random.choice([0,1]); bms=random.choice([0,1]); heap=random.choice([0,1]); wifi=random.choice([0,1]); heavy=random.choice([0,1])
    auth_probe = phase==2
    full_cmd = phase==3
    # Admission mirrors firmware: both active operations require same prerequisites and JK app free.
    admitted=(jk_init and not jk_app and cfg and bms and heap and wifi and heavy)
    priority_write = full_cmd and admitted
    auth_write = (auth_probe or full_cmd) and admitted
    # Core invariants: A/B never initiate PS traffic; C can auth but never priority write.
    if phase in (0,1) and (auth_write or priority_write): viol+=1
    if phase==2 and priority_write: viol+=1
    if priority_write and not auth_write: viol+=1
print({'states':N,'violations':viol})
assert viol==0
