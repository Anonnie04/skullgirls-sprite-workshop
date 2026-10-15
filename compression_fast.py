"""Native CPU planner for exact RLE, preserving the reference tie rules."""
import numpy as np
from numba import njit

@njit
def query(values,indices,base,left,right):
 left+=base;right+=base;best=1000000000;index=2147483647
 while left<=right:
  if left&1:
   if values[left]<best or (values[left]==best and indices[left]<index):best=values[left];index=indices[left]
   left+=1
  if not right&1:
   if values[right]<best or (values[right]==best and indices[right]<index):best=values[right];index=indices[right]
   right-=1
  left//=2;right//=2
 return best,index

@njit
def optimal(data,run_limits=None):
 n=len(data);dp=np.full(n+1,1000000000,np.int64);dp[n]=0
 length=np.zeros(n,np.int32);repeat=np.zeros(n,np.bool_);runs=np.ones(n,np.int32)
 for i in range(n-2,-1,-1):
  if data[i]==data[i+1]:runs[i]=runs[i+1]+1
 if run_limits is not None:runs=run_limits
 base=1
 while base<n+1:base*=2
 values=np.full(base*2,1000000000,np.int64);indices=np.full(base*2,2147483647,np.int32)
 literals=np.full(base*2,1000000000,np.int64);literal_indices=np.full(base*2,2147483647,np.int32)
 node=base+n;values[node]=0;literals[node]=n;literal_indices[node]=n;indices[node]=n
 while node>1:
  node//=2;a=node*2;b=a+1
  if values[a]<values[b] or (values[a]==values[b] and indices[a]<indices[b]):values[node]=values[a];indices[node]=indices[a]
  else:values[node]=values[b];indices[node]=indices[b]
  pick=a if literals[a]<literals[b] or (literals[a]==literals[b] and literal_indices[a]<literal_indices[b]) else b
  literals[node]=literals[pick];literal_indices[node]=literal_indices[pick]
 for i in range(n-1,-1,-1):
  best=1000000000;count=1
  for k in range(1,min(125,n-i)+1):
   cost=dp[i+k]+k+1
   if cost<best:best=cost;count=k
  length[i]=count
  for group in range(3):
   if group==0:lo=126;hi=255;cost=2
   elif group==1:lo=256;hi=65535;cost=3
   else:lo=65536;hi=16777215;cost=4
   end=min(n-i,hi)
   if end<lo:continue
   # A separate range tree stores dp[j]+j for literal packet endpoints.
   value,index=query(literals,literal_indices,base,i+lo,i+end)
   if value-i+cost<best:best=value-i+cost;length[i]=index-i
  for group in range(4):
   if group==0:lo=1;hi=125;cost=2
   elif group==1:lo=126;hi=255;cost=3
   elif group==2:lo=256;hi=65535;cost=4
   else:lo=65536;hi=16777215;cost=5
   end=min(runs[i],hi)
   if end<lo:continue
   value,index=query(values,indices,base,i+lo,i+end)
   if value+cost<best:best=value+cost;length[i]=index-i;repeat[i]=True
  dp[i]=best;node=base+i;values[node]=best;indices[node]=i;literals[node]=best+i;literal_indices[node]=i
  while node>1:
   node//=2;a=node*2;b=a+1
   if values[a]<values[b] or (values[a]==values[b] and indices[a]<indices[b]):values[node]=values[a];indices[node]=indices[a]
   else:values[node]=values[b];indices[node]=indices[b]
   pick=a if literals[a]<literals[b] or (literals[a]==literals[b] and literal_indices[a]<literal_indices[b]) else b
   literals[node]=literals[pick];literal_indices[node]=literal_indices[pick]
 return int(dp[0]),length,repeat

@njit
def compatible_runs(data,free):
 # Sliding window: one high-bit group and at most one fixed byte value.
 n=len(data);runs=np.ones(n,np.int32);high=np.zeros(8,np.int32);fixed=np.zeros(256,np.int32);right=0;hi_kind=-1;fixed_kind=-1
 for left in range(n):
  while right<n:
   value=int(data[right]);group=value>>5
   if hi_kind!=-1 and hi_kind!=group:break
   if not free[right] and fixed_kind!=-1 and fixed_kind!=value:break
   high[group]+=1;hi_kind=group
   if not free[right]:fixed[value]+=1;fixed_kind=value
   right+=1
  runs[left]=right-left
  value=int(data[left]);group=value>>5;high[group]-=1
  if high[group]==0:hi_kind=-1
  if not free[left]:
   fixed[value]-=1
   if fixed[value]==0:fixed_kind=-1
 return runs

@njit
def equivalent_runs(data,contexts,groups):
 n=len(data);width=groups.shape[1];ends=np.full(width,n,np.int32);runs=np.ones(n,np.int32)
 for i in range(n-1,-1,-1):
  context=contexts[i];label=groups[context,data[i]];best=i+1
  for value in range(width):
   if groups[context,value]!=label:ends[value]=i
   elif ends[value]>best:best=ends[value]
  runs[i]=best-i
 return runs
