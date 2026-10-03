#!/usr/bin/env python3
Import('env')
from pathlib import Path

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# Establish and verify TLS before HTTPClient, URL and request-header allocations
# consume the last INTERNAL heap margin. HTTPClient subsequently reuses the same
# connected WiFiClientSecure instance. Verification remains fail-closed.
ca_anchor='''  client.setCACert(ECOFLOW_CA_BUNDLE);
  snap15ae(g15aeCaFree,g15aeCaLargest);
  tlsMemSnap(gTlsHeapCa,gTlsLargestCa);
  HTTPClient http; http.setTimeout(12000);'''
early='''  client.setCACert(ECOFLOW_CA_BUNDLE);
  snap15ae(g15aeCaFree,g15aeCaLargest);
  tlsMemSnap(gTlsHeapCa,gTlsLargestCa);

  // 15AH: run the certificate/RSA peak before HTTP request bookkeeping.
  static constexpr uint32_t TLS_EARLY_MIN_LARGEST8 = 32768;
  if(gTlsLargestCa.load(std::memory_order_relaxed) < TLS_EARLY_MIN_LARGEST8){
    err="TLS preflight: largest8 zu klein ("+String(gTlsLargestCa.load())+
        ", Minimum "+String(TLS_EARLY_MIN_LARGEST8)+")";
    return false;
  }
  gTlsAttemptedThisJob.store(true,std::memory_order_relaxed);
  gTlsFailedAllocCount.store(0,std::memory_order_relaxed);
  gTlsFailedAllocSize.store(0,std::memory_order_relaxed);
  gTlsFailedAllocCaps.store(0,std::memory_order_relaxed);
  gTlsFailedAllocTask.store(0,std::memory_order_relaxed);
  gTlsFailedCapsFree.store(0,std::memory_order_relaxed); gTlsFailedCapsLargest.store(0,std::memory_order_relaxed);
  gTlsFailedInternalFree.store(0,std::memory_order_relaxed); gTlsFailedInternalLargest.store(0,std::memory_order_relaxed);
  gTlsFailed8BitFree.store(0,std::memory_order_relaxed); gTlsFailed8BitLargest.store(0,std::memory_order_relaxed);
  gTlsFailedDmaFree.store(0,std::memory_order_relaxed); gTlsFailedDmaLargest.store(0,std::memory_order_relaxed);
  gTlsFailed32BitFree.store(0,std::memory_order_relaxed); gTlsFailed32BitLargest.store(0,std::memory_order_relaxed);
  const time_t tlsNowPre=time(nullptr);
  gTlsEpochPre=(int64_t)tlsNowPre; gTlsTimeSanePre=tlsEpochSane(tlsNowPre);
  gTlsInternalPreVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPreVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsAllocWindow.store(true,std::memory_order_release);
  const bool tlsEarlyConnected=client.connect(API_HOST,443);
#!/usr/bin/env python3
Import('env')
from pathlib import Path

root=Path(env['PROJECT_DIR'])
p=root/'src'/'powerstream_api.cpp'
s=p.read_text(encoding='utf-8')

# Establish and verify TLS before HTTPClient, URL and request-header allocations
# consume the last INTERNAL heap margin. HTTPClient subsequently reuses the same
# connected WiFiClientSecure instance. Verification remains fail-closed.
ca_anchor='''  client.setCACert(ECOFLOW_CA_BUNDLE);
  snap15ae(g15aeCaFree,g15aeCaLargest);
  tlsMemSnap(gTlsHeapCa,gTlsLargestCa);
  HTTPClient http; http.setTimeout(12000);'''
early='''  client.setCACert(ECOFLOW_CA_BUNDLE);
  snap15ae(g15aeCaFree,g15aeCaLargest);
  tlsMemSnap(gTlsHeapCa,gTlsLargestCa);

  // 15AH: run the certificate/RSA peak before HTTP request bookkeeping.
  static constexpr uint32_t TLS_EARLY_MIN_LARGEST8 = 32768;
  if(gTlsLargestCa.load(std::memory_order_relaxed) < TLS_EARLY_MIN_LARGEST8){
    err="TLS preflight: largest8 zu klein ("+String(gTlsLargestCa.load())+
        ", Minimum "+String(TLS_EARLY_MIN_LARGEST8)+")";
    return false;
  }
  gTlsAttemptedThisJob.store(true,std::memory_order_relaxed);
  gTlsFailedAllocCount.store(0,std::memory_order_relaxed);
  gTlsFailedAllocSize.store(0,std::memory_order_relaxed);
  gTlsFailedAllocCaps.store(0,std::memory_order_relaxed);
  gTlsFailedAllocTask.store(0,std::memory_order_relaxed);
  gTlsFailedCapsFree.store(0,std::memory_order_relaxed); gTlsFailedCapsLargest.store(0,std::memory_order_relaxed);
  gTlsFailedInternalFree.store(0,std::memory_order_relaxed); gTlsFailedInternalLargest.store(0,std::memory_order_relaxed);
  gTlsFailed8BitFree.store(0,std::memory_order_relaxed); gTlsFailed8BitLargest.store(0,std::memory_order_relaxed);
  gTlsFailedDmaFree.store(0,std::memory_order_relaxed); gTlsFailedDmaLargest.store(0,std::memory_order_relaxed);
  gTlsFailed32BitFree.store(0,std::memory_order_relaxed); gTlsFailed32BitLargest.store(0,std::memory_order_relaxed);
  const time_t tlsEarlyNowPre=time(nullptr);
  gTlsEpochPre=(int64_t)tlsEarlyNowPre; gTlsTimeSanePre=tlsEpochSane(tlsEarlyNowPre);
  gTlsInternalPreVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPreVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsAllocWindow.store(true,std::memory_order_release);
  const bool tlsEarlyConnected=client.connect(API_HOST,443);
  const time_t tlsEarlyNowPost=time(nullptr);
  gTlsEpochPost=(int64_t)tlsEarlyNowPost; gTlsTimeSanePost=tlsEpochSane(tlsEarlyNowPost);
  gTlsInternalPostVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPostVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsAllocWindow.store(false,std::memory_order_release);
  tlsMemSnap(gTlsHeapGetPost,gTlsLargestGetPost);
  tlsInternalSnap(gTlsInternalGetPostFree,gTlsInternalGetPostLargest);
  tlsInternalSnap(gTlsInternalFreePost,gTlsInternalLargestPost);
  if(!tlsEarlyConnected){
    char tlsReason[96]={0}; const int tlsCode=client.lastError(tlsReason,sizeof(tlsReason));
    err="EcoFlow TLS-Handschlag fehlgeschlagen (TLS "+String(tlsCode)+": "+String(tlsReason)+
        ", heap "+String(ESP.getFreeHeap())+", largest8 "+
        String(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT))+")";
    return false;
  }

  HTTPClient http; http.setTimeout(12000);'''

if 'TLS_EARLY_MIN_LARGEST8' not in s:
    if s.count(ca_anchor)!=1: raise RuntimeError('15AH CA/HTTP anchor missing or non-unique')
    s=s.replace(ca_anchor,early,1)

# The real TLS attempt and allocation window now belong to the early connect.
# Keep the later GET as a plain HTTP operation over the verified connection.
old='''  if(method=="GET") {
    gTlsAttemptedThisJob.store(true,std::memory_order_relaxed);
    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);
    gTlsFailedAllocSize.store(0,std::memory_order_relaxed);
    gTlsFailedAllocCaps.store(0,std::memory_order_relaxed);
    gTlsFailedAllocTask.store(0,std::memory_order_relaxed);
    gTlsFailedCapsFree.store(0,std::memory_order_relaxed); gTlsFailedCapsLargest.store(0,std::memory_order_relaxed);
    gTlsFailedInternalFree.store(0,std::memory_order_relaxed); gTlsFailedInternalLargest.store(0,std::memory_order_relaxed);
    gTlsFailed8BitFree.store(0,std::memory_order_relaxed); gTlsFailed8BitLargest.store(0,std::memory_order_relaxed);
    gTlsFailedDmaFree.store(0,std::memory_order_relaxed); gTlsFailedDmaLargest.store(0,std::memory_order_relaxed);
    gTlsFailed32BitFree.store(0,std::memory_order_relaxed); gTlsFailed32BitLargest.store(0,std::memory_order_relaxed);
    gTlsAllocWindow.store(true,std::memory_order_release);
    httpCode=http.GET();
  const time_t tlsNowPost=time(nullptr);
  gTlsEpochPost=(int64_t)tlsNowPost;
  gTlsTimeSanePost=tlsEpochSane(tlsNowPost);
  gTlsInternalPostVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPostVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    gTlsAllocWindow.store(false,std::memory_order_release);
  } else if(method=="PUT")'''
new='''  if(method=="GET") {
    httpCode=http.GET();
  } else if(method=="PUT")'''
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise RuntimeError('15AH GET instrumentation anchor missing')

# Security and lifecycle gates.
code=s.replace('// Never fall back to setInsecure() because API secrets are sent in request headers.','')
if 'setInsecure(' in code: raise RuntimeError('15AH security invariant: insecure TLS')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s: raise RuntimeError('15AH CA lost')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AH early handshake cardinality')
if s.count('gTlsAttemptedThisJob.store(true')!=1: raise RuntimeError('15AH attempt marker cardinality')
if s.count('gTlsAllocWindow.store(true')!=1: raise RuntimeError('15AH alloc-window cardinality')

p.write_text(s,encoding='utf-8')
print('[15AH] early verified TLS handshake installed before HTTP allocations')
  const time_t tlsNowPost=time(nullptr);
  gTlsEpochPost=(int64_t)tlsNowPost; gTlsTimeSanePost=tlsEpochSane(tlsNowPost);
  gTlsInternalPostVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPostVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsAllocWindow.store(false,std::memory_order_release);
  tlsMemSnap(gTlsHeapGetPost,gTlsLargestGetPost);
  tlsInternalSnap(gTlsInternalGetPostFree,gTlsInternalGetPostLargest);
  tlsInternalSnap(gTlsInternalFreePost,gTlsInternalLargestPost);
  if(!tlsEarlyConnected){
    char tlsReason[96]={0}; const int tlsCode=client.lastError(tlsReason,sizeof(tlsReason));
    err="EcoFlow TLS-Handschlag fehlgeschlagen (TLS "+String(tlsCode)+": "+String(tlsReason)+
        ", heap "+String(ESP.getFreeHeap())+", largest8 "+
        String(heap_caps_get_largest_free_block(MALLOC_CAP_8BIT))+")";
    return false;
  }

  HTTPClient http; http.setTimeout(12000);'''

