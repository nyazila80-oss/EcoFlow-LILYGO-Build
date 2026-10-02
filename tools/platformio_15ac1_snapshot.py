Import('env')
from pathlib import Path
p=Path('src/powerstream_api.cpp')
s=p.read_text(encoding='utf-8')
old='''  const String requestAccess=gAccess;\n  const uint32_t requestSecretFp=credentialFingerprint(gSecret);\n  signBase += "accessKey="+requestAccess+"&nonce="+nonce+"&timestamp="+timestamp;\n  tlsInternalSnap(gTlsInternalHmacPreFree,gTlsInternalHmacPreLargest);\n  String sig=hmac256(signBase,gSecret);'''
new='''  String requestAccess;\n  String requestSecret;\n  {\n    ApiLock credentialSnapshot(pdMS_TO_TICKS(250));\n    if(!credentialSnapshot.held){err="Credential snapshot lock failed";return false;}\n    requestAccess=gAccess;\n    requestSecret=gSecret;\n  }\n  if(!requestAccess.length() || !requestSecret.length()){err="EcoFlow API credentials missing";return false;}\n  const uint32_t requestSecretFp=credentialFingerprint(requestSecret);\n  signBase += "accessKey="+requestAccess+"&nonce="+nonce+"&timestamp="+timestamp;\n  tlsInternalSnap(gTlsInternalHmacPreFree,gTlsInternalHmacPreLargest);\n  String sig=hmac256(signBase,requestSecret);'''
if old in s:
    if s.count(old)!=1: raise RuntimeError('15AC1 snapshot anchor non-unique')
    s=s.replace(old,new)
elif new not in s:
    raise RuntimeError('15AC1 snapshot anchor missing; apply 15D first')
s=s.replace('gCredRequestSecretMatch.store(requestSecretFp==gCredSecretFp.load(std::memory_order_relaxed),std::memory_order_relaxed);','gCredRequestSecretMatch.store(requestSecretFp==credentialFingerprint(requestSecret),std::memory_order_relaxed);')
s=s.replace('gCredRequestAccessMatch.store(requestAccess==gAccess && credentialFingerprint(requestAccess)==gCredAccessFp.load(std::memory_order_relaxed),std::memory_order_relaxed);','gCredRequestAccessMatch.store(requestAccess.length()>0,std::memory_order_relaxed);')
p.write_text(s,encoding='utf-8')
print('15AC1 request-local credential snapshot applied')
