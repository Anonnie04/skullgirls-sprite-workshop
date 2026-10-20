"""Export mirrored projects and prepare/apply art-only PNG replacements."""
from pathlib import Path
import datetime,hashlib,io,json,os,shutil,struct,ctypes,tempfile,zipfile
import numpy as np
from PIL import Image
from scipy.spatial import cKDTree
from functools import lru_cache
from decoder import GFS,NAMES,data_folder,parse_frames_data,decode_image,colorize,Cancelled,rle,load_palette
from compression import encode_exact,optimize_ignored_brightness,optimize_equivalent_indices
from layout import Catalog,reference_folder,descriptor,compendium_route
from decoder import available_characters

SCHEMA=2
ART_FILES={5:('characters-art.gfs','.art'),4:('characters-art-pt.gfs','.art-pt')}

def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()

def pixel_hash(image):
 im=image.convert('RGBA')
 return hashlib.sha256(struct.pack('<2I',*im.size)+im.tobytes()).hexdigest()

def stopped(cancel):
 if cancel and cancel.is_set():raise Cancelled()

def write_json(path,value):
 path=Path(path);temporary=None
 try:
  with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,delete=False) as stream:
   temporary=Path(stream.name);json.dump(value,stream,indent=2);stream.flush();os.fsync(stream.fileno())
  temporary.replace(path)
 finally:
  if temporary is not None:temporary.unlink(missing_ok=True)

def unique(parent,prefix):
 parent=Path(parent);parent.mkdir(parents=True,exist_ok=True)
 name=prefix+' '+datetime.datetime.now().strftime('%Y-%m-%d_%H-%M-%S');path=parent/name;i=1
 while path.exists():path=parent/f'{name} ({i})';i+=1
 path.mkdir();return path

def safe_path(root,relative):
 p=(Path(root)/relative).resolve()
 if not p.is_relative_to(Path(root).resolve()):raise ValueError('A project path escapes its folder.')
 return p

def project_info(project):
 p=Path(project).expanduser().resolve();m=json.loads((p/'project.json').read_text(encoding='utf-8'))
 if m.get('schema')!=SCHEMA:raise ValueError('Choose a project exported by this version of the app.')
 return p,m

def route_signature(relative):
 parts=str(relative).replace('\\','/').split('/')
 if any(part in ['', '.', '..'] for part in parts):return None
 folded=[part.casefold() for part in parts]
 if 'data' not in folded:return None
 index=folded.index('data');prefix=folded[:index]
 if not prefix or len(prefix)>2 or any(part!=prefix[0] for part in prefix):return None
 name='bossmarie' if prefix[0]=='boss_marie' else prefix[0]
 if name not in NAMES:return None
 # Compendium distributions place the reserved frames directory at different depths.
 route=[part for part in folded[index+1:] if part!='frames']
 # Parasoul troop names carry Misc_ in some Compendium distributions.
 if name=='parasoul' and route and route[0]=='troops' and route[-1].startswith('misc_'):
  route[-1]=route[-1][5:]
 return (name,tuple(route))


def scan_input(project):
 p,m=project_info(project);entries={**m.get('reference_files',{}),**m['exports']};known={k.casefold():k for k in entries};found=[];unknown=[];aliases={};normalized={};reference_names=set()
 def index_route(route):
  signature=route_signature(route)
  if signature is not None:normalized.setdefault(signature,[]).append(route)
 for route in entries:index_route(route)
 for receipt in (p/'Sequence Imports').glob('*/mapping.json'):
  try:
   saved=json.loads(receipt.read_text(encoding='utf-8'))
   if saved.get('status')!='staged':continue
   for item in saved['mapping']:
    source=Path(item['source']);route=item['target']
    if source.is_relative_to((p/'Input').resolve()) and route in entries:aliases.setdefault(source,[]).append((item['sha256'],route))
  except (OSError,ValueError,KeyError,TypeError):continue
 for f in sorted((p/'Input').rglob('*')):
  if not f.is_file() or f.suffix.lower()!='.png':continue
  rel=f.relative_to(p/'Input').as_posix();key=known.get(rel.casefold());signature=route_signature(rel)
  if key is None and signature is not None:
   candidates=normalized.get(signature,[])
   if not candidates:
    name=signature[0]
    if name in m['characters'] and name not in reference_names:
     reference_names.add(name);folder=reference_folder(m['game'],name)
     for reference in sorted(folder.rglob('*.png')) if folder else []:
      if not reference.stem.lower().endswith('_1p') or 'palettes' in [part.casefold() for part in reference.parts]:continue
      relative=reference.relative_to(folder).as_posix();route=compendium_route(name,relative)
      if route in entries:continue
      entries[route]=dict(character=name,frame=None,layer=0,reference_relative=relative);known[route.casefold()]=route;index_route(route)
     candidates=normalized.get(signature,[])
   if len(candidates)==1:key=candidates[0]
  if key:
   found.append((f,rel,{**entries[key],'_route':key}));continue
  registered=aliases.get(f.resolve(),[]);matched=False
  for digest,route in registered:
   target=safe_path(p/'Input',route)
   if target.is_file() and sha(f)==digest and sha(target)==digest:matched=True;break
  if not matched:unknown.append(rel)
 return found,unknown


def generate_input_tree(game,parent,progress=lambda *a:None,cancel=None):
 source=data_folder(game);parent=Path(parent).expanduser().resolve()
 if parent.is_relative_to(source.parent):raise ValueError('Save the project outside the game installation.')
 names=available_characters(game);project=unique(parent,'Skullgirls Input Project')
 for branch in ['Input','Output']:(project/branch).mkdir()
 manifest=dict(schema=SCHEMA,game=str(source.parent),status='generating',input_only=True,exports={},reference_files={},characters={},errors=[],palette='1p',lighting='neutral')
 try:
  manifest['palette_archive_sha256']=sha(source/'sprites.gfs')
  with GFS(source/'characters-foits.gfs') as foit,GFS(source/'characters-art.gfs') as art:
   for i,name in enumerate(names):
    stopped(cancel);progress(i,len(names),f'Creating empty folders: {NAMES[name]}')
    data=foit.read(f'characters/{name}.foit');frames=parse_frames_data(name,data,art.entries[f'characters/{name}.art'][1])
    manifest['characters'][name]=dict(foit_sha256=hashlib.sha256(data).hexdigest(),frames=len(frames),exported=0,unmapped=0)
    folders=set();folder=reference_folder(source,name)
    files=sorted(folder.rglob('*.png')) if folder else []
    files=[f for f in files if f.stem.lower().endswith('_1p') and 'palettes' not in [x.lower() for x in f.parts]]
    for f in files:
     stopped(cancel);relative=f.relative_to(folder).as_posix();route=compendium_route(name,relative)
     manifest['reference_files'][route]=dict(character=name,frame=None,layer=0,reference_relative=relative)
     folders.add(Path(route).parent.as_posix())
    if not files:
     for index,fr in enumerate(frames):
      layers=[k for k in [0,1] if k in fr['images'] and fr['images'][k]['offset']>=0]
      for layer in layers:
       route=(Path(name)/name/'data'/'unmapped'/'internal_frames'/'frames'/f'frame_{index:04d}_{name}_1p.png').as_posix()
       if len(layers)>1:
        q=Path(route);route=(q.parent/'layers'/f'{q.stem}_layer{layer}.png').as_posix()
       manifest['exports'][route]=dict(character=name,frame=index,layer=layer,pixel_sha256=None)
       folders.add(Path(route).parent.as_posix())
    for directory in sorted(folders):
     stopped(cancel)
     for branch in ['Input','Output']:safe_path(project/branch,directory).mkdir(parents=True,exist_ok=True)
  manifest['status']='complete';progress(len(names),len(names),'Empty Input tree ready')
 except Cancelled:manifest['status']='cancelled'
 finally:
  write_json(project/'project.json',manifest)
  (project/'README.txt').write_text('Input and Output have matching empty folders. No PNGs were extracted.\nPlace edited Compendium PNGs in Input with their original filenames. Prepare previews resolves their game frames when needed.\nWithout the Compendium, use the numbered internal frame paths recorded in project.json.\n',encoding='utf-8')
 return project,manifest

