#!/usr/bin/env python3
from pathlib import Path
import runpy

p = Path('src/powerstream_api.cpp')
s = p.read_text(encoding='utf-8')

def rep(old, new, name):
    global s
    if s.count(old) != 1:
        raise SystemExit(f'{name}: expected exactly one match, got {s.count(old)}')
    s = s.replace(old, new)

rep('static std::atomic<uint32_t> gTlsInternalFreePre{0}, gTlsInternalLargestPre{0};\nstatic std::atomic<uint32_t> gTlsInternalFreePost{0}, gTlsInternalLargestPost{0};', '''static std::atomic<uint32_t> gTlsInternalFreePre{0}, gTlsInternalLargestPre{0};
static std::atomic<uint32_t> gTlsInternalFreePost{0}, gTlsInternalLargestPost{0};
// 9.36.7.15D: runtime credential provenance + INTERNAL-DRAM phase trace.
// Fingerprints are truncated SHA-256 values; raw credentials are never exported.
static std::atomic<uint32_t> gCredAccessLen{0}, gCredSecretLen{0};
static std::atomic<bool> gCredAccessNvsMatch{false}, gCredSecretNvsMatch{false};
static std::atomic<uint32_t> gCredAccessFp{0}, gCredSecretFp{0};
static std::atomic<bool> gCredRequestAccessMatch{false}, gCredRequestSecretMatch{false};
static std::atomic<uint32_t> gTlsInternalHmacPreFree{0}, gTlsInternalHmacPreLargest{0};
static std::atomic<uint32_t> gTlsInternalHmacPostFree{0}, gTlsInternalHmacPostLargest{0};
static std::atomic<uint32_t> gTlsInternalHeadersPostFree{0}, gTlsInternalHeadersPostLargest{0};
static std::atomic<uint32_t> gTlsInternalGetPreFree{0}, gTlsInternalGetPreLargest{0};
static std::atomic<uint32_t> gTlsInternalGetPostFree{0}, gTlsInternalGetPostLargest{0};''', 'diag atomics')

rep('static String maskKey(const String& s) {', '''static uint32_t credentialFingerprint(const String& value) {
  unsigned char out[32]{};
  const mbedtls_md_info_t* info=mbedtls_md_info_from_type(MBEDTLS_MD_SHA256);
  if(!info || mbedtls_md(info,(const unsigned char*)value.c_str(),value.length(),out)!=0) return 0;
  return ((uint32_t)out[0]<<24)|((uint32_t)out[1]<<16)|((uint32_t)out[2]<<8)|out[3];
}
static String fpHex(uint32_t v){ char b[9]; snprintf(b,sizeof(b),"%08lx",(unsigned long)v); return String(b); }
static void credentialProvenanceRefresh(bool verifyNvs) {
  gCredAccessLen.store(gAccess.length(),std::memory_order_relaxed);
  gCredSecretLen.store(gSecret.length(),std::memory_order_relaxed);
  gCredAccessFp.store(credentialFingerprint(gAccess),std::memory_order_relaxed);
  gCredSecretFp.store(credentialFingerprint(gSecret),std::memory_order_relaxed);
  if(!verifyNvs) return;
  Preferences p; p.begin("psapi",true);
  String a=p.getString("access",""); String k=p.getString("secret",""); p.end();
  gCredAccessNvsMatch.store(a==gAccess,std::memory_order_relaxed);
  gCredSecretNvsMatch.store(k==gSecret,std::memory_order_relaxed);
}

static String maskKey(const String& s) {''', 'fingerprint helper')

rep('  p.end();\n  psApiState.configured = gSn.length() && gAccess.length() && gSecret.length();\n}\n\nbool powerStreamApiSave', '  p.end();\n  psApiState.configured = gSn.length() && gAccess.length() && gSecret.length();\n  credentialProvenanceRefresh(true);\n}\n\nbool powerStreamApiSave', 'load provenance')
rep('  p.end();\n  psApiState.configured = gSn.length() && gAccess.length() && gSecret.length();\n  return true;\n}', '  p.end();\n  psApiState.configured = gSn.length() && gAccess.length() && gSecret.length();\n  credentialProvenanceRefresh(true);\n  return true;\n}', 'save provenance')
rep('  gAccess=""; gSecret=""; gSn="HW51ZEH49GB10829";\n  psApiState = PowerStreamApiState();', '  gAccess=""; gSecret=""; gSn="HW51ZEH49GB10829";\n  credentialProvenanceRefresh(true);\n  psApiState = PowerStreamApiState();', 'clear provenance')

