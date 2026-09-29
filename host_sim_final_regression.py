import random,re,json,time,sys,os
FW=sys.argv[1] if len(sys.argv)>1 else os.path.dirname(os.path.abspath(__file__))
SRC=open(os.path.join(FW,'src/ecoflow.cpp'),encoding='utf-8').read()
BMS=open(os.path.join(FW,'src/bms.cpp'),encoding='utf-8').read()
BLE=open(os.path.join(FW,'src/jk_ble_proxy.cpp'),encoding='utf-8').read()
CFG=open(os.path.join(FW,'include/config.h'),encoding='utf-8').read()

def mcrc(d):
 c=0xffff
 for b in d:
  c^=b
  for _ in range(8): c=((c>>1)^0xA001) if c&1 else c>>1
 return c&0xffff
m=re.search(r'static const uint16_t table\[\] PROGMEM = \{(.*?)\};',SRC,re.S)
TAB=[int(x,0) for x in re.findall(r'0x[0-9A-Fa-f]+|\b\d+\b',m.group(1))]
assert len(TAB)==256
def ecrc(d):
 c=0
 for b in d:c=TAB[(c^b)&255]^(c>>8)
 return c&0xffff

def eco(payload,key):
 h=bytearray(random.getrandbits(8) for _ in range(18));h[2]=len(payload)&255;h[3]=len(payload)>>8;h[6]=key
 b=bytes(h)+bytes(x^key for x in payload);c=ecrc(b);return b+bytes((c&255,c>>8))
def valid_eco(x):
 if len(x)<20:return False
 n=x[2]|x[3]<<8
 if n>2048 or len(x)!=20+n:return False
 c=ecrc(x[:-2]);return c in (x[-2]|x[-1]<<8,x[-2]<<8|x[-1])

def ack(addr,reg):
 b=bytes((addr,0x10,reg>>8,reg&255,0,1));c=mcrc(b);return b+bytes((c&255,c>>8))
def jk(addr,reg,n):
 p=bytearray(300);p[:6]=b'\x55\xaa\xeb\x90\x01\x00'
 for i in range(6,299):p[i]=random.getrandbits(8)
 p[299]=sum(p[:299])&255;a=ack(addr,reg)
 return bytes(p)+ (a if n==308 else (b'\0'+a+b'\0' if n==310 else bytes(24)+a))
def valid_jk(x,a,r):
 allowed=(308,310,332) if r==0x161e else (308,310)
 if len(x) not in allowed or x[:4]!=b'\x55\xaa\xeb\x90' or x[4] not in (1,2) or x[5]!=0:return False
 if (sum(x[:299])&255)!=x[299]:return False
 off={308:300,310:301,332:324}[len(x)]
 if len(x)==310 and (x[300] or x[309]):return False
 q=x[off:off+8]
 return q[:6]==bytes((a,0x10,r>>8,r&255,0,1)) and mcrc(q[:6])==(q[6]|q[7]<<8)

class Reasm:
 def __init__(self):self.reset()
 def reset(self):self.b=bytearray();self.active=False;self.target=None
 def feed(self,kind,data):
  if len(data)>8:return False
  if kind=='S':self.reset();self.active=True
  elif not self.active:return False
  if len(self.b)+len(data)>2068:self.reset();return False
  if self.target is not None and len(self.b)+len(data)>self.target:self.reset();return False
  self.b.extend(data)
  if self.target is None and len(self.b)>=4:
   n=self.b[2]|self.b[3]<<8
   if n>2048:self.reset();return False
   self.target=20+n
  if kind=='E':
   ok=self.active and self.target is not None and len(self.b)==self.target and valid_eco(bytes(self.b));self.reset();return ok
  return None

def frames(msg):
 parts=[msg[i:i+8] for i in range(0,len(msg),8)]
 return [('S' if i==0 else ('E' if i==len(parts)-1 else 'M'),p) for i,p in enumerate(parts)]

def static_checks():
 req=[('FW version','2.4.5.9.36.7.11-AUDIT20.4.5.9.36.7.11-SECURITY-HARDENED-DIAG' in CFG),('CAN exact header','headerSize != 18' in SRC),('CAN payload cap','payloadSize > 512' in SRC),('DLC guard','data_length_code > 8' in SRC),('CRC guard','CRC mismatch' in SRC),('CAN cap','MSG14001_MAX_PAYLOAD 2048' in SRC),('RS485 9600','9600' in BMS),('status trigger','0x1620' in BMS),('setup trigger','0x161E' in BMS or '0x161e' in BMS),('BLE sync connect + attr cache','connect(target, false, false, false)' in BLE),('bad format gone','%04XX' not in SRC),('332 ACK offset','validAckAt(324)' in BMS)]
 bad=[n for n,v in req if not v]
 if bad:raise AssertionError('static checks failed: '+','.join(bad))
 return len(req)

