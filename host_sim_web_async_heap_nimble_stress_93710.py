#!/usr/bin/env python3
import random, statistics
random.seed(93710)
RUNS=500_000
viol=0; admitted=0; runtime_abort=0; web_alloc_fail=0; ws_drop=0; auth_probe=0; command=0
largest_samples=[]; frag_samples=[]
for _ in range(RUNS):
    # deliberately broad ESP32-like free/largest envelope, not allocator emulation
    free=random.randint(15000,42000)
    largest=random.randint(max(3500, int(free*.18)), max(4000,int(free*.82)))
    largest=min(largest,free)
    # resident pressure: cloud task already created, websocket/client churn, async tcp bookkeeping
    if random.random()<.55: free-=random.randint(1500,5000); largest-=random.randint(500,2800)
    if random.random()<.70: free-=random.randint(300,1800); largest-=random.randint(200,1400)
    free=max(0,free); largest=max(0,min(largest,free))
    # concurrent REST construction: bms/full/state style contiguous demand + temporaries
    rest=random.random()<.62
    rest_need=random.randint(2600,6200) if rest else 0
    if rest and largest < rest_need:
        web_alloc_fail+=1
    elif rest:
        free=max(0,free-rest_need); largest=max(0,min(largest-random.randint(400,rest_need),free))
    # bounded websocket allocation is allowed to fail closed
    if random.random()<.45:
        ws_need=random.randint(180,1500)
        if largest<ws_need or free<ws_need+1000: ws_drop+=1
        else:
            free-=ws_need; largest=max(0,min(largest-random.randint(50,ws_need),free))
    # PS BLE admission mirrors current pre-task intent: free>=18k largest>=9k
    want=random.random()<.28
    if want and free>=18000 and largest>=9000:
        admitted+=1
        auth_only=random.random()<.65
        auth_probe += auth_only
        command += (not auth_only)
        # worker stack/TCB + client/GATT/notify/transient allocations; deliberately stressed
        free-=random.randint(6500,10500)
        largest-=random.randint(2800,6500)
        free=max(0,free); largest=max(0,min(largest,free))
        # runtime guard current design ~9k free/6k largest should fail closed
        if free<9000 or largest<6000:
            runtime_abort+=1
        else:
            # if operation proceeds, model bounded auth/command transients
            need=random.randint(700,2400 if auth_only else 3200)
            if largest<need or free<need+2500:
                viol+=1  # proceeded past runtime guard but cannot satisfy modeled bounded op
    largest_samples.append(largest)
    frag_samples.append((free-largest) if free>=largest else 0)
print(f'runs={RUNS} violations={viol} admitted={admitted} runtime_abort={runtime_abort} web_alloc_fail={web_alloc_fail} ws_failclosed_drop={ws_drop} auth_only={auth_probe} command={command}')
print(f'largest_median={int(statistics.median(largest_samples))} largest_p10={int(sorted(largest_samples)[RUNS//10])} fragmentation_gap_median={int(statistics.median(frag_samples))}')
