#!/usr/bin/env python3
Import('env')
from pathlib import Path
import re

root=Path(env['PROJECT_DIR'])
ble=root/'src'/'powerstream_ble_lab.cpp'
api=root/'src'/'powerstream_api.cpp'
b=ble.read_text(encoding='utf-8')
p=api.read_text(encoding='utf-8')

# 15AG solution: reclaim only the idle PowerStream client before Cloud TLS.
fn='''
bool powerStreamBleLabReclaimIdleClientForCloud(bool& released){
  released=false;
  bool gate=false;
  if(!sConfigGate.compare_exchange_strong(gate,true)) return false;
  if(sWorkerRunning.load() || sLinkUp.load() || (sClient && sClient->isConnected())){
    sConfigGate.store(false);
    return false;
  }
  if(sClient){
    NimBLEDevice::deleteClient(sClient);
    sClient=nullptr; sWrite=nullptr; sNotify=nullptr;
    clearNotifyQueue();
    released=true;
  }
  sConfigGate.store(false);
  return true;
}
'''
if 'bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)' not in b:
    anchor='static bool wifiStaEnabled(){'
    if b.count(anchor)!=1: raise RuntimeError('15AG BLE reclaim anchor missing/non-unique')
    b=b.replace(anchor,fn+'\n'+anchor,1)
elif b.count('bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)')!=1:
    raise RuntimeError('15AG BLE reclaim function duplicated')

call='''  bool psBleReleased=false;
  if(!powerStreamBleLabReclaimIdleClientForCloud(psBleReleased)){
    err="Cloud TLS blockiert: PowerStream BLE aktiv/busy";
    return false;
  }
  if(psBleReleased) vTaskDelay(pdMS_TO_TICKS(1));
  if(!heap_caps_check_integrity_all(false)){
    err="Cloud TLS blockiert: Heap-Integritaet fehlgeschlagen";
    return false;
  }
'''
marker='bool psBleReleased=false;'
ctor='  WiFiClientSecure client;'
if p.count(marker)==1: pass
elif p.count(marker)>1: raise RuntimeError('15AG TLS reclaim target duplicated')
elif p.count(ctor)==1: p=p.replace(ctor,call+'\n'+ctor,1)
else: raise RuntimeError('15AG WiFiClientSecure semantic anchor missing/non-unique: '+str(p.count(ctor)))

# 15AG originally raises the admission threshold 10KiB -> 32KiB. 15AM later
# performs the controlled 32KiB -> 24KiB A/B. PlatformIO pre-scripts execute
# again for subsequent targets, so a canonical downstream 15AM/15AN source is
# already a valid 15AG fixed point and must not be rewritten backwards.
old_thr='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 10240;'
new_thr='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 32768;'
downstream_thr='static constexpr uint32_t TLS_GET_MIN_LARGEST8 = 24576;'
lineage_versions={
    '9.36.7.15AG-TLS-PEAK-FIX',
    '9.36.7.15AH-EARLY-TLS-HANDSHAKE',
    '9.36.7.15AI-PS-BLE-RECLAIM-DIAG',
    '9.36.7.15AK-TLS-ALLOC-PEAK-DIAG',
    '9.36.7.15AL-TLS-DYNAMIC-BUFFER-FIX',
    '9.36.7.15AM-PREFLIGHT-AB-24K',
    '9.36.7.15AN-TLS-INTERNAL8-FIX',
}
version_re=re.compile(r'tls15z_version\\\":\\\"([^\\\"]+)')
versions=version_re.findall(p)
if len(versions)!=1:
    raise RuntimeError('15AG provenance missing/non-unique: '+repr(versions))
current_version=versions[0]

if p.count(new_thr)==1: pass
elif p.count(new_thr)>1: raise RuntimeError('15AG TLS admission threshold duplicated')
elif p.count(old_thr)==1: p=p.replace(old_thr,new_thr,1)
elif p.count(downstream_thr)==1 and current_version in lineage_versions:
    pass
else: raise RuntimeError('15AG TLS admission threshold source missing/non-unique')

old_ver='9.36.7.15AF-NO-AUX-RESERVATION'
new_ver='9.36.7.15AG-TLS-PEAK-FIX'
if current_version==old_ver:
    p=p.replace(old_ver,new_ver)
elif current_version in lineage_versions:
    pass