def export_project(game,parent,characters,progress=lambda *a:None,cancel=None,limit=None):
 source=data_folder(game);parent=Path(parent).expanduser().resolve()
 if parent.is_relative_to(source.parent):raise ValueError('Save the project outside the game installation.')
 if not characters or any(n not in NAMES for n in characters):raise ValueError('Select at least one character.')
 project=unique(parent,'Skullgirls Project');out=project/'Output';inp=project/'Input';out.mkdir();inp.mkdir()
 manifest=dict(schema=SCHEMA,game=str(source.parent),status='exporting',palette='1p',lighting='neutral',exports={},characters={},errors=[])
 try:
  with GFS(source/'characters-art.gfs') as art,GFS(source/'characters-art-pt.gfs') as pt,GFS(source/'characters-foits.gfs') as foit,GFS(source/'sprites.gfs') as sprites:
   manifest['palette_archive_sha256']=sha(source/'sprites.gfs');prepared={}
   for name in characters:
    stopped(cancel);data=foit.read(f'characters/{name}.foit');frames=parse_frames_data(name,data,art.entries[f'characters/{name}.art'][1]);prepared[name]=frames
    manifest['characters'][name]=dict(foit_sha256=hashlib.sha256(data).hexdigest(),frames=len(frames),exported=0,unmapped=0)
   total=sum(min(len(f),limit) if limit is not None else len(f) for f in prepared.values());done=0
   for name,frames in prepared.items():
    stopped(cancel);catalog=Catalog(source.parent,name,parent/'.skullgirls-cache',progress,cancel)
    for rel in catalog.paths:
     route=catalog.convert(rel)
     safe_path(out,route).parent.mkdir(parents=True,exist_ok=True);safe_path(inp,route).parent.mkdir(parents=True,exist_ok=True)
    banks={5:art.read(f'characters/{name}.art'),4:pt.read(f'characters/{name}.art-pt')}
    palette=load_palette(name,foit.read(f'characters/{name}.foit'),sprites)
    selected=frames if limit is None else frames[:limit]
    for index,fr in enumerate(selected):
     stopped(cancel)
     try:
      layers=[]
      for layer in [0,1]:
       meta=fr['images'].get(layer)
       if meta and meta['offset']>=0:layers.append((layer,colorize(decode_image(meta,banks[fr['art_bank']]),palette)))
      if layers:
       composite=layers[0][1].copy()
       for _,image in layers[1:]:composite=Image.alpha_composite(composite,image)
       route,distance=catalog.route(composite,index)
       if route==catalog.fallback(index):manifest['characters'][name]['unmapped']+=1
       if route in manifest['exports']:
        p=Path(route);route=p.with_name(p.stem+f'__frame_{index:04d}'+p.suffix).as_posix()
       def save(rel,image,layer):
        path=safe_path(out,rel);path.parent.mkdir(parents=True,exist_ok=True);safe_path(inp,rel).parent.mkdir(parents=True,exist_ok=True)
        image.save(path,compress_level=3)
        manifest['exports'][rel]=dict(character=name,frame=index,layer=layer,art_bank=fr['art_bank'],size=list(image.size),pixel_sha256=pixel_hash(image),match_distance=distance)
       save(route,composite,layers[0][0] if len(layers)==1 else None)
       if len(layers)>1:
        for layer,image in layers:
         p=Path(route);save((p.parent/'layers'/f'{p.stem}_layer{layer}.png').as_posix(),image,layer)
       manifest['characters'][name]['exported']+=1
     except Exception as exc:manifest['errors'].append(dict(character=name,frame=index,error=str(exc) or repr(exc)))
     done+=1
     if index%10==0 or index==len(selected)-1:progress(done,total,f'Exporting {NAMES[name]} · {index+1:,} / {len(selected):,}')
   manifest['status']='complete' if not manifest['errors'] else 'complete_with_errors'
 except Cancelled:manifest['status']='cancelled'
 except Exception as exc:
  manifest['status']='failed';manifest['errors'].append(dict(error=str(exc)));raise
 finally:
  write_json(project/'project.json',manifest)
  (project/'README.txt').write_text('Output contains exported PNGs, grouped like the Digital Art Compendium.\nInput mirrors the same directories and starts empty. Place only replacement PNGs in Input, at the matching relative paths.\nPrepare an import to review how each PNG fits and renders before applying it. Unchanged files are skipped.\nFor layered frames, edit the individual PNGs in the layers subfolder; the composite is a reference.\nFrames with no reliable Compendium match are in data/unmapped/internal_frames and remain importable through project.json.\nImport updates art streams and their storage references. Palettes, animation timing, hitboxes, masks and normals stay unchanged.\nThe installed palette still limits available colors; compressed storage does not force color approximation. Backups include a verified restore manifest.\n',encoding='utf-8')
 return project,manifest

def fit_image(image,before):
 image=image.convert('RGBA')
 if image.size==before.size:return np.array(image),dict(mode='same canvas',scale=1,alignment=[0,0])
 src=np.array(image);target=np.array(before);sy,sx=np.where(src[:,:,3]>128);ty,tx=np.where(target[:,:,3]>128)
 if not len(sx) or not len(tx):raise ValueError('Cannot align an empty image with a different canvas size.')
 ratio=(ty.max()-ty.min()+1)/(sy.max()-sy.min()+1)
 if 0.45<=ratio<=0.55:ratio=0.5
 elif 1.8<=ratio<=2.2:ratio=2.0
 w=max(1,round(image.width*ratio));h=max(1,round(image.height*ratio))
 if w*h>16000000:raise ValueError('The fitted canvas is too large; use the exported canvas dimensions.')
 resized=np.array(image.resize((w,h),Image.Resampling.BOX if ratio<1 else Image.Resampling.NEAREST))
 if (w,h)==before.size:return resized,dict(mode='scaled to canvas',scale=ratio,alignment=[0,0])
 # Zero-pad small canvases; find the best whole-image translation by silhouette.
 H=max(h,before.height);W=max(w,before.width);source=np.zeros((H,W));source[:h,:w]=resized[:,:,3]>128
 target_mask=(target[:,:,3]>128).astype(float);fft=(1<<(H+before.height-1).bit_length(),1<<(W+before.width-1).bit_length())
 correlation=np.fft.irfft2(np.fft.rfft2(source,s=fft)*np.conj(np.fft.rfft2(target_mask,s=fft)),s=fft)
 y,x=map(int,np.unravel_index(correlation.argmax(),correlation.shape))
 if x>W:x-=fft[1]
 if y>H:y-=fft[0]
 fitted=np.zeros_like(target);sx0=max(x,0);sy0=max(y,0);dx=max(-x,0);dy=max(-y,0);ww=min(w-sx0,before.width-dx);hh=min(h-sy0,before.height-dy)
 if ww<=0 or hh<=0:raise ValueError('The replacement cannot be aligned with the exported frame.')
 fitted[dy:dy+hh,dx:dx+ww]=resized[sy0:sy0+hh,sx0:sx0+ww]
 return fitted,dict(mode='scaled and aligned',scale=ratio,alignment=[x,y])

