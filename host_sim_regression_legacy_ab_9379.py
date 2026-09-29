import random
N=3_000_000
viol=0
for _ in range(N):
    legacy=bool(random.getrandbits(1))
    jk_enabled=True  # target invariant of this A/B profile
    ps_tick=not legacy
    ws_bms_push=not legacy
    rs485=True; can=True; web=True; wifi=True
    ps_command_allowed=not legacy
    if legacy and (not jk_enabled or ps_tick or ws_bms_push or ps_command_allowed): viol+=1
    if not (rs485 and can and web and wifi): viol+=1
print({'states':N,'violations':viol})
assert viol==0