else:
    raise RuntimeError('15AG provenance source missing/unknown: '+current_version)

# Per-job TLS diagnostic hygiene. A preflight-aborted job must never expose POST,
# X509 or failed-allocation values inherited from an earlier job.
diag_decl='static std::atomic<uint32_t> gTlsDiagJobId{0};\nstatic std::atomic<bool> gTlsAttemptedThisJob{false};'
trace_decl='static std::atomic<uint32_t> gCloudTraceJobId{0};'
if diag_decl not in p:
    if p.count(trace_decl)!=1: raise RuntimeError('15AG diag trace declaration anchor missing/non-unique')
    p=p.replace(trace_decl,trace_decl+'\n'+diag_decl,1)

timing_decl='static std::atomic<uint32_t> gCloudNotBeforeMs{0}, gCloudQueuedAtMs{0}, gCloudStartedAtMs{0};'
if timing_decl not in p:
    if p.count(diag_decl)!=1: raise RuntimeError('15AG HTTP quiet timing declaration anchor missing/non-unique')
    p=p.replace(diag_decl,diag_decl+'\n'+timing_decl,1)

frag_decl='''
static std::atomic<uint32_t> gFragQueueFree{0},gFragQueueLargest{0},gFragQueueBlocks{0};
static std::atomic<uint32_t> gFragStartFree{0},gFragStartLargest{0},gFragStartBlocks{0};
static std::atomic<uint32_t> gFragPsramTotal{0},gFragPsramFree{0},gFragPsramLargest{0};
static inline void tls15agFragSnap(std::atomic<uint32_t>& fr,std::atomic<uint32_t>& lg,std::atomic<uint32_t>& blocks){
  multi_heap_info_t i{}; heap_caps_get_info(&i,MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  fr.store((uint32_t)i.total_free_bytes,std::memory_order_relaxed);
  lg.store((uint32_t)i.largest_free_block,std::memory_order_relaxed);
  blocks.store((uint32_t)i.free_blocks,std::memory_order_relaxed);
}
'''
if 'gFragQueueFree' not in p:
    if p.count(timing_decl)!=1: raise RuntimeError('15AG fragmentation declaration anchor missing/non-unique')
    p=p.replace(timing_decl,timing_decl+frag_decl,1)

reset_fn='''
static void resetTlsDiagnosticsForJob(uint32_t jobId){
  gTlsDiagJobId.store(jobId,std::memory_order_relaxed);
  gTlsAttemptedThisJob.store(false,std::memory_order_relaxed);
  gTlsHeapClient=0; gTlsLargestClient=0; gTlsHeapCa=0; gTlsLargestCa=0;
  gTlsHeapBeginPre=0; gTlsLargestBeginPre=0; gTlsHeapBeginPost=0; gTlsLargestBeginPost=0;
  gTlsHeapGetPre=0; gTlsLargestGetPre=0; gTlsHeapGetPost=0; gTlsLargestGetPost=0;
  gDnsOk=-1; gDnsIp=0; gTcp443Ok=-1;
  gTlsInternalFreePre=0; gTlsInternalLargestPre=0; gTlsInternalFreePost=0; gTlsInternalLargestPost=0;
  gTlsInternalHmacPreFree=0; gTlsInternalHmacPreLargest=0; gTlsInternalHmacPostFree=0; gTlsInternalHmacPostLargest=0;
  gTlsInternalHeadersPostFree=0; gTlsInternalHeadersPostLargest=0;
  gTlsInternalGetPreFree=0; gTlsInternalGetPreLargest=0; gTlsInternalGetPostFree=0; gTlsInternalGetPostLargest=0;
  gTlsEpochPre=0; gTlsEpochPost=0; gTlsTimeSanePre=false; gTlsTimeSanePost=false;
  gTlsInternalPreVerifyFree=0; gTlsInternalPreVerifyLargest=0; gTlsInternalPostVerifyFree=0; gTlsInternalPostVerifyLargest=0;
  gTlsFailedAllocCount=0; gTlsFailedAllocSize=0; gTlsFailedAllocCaps=0; gTlsFailedAllocTask=0;
  gTlsFailedCapsFree=0; gTlsFailedCapsLargest=0; gTlsFailedInternalFree=0; gTlsFailedInternalLargest=0;
  gTlsFailed8BitFree=0; gTlsFailed8BitLargest=0; gTlsFailedDmaFree=0; gTlsFailedDmaLargest=0;
  gTlsFailed32BitFree=0; gTlsFailed32BitLargest=0;
  gTlsAllocWindow.store(false,std::memory_order_release);
  gCloudQueuedAtMs.store(millis(),std::memory_order_relaxed);
  gCloudStartedAtMs.store(0,std::memory_order_relaxed);
  gCloudNotBeforeMs.store(millis()+750U,std::memory_order_release);
  tls15agFragSnap(gFragQueueFree,gFragQueueLargest,gFragQueueBlocks);
  gFragPsramTotal.store((uint32_t)heap_caps_get_total_size(MALLOC_CAP_SPIRAM),std::memory_order_relaxed);
  gFragPsramFree.store((uint32_t)heap_caps_get_free_size(MALLOC_CAP_SPIRAM),std::memory_order_relaxed);
  gFragPsramLargest.store((uint32_t)heap_caps_get_largest_free_block(MALLOC_CAP_SPIRAM),std::memory_order_relaxed);
  { ApiLock lk(pdMS_TO_TICKS(50)); if(lk.held){ psApiState.lastHttpCode=-1; psApiState.lastResponseBytes=0; } }
}
'''
job_comment='// AUDIT20.4.5.9.13: dedicated cloud worker.'
if 'static void resetTlsDiagnosticsForJob(uint32_t jobId)' not in p:
    if p.count(job_comment)!=1: raise RuntimeError('15AG diag reset insertion anchor missing/non-unique')
    p=p.replace(job_comment,reset_fn+'\n'+job_comment,1)

