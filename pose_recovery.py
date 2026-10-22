"""Recover reused/reordered poses with opacity-aware image registration."""
import math
import numpy as np
from numpy.fft import rfft2,irfft2
from PIL import Image,ImageFilter
from scipy.spatial.distance import cdist


def shape(image):
 alpha=image.convert('RGBA').getchannel('A');peak=alpha.getextrema()[1]
 if not peak:return dict(size=image.size,alpha=None,vector=None)
 normalized=alpha.point([round(v*255/peak) for v in range(256)])
 binary=normalized.point([0]*39+[255]*217);box=binary.getbbox()
 mask=binary.crop(box).resize((32,32),Image.Resampling.BOX).filter(ImageFilter.GaussianBlur(1))
 vector=np.concatenate([np.asarray(mask,dtype=np.float32).ravel()/255,np.array([math.log((box[2]-box[0])/(box[3]-box[1]))*4],np.float32)])
 short=normalized.copy();short.thumbnail((64,64),Image.Resampling.BOX)
 return dict(size=image.size,alpha=short,vector=vector)


def overlap(left,right):
 """Best translated overlap at the same native scale, with small scale slack."""
 if left['alpha'] is None or right['alpha'] is None:
  return float(left['alpha'] is None and right['alpha'] is None)
 longest=max(*left['size'],*right['size']);factor=min(1,64/longest)
 def pixels(item,scale=1):
  w,h=item['size'];size=(max(1,round(w*factor*scale)),max(1,round(h*factor*scale)))
  return np.asarray(item['alpha'].resize(size,Image.Resampling.BOX).filter(ImageFilter.GaussianBlur(.5)),dtype=np.float32)/255
 b=pixels(right);bn=float(np.square(b).sum());best=0.
 for scale in [1.,.92,1.08]:
  a=pixels(left,scale);an=float(np.square(a).sum())
  if not an or not bn:continue
  h,w=(1<<(a.shape[k]+b.shape[k]-2).bit_length() for k in range(2))
  af=rfft2(a,s=(h,w));bf=rfft2(b,s=(h,w))
  cross=float(irfft2(af*np.conj(bf),s=(h,w)).max())
  score=min(1.,max(0.,2*cross/(an+bn)))
  best=max(best,score)
  if best>.995:break
 return 1. if best>1.-1e-6 else best


def recover(source,target,old,new,pairs,needs,accepted,progress,cancel,min_overlap=.94,source_shapes=None,target_shapes=None):
 """Return verified candidates without changing the primary sequence mapping."""
 from project_match import primary
 from workshop import safe_path,stopped,pixel_hash
 if not needs:return {}
 primary_pairs={i:j for i,j,_ in pairs};owners={j:i for i,j,_ in pairs}
 targets=[];target_pixels=[]
 for j,(_,entries) in enumerate(new):
  stopped(cancel);route,_=primary(entries)
  with Image.open(safe_path(target/'Output',route)) as im:
   targets.append(target_shapes[j] if target_shapes is not None else shape(im));target_pixels.append(pixel_hash(im))
  if j%100==0:progress(j,len(new),'Indexing reordered and reused poses…')
 matrix=np.array([s['vector'] if s['vector'] is not None else np.full(1025,100) for s in targets])
 fingerprints={}
 def fingerprint(i):
  if i not in fingerprints:
   parts=[]
   for route,e in old[i][1]:
    if e['layer'] is None:continue
    with Image.open(safe_path(source/'Output',route)) as im:
     # Fully transparent RGB is not visible artwork.
     key='transparent' if not im.convert('RGBA').getchannel('A').getbbox() else pixel_hash(im)
    parts.append((e['layer'],key))
   fingerprints[i]=tuple(sorted(parts))
  return fingerprints[i]
 result={}
 for done,i in enumerate(sorted(needs)):
  stopped(cancel);route,_=primary(old[i][1])
  if source_shapes is not None:s=source_shapes[i]
  else:
   with Image.open(safe_path(source/'Output',route)) as im:s=shape(im)
  if s['vector'] is None:candidates=[j for j,t in enumerate(targets) if t['vector'] is None]
  else:candidates=list(map(int,np.argsort(cdist([s['vector']],matrix)[0])[:8]))
  if i in primary_pairs and primary_pairs[i] not in candidates:candidates.append(primary_pairs[i])
  if not candidates:continue
  scores={j:overlap(s,targets[j]) for j in candidates}
  ranked=sorted(scores,key=lambda j:(-scores[j],abs(j-primary_pairs.get(i,j)),j));j=ranked[0]
  # Retain sequence context when its candidate is essentially equally good.
  preferred=primary_pairs.get(i)
  if preferred is not None and scores[preferred]>=scores[j]-.01:j=preferred
  score=scores[j]
  if score<min(.8,min_overlap):continue
  # Identical target images are equivalent, not competing visual poses.
  runner=max((scores[k] for k in candidates if k!=j and target_pixels[k]!=target_pixels[j]),default=0.)
  same_owner=j in owners and owners[j] in accepted and fingerprint(i)==fingerprint(owners[j])
  invisible=s['alpha'] is None and targets[j]['alpha'] is None
  confident=score>=min_overlap and (same_owner or invisible or score-runner>=.02)
  result[i]=dict(target=j,overlap=round(score,5),margin=round(score-runner,5),confident=confident,
   method='identical-source' if same_owner else 'transparent' if invisible else 'registered-pose',
   reason=None if confident else 'A similar pose was found; neighboring or revised artwork requires review')
  if done%10==0:progress(done+1,len(needs),'Recovering reordered, reused and translucent frames…')
 # A many-to-one mapping may reuse identical source art. Different source
 # images must never race to overwrite the same target Input file.
 assignments=dict(primary_pairs);assignments.update({i:r['target'] for i,r in result.items()})
 groups={}
 for i,j in assignments.items():groups.setdefault(j,[]).append(i)
 for i,r in result.items():
  if any(fingerprint(k)!=fingerprint(i) for k in groups[r['target']] if k!=i):
   r['confident']=False;r['reason']='Different source artwork shares this target frame; review before copying'
 return result
