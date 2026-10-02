Import("env")
from pathlib import Path

# 15AC-A is observation-only. It records authentication construction metadata
# without exposing UID/SN/digest/key/IV/frame bytes and without changing the
# transmitted authentication payload.
p = Path(env.subst("$PROJECT_DIR")) / "src" / "powerstream_ble_lab.cpp"
s = p.read_text(encoding="utf-8")

anchor = 'static std::atomic<int> sAuthDisconnectAtFailure{-1};'
insert = '''static std::atomic<uint32_t> s15acUidLen{0},s15acSnLen{0},s15acInputLen{0};
static std::atomic<uint32_t> s15acDigestRawLen{0},s15acDigestTxLen{0};
static std::atomic<uint32_t> s15acAuthStatusFrameLen{0},s15acAuthFrameLen{0};
static std::atomic<int> s15acAuthStatusVersion{3},s15acAuthVersion{3};
static std::atomic<int> s15acAuthStatusCmdSet{0x35},s15acAuthStatusCmdId{0x89};
static std::atomic<int> s15acAuthCmdSet{0x35},s15acAuthCmdId{0x86};
'''
if insert not in s:
    if s.count(anchor) != 1:
        raise RuntimeError("15AC auth state anchor missing/non-unique")
    s = s.replace(anchor, anchor + "\n" + insert, 1)

old = 'static size_t authStatus(uint8_t*out){uint8_t p[64];return encrypt(p,packet(p,0x21,0x35,0x35,0x89,nullptr,0,3,1,1),out);}'
new = 'static size_t authStatus(uint8_t*out){uint8_t p[64];size_t n=encrypt(p,packet(p,0x21,0x35,0x35,0x89,nullptr,0,3,1,1),out);s15acAuthStatusFrameLen=n;return n;}'
if old in s:
    s = s.replace(old,new,1)
elif new not in s:
    raise RuntimeError("15AC authStatus anchor missing/non-unique")

old = 'static size_t autoAuth(uint8_t*out){uint8_t m[16];String x=sUid+sSn;md5raw((const uint8_t*)x.c_str(),x.length(),m);const char*H="0123456789ABCDEF";uint8_t hp[32];for(int i=0;i<16;i++){hp[2*i]=H[m[i]>>4];hp[2*i+1]=H[m[i]&15];}uint8_t p[80];return encrypt(p,packet(p,0x21,0x35,0x35,0x86,hp,32,3,1,1),out);}'
new = 'static size_t autoAuth(uint8_t*out){uint8_t m[16];String x=sUid+sSn;s15acUidLen=sUid.length();s15acSnLen=sSn.length();s15acInputLen=x.length();s15acDigestRawLen=16;s15acDigestTxLen=32;md5raw((const uint8_t*)x.c_str(),x.length(),m);const char*H="0123456789ABCDEF";uint8_t hp[32];for(int i=0;i<16;i++){hp[2*i]=H[m[i]>>4];hp[2*i+1]=H[m[i]&15];}uint8_t p[80];size_t n=encrypt(p,packet(p,0x21,0x35,0x35,0x86,hp,32,3,1,1),out);s15acAuthFrameLen=n;return n;}'
if old in s:
    s = s.replace(old,new,1)
elif new not in s:
    raise RuntimeError("15AC autoAuth anchor missing/non-unique")

# Add metadata to the existing JSON diagnostics adjacent to auth_frame_len.
anchor = 'root["auth_frame_len"]=(uint32_t)sAuthFrameLen.load();'
extra = '''root["auth15ac_version"]="9.36.7.15AC-A-METADATA";
  root["auth15ac_variant"]="A_UID_PLUS_SN_ASCII_HEX";
  root["auth15ac_uid_len"]=(uint32_t)s15acUidLen.load();
  root["auth15ac_sn_len"]=(uint32_t)s15acSnLen.load();
  root["auth15ac_input_len"]=(uint32_t)s15acInputLen.load();
  root["auth15ac_digest_raw_len"]=(uint32_t)s15acDigestRawLen.load();
  root["auth15ac_digest_tx_len"]=(uint32_t)s15acDigestTxLen.load();
  root["auth15ac_status_frame_len"]=(uint32_t)s15acAuthStatusFrameLen.load();
  root["auth15ac_auth_frame_len"]=(uint32_t)s15acAuthFrameLen.load();
  root["auth15ac_status_version"]=(int)s15acAuthStatusVersion.load();
  root["auth15ac_auth_version"]=(int)s15acAuthVersion.load();
  root["auth15ac_status_cmd_set"]=(int)s15acAuthStatusCmdSet.load();
  root["auth15ac_status_cmd_id"]=(int)s15acAuthStatusCmdId.load();
  root["auth15ac_auth_cmd_set"]=(int)s15acAuthCmdSet.load();
  root["auth15ac_auth_cmd_id"]=(int)s15acAuthCmdId.load();'''
if extra not in s:
    if s.count(anchor) != 1:
        raise RuntimeError("15AC JSON anchor missing/non-unique")
    s = s.replace(anchor, anchor + "\n  " + extra, 1)

p.write_text(s,encoding="utf-8")
print("[15AC-A] auth metadata probe installed; transmitted payload unchanged")