queue_old='gJobId=n;gCloudTraceJobId=n;cloudDiagMark(CLOUD_DIAG_QUEUED,n);gJobPending=true;'
queue_new='gJobId=n;gCloudTraceJobId=n;resetTlsDiagnosticsForJob(n);cloudDiagMark(CLOUD_DIAG_QUEUED,n);gJobPending=true;'
if queue_new not in p:
    if p.count(queue_old)!=1: raise RuntimeError('15AG queue reset anchor missing/non-unique')
    p=p.replace(queue_old,queue_new,1)

loop_old='void powerStreamApiLoopTick(){ if(gJobPending.load(std::memory_order_acquire)) runCloudJobOnLoopTask(); }'
loop_new='''void powerStreamApiLoopTick(){
  if(!gJobPending.load(std::memory_order_acquire)) return;
  const uint32_t notBefore=gCloudNotBeforeMs.load(std::memory_order_acquire);
  if((int32_t)(millis()-notBefore)<0) return;
  tls15agFragSnap(gFragStartFree,gFragStartLargest,gFragStartBlocks);
  gCloudStartedAtMs.store(millis(),std::memory_order_relaxed);
  runCloudJobOnLoopTask();
}'''
if loop_new not in p:
    if p.count(loop_old)!=1: raise RuntimeError('15AG HTTP quiet loop anchor missing/non-unique')
    p=p.replace(loop_old,loop_new,1)

get_anchor='if(method=="GET") {\n    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);'
get_mark='if(method=="GET") {\n    gTlsAttemptedThisJob.store(true,std::memory_order_relaxed);\n    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);'
if get_mark not in p:
    if p.count(get_anchor)!=1: raise RuntimeError('15AG TLS attempted anchor missing/non-unique')
    p=p.replace(get_anchor,get_mark,1)

json_anchor='return String("{\\\"ok\\\":true,\\\"job_id\\\":")+String(gJobId.load())+'
json_new='return String("{\\\"ok\\\":true,\\\"job_id\\\":")+String(gJobId.load())+",\\\"tls_diag_job_id\\\":"+String(gTlsDiagJobId.load())+",\\\"tls_attempted_this_job\\\":"+(gTlsAttemptedThisJob.load()?"true":"false")+'
if 'tls_attempted_this_job' not in p:
    if p.count(json_anchor)!=1: raise RuntimeError('15AG JSON ownership anchor missing/non-unique')
    p=p.replace(json_anchor,json_new,1)