if 'TLS_EARLY_MIN_LARGEST8' not in s:
    if s.count(ca_anchor)!=1: raise RuntimeError('15AH CA/HTTP anchor missing or non-unique')
    s=s.replace(ca_anchor,early,1)

# The real TLS attempt and allocation window now belong to the early connect.
# Keep the later GET as a plain HTTP operation over the verified connection.
old='''  if(method=="GET") {
    gTlsAttemptedThisJob.store(true,std::memory_order_relaxed);
    gTlsFailedAllocCount.store(0,std::memory_order_relaxed);
    gTlsFailedAllocSize.store(0,std::memory_order_relaxed);
    gTlsFailedAllocCaps.store(0,std::memory_order_relaxed);
    gTlsFailedAllocTask.store(0,std::memory_order_relaxed);
    gTlsFailedCapsFree.store(0,std::memory_order_relaxed); gTlsFailedCapsLargest.store(0,std::memory_order_relaxed);
    gTlsFailedInternalFree.store(0,std::memory_order_relaxed); gTlsFailedInternalLargest.store(0,std::memory_order_relaxed);
    gTlsFailed8BitFree.store(0,std::memory_order_relaxed); gTlsFailed8BitLargest.store(0,std::memory_order_relaxed);
    gTlsFailedDmaFree.store(0,std::memory_order_relaxed); gTlsFailedDmaLargest.store(0,std::memory_order_relaxed);
    gTlsFailed32BitFree.store(0,std::memory_order_relaxed); gTlsFailed32BitLargest.store(0,std::memory_order_relaxed);
    gTlsAllocWindow.store(true,std::memory_order_release);
    httpCode=http.GET();
  const time_t tlsNowPost=time(nullptr);
  gTlsEpochPost=(int64_t)tlsNowPost;
  gTlsTimeSanePost=tlsEpochSane(tlsNowPost);
  gTlsInternalPostVerifyFree=heap_caps_get_free_size(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
  gTlsInternalPostVerifyLargest=heap_caps_get_largest_free_block(MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT);
    gTlsAllocWindow.store(false,std::memory_order_release);
  } else if(method=="PUT")'''
new='''  if(method=="GET") {
    httpCode=http.GET();
  } else if(method=="PUT")'''
if old in s:
    s=s.replace(old,new,1)
elif new not in s:
    raise RuntimeError('15AH GET instrumentation anchor missing')

# Security and lifecycle gates.
code=s.replace('// Never fall back to setInsecure() because API secrets are sent in request headers.','')
if 'setInsecure(' in code: raise RuntimeError('15AH security invariant: insecure TLS')
if 'client.setCACert(ECOFLOW_CA_BUNDLE);' not in s: raise RuntimeError('15AH CA lost')
if s.count('client.connect(API_HOST,443)')!=1: raise RuntimeError('15AH early handshake cardinality')
if s.count('gTlsAttemptedThisJob.store(true')!=1: raise RuntimeError('15AH attempt marker cardinality')
if s.count('gTlsAllocWindow.store(true')!=1: raise RuntimeError('15AH alloc-window cardinality')

p.write_text(s,encoding='utf-8')
print('[15AH] early verified TLS handshake installed before HTTP allocations')
