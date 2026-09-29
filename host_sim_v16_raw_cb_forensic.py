import random
PRE=160; POST=160; POST_MS=5000
class R:
 def __init__(self): self.pre=[];self.post=[];self.tr=False;self.fr=False;self.t=0;self.trk=0
 def raw(self,ms,token):
  if self.fr:return
  if not self.tr:
   self.pre.append((ms,token));self.pre=self.pre[-PRE:]
  else:
   if len(self.post)<POST:self.post.append((ms,token))
   if len(self.post)>=POST or ((ms-self.t)&0xffffffff)>=POST_MS:self.fr=True
 def trigger(self,ms,trk):
  if trk not in (0x2031,0x2033):return
  if not self.tr and not self.fr:self.tr=True;self.t=ms;self.trk=trk
 def tick(self,ms):
  if self.tr and not self.fr and ((ms-self.t)&0xffffffff)>=POST_MS:self.fr=True
checks=0
for seed in range(4000):
 random.seed(seed); r=R(); ms=random.randrange(0xffffffff-20000,0xffffffff) if seed%7==0 else random.randrange(1000000)
 hist=[]
 n=random.randint(0,500)
 for i in range(n):
  ms=(ms+random.randint(0,20))&0xffffffff; tok=('pre',seed,i);hist.append((ms,tok));r.raw(ms,tok);checks+=1
 exp=hist[-PRE:]; assert r.pre==exp; checks+=1
 # false trigger must not arm
 r.trigger(ms,0x0321); assert not r.tr; checks+=1
 trk=0x2031 if seed&1 else 0x2033; r.trigger(ms,trk); assert r.tr and r.trk==trk;checks+=1
 frozen_pre=list(r.pre)
 # second valid trigger must not overwrite first
 r.trigger((ms+1)&0xffffffff,0x2033 if trk==0x2031 else 0x2031); assert r.trk==trk;checks+=1
 for j in range(random.randint(0,300)):
  ms=(ms+random.randint(0,60))&0xffffffff;r.raw(ms,('post',seed,j));checks+=1
  if r.fr:break
 assert r.pre==frozen_pre and len(r.post)<=POST;checks+=2
 # force timeout with wrap-safe arithmetic
 r.tick((r.t+POST_MS)&0xffffffff); assert r.fr;checks+=1
 old=(list(r.pre),list(r.post));r.raw((ms+1)&0xffffffff,('late',seed));assert old==(r.pre,r.post);checks+=1
print(f'PASS RAW CB forensic model: {checks:,} checks; seeds=4000; wrap, ring, false-trigger, retrigger, freeze tested')