json_timing_anchor='",\\\"pending\\\":"+(pending?"true":"false")+'
json_timing_new='",\\\"cloud_queued_at_ms\\\":"+String(gCloudQueuedAtMs.load())+",\\\"cloud_started_at_ms\\\":"+String(gCloudStartedAtMs.load())+",\\\"cloud_queue_to_start_ms\\\":"+String(gCloudStartedAtMs.load()?gCloudStartedAtMs.load()-gCloudQueuedAtMs.load():0)+",\\\"http_quiet_window_ms\\\":750,\\\"pending\\\":"+(pending?"true":"false")+'
if 'http_quiet_window_ms' not in p:
    if p.count(json_timing_anchor)!=1: raise RuntimeError('15AG HTTP quiet JSON anchor missing/non-unique')
    p=p.replace(json_timing_anchor,json_timing_new,1)

frag_json_anchor='",\\"http_quiet_window_ms\\":750,\\"pending\\":"'
frag_json_new='",\\"http_quiet_window_ms\\":750,\\"frag_queue_free\\":"+String(gFragQueueFree.load())+",\\"frag_queue_largest\\":"+String(gFragQueueLargest.load())+",\\"frag_queue_blocks\\":"+String(gFragQueueBlocks.load())+",\\"frag_start_free\\":"+String(gFragStartFree.load())+",\\"frag_start_largest\\":"+String(gFragStartLargest.load())+",\\"frag_start_blocks\\":"+String(gFragStartBlocks.load())+",\\"frag_psram_total\\":"+String(gFragPsramTotal.load())+",\\"frag_psram_free\\":"+String(gFragPsramFree.load())+",\\"frag_psram_largest\\":"+String(gFragPsramLargest.load())+",\\"pending\\":"'
if 'frag_queue_largest' not in p:
    if p.count(frag_json_anchor)!=1: raise RuntimeError('15AG fragmentation JSON anchor missing/non-unique')
    p=p.replace(frag_json_anchor,frag_json_new,1)

code=re.sub(r'//[^\n]*|/\*.*?\*/','',p+'\n'+b,flags=re.S)
for bad in ('setInsecure(', 'MBEDTLS_SSL_VERIFY_NONE'):
    if bad in code: raise RuntimeError('15AG security invariant: '+bad)
if 'setCACert(ECOFLOW_CA_BUNDLE)' not in p: raise RuntimeError('15AG CA verification missing')
if 'NimBLEDevice::deinit' in fn: raise RuntimeError('15AG must not deinit shared NimBLE host')
if 'jkBleProxy' in fn: raise RuntimeError('15AG must not manipulate JK proxy/client')
if b.count('bool powerStreamBleLabReclaimIdleClientForCloud(bool& released)')!=1: raise RuntimeError('15AG reclaim function cardinality != 1')
if p.count(marker)!=1: raise RuntimeError('15AG reclaim call cardinality != 1')
# Accept only the native 15AG threshold or the known 15AM/15AN A/B descendant.
if not ((p.count(new_thr)==1 and p.count(downstream_thr)==0) or
        (p.count(new_thr)==0 and p.count(downstream_thr)==1 and version_re.findall(p)[0] in lineage_versions)):
    raise RuntimeError('15AG TLS admission threshold invariant failed')
post_versions=version_re.findall(p)
if len(post_versions)!=1 or post_versions[0] not in lineage_versions:
    raise RuntimeError('15AG provenance invariant after transform: '+repr(post_versions))
if p.count('resetTlsDiagnosticsForJob(n)')!=1: raise RuntimeError('15AG per-job diag reset missing/duplicated')
if p.count('gTlsAttemptedThisJob.store(true')!=1: raise RuntimeError('15AG TLS attempt marker missing/duplicated')
if 'tls_diag_job_id' not in p or 'tls_attempted_this_job' not in p: raise RuntimeError('15AG JSON ownership fields missing')
if p.count('gCloudNotBeforeMs.store(millis()+750U')!=1: raise RuntimeError('15AG HTTP quiet window missing/duplicated')
if p.count('http_quiet_window_ms')!=1: raise RuntimeError('15AG HTTP quiet JSON field missing/duplicated')
if p.count('tls15agFragSnap(')!=3 or 'frag_psram_total' not in p: raise RuntimeError('15AG fragmentation attribution missing/malformed')

ble.write_text(b,encoding='utf-8')
api.write_text(p,encoding='utf-8')
print('[15AG] reclaim retained; TLS diagnostics reset and job-owned; lineage=%s; CA verification retained' % post_versions[0])
