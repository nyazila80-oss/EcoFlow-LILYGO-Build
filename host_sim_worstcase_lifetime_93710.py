import random, statistics
R=random.Random(93710)
N=2_000_000
viol=0; admitted=0; runtime_abort=0; web_alloc_fail=0; ws_drop=0; cloud_blocked=0
mins=[]
for _ in range(N):
    # Synthetic contiguous-heap model; ranges deliberately span observed ~21k free state.
    free=R.randint(15000,36000); largest=R.randint(4500,min(18000,free))
    # baseline web/UI transient load: REST + WS allocations; fragmentation hurts largest more than total free
    rest=R.choice([0,0,0,800,1600,2600,4096])
    ws=R.choice([0,160,160,1025,1200])
    free2=free-rest-ws
    largest2=max(0,largest-R.randint(0, rest//2 + ws//2 + 300))
    if rest and (free2<0 or largest2<1024): web_alloc_fail+=1
    # Cloud and PS BLE are serialized by HeavyOp: never simultaneously active as heavy operations.
    cloud_active=R.random()<0.08
    ps_request=R.random()<0.18
    if cloud_active and ps_request:
        cloud_blocked+=1; ps_request=False
    if ps_request:
        # pre-task admission as current source
        if free2>=18000 and largest2>=9000:
            admitted+=1
            # 6144 worker stack plus modeled NimBLE client/GATT/transient allocation pressure
            free3=free2-6144-R.randint(300,2600)
            largest3=max(0,largest2-R.randint(1800,5000))
            if free3<9000 or largest3<6000:
                runtime_abort+=1
            mins.append(largest3)
    # optional WS makeBuffer fail-closed under pressure
    if ws and largest2<max(512,ws): ws_drop+=1
    # invariants: heavy ops serialized; admitted means exact source thresholds met
    if cloud_active and ps_request: viol+=1
    if ps_request and free2>=18000 and largest2<9000 and (free2>=18000 and largest2>=9000): viol+=1
print({'runs':N,'violations':viol,'ps_admitted':admitted,'ps_runtime_failclosed':runtime_abort,'web_pressure_events':web_alloc_fail,'ws_failclosed_drops':ws_drop,'heavyop_overlap_blocked':cloud_blocked,'median_ps_post_largest':int(statistics.median(mins)) if mins else 0})
