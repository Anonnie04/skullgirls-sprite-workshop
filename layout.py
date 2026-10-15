"""Match game art to the installed Compendium's animation folder names."""
from pathlib import Path
import hashlib,json,sys,tempfile,zipfile
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree

def descriptor(image):
 alpha=image.getchannel('A') if image.mode=='RGBA' else image.convert('RGBA').getchannel('A')
 binary=alpha.point([0]*129+[255]*127);box=binary.getbbox()
 if box is None:return None
 mask=binary.crop(box).resize((32,32),Image.Resampling.BOX)
 vector=np.concatenate([np.asarray(mask,dtype=np.float32).ravel()/255,np.array([(box[2]-box[0])/(box[3]-box[1])*12],np.float32)])
 return vector

def reference_folder(game,name):
 root=Path(game)
 if root.name.lower()=='data01':root=root.parent
 root=root/'Digital Art Compendium'/'Frame Dump'
 folder=root/('boss_marie' if name=='bossmarie' else name)
 return folder if folder.is_dir() else None

class Catalog:
 def __init__(self,game,name,cache,progress=lambda *a:None,cancel=None):
  self.name=name;self.paths=[];self.tree=None;self.vectors=None;self.stamp='no-reference'
  folder=reference_folder(game,name)
  if not folder:return
  files=sorted(p for p in folder.rglob('*.png') if 'palettes' not in [x.lower() for x in p.parts] and p.stem.lower().endswith('_1p'))
  if not files:return
  stamp=hashlib.sha256(('\n'.join(f'{p.relative_to(folder).as_posix()}:{p.stat().st_size}:{p.stat().st_mtime_ns}' for p in files)).encode()).hexdigest()[:20]
  self.stamp=stamp
  cache=Path(cache);cache.mkdir(parents=True,exist_ok=True);path=cache/f'{name}-{stamp}.npz'
  if path.exists():
   try:
    with np.load(path,allow_pickle=False) as data:
     paths=data['paths'].tolist();vectors=data['vectors'].copy()
    if not isinstance(paths,list) or not all(isinstance(p,str) for p in paths) or vectors.shape!=(len(paths),1025) or not np.isfinite(vectors).all():raise ValueError('Invalid catalog cache')
    self.paths=paths;self.vectors=vectors
   except (OSError,ValueError,KeyError,EOFError,TypeError,zipfile.BadZipFile):pass
  if self.vectors is None:
   vectors=[]
   for i,p in enumerate(files):
    if cancel and cancel.is_set():
     from decoder import Cancelled
     raise Cancelled()
    with Image.open(p) as im:v=descriptor(im)
    if v is not None:self.paths.append(p.relative_to(folder).as_posix());vectors.append(v)
    if i%25==0:progress(i+1,len(files),f'Indexing {name} animation names · {i+1:,} / {len(files):,}')
   self.vectors=np.array(vectors,np.float32).reshape(-1,1025);temporary=None
   try:
    with tempfile.NamedTemporaryFile(dir=cache,suffix='.npz',delete=False) as stream:
     temporary=Path(stream.name);np.savez_compressed(stream,paths=np.array(self.paths),vectors=self.vectors)
    temporary.replace(path)
   finally:
    if temporary is not None:temporary.unlink(missing_ok=True)
  if len(self.paths):self.tree=cKDTree(self.vectors)

 def route(self,image,frame):
  # This specific sequence was confirmed with the twelve supplied PNGs and
  # tested in-game. It also remains identifiable after changing the emblems.
  if self.name=='valentine' and 1<=frame<=12:
   suffix=f'idle/stand_idle/idle{frame:02d}_valentine_1p.png'
   if suffix in self.paths:
    v=descriptor(image);distance=float(np.linalg.norm(v-self.vectors[self.paths.index(suffix)])) if v is not None else 100
    if distance<5:return self.convert(suffix),distance
  v=descriptor(image)
  if self.tree is None or v is None:return self.fallback(frame),None
  distance,index=self.tree.query(v,k=1)
  if distance>5.0:
   # These four translucent muzzle flashes differ at the alpha boundary in
   # Compendium renders. Verified against old/current game art: allow a small
   # extra distance only when the runner-up remains clearly worse.
   flashes={f'troops/crimsonhunting/Misc_{n}_parasoul_1p.png' for n in ['afire1','afire2','cfire1','cfire2']}
   special=self.name=='parasoul' and self.paths[int(index)] in flashes and distance<=7.0 and len(self.paths)>1
   if not special or self.tree.query(v,k=2)[0][1]-distance<3.0:return self.fallback(frame),float(distance)
  return self.convert(self.paths[int(index)]),float(distance)

 def convert(self,relative):
  return compendium_route(self.name,relative)

 def fallback(self,frame):
  return (Path(self.name)/self.name/'data'/'unmapped'/'internal_frames'/'frames'/f'frame_{frame:04d}_{self.name}_1p.png').as_posix()

def compendium_route(name,relative):
  p=Path(relative);parts=list(p.parent.parts)
  if parts and parts[-1].lower()=='frames':parts.pop()
  if 'data' in parts:parts=parts[parts.index('data')+1:]
  return (Path(name)/name/'data'/Path(*parts)/'frames'/p.name).as_posix()
