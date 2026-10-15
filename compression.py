"""Exact-length encoding for the game's compressed tile channels."""
import numpy as np
import heapq
from functools import lru_cache
try:
 from compression_fast import optimal as native_optimal
except (ImportError,OSError):native_optimal=None

def header(n,repeat,extra=0):
 flag=128 if repeat else 0
 natural=0 if n<=125 else 1 if n<=255 else 2 if n<=65535 else 3
 width=min(3,natural+extra)
 return bytes([flag+n-1]) if width==0 else bytes([flag+124+width])+n.to_bytes(width,'big')

def reference_optimal(data,run_limits=None):
 n=len(data);dp=np.full(n+1,10**9,dtype=np.int64);dp[n]=0
 length=np.zeros(n,dtype=np.int32);repeat=np.zeros(n,dtype=bool)
 runs=np.ones(n,dtype=np.int32)
 for i in range(n-2,-1,-1):
  if data[i]==data[i+1]:runs[i]=runs[i+1]+1
 if run_limits is not None:runs=run_limits
 seq=np.arange(1,126)
 for i in range(n-1,-1,-1):
  count=min(125,n-i);costs=dp[i+1:i+count+1]+seq[:count]+1
  k=int(costs.argmin());dp[i]=costs[k];length[i]=k+1
  for lo,hi,cost in [(126,255,2),(256,65535,3),(65536,16777215,4)]:
   end=min(n-i,hi)
   if end<lo:continue
   costs=dp[i+lo:i+end+1]+np.arange(lo,end+1)+cost
   j=int(costs.argmin());value=int(costs[j])
   if value<dp[i]:dp[i]=value;length[i]=lo+j
  for lo,hi,cost in [(1,125,2),(126,255,3),(256,65535,4),(65536,16777215,5)]:
   end=min(int(runs[i]),hi)
   if end<lo:continue
   part=dp[i+lo:i+end+1];j=int(part.argmin());value=int(part[j])+cost
   if value<dp[i]:dp[i]=value;length[i]=lo+j;repeat[i]=True
 return int(dp[0]),length,repeat

@lru_cache(maxsize=4)
def packet_plan(data):
 global native_optimal
 if native_optimal is not None:
  try:minimum,length,repeat=native_optimal(np.frombuffer(data,dtype=np.uint8))
  except Exception:
   native_optimal=None;minimum,length,repeat=reference_optimal(data)
 else:minimum,length,repeat=reference_optimal(data)
 tokens=[];i=0
 while i<len(data):
  count=int(length[i]);tokens.append((i,count,bool(repeat[i])));i+=count
 return minimum,tuple(tokens)

def encode_exact(data,size):
 """Plan once per channel; expand valid packet headers to the exact length."""
 data=bytes(data);minimum,plan=packet_plan(data)
 if size is None:size=minimum
 if minimum>size:raise ValueError(f'Compressed replacement needs {minimum} bytes; only {size} available')
 tokens=dict(enumerate(plan));serial=len(tokens)
 def cost(token):
  _,count,rep=token;return len(header(count,rep))+(1 if rep else count)
 def room(token):return 4-len(header(token[1],token[2]))
 base=minimum;capacity=sum(room(t) for t in tokens.values());heap=[(-t[1],k) for k,t in tokens.items() if t[1]>1];heapq.heapify(heap)
 # Very simple replacements can compress far below the old size. Split runs
 # into additional legal packets before enlarging headers; padding must be
 # real RLE, not trailing garbage that the game might interpret as pixels.
 while base+capacity<size:
  if not heap:raise ValueError('Cannot construct this exact compressed length.')
  _,key=heapq.heappop(heap);old=tokens.pop(key);start,count,rep=old
  parts=[(start,1,rep),(start+1,count-1,rep)];delta=sum(cost(t) for t in parts)-cost(old)
  if base+delta>size:raise ValueError('This compression length cannot be represented exactly.')
  base+=delta;capacity+=sum(room(t) for t in parts)-room(old)
  for token in parts:
   tokens[serial]=token
   if token[1]>1:heapq.heappush(heap,(-token[1],serial))
   serial+=1
 remaining=size-base;result=bytearray()
 for start,count,rep in sorted(tokens.values()):
  extra=min(remaining,4-len(header(count,rep)));remaining-=extra
  result.extend(header(count,rep,extra));result.extend(data[start:start+1] if rep else data[start:start+count])
 assert remaining==0 and len(result)==size,(remaining,len(result),size)
 return bytes(result),minimum