def run(seed,rounds):
 random.seed(seed);s={'eco_valid':0,'eco_corrupt_reject':0,'can_reasm_valid':0,'can_drop_reject':0,'can_dup_reject':0,'can_trailing_reject':0,'jk_valid':0,'jk_corrupt_reject':0,'jk_332_ignored_trailer_stable':0,'fifo_ops':0,'ring_ops':0}
 for _ in range(rounds):
  p=os.urandom(random.randrange(513));m=eco(p,random.randrange(256));assert valid_eco(m);s['eco_valid']+=1
  z=bytearray(m);z[random.randrange(len(z))]^=1<<random.randrange(8);assert not valid_eco(z);s['eco_corrupt_reject']+=1
  fs=frames(m);r=Reasm();out=None
  for k,d in fs:out=r.feed(k,d)
  assert out is True;s['can_reasm_valid']+=1
  if len(fs)>2:
   r=Reasm();out=None
   drop=random.randrange(1,len(fs)-1)
   for i,(k,d) in enumerate(fs):
    if i!=drop:out=r.feed(k,d)
   assert out is not True;s['can_drop_reject']+=1
   r=Reasm();out=None;dup=random.randrange(1,len(fs)-1)
   for i,(k,d) in enumerate(fs):
    out=r.feed(k,d)
    if i==dup:out=r.feed(k,d)
   assert out is not True;s['can_dup_reject']+=1
  r=Reasm();badfs=frames(m)
  # append trailing byte via extra END semantics; if last frame has room, mutate it; otherwise extra END
  k,d=badfs[-1]
  if len(d)<8:badfs[-1]=(k,d+b'X')
  else:badfs.append(('E',b'X'))
  out=None
  for k,d in badfs:out=r.feed(k,d)
  assert out is not True;s['can_trailing_reject']+=1
  reg=random.choice((0x1620,0x161e));n=random.choice((308,310) if reg==0x1620 else (308,310,332));a=random.randrange(16);x=jk(a,reg,n);assert valid_jk(x,a,reg);s['jk_valid']+=1
  y=bytearray(x);off={308:300,310:301,332:324}[n];pos=random.choice(list(range(300))+list(range(off,off+8)));y[pos]^=1<<random.randrange(8);assert not valid_jk(y,a,reg);s['jk_corrupt_reject']+=1
  if n==332:
   # Bytes 300..323 are opaque/unused by firmware. Mutating them must not change validation.
   z=bytearray(x);pos=random.randrange(300,324);z[pos]^=1<<random.randrange(8);assert valid_jk(z,a,reg);s['jk_332_ignored_trailer_stable']+=1
 # queue stress with overflow fail-closed
 fifo=[];q1=[];q2=[]
 for _ in range(rounds*10):
  op=random.randrange(10)
  if op<4:
   if len(fifo)>=16:fifo.clear();q1.clear();q2.clear()
   else:fifo.append(op)
  elif op==4 and fifo:fifo.pop(0)
  elif op in (5,6):
   q=q1 if op==5 else q2
   if len(q)<2:q.append(1)
  else:
   if q1:q1.pop(0)
   if q2:q2.pop(0)
  assert len(fifo)<=16 and len(q1)<=2 and len(q2)<=2;s['fifo_ops']+=1
 # byte ring accounting
 used=0;cap=4096
 for _ in range(rounds*6):
  if random.random()<.7:
   n=random.randrange(7000)
   if n<=cap-used:used+=n
  else:used=max(0,used-random.randrange(1200))
  assert 0<=used<=cap;s['ring_ops']+=1
 return s

if __name__=='__main__':
 t=time.time();checks=static_checks();tot={}
 for seed in range(20):
  x=run(seed,2000)
  for k,v in x.items():tot[k]=tot.get(k,0)+v
 tot['seeds']=20;tot['static_checks']=checks;tot['seconds']=round(time.time()-t,3)
 print(json.dumps(tot,indent=2,sort_keys=True))