rep('  String signBase = flattened.length() ? flattened + "&" : "";\n  signBase += "accessKey="+gAccess+"&nonce="+nonce+"&timestamp="+timestamp;\n  String sig=hmac256(signBase,gSecret);\n  if(!sig.length()){err="HMAC-SHA256 fehlgeschlagen";return false;}\n  http.addHeader("accessKey",gAccess); http.addHeader("nonce",nonce);\n  http.addHeader("timestamp",timestamp); http.addHeader("sign",sig);', '''  String signBase = flattened.length() ? flattened + "&" : "";
  const String requestAccess=gAccess;
  const uint32_t requestSecretFp=credentialFingerprint(gSecret);
  signBase += "accessKey="+requestAccess+"&nonce="+nonce+"&timestamp="+timestamp;
  tlsInternalSnap(gTlsInternalHmacPreFree,gTlsInternalHmacPreLargest);
  String sig=hmac256(signBase,gSecret);
  tlsInternalSnap(gTlsInternalHmacPostFree,gTlsInternalHmacPostLargest);
  gCredRequestSecretMatch.store(requestSecretFp==gCredSecretFp.load(std::memory_order_relaxed),std::memory_order_relaxed);
  if(!sig.length()){err="HMAC-SHA256 fehlgeschlagen";return false;}
  http.addHeader("accessKey",requestAccess); http.addHeader("nonce",nonce);
  http.addHeader("timestamp",timestamp); http.addHeader("sign",sig);
  gCredRequestAccessMatch.store(requestAccess==gAccess && credentialFingerprint(requestAccess)==gCredAccessFp.load(std::memory_order_relaxed),std::memory_order_relaxed);
  tlsInternalSnap(gTlsInternalHeadersPostFree,gTlsInternalHeadersPostLargest);''', 'auth phase trace')
rep('  cloudDiagMark(CLOUD_DIAG_HTTP_GET,gCloudTraceJobId.load());\n  tlsMemSnap(gTlsHeapGetPre,gTlsLargestGetPre);', '  cloudDiagMark(CLOUD_DIAG_HTTP_GET,gCloudTraceJobId.load());\n  tlsMemSnap(gTlsHeapGetPre,gTlsLargestGetPre);\n  tlsInternalSnap(gTlsInternalGetPreFree,gTlsInternalGetPreLargest);', 'get pre internal')
rep('  tlsMemSnap(gTlsHeapGetPost,gTlsLargestGetPost);\n  tlsInternalSnap(gTlsInternalFreePost,gTlsInternalLargestPost);', '  tlsMemSnap(gTlsHeapGetPost,gTlsLargestGetPost);\n  tlsInternalSnap(gTlsInternalGetPostFree,gTlsInternalGetPostLargest);\n  tlsInternalSnap(gTlsInternalFreePost,gTlsInternalLargestPost);', 'get post internal')

needle = ',\\\"internal_free_pre\\\":"+String(gTlsInternalFreePre.load())+",\\\"internal_largest_pre\\\":"+String(gTlsInternalLargestPre.load())+",\\\"internal_free_post\\\":"+String(gTlsInternalFreePost.load())+",\\\"internal_largest_post\\\":"+String(gTlsInternalLargestPost.load())+'
insert = ',\\\"cred_access_len\\\":"+String(gCredAccessLen.load())+",\\\"cred_secret_len\\\":"+String(gCredSecretLen.load())+",\\\"cred_access_nvs_match\\\":"+(gCredAccessNvsMatch.load()?"true":"false")+",\\\"cred_secret_nvs_match\\\":"+(gCredSecretNvsMatch.load()?"true":"false")+",\\\"cred_access_fp\\\":\\\""+fpHex(gCredAccessFp.load())+"\\\",\\\"cred_secret_fp\\\":\\\""+fpHex(gCredSecretFp.load())+"\\\",\\\"cred_request_access_match\\\":"+(gCredRequestAccessMatch.load()?"true":"false")+",\\\"cred_request_secret_match\\\":"+(gCredRequestSecretMatch.load()?"true":"false")+",\\\"tls_internal_hmac_pre_free\\\":"+String(gTlsInternalHmacPreFree.load())+",\\\"tls_internal_hmac_pre_largest\\\":"+String(gTlsInternalHmacPreLargest.load())+",\\\"tls_internal_hmac_post_free\\\":"+String(gTlsInternalHmacPostFree.load())+",\\\"tls_internal_hmac_post_largest\\\":"+String(gTlsInternalHmacPostLargest.load())+",\\\"tls_internal_headers_post_free\\\":"+String(gTlsInternalHeadersPostFree.load())+",\\\"tls_internal_headers_post_largest\\\":"+String(gTlsInternalHeadersPostLargest.load())+",\\\"tls_internal_get_pre_free\\\":"+String(gTlsInternalGetPreFree.load())+",\\\"tls_internal_get_pre_largest\\\":"+String(gTlsInternalGetPreLargest.load())+",\\\"tls_internal_get_post_free\\\":"+String(gTlsInternalGetPostFree.load())+",\\\"tls_internal_get_post_largest\\\":"+String(gTlsInternalGetPostLargest.load())+"' + needle
rep(needle, insert, 'status json')

p.write_text(s, encoding='utf-8')
print('15D runtime patch applied deterministically')
# On the 15E branch, layer the allocator-failure probe only after the proven 15D transform.
runpy.run_path('tools/apply_tls15e_failed_alloc_patch.py', run_name='__main__')