def optimize_ignored_brightness(data,free):
 """Find shortest RLE over legal low-bit values; retain all visible bits."""
 values=np.asarray(data,dtype=np.uint8).ravel().copy();free=np.asarray(free,dtype=bool).ravel()
 if len(values)!=len(free):raise ValueError('Brightness mask length differs')
 if native_optimal is not None:
  from compression_fast import compatible_runs
  runs=compatible_runs(values,free);minimum,length,repeat=native_optimal(values,runs)
 else:
  runs=np.ones(len(values),np.int32);high=[0]*8;fixed=[0]*256;right=0;hi_kind=fixed_kind=-1
  for left in range(len(values)):
   while right<len(values):
    value=int(values[right]);group=value>>5
    if hi_kind!=-1 and hi_kind!=group:break
    if not free[right] and fixed_kind!=-1 and fixed_kind!=value:break
    high[group]+=1;hi_kind=group
    if not free[right]:fixed[value]+=1;fixed_kind=value
    right+=1
   runs[left]=right-left;value=int(values[left]);group=value>>5;high[group]-=1
   if high[group]==0:hi_kind=-1
   if not free[left]:
    fixed[value]-=1
    if fixed[value]==0:fixed_kind=-1
  minimum,length,repeat=reference_optimal(values,runs)
 fixed_positions=np.flatnonzero(~free);pos=0
 while pos<len(values):
  count=int(length[pos])
  if repeat[pos]:
   k=int(np.searchsorted(fixed_positions,pos));value=values[fixed_positions[k]] if k<len(fixed_positions) and fixed_positions[k]<pos+count else values[pos]
   values[pos:pos+count]=value
  pos+=count
 return values,int(minimum)

def optimize_equivalent_indices(data,contexts,groups,preferred=None):
 """RLE across palette values with identical rendering in this context."""
 values=np.asarray(data,np.uint8).ravel().copy();contexts=np.asarray(contexts,np.int32).ravel();groups=np.asarray(groups,np.int16)
 if native_optimal is not None:
  from compression_fast import equivalent_runs
  runs=equivalent_runs(values,contexts,groups);minimum,length,repeat=native_optimal(values,runs)
 else:
  ends=np.full(groups.shape[1],len(values),np.int32);runs=np.ones(len(values),np.int32)
  for i in range(len(values)-1,-1,-1):
   compatible=groups[contexts[i]]==groups[contexts[i],values[i]];ends[~compatible]=i;runs[i]=int(ends[compatible].max())-i
  minimum,length,repeat=reference_optimal(values,runs)
 pos=0
 while pos<len(values):
  count=int(length[pos])
  if repeat[pos]:
   allowed=np.ones(groups.shape[1],bool)
   for i in range(pos,pos+count):allowed&=groups[contexts[i]]==groups[contexts[i],values[i]]
   choices=np.flatnonzero(allowed);assert len(choices)
   if preferred is None:value=int(values[pos]) if allowed[values[pos]] else int(choices[0])
   else:
    target=np.asarray(preferred[pos:pos+count]);target=target[target>=0]
    center=float(np.median(target)) if len(target) else float(values[pos])
    value=int(choices[np.abs(choices.astype(float)-center).argmin()])
   values[pos:pos+count]=value
  pos+=count
 return values,int(minimum)