def color_table(palette,levels,bands):
 return cached_color_table(palette.shape,palette.astype(np.float64).tobytes(),tuple(levels),tuple(bands))

@lru_cache(maxsize=64)
def cached_color_table(shape,data,levels,bands):
 palette=np.frombuffer(data,dtype=np.float64).reshape(shape)
 pairs=np.array([(b*32+i,idx) for idx in bands for b in range(8) for i in levels],np.uint8)
 raw=np.zeros((1,len(pairs),3),np.uint8);raw[0,:,1:]=pairs
 rgba=np.array(colorize(raw,palette))[0].astype(float);rgba[:,:3]*=rgba[:,3:4]/255;rgba[:,3]*=2**0.5
 # Repeated palette rows and outlined black produce many identical samples.
 # One representative keeps nearest-color queries fast for large old frames;
 # the existing per-material tie pass still preserves original materials.
 _,first=np.unique(rgba,axis=0,return_index=True);first.sort()
 return cKDTree(rgba[first]),pairs[first]

def white_materials(palette):
 # Only opaque palette rows with an actual near-white sample are candidates.
 rgb=palette[:,:,:3];white=(rgb.min(axis=2)>=180)&(np.ptp(rgb,axis=2)<=45)
 return [i for i in range(1,len(palette)) if np.all(palette[i,:,3]==255) and np.any(white[i])]

