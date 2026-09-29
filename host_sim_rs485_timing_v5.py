import random, json
TIMEOUT=1200

def crc16(data):
 c=0xffff
 for b in data:
  c^=b
  for _ in range(8): c=(c>>1)^0xA001 if c&1 else c>>1
 return c&0xffff

def payload(seq=1):
 p=bytearray(300); p[:6]=bytes([0x55,0xaa,0xeb,0x90,seq,0]);
 for i in range(6,299): p[i]=(i*37+11)&255
 p[299]=sum(p[:299])&255; return p

def ack(addr,reg):
 a=bytearray([addr,0x10,reg>>8,reg&255,0,1]); c=crc16(a); return a+bytes([c&255,c>>8])
def frame(addr,reg,kind):
 p=payload()
 if kind==308:return p+ack(addr,reg)
 if kind==310:return p+b'\0'+ack(addr,reg)+b'\0'
 if kind==332:return p+bytes((i*13+7)&255 for i in range(24))+ack(addr,reg)

# Transaction-level model of exact acceptance rules in bms.cpp.
def accepts(buf,addr,reg):
 n=len(buf)
 if n not in ((308,310) if reg==0x1620 else (308,310,332)): return False
 if buf[:4]!=b'\x55\xaa\xeb\x90' or buf[4] not in (1,2) or buf[5]!=0:return False
 if (sum(buf[:299])&255)!=buf[299]:return False
 off=300 if n==308 else 301 if n==310 else 324
 if n==310 and not(buf[300]==0 and buf[309]==0):return False
 a=buf[off:off+8]
 if a[:6]!=bytes([addr,0x10,reg>>8,reg&255,0,1]):return False
 return crc16(a[:6])==(a[6]|a[7]<<8)

def run(seed,cycles=500):
 r=random.Random(seed); stats={k:0 for k in ['valid','timeout','late_old','mixed_reject','false_accept','boundary_ok']}
 for _ in range(cycles):
  addr=r.randrange(16); reg=r.choice([0x1620,0x161e]); kind=r.choice([308,310] + ([332] if reg==0x161e else [])); f=frame(addr,reg,kind)
  # byte arrival schedule, ~1.04ms/byte plus random pauses, including timeout-edge pauses
  t=r.uniform(0,80); arrival=[]
  cut=r.randrange(20,len(f)-10)
  for i,b in enumerate(f):
   if i==cut and r.random()<0.35: t+=r.choice([1100,1180,1195,1201,1250,1600])
   else: t+=r.uniform(.85,1.5)
   arrival.append((t,b))
  before=bytes(b for t,b in arrival if t<=TIMEOUT)
  if len(before)==len(f):
   stats['valid']+=1
   if not accepts(before,addr,reg): stats['false_accept']+=1 # valid should accept
   continue
  stats['timeout']+=1
  late=bytes(b for t,b in arrival if t>TIMEOUT); stats['late_old']+=len(late)
  # next request: firmware drains max 128 stale bytes, then starts capture. Model remaining old + new response.
  remain=late[128:]
  newreg=r.choice([0x1620,0x161e]); nk=r.choice([308,310] + ([332] if newreg==0x161e else [])); nf=frame(addr,newreg,nk)
  stream=remain+nf
  # header sync: first 55AAEB90 after bounded drain
  pos=stream.find(b'\x55\xaa\xeb\x90')
  if pos<0: continue
  candidate=stream[pos:]
  lengths=[308,310] + ([332] if newreg==0x161e else [])
  accepted=False
  for n in lengths:
   if len(candidate)>=n and accepts(candidate[:n],addr,newreg): accepted=True; break
  if remain:
   if accepted and pos < len(remain): stats['false_accept']+=1
   elif accepted: stats['boundary_ok']+=1
   else: stats['mixed_reject']+=1
  else:
   if accepted: stats['boundary_ok']+=1
   else: stats['false_accept']+=1
 return stats

tot={}
for s in range(100,200):
 d=run(s)
 for k,v in d.items():tot[k]=tot.get(k,0)+v
print(json.dumps(tot,indent=2))
with open('HOST_SIM_RS485_TIMING_V5_RESULTS.json','w') as f: json.dump(tot,f,indent=2)
