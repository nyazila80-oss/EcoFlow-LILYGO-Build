Import("env")
from pathlib import Path

root=Path(env.subst("$PROJECT_DIR"))
p=root/"src"/"powerstream_api.cpp"
s=p.read_text(encoding="utf-8")

# Build-time diagnostic patch only. Runtime snapshots call heap metadata APIs and
# store into atomics; they do not log, allocate Strings, or expose credentials.
anchor='static std::atomic<uint32_t> gTlsHeapGetPost{0}, gTlsLargestGetPost{0};'
insert='''\n// 15AE real-hardware phase attribution (allocation-free snapshots).\nstatic std::atomic<uint32_t> g15aeClientFree{0},g15aeClientLargest{0};\nstatic std::atomic<uint32_t> g15aeCaFree{0},g15aeCaLargest{0};\nstatic std::atomic<uint32_t> g15aeHttpFree{0},g15aeHttpLargest{0};\nstatic std::atomic<uint32_t> g15aeUrlFree{0},g15aeUrlLargest{0};\nstatic std::atomic<uint32_t> g15aeBeginFree{0},g15aeBeginLargest{0};\nstatic std::atomic<uint32_t> g15aeAuthFree{0},g15aeAuthLargest{0};\nstatic inline void snap15ae(std::atomic<uint32_t>& f,std::atomic<uint32_t>& l){\n const uint32_t c=MALLOC_CAP_INTERNAL|MALLOC_CAP_8BIT;\n f.store(heap_caps_get_free_size(c),std::memory_order_relaxed);\n l.store(heap_caps_get_largest_free_block(c),std::memory_order_relaxed);\n}\n'''
if anchor not in s: raise RuntimeError("15AE atomics anchor missing")
s=s.replace(anchor,anchor+insert,1)

repls=[
('  WiFiClientSecure client;\n  tlsMemSnap(gTlsHeapClient,gTlsLargestClient);','  WiFiClientSecure client;\n  snap15ae(g15aeClientFree,g15aeClientLargest);\n  tlsMemSnap(gTlsHeapClient,gTlsLargestClient);'),
('  client.setCACert(ECOFLOW_CA_BUNDLE);\n  tlsMemSnap(gTlsHeapCa,gTlsLargestCa);','  client.setCACert(ECOFLOW_CA_BUNDLE);\n  snap15ae(g15aeCaFree,g15aeCaLargest);\n  tlsMemSnap(gTlsHeapCa,gTlsLargestCa);'),
('  HTTPClient http; http.setTimeout(12000);\n  String url=String(API_BASE)+path+(query.length()?"?"+query:"");','  HTTPClient http; http.setTimeout(12000);\n  snap15ae(g15aeHttpFree,g15aeHttpLargest);\n  String url=String(API_BASE)+path+(query.length()?"?"+query:"");\n  snap15ae(g15aeUrlFree,g15aeUrlLargest);'),
('  tlsMemSnap(gTlsHeapBeginPost,gTlsLargestBeginPost);\n  if(!authHeaders(http,flattened,err))','  tlsMemSnap(gTlsHeapBeginPost,gTlsLargestBeginPost);\n  snap15ae(g15aeBeginFree,g15aeBeginLargest);\n  if(!authHeaders(http,flattened,err))'),
('  if(body.length()) http.addHeader("Content-Type","application/json;charset=UTF-8");','  snap15ae(g15aeAuthFree,g15aeAuthLargest);\n  if(body.length()) http.addHeader("Content-Type","application/json;charset=UTF-8");')]
for a,b in repls:
 if a not in s: raise RuntimeError("15AE phase anchor missing: "+a[:50])
 s=s.replace(a,b,1)

json_anchor='"\\\"tls_heap_client\\\":"+String(gTlsHeapClient.load())+'
json_insert='''"\\\"15ae_client_free\\\":"+String(g15aeClientFree.load())+",\\\"15ae_client_largest\\\":"+String(g15aeClientLargest.load())+",\\\"15ae_ca_free\\\":"+String(g15aeCaFree.load())+",\\\"15ae_ca_largest\\\":"+String(g15aeCaLargest.load())+",\\\"15ae_http_free\\\":"+String(g15aeHttpFree.load())+",\\\"15ae_http_largest\\\":"+String(g15aeHttpLargest.load())+",\\\"15ae_url_free\\\":"+String(g15aeUrlFree.load())+",\\\"15ae_url_largest\\\":"+String(g15aeUrlLargest.load())+",\\\"15ae_begin_free\\\":"+String(g15aeBeginFree.load())+",\\\"15ae_begin_largest\\\":"+String(g15aeBeginLargest.load())+",\\\"15ae_auth_free\\\":"+String(g15aeAuthFree.load())+",\\\"15ae_auth_largest\\\":"+String(g15aeAuthLargest.load())+","+'''
if json_anchor not in s: raise RuntimeError("15AE JSON anchor missing")
s=s.replace(json_anchor,json_insert+json_anchor,1)

p.write_text(s,encoding="utf-8")
print("15AE phase attribution instrumentation applied")