def remap_whites(raw,palette,input_pixels,used,band,max_error=24):
 """Consolidate whites while preserving outline strength and exact opacity."""
 result=raw.copy();rgb=input_pixels[:,:,:3].astype(np.int16)
 white=used&(input_pixels[:,:,3]>=250)&(rgb.min(axis=2)>=140)&(np.ptp(rgb,axis=2)<=65)
 count=0
 for outline in range(8):
  mask=white&(raw[:,:,1]//32==outline)
  if not mask.any():continue
  levels=np.array([0,8,16,24,31]);sample=np.zeros((1,len(levels),3),np.uint8);sample[0,:,1]=outline*32+levels;sample[0,:,2]=band
  rendered=np.array(colorize(sample,palette))[0].astype(np.int16)
  target=input_pixels[mask].astype(np.int16);distance=((rendered[None,:,:3].astype(float)-target[:,None,:3])**2).sum(axis=2)
  best=distance.argmin(axis=1);chosen=rendered[best]
  acceptable=(np.max(np.abs(chosen[:,:3]-target[:,:3]),axis=1)<=max_error)&(chosen[:,3]==target[:,3])
  ys,xs=np.where(mask);ys=ys[acceptable];xs=xs[acceptable];values=(outline*32+levels[best[acceptable]]).astype(np.uint8)
  count+=int(np.sum((result[ys,xs,1]!=values)|(result[ys,xs,2]!=band)))
  result[ys,xs,1]=values;result[ys,xs,2]=band
 return result,count

def equivalent_material_groups(palette):
 # Exact full-gradient duplicates, invisible colors, or completely black outlines.
 palette=palette[np.minimum(np.arange(256),len(palette)-1)]
 _,labels=np.unique(palette.reshape(len(palette),-1),axis=0,return_inverse=True)
 groups=np.tile(labels,(256,1)).astype(np.int16);invisible=int(labels.max())+1
 for g in range(256):
  if g//32==7:groups[g]=0;continue
  if g//32:continue
  x=(g%32)/31*15;lo=int(x);hi=min(lo+1,15);t=x-lo
  alpha=palette[:,lo,3]*(1-t)+palette[:,hi,3]*t
  groups[g,(alpha%128)==0]=invisible
 return groups

def optimize_nearby_brightness(g,index,palette,free,max_error=8,locked=None):
 # Each pixel may use any nearby shade with the same outline and opacity.
 bands,inverse=np.unique(index,return_inverse=True);tables=[]
 values=np.arange(256,dtype=np.uint8);outlines=values//32
 for band in bands:
  sample=np.zeros((1,256,3),np.uint8);sample[0,:,1]=values;sample[0,:,2]=band
  rgba=np.array(colorize(sample,palette))[0].astype(np.int16)
  close=np.max(np.abs(rgba[:,None,:3]-rgba[None,:,:3]),axis=2)<=max_error
  close&=rgba[:,None,3]==rgba[None,:,3];close&=outlines[:,None]==outlines[None,:]
  close&=np.abs((values%32).astype(np.int16)[:,None]-(values%32).astype(np.int16)[None,:])<=(max_error//4)
  tables.append(close.astype(np.int16))
 groups=np.concatenate(tables);contexts=inverse.reshape(g.shape)*256+g.astype(np.int32)
 base=len(groups);ignored=(outlines[None,:]==np.arange(8)[:,None]).astype(np.int16)
 groups=np.concatenate([groups,ignored,np.eye(256,dtype=np.int16)]);contexts[free]=base+(g[free].astype(np.int32)//32)
 if locked is not None:contexts[locked]=base+8+g[locked].astype(np.int32)
 return optimize_equivalent_indices(g,contexts,groups,preferred=np.where(free,-1,g.astype(np.int16)).ravel())

def encode_replacement(meta,art,palette,input_pixels,unrestricted=False):
 raw=decode_image(meta,art);used=np.zeros(raw.shape[:2],bool);mask=bytes.fromhex(meta['mask']);tiles=[]
 for t in range(meta['n']):
  if mask[t//8]&(1<<(t%8)):
   y,x=divmod(t,meta['w']);tiles.append((y,x));used[y*16:y*16+16,x*16:x*16+16]=True
 if not tiles:raise ValueError('The frame contains no editable art tiles.')
 stored_g=None
 if meta['flags']&64 and not unrestricted:
  offset=meta['offset']+meta['sizes'][0]
  stored_g=rle(art[offset:offset+meta['sizes'][1]],meta['used']*256).reshape(16,-1)
 clipped=int(np.sum((input_pixels[:,:,3]>128)&~used))
 # Preserve exact colors/materials for pixels that the user left unchanged.
 before=np.array(colorize(raw,palette));unchanged=np.all(input_pixels==before,axis=2)
 unique_colors,inverse=np.unique(np.ascontiguousarray(input_pixels).reshape(-1,4).view(np.uint32).ravel(),return_inverse=True)
 colors=unique_colors.view(np.uint8).reshape(-1,4).astype(float);colors[:,:3]*=colors[:,3:4]/255;colors[:,3]*=2**0.5
 original_indices=raw[:,:,2].ravel();attempts=[];equivalent_groups=None
 # Original material bands plus existing opaque colors avoid animated-effect
 # palette bands, which caused speckled edges in the initial experiment.
 bands=[0]+[i for i in range(1,len(palette)) if np.all(palette[i,:,3]==255)]
 if unrestricted:bands=list(range(min(256,len(palette))))
 full=list(range(32));nine=[0,4,8,12,16,20,24,28,31]
 settings=[(full,0),(full,2),(full,4),(nine,0),(nine,4),([0,8,16,24,31],0),([0,8,16,24,31],4),([0,16,31],0),([0,16,31],4),([0,31],0),([0,31],4)]
 # First try the closest palette with lossless storage optimization only.
 # Visible fitting and the original material bias are fallback passes.
 settings=[(full,0,None,False,False),(full,0,None,False,True)]+[(levels,tolerance,None,True,True) for levels,tolerance in settings]+[(full,0,-1,True,True)]+[(full,0,band,True,True) for band in white_materials(palette)]
 if unrestricted:settings=[(full,0,None,False,False)]
 delta=np.max(np.abs(input_pixels.astype(np.int16)-before.astype(np.int16)),axis=2)
 for levels,tolerance,white_band,material_bias,allow_shading in settings:
  preserve=delta<=tolerance
  tree,pairs=color_table(palette,levels,bands);distance,indices=tree.query(colors,workers=1);dist=distance[inverse];chosen=pairs[indices[inverse]].copy()
  biased_pixels=np.zeros(len(original_indices),bool)
  for band in np.unique(original_indices):
   where=np.flatnonzero(original_indices==band);local_tree,local_pairs=color_table(palette,levels,[int(band)])
   active,back=np.unique(inverse[where],return_inverse=True);local_dist,local=local_tree.query(colors[active],workers=1);local_dist=local_dist[back];local=local[back];prefer=local_dist**2<=dist[where]**2+(16384 if material_bias else 1e-8);chosen[where[prefer]]=local_pairs[local[prefer]]
   biased_pixels[where[prefer]]=local_dist[prefer]**2>dist[where[prefer]]**2+1e-8
  modified=raw.copy();modified[:,:,1:]=chosen.reshape(*raw.shape[:2],2);modified[preserve]=raw[preserve];modified[~used,1:]=0
  white_swaps=0
  if white_band==-1:
   original_material=modified[:,:,2].copy()
   for band in white_materials(palette):
    equivalents=[i for i in white_materials(palette) if np.array_equal(palette[i],palette[band])]
    modified[original_material==band,2]=min(equivalents)
   white_swaps=int(np.sum(modified[:,:,2]!=original_material))
  elif white_band is not None:modified,white_swaps=remap_whites(modified,palette,input_pixels,used,white_band)
  rgba=np.array(colorize(modified,palette));modified[(rgba[:,:,3]==0)&~preserve,1:]=0
  strip=np.stack([modified[y*16:y*16+16,x*16:x*16+16] for y,x in tiles]).transpose(1,0,2,3).reshape(16,len(tiles)*16,3)
  # Interpolated shading rows store only outline bits. The decoder derives
  # their low five brightness bits from neighboring rows; storing derived
  # values wastes compression space without affecting the rendered result.
  g=strip[:,:,1].copy()
  if stored_g is not None:g[1:15:2]&=224
  index_stream=encode_exact(strip[:,:,2].ravel(),None)[0];g_stream=encode_exact(g.ravel(),None)[0]
  if stored_g is not None and len(g_stream)>meta['sizes'][1] and len(index_stream)<=meta['sizes'][2]:
   # Explore equivalent values only when the default representation cannot fit.
   for low in [stored_g,np.roll(g,1,axis=0),np.roll(g,-1,axis=0)]:
    candidate=g.copy();candidate[1:15:2]=(candidate[1:15:2]&224)|(low[1:15:2]&31)
    stream=encode_exact(candidate.ravel(),None)[0]
    if len(stream)<len(g_stream):g=candidate;g_stream=stream
    if len(g_stream)<=meta['sizes'][1]:break
  storage_index_swaps=0
  if not unrestricted and len(index_stream)>meta['sizes'][2]:
   if equivalent_groups is None:equivalent_groups=equivalent_material_groups(palette)
   optimized,minimum=optimize_equivalent_indices(strip[:,:,2],strip[:,:,1],equivalent_groups)
   if minimum<len(index_stream):
    storage_index_swaps=int(np.sum(optimized!=strip[:,:,2].ravel()));strip[:,:,2]=optimized.reshape(g.shape);index_stream=encode_exact(optimized,None)[0]
  if not unrestricted and len(g_stream)>meta['sizes'][1] and len(index_stream)<=meta['sizes'][2]:
   free=(g>>5)==7
   if stored_g is not None:free[:]=False;free[1:15:2]=True
   if free.any():
    optimized,minimum=optimize_ignored_brightness(g,free)
    if minimum<len(g_stream):g=optimized.reshape(g.shape);g_stream=encode_exact(g.ravel(),None)[0]
  brightness_color_tolerance=0
  if allow_shading and len(g_stream)>meta['sizes'][1] and len(index_stream)<=meta['sizes'][2]:
   free=(g>>5)==7
   if stored_g is not None:free[:]=False;free[1:15:2]=True
   def strip_preview(values):
    values=values.copy()
    if stored_g is not None:values[1:15:2]=(values[1:15:2]&224)|(((values[0:14:2]&31).astype(np.uint16)+(values[2:16:2]&31))//2)
    pixels=np.zeros((*values.shape,3),np.uint8);pixels[:,:,1]=values;pixels[:,:,2]=strip[:,:,2]
    return np.array(colorize(pixels,palette))
   expected_strip=strip_preview(g)
   for color_tolerance,decoded_limit,step in [(8,12,2),(12,16,3),(16,20,4),(20,24,5)]:
    locked=np.zeros(g.shape,bool)
    # Freeze contributors whose interpolation can cross sharp palette transitions.
    if stored_g is not None:
     for shift in range(-step,step+1):
      if not shift:continue
      moved=(g&224)|np.clip((g&31).astype(np.int16)+shift,0,31).astype(np.uint8)
      probe=strip_preview(moved);risk=((np.max(np.abs(probe[:,:,:3].astype(np.int16)-expected_strip[:,:,:3]),axis=2)>decoded_limit)&(expected_strip[:,:,3]>0))|(probe[:,:,3]!=expected_strip[:,:,3])
      odd=risk[1:15:2];locked[0:14:2]|=odd;locked[2:16:2]|=odd
    for refinement in range(5):
     optimized,minimum=optimize_nearby_brightness(g,strip[:,:,2],palette,free,max_error=color_tolerance,locked=locked)
     if minimum>meta['sizes'][1]:break
     candidate=optimized.reshape(g.shape);actual_strip=strip_preview(candidate)
     difference=np.max(np.abs(actual_strip[:,:,:3].astype(np.int16)-expected_strip[:,:,:3]),axis=2)
     bad=((difference>decoded_limit)&(expected_strip[:,:,3]>0))|(actual_strip[:,:,3]!=expected_strip[:,:,3])
     if not bad.any():
      g=candidate;g_stream=encode_exact(g.ravel(),None)[0];brightness_color_tolerance=color_tolerance;break
     locked|=bad
     if stored_g is not None:
      odd=bad[1:15:2];locked[0:14:2]|=odd;locked[2:16:2]|=odd
    if brightness_color_tolerance:break
  strip[:,:,1]=g
  short=[g_stream,index_stream];sizes=list(map(len,short));attempts.append(dict(levels=len(levels),near_color_tolerance=tolerance,white_material=white_band,white_swaps=white_swaps,material_bias=material_bias,allow_shading=allow_shading,compressed=sizes))
  if unrestricted or all(n<=limit for n,limit in zip(sizes,meta['sizes'][1:])):
   encoded=[encode_exact(strip[:,:,c].ravel(),None if unrestricted else meta['sizes'][c])[0] for c in [1,2]]
   start=meta['offset'];payload=art[start:start+meta['sizes'][0]]+b''.join(encoded)
   encoded_sizes=[meta['sizes'][0]]+list(map(len,encoded))
   encoded_flags=meta['flags']&~64 if unrestricted else meta['flags']
   decoded=decode_image({**meta,'offset':0,'sizes':encoded_sizes,'flags':encoded_flags},payload)
   assert np.array_equal(decoded[:,:,0],raw[:,:,0])
   preview=colorize(decoded,palette);changed=int(np.any(np.array(preview)!=before,axis=2).sum());shading_max_error=0;shading_adjusted_pixels=0
   if brightness_color_tolerance or storage_index_swaps:
    baseline=modified.copy()
    if stored_g is not None:
     for y,x in tiles:
      channel=baseline[y*16:y*16+16,x*16:x*16+16,1]
      channel[1:15:2]=(channel[1:15:2]&224)|(((channel[0:14:2]&31).astype(np.uint16)+(channel[2:16:2]&31))//2)
    expected=np.array(colorize(baseline,palette));actual=np.array(preview)
    difference=np.abs(actual[:,:,:3].astype(np.int16)-expected[:,:,:3]);difference[expected[:,:,3]==0]=0
    shading_max_error=int(difference.max())
    if not np.array_equal(actual[:,:,3],expected[:,:,3]) or shading_max_error>(brightness_color_tolerance+4 if brightness_color_tolerance else 0):continue
    shading_adjusted_pixels=int(np.any(difference>0,axis=2).sum())
   return payload,preview,dict(encoded_flags=encoded_flags,encoded_sizes=encoded_sizes,material_color_changes=int(np.sum(biased_pixels.reshape(used.shape)&used&~preserve)),palette_selection='original material fallback' if material_bias else 'closest palette',changed_pixels=changed,brightness_levels=len(levels),near_color_tolerance=tolerance,white_material=white_band,white_swaps=white_swaps,storage_index_swaps=storage_index_swaps,brightness_color_tolerance=brightness_color_tolerance,shading_max_error=shading_max_error,shading_adjusted_pixels=shading_adjusted_pixels,clipped_pixels=clipped,compression_attempts=attempts)
 raise ValueError('Replacement exceeds this frame’s fixed compression space, even after color fitting. Try fewer colors or a smaller edit. Game files were not changed. '+f'Final channel sizes {sizes}; slot limits {list(meta["sizes"][1:])}.')

def matching_silhouette(meta,bank,palette):
 # Same alpha calculation as colorize, without generating RGB shading arrays.
 raw=decode_image(meta,bank,selected_channels=(1,2));idx=np.minimum(raw[:,:,2].astype(int),len(palette)-1);g=raw[:,:,1].astype(float)
 x=(g%32)/31*15;lo=np.floor(x).astype(int);hi=np.minimum(lo+1,15);t=x-lo
 alpha=palette[idx,lo,3]*(1-t)+palette[idx,hi,3]*t
 alpha=np.maximum((alpha%128)*2,(g//32)/7*255)
 a=Image.fromarray(np.clip(np.rint(alpha),0,255).astype(np.uint8));zero=Image.new('L',a.size)
 return Image.merge('RGBA',(zero,zero,zero,a))

def resolve_frame_routes(source,name,frames,palette,banks,project,progress,cancel):
 cache=project.parent/'.skullgirls-cache';catalog=Catalog(source.parent,name,cache,progress,cancel)
 # Content hashes protect the persistent map from updates and art replacements.
 identity=hashlib.sha256()
 identity.update(b'frame-routes-v3');identity.update(catalog.stamp.encode())
 identity.update(json.dumps(frames,sort_keys=True).encode());identity.update(palette.tobytes())
 for bank in sorted(banks):identity.update(banks[bank])
 path=cache/f'{name}-routes-{identity.hexdigest()}.json'
 if path.exists():
  try:
   resolved=json.loads(path.read_text(encoding='utf-8'))
   if all(isinstance(v,list) and len(v)==2 and isinstance(v[0],int) and 0<=v[0]<len(frames) and v[1] in [None,0,1] for v in resolved.values()):
    progress(0,0,f'Using cached {NAMES[name]} frame matches');return resolved
  except (ValueError,OSError):pass
 from collections import Counter
 uses=Counter((fr['art_bank'],json.dumps(m,sort_keys=True)) for fr in frames for k,m in fr['images'].items() if k in [0,1] and m['offset']>=0)
 resolved={};images_cache={}
 for j,candidate in enumerate(frames):
  stopped(cancel)
  if j%25==0:progress(j,len(frames),f'Matching {NAMES[name]} silhouettes: {j+1:,} / {len(frames):,}')
  images=[]
  for k,m in candidate['images'].items():
   if k not in [0,1] or m['offset']<0:continue
   key=(candidate['art_bank'],json.dumps(m,sort_keys=True))
   image=images_cache.get(key)
   if image is None:image=matching_silhouette(m,banks[candidate['art_bank']],palette)
   uses[key]-=1
   if uses[key]:images_cache[key]=image
   else:images_cache.pop(key,None)
   images.append((k,image))
  if not images:continue
  composite=images[0][1]
  for _,im in images[1:]:composite=Image.alpha_composite(composite,im)
  route,distance=catalog.route(composite,j)
  if route in resolved:
   q=Path(route);route=q.with_name(q.stem+f'__frame_{j:04d}'+q.suffix).as_posix()
  resolved[route]=(j,images[0][0] if len(images)==1 else None)
 # Write only complete maps. Cancelled passes never become cached matches.
 stopped(cancel);cache.mkdir(parents=True,exist_ok=True);temporary=path.with_suffix('.tmp');write_json(temporary,resolved);temporary.replace(path)
 return resolved

def prepare_import(game,project,progress=lambda *a:None,cancel=None):
 source=data_folder(game);project,manifest=project_info(project);found,unknown=scan_input(project)
 if not found and not unknown:raise ValueError('Input contains no PNGs. Place replacement files in its empty folders first.')
 prepared=unique(project/'Prepared','Import');plan=dict(schema=SCHEMA,storage='relocatable',game=str(source),project=str(project),status='prepared',patches=[],errors=[],skipped=[],source_hashes={},input_hashes={},protected_hashes={})
 for rel in unknown:plan['errors'].append(dict(path=rel,error='No exported frame matches this path. Use the same relative path as Output.'))
 try:
  with GFS(source/'characters-art.gfs') as art,GFS(source/'characters-art-pt.gfs') as pt,GFS(source/'characters-foits.gfs') as foit,GFS(source/'sprites.gfs') as sprites:
   plan['protected_hashes']={name:sha(source/name) for name in ['characters-foits.gfs','sprites.gfs']}
   if plan['protected_hashes']['sprites.gfs']!=manifest['palette_archive_sha256']:raise ValueError('The game palettes changed since export. Export a new project.')
   loaded={};payloads={};conflicts=set()
   for position,(path,relative,entry) in enumerate(found):
    stopped(cancel);progress(position,len(found),f'Preparing {relative}')
    try:
     name=entry['character'];layer=entry['layer']
     with Image.open(path) as png:
      if pixel_hash(png)==entry.get('pixel_sha256'):plan['skipped'].append(dict(path=relative,reason='unchanged exported PNG'));continue
      png=png.convert('RGBA')
     if layer is None:raise ValueError('This is a layered composite. Place edited individual layers in Input’s matching layers folder.')
     if name not in loaded:
      b=foit.read(f'characters/{name}.foit')
      if hashlib.sha256(b).hexdigest()!=manifest['characters'][name]['foit_sha256']:raise ValueError('Character metadata changed since export. Export a new project.')
      fs=parse_frames_data(name,b,art.entries[f'characters/{name}.art'][1])
      pal=load_palette(name,b,sprites)
      loaded[name]=(fs,pal,{5:art.read(f'characters/{name}.art'),4:pt.read(f'characters/{name}.art-pt')})
     frames,palette,banks=loaded[name][:3]
     if entry['frame'] is None:
      if len(loaded[name])==3:
       resolved=resolve_frame_routes(source,name,frames,palette,banks,project,progress,cancel)
       loaded[name]=(frames,palette,banks,resolved)
      mapped_route=entry.get('_route',relative)
      if mapped_route not in loaded[name][3]:raise ValueError('This Compendium image has no reliable stored game-frame match. The Compendium includes unused poses and separate parts that may be combined in game. Art-only import needs an existing game art slot; choose a corresponding Output frame or its individual layers.')
      index,layer=loaded[name][3][mapped_route]
      if layer is None:raise ValueError('This frame contains multiple art layers. Export it and edit individual layer PNGs.')
     else:index=int(entry['frame'])
     fr=frames[index];bank=fr['art_bank'];meta=fr['images'][int(layer)]
     if bank not in ART_FILES or meta['offset']<0:raise ValueError('This frame has no supported art slot.')
     before=colorize(decode_image(meta,banks[bank]),palette);fitted,fit=fit_image(png,before)
     payload,after,stats=encode_replacement(meta,banks[bank],palette,fitted,unrestricted=True)
     actual=np.array(after).astype(np.int16);requested=fitted.astype(np.int16)
     # Ignore invisible RGB, but expose real palette differences instead of
     # describing an approximate PNG as an exact import.
     visible=requested[:,:,3]>0;difference=np.max(np.abs(actual-requested),axis=2)
     stats['input_color_difference_pixels']=int(np.sum((difference>1)&visible))
     stats['input_color_max_difference']=int(difference[visible].max()) if visible.any() else 0
     if stats['changed_pixels']==0:plan['skipped'].append(dict(path=relative,reason='no rendered change after palette fitting'));continue
     start=meta['offset'];end=start+sum(meta['sizes']);references=[]
     for j,other in enumerate(frames):
      if other['art_bank']!=bank:continue
      for k,m in other['images'].items():
       if m['offset']>=0 and m['offset']<end and m['offset']+sum(m['sizes'])>start:
        if m!=meta:raise ValueError('This art slot overlaps another image with different metadata. Replacement refused.')
        references.append([j,k])
     archive_name,suffix=ART_FILES[bank];archive=art if bank==5 else pt;absolute=archive.entries[f'characters/{name}{suffix}'][0]+start;key=(archive_name,absolute)
     if key in conflicts:raise ValueError('Conflicting edits target this shared art slot. All versions of that slot are skipped.')
     if key in payloads:
      if payloads[key]!=payload:
       conflicts.add(key)
       for prior in list(plan['patches']):
        if (prior['archive'],prior['offset'])==key:
         plan['patches'].remove(prior);plan['input_hashes'].pop(prior['path'],None);plan['errors'].append(dict(path=prior['path'],error='Conflicting edit targets the same shared art slot. Both replacements are skipped.'))
       raise ValueError('Two Input files propose conflicting edits to the same shared art slot. Both are skipped.')
      plan['skipped'].append(dict(path=relative,reason='same replacement already prepared for shared art'));continue
     payloads[key]=payload;stem=f'{position:05d}';(prepared/f'{stem}.payload').write_bytes(payload)
     before.save(prepared/f'{stem}-before.png');after.save(prepared/f'{stem}-after.png');Image.fromarray(fitted).save(prepared/f'{stem}-fitted.png')
     warnings=[]
     if stats['input_color_difference_pixels']:warnings.append(f'{stats["input_color_difference_pixels"]} pixels differ from the supplied PNG (maximum channel difference {stats["input_color_max_difference"]}/255); check palette availability and tile coverage')
     if stats.get('material_color_changes'):warnings.append(f'Original-material fallback altered {stats["material_color_changes"]} pixels after closest-color fitting could not fit')
     if stats.get('brightness_color_tolerance'):warnings.append(f'Nearby shading optimized: {stats["shading_adjusted_pixels"]} pixels; maximum decoded RGB difference {stats["shading_max_error"]}/255 from normal fitting')
     if stats.get('brightness_color_tolerance',0)>=16:warnings.append('Stronger shading fitting: inspect for visible color bands')
     if stats.get('storage_index_swaps'):warnings.append('Equivalent palette indices optimized; alternate palettes may differ')
     if stats.get('white_swaps'):
      material=stats['white_material']
      warnings.append(f'{stats["white_swaps"]} white pixels use identical default-palette materials' if material==-1 else f'{stats["white_swaps"]} white pixels fitted to similar palette material {material} (up to 24/255 RGB difference)')
      warnings.append('Material substitutions may render differently with other character palettes')
     if stats.get('near_color_tolerance'):warnings.append(f'Small color differences up to {stats["near_color_tolerance"]}/255 fitted to existing pixels')
     if stats['brightness_levels']<32:warnings.append(f'Colors fitted to {stats["brightness_levels"]} brightness levels')
     if stats['clipped_pixels']:warnings.append(f'{stats["clipped_pixels"]} opaque pixels outside original tiles were clipped')
     if len(references)>1:warnings.append(f'Shared art: also affects {len(references)-1} other frame/layer references')
     record=dict(path=relative,character=name,frame=index,layer=layer,art_bank=bank,meta=meta,encoded_sizes=stats['encoded_sizes'],encoded_flags=stats['encoded_flags'],archive=archive_name,offset=absolute,bytes=len(payload),payload=f'{stem}.payload',payload_sha256=hashlib.sha256(payload).hexdigest(),before=f'{stem}-before.png',after=f'{stem}-after.png',fitted=f'{stem}-fitted.png',fit=fit,statistics=stats,warnings=warnings,affected_references=references)
     plan['patches'].append(record);plan['input_hashes'][relative]=sha(path)
     if archive_name not in plan['source_hashes']:plan['source_hashes'][archive_name]=sha(source/archive_name)
    except Cancelled:raise
    except Exception as exc:plan['errors'].append(dict(path=relative,error=str(exc) or repr(exc)))
   # No conflicting overlapping writes, including different characters.
   ordered=sorted(plan['patches'],key=lambda p:(p['archive'],p['offset']))
   for a,b in zip(ordered,ordered[1:]):
    if a['archive']==b['archive'] and a['offset']+sum(a['meta']['sizes'])>b['offset']:raise ValueError('Prepared writes overlap. No import can be applied.')
   plan['source_hashes']={name:digest for name,digest in plan['source_hashes'].items() if any(r['archive']==name for r in plan['patches'])}
   if plan['patches']:plan['source_hashes']['characters-foits.gfs']=plan['protected_hashes'].pop('characters-foits.gfs')
  progress(len(found),len(found),f'Prepared {len(plan["patches"])} replacements')
 except Cancelled:plan['status']='cancelled';plan['patches']=[]
 except Exception:
  plan['status']='failed';plan['patches']=[];raise
 finally:write_json(prepared/'plan.json',plan)
 return prepared,plan

def game_running():
 if os.name!='nt':return False
 from ctypes import wintypes
 class Entry(ctypes.Structure):
  _fields_=[('dwSize',wintypes.DWORD),('cntUsage',wintypes.DWORD),('th32ProcessID',wintypes.DWORD),('th32DefaultHeapID',ctypes.c_size_t),('th32ModuleID',wintypes.DWORD),('cntThreads',wintypes.DWORD),('th32ParentProcessID',wintypes.DWORD),('pcPriClassBase',wintypes.LONG),('dwFlags',wintypes.DWORD),('szExeFile',wintypes.WCHAR*260)]
 kernel=ctypes.WinDLL('kernel32',use_last_error=True);kernel.CreateToolhelp32Snapshot.restype=wintypes.HANDLE;kernel.Process32FirstW.argtypes=[wintypes.HANDLE,ctypes.POINTER(Entry)];kernel.Process32NextW.argtypes=kernel.Process32FirstW.argtypes;kernel.CloseHandle.argtypes=[wintypes.HANDLE]
 snapshot=kernel.CreateToolhelp32Snapshot(2,0)
 if snapshot==wintypes.HANDLE(-1).value:raise OSError('Cannot check whether Skullgirls is running.')
 try:
  entry=Entry();entry.dwSize=ctypes.sizeof(entry);ok=kernel.Process32FirstW(snapshot,ctypes.byref(entry))
  while ok:
   if entry.szExeFile.casefold()=='skullgirls.exe':return True
   ok=kernel.Process32NextW(snapshot,ctypes.byref(entry))
  return False
 finally:kernel.CloseHandle(snapshot)

def validate_prepared(prepared,check_running=False):
 prepared=Path(prepared).resolve();plan=json.loads((prepared/'plan.json').read_text(encoding='utf-8'))
 if plan.get('status')!='prepared' or not plan['patches']:raise ValueError('There are no prepared replacements to apply.')
 if plan.get('storage') not in [None,'relocatable']:raise ValueError('Unsupported import storage mode.')
 if plan.get('storage')=='relocatable':
  archives={r['archive'] for r in plan['patches']}|{'characters-foits.gfs'}
  if set(plan['source_hashes'])!=archives or set(plan['protected_hashes'])!={'sprites.gfs'}:raise ValueError('Incomplete archive baseline in import plan.')
 if check_running and game_running():raise ValueError('Close Skullgirls before applying an import.')
 source=data_folder(plan['game']);project,manifest=project_info(plan['project'])
 if not prepared.is_relative_to(project/'Prepared'):raise ValueError('The preparation is outside this project.')
 for name,digest in {**plan['source_hashes'],**plan['protected_hashes']}.items():
  if name not in ['characters-art.gfs','characters-art-pt.gfs','characters-foits.gfs','sprites.gfs']:raise ValueError('Invalid archive in import plan.')
  if sha(source/name)!=digest:raise ValueError('The game files changed after preparation. Prepare the import again.')
 for relative,digest in plan['input_hashes'].items():
  if sha(safe_path(project/'Input',relative))!=digest:raise ValueError('An Input PNG changed after preparation. Prepare again.')
 # Validate the actual metadata-derived slot instead of trusting offsets in JSON.
 with GFS(source/'characters-art.gfs') as art,GFS(source/'characters-art-pt.gfs') as pt,GFS(source/'characters-foits.gfs') as foit:
  frames={}
  for record in plan['patches']:
   name=record['character'];bank=record['art_bank'];archive,suffix=ART_FILES[bank]
   if name not in NAMES or archive!=record['archive']:raise ValueError('Invalid character or bank in import plan.')
   if name not in frames:frames[name]=parse_frames_data(name,foit.read(f'characters/{name}.foit'),art.entries[f'characters/{name}.art'][1])
   frame=frames[name][record['frame']];meta=frame['images'][record['layer']];expected=json.loads(json.dumps(meta))
   g=art if bank==5 else pt;absolute=g.entries[f'characters/{name}{suffix}'][0]+meta['offset']
   relocating=plan.get('storage')=='relocatable';sizes=record.get('encoded_sizes') if relocating else meta['sizes']
   flags=record.get('encoded_flags') if relocating else meta['flags']
   if flags!=(meta['flags']&~64 if relocating else meta['flags']):raise ValueError('Invalid art storage flags.')
   if not isinstance(sizes,(list,tuple)) or len(sizes)!=3 or any(type(s)!=int or s<=0 for s in sizes) or sizes[0]!=meta['sizes'][0]:raise ValueError('Invalid encoded channel sizes.')
   if frame['art_bank']!=bank or expected!=record['meta'] or absolute!=record['offset'] or sum(sizes)!=record['bytes']:raise ValueError('The art slot no longer matches the prepared import.')
   payload=safe_path(prepared,record['payload']).read_bytes()
   if len(payload)!=record['bytes'] or hashlib.sha256(payload).hexdigest()!=record['payload_sha256']:raise ValueError('A prepared payload was altered.')
   if payload[:meta['sizes'][0]]!=g.data[absolute:absolute+meta['sizes'][0]]:raise ValueError('Import would alter lighting normals.')
   decode_image({**meta,'offset':0,'sizes':sizes,'flags':flags},payload)
  ordered=sorted(plan['patches'],key=lambda r:(r['archive'],r['offset']))
  for a,b in zip(ordered,ordered[1:]):
   length=sum(a['meta']['sizes']) if plan.get('storage')=='relocatable' else a['bytes']
   if a['archive']==b['archive'] and a['offset']+length>b['offset']:raise ValueError('Prepared art writes overlap.')
 return prepared,plan,source,project,manifest


def export_mod_zips(prepared,parent,progress=lambda *a:None,cancel=None):
 stopped(cancel);prepared,plan,source,project,_=validate_prepared(prepared)
 parent=Path(parent).expanduser().resolve()
 if parent.is_relative_to(source.parent) or any(parent.is_relative_to(project/branch) for branch in ['Input','Output','Prepared','Backups']):raise ValueError('Save mod ZIPs outside the game installation and project working folders.')
 parent.mkdir(parents=True,exist_ok=True)
 groups={}
 for record in plan['patches']:groups.setdefault(record['character'],[]).append(record)
 # Stage the complete batch before publishing any ZIPs.
 with tempfile.TemporaryDirectory(dir=parent,prefix='.workshop-mods-') as staging:
  staging=Path(staging);result=[]
  for index,(name,records) in enumerate(sorted(groups.items())):
   stopped(cancel);progress(index,len(groups),f'Building {NAMES[name]} mod ZIP…');assets={};identity=hashlib.sha256(name.encode())
   if plan.get('storage')=='relocatable':
    from repacking import character_assets
    assets=character_assets(source,prepared,name,records)
    for path,content in assets.items():identity.update(path.encode());identity.update(content)
   for archive_name in ([] if plan.get('storage')=='relocatable' else sorted({r['archive'] for r in records})):
    stopped(cancel)
    with GFS(source/archive_name) as archive:
     bank=next(bank for bank,(filename,_) in ART_FILES.items() if filename==archive_name);suffix=ART_FILES[bank][1]
     location=archive.entries[f'characters/{name}{suffix}'];offset,size=location
     internal=next(key for key,value in archive.entries.items() if value==location)
     safe_path(staging,internal)
     content=bytearray(archive.data[offset:offset+size])
     for record in records:
      if record['archive']!=archive_name:continue
      payload=safe_path(prepared,record['payload']).read_bytes()
      if hashlib.sha256(payload).hexdigest()!=record['payload_sha256']:raise ValueError('A prepared payload was altered.')
      start=record['offset']-offset
      if not 0<=start<=size-len(payload):raise ValueError('A prepared slot escapes its character asset.')
      content[start:start+len(payload)]=payload
     path=archive_name+'/'+internal;assets[path]=bytes(content);identity.update(path.encode());identity.update(content)
   info=dict(id=f'spriteworkshop.{name}.{identity.hexdigest()[:16]}',name=f'{NAMES[name]} sprite replacements',author='Sprite Workshop',desc='Prepared character sprite replacements. Requires the same game version used to prepare this mod.',version='1.0.0',url=None)
   filename=name+'-sprites.zip'
   with zipfile.ZipFile(staging/filename,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
    output.writestr('mod.json',json.dumps(info,indent=2))
    for path,content in assets.items():stopped(cancel);output.writestr(path,content)
   with zipfile.ZipFile(staging/filename) as output:
    if output.testzip() is not None:raise ValueError('Mod ZIP verification failed.')
    for path,content in assets.items():
     if output.read(path)!=content:raise ValueError('A packaged character asset differs from the prepared art.')
   result.append(dict(character=name,file=filename,assets=list(assets),frames=len(records)))
  # Recheck the baseline and Inputs before publishing a potentially long export.
  stopped(cancel);validate_prepared(prepared);stopped(cancel)
  folder=unique(parent,'Skullgirls Mods')
  for record in result:(staging/record['file']).replace(folder/record['file'])
  progress(len(groups),len(groups),f'Saved {len(result)} character mod ZIPs')
  return folder,result


def apply_import(prepared,progress=lambda *a:None,check_running=True):
 prepared,plan,source,project,manifest=validate_prepared(prepared,check_running)
 if plan.get('storage')=='relocatable':
  from repacking import apply_relocated
  return apply_relocated(prepared,plan,source,project,progress,check_running)
 backup=unique(project/'Backups','Import');receipt=dict(schema=SCHEMA,game=str(source),before=plan['source_hashes'],after={},frames=len(plan['patches']),protected=plan['protected_hashes'],status='backing_up')
 write_json(backup/'restore.json',receipt)
 for i,(name,digest) in enumerate(plan['source_hashes'].items()):
  progress(i,len(plan['source_hashes']),f'Backing up {name}…');shutil.copy2(source/name,backup/name)
  if sha(backup/name)!=digest:raise ValueError('Backup verification failed; no archives were changed.')
 if check_running and game_running():raise ValueError('Skullgirls opened during backup. Close it and prepare again.')
 for name,digest in {**plan['source_hashes'],**plan['protected_hashes']}.items():
  if sha(source/name)!=digest:raise ValueError('Game files changed during backup; import stopped before writing.')
 try:
  for name in plan['source_hashes']:
   progress(0,1,f'Writing verified art to {name}…')
   with (source/name).open('r+b') as out:
    for record in plan['patches']:
     if record['archive']==name:out.seek(record['offset']);out.write(safe_path(prepared,record['payload']).read_bytes())
    out.flush();os.fsync(out.fileno())
   # Compare the complete archive to prove no bytes outside approved slots changed.
   slots=[(r['offset'],r['offset']+r['bytes']) for r in plan['patches'] if r['archive']==name]
   with (source/name).open('rb') as new,(backup/name).open('rb') as old:
    pos=0
    while True:
     aa=new.read(1024*1024);bb=old.read(1024*1024)
     if len(aa)!=len(bb):raise ValueError('Archive size changed unexpectedly.')
     if not aa:break
     dif=np.flatnonzero(np.frombuffer(aa,np.uint8)!=np.frombuffer(bb,np.uint8))+pos;allowed=np.zeros(len(dif),bool)
     for start,end in slots:allowed|=(dif>=start)&(dif<end)
     if not allowed.all():raise ValueError('Unexpected changes outside the selected art slots.')
     pos+=len(aa)
   with GFS(source/name) as g:
    for record in plan['patches']:
     if record['archive']==name:
      offset=record['offset'];payload=safe_path(prepared,record['payload']).read_bytes()
      if g.data[offset:offset+len(payload)]!=payload:raise ValueError('Written payload verification failed.')
   receipt['after'][name]=sha(source/name)
  for name,digest in plan['protected_hashes'].items():
   if sha(source/name)!=digest:raise ValueError('A protected archive changed unexpectedly.')
 except Exception:
  for name in plan['source_hashes']:shutil.copy2(backup/name,source/name)
  receipt['status']='rolled_back';write_json(backup/'restore.json',receipt);raise
 receipt['status']='installed';write_json(backup/'restore.json',receipt);plan['status']='applied';plan['backup']=str(backup);write_json(prepared/'plan.json',plan)
 progress(1,1,f'Installed {len(plan["patches"])} replacements; backup verified')
 return backup,receipt

def restore_import(backup,progress=lambda *a:None,check_running=True):
 backup=Path(backup).resolve();receipt=json.loads((backup/'restore.json').read_text(encoding='utf-8'));source=data_folder(receipt['game'])
 if receipt['status'] not in ['installed','restoring']:raise ValueError('This backup is not an installed import.')
 if check_running and game_running():raise ValueError('Close Skullgirls before restoring an import.')
 for name,digest in receipt['protected'].items():
  if name not in ['characters-foits.gfs','sprites.gfs'] or sha(source/name)!=digest:raise ValueError('Game metadata or palettes changed since this import. Restore refused.')
 for name,digest in receipt['after'].items():
  if name not in ['characters-art.gfs','characters-art-pt.gfs','characters-foits.gfs','sprites.gfs']:raise ValueError('Invalid backup archive.')
  allowed={digest}
  if receipt['status']=='restoring':allowed.add(receipt['before'][name])
  if sha(source/name) not in allowed:raise ValueError('The game has changed since this import. Restore refused to avoid overwriting newer changes.')
  if sha(backup/name)!=receipt['before'][name]:raise ValueError('The backup failed its integrity check.')
 receipt['status']='restoring';write_json(backup/'restore.json',receipt)
 for i,name in enumerate(receipt['after']):
  if sha(source/name)==receipt['before'][name]:continue
  progress(i,len(receipt['after']),f'Restoring {name}…');temporary=None
  try:
   with tempfile.NamedTemporaryFile(dir=source,prefix=name+'.restore-',delete=False) as stream:temporary=Path(stream.name)
   shutil.copy2(backup/name,temporary)
   if sha(temporary)!=receipt['before'][name]:raise ValueError('Restored archive verification failed.')
   if check_running and game_running():raise ValueError('Close Skullgirls before restoring an import.')
   for protected,digest in receipt['protected'].items():
    if sha(source/protected)!=digest:raise ValueError('Game metadata or palettes changed during restore.')
   if sha(source/name)!=receipt['after'][name]:raise ValueError('The game has changed during restore. Restore refused.')
   temporary.replace(source/name)
  finally:
   if temporary is not None:temporary.unlink(missing_ok=True)
 if receipt.get('storage')=='relocatable':
  from repacking import refresh_project_metadata
  refresh_project_metadata(backup.parent.parent,source,receipt['characters'])
 receipt['status']='restored';write_json(backup/'restore.json',receipt);progress(1,1,'Original art restored')
 return backup,receipt
