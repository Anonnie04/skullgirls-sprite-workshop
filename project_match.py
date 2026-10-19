"""Align exported animation frame sequences and stage verified copies."""
from pathlib import Path
import json,os,shutil,tempfile
import numpy as np
from PIL import Image
from scipy.spatial.distance import cdist
from layout import descriptor
from workshop import project_info,safe_path,stopped,pixel_hash,sha,write_json,unique

def frame_groups(manifest):
 groups={}
 for route,entry in manifest['exports'].items():
  group=groups.setdefault(entry['character'],{}).setdefault(entry['frame'],[]);group.append((route,entry))
 return {name:sorted(frames.items()) for name,frames in groups.items()}

def primary(entries):
 return next((pair for pair in entries if 'layers' not in Path(pair[0]).parts),entries[0])

def present_frames(project,groups,side,report,cancel):
 result={}
 for name,frames in groups.items():
  available=[]
  for index,entries in frames:
   stopped(cancel)
   missing=[route for route,_ in entries if not safe_path(project/'Output',route).is_file()]
   if missing:
    report['missing_exports'].append(dict(project=side,character=name,frame=index,paths=missing))
    if side=='source':report['unmatched'].append(dict(character=name,source_frame=index,reason='Source Output PNGs are missing; frame skipped'))
   else:available.append((index,entries))
  if available:result[name]=available
 return result

def vectors(project,frames,progress,cancel):
 result=[]
 for i,(_,entries) in enumerate(frames):
  stopped(cancel);route,_=primary(entries)
  with Image.open(safe_path(project/'Output',route)) as im:result.append(descriptor(im))
  if i%25==0:progress(i,len(frames),f'Reading exported silhouettes: {project.name} {i+1:,} / {len(frames):,}')
 return result

def align_sequences(left,right,cancel):
 # Monotonic global alignment permits additions/removals without shifting all
 # following frames. Matching a poor silhouette costs more than skipping it.
 n=len(left);m=len(right);a=np.array([v if v is not None else np.zeros(1025) for v in left]);b=np.array([v if v is not None else np.zeros(1025) for v in right])
 distance=np.empty((n,m),np.float32)
 # Keep the temporary float64 distance buffer below roughly 8 MiB.
 batch=max(1,min(128,1048576//max(1,m)))
 for first in range(0,n,batch):
  stopped(cancel);distance[first:first+batch]=cdist(a[first:first+batch],b)
 for i,v in enumerate(left):
  if v is None:distance[i,:]=10
 for j,v in enumerate(right):
  if v is None:distance[:,j]=10
 gap=1.25;trace=np.zeros((n+1,m+1),np.uint8);previous=np.arange(m+1,dtype=np.float32)*gap
 for i in range(1,n+1):
  stopped(cancel);current=np.empty(m+1,np.float32);current[0]=i*gap;trace[i,0]=1
  for j in range(1,m+1):
   match=float(previous[j-1])+float(distance[i-1,j-1]);skip_old=float(previous[j])+gap;skip_new=float(current[j-1])+gap
   if match<=skip_old and match<=skip_new:current[j]=match;trace[i,j]=0
   elif skip_old<=skip_new:current[j]=skip_old;trace[i,j]=1
   else:current[j]=skip_new;trace[i,j]=2
  previous=current
 i=n;j=m;pairs=[]
 while i or j:
  if not i:j-=1
  elif not j:i-=1
  elif trace[i,j]==0:pairs.append((i-1,j-1,float(distance[i-1,j-1])));i-=1;j-=1
  elif trace[i,j]==1:i-=1
  else:j-=1
 return list(reversed(pairs)),distance

def match_projects(source,target,progress=lambda *a:None,cancel=None,report_parent=None):
 source,sm=project_info(source);target,tm=project_info(target)
 if source==target:raise ValueError('Choose two different exported projects.')
 if not sm['exports'] or not tm['exports']:raise ValueError('Both projects must contain exported Output PNGs. Empty folder trees cannot be matched.')
 report=dict(source=str(source),target=str(target),matches=[],review=[],unmatched=[],missing_exports=[],status='matching',source_manifest_sha256=sha(source/'project.json'),target_manifest_sha256=sha(target/'project.json'))
 progress(0,0,'Checking exported PNGs before matching…')
 sg=present_frames(source,frame_groups(sm),'source',report,cancel)
 tg=present_frames(target,frame_groups(tm),'target',report,cancel)
 for name,old in sg.items():
  stopped(cancel)
  if name not in tg:
   report['unmatched'].extend(dict(character=name,source_frame=i,reason='No available exported frames for this character in target') for i,_ in old);continue
  new=tg[name];left=vectors(source,old,progress,cancel);right=vectors(target,new,progress,cancel);progress(0,0,f'Aligning {name} frame order')
  pairs,distances=align_sequences(left,right,cancel);paired=set()
  for i,j,distance in pairs:
   paired.add(i);old_frame,oe=old[i];new_frame,ne=new[j];record=dict(character=name,source_frame=old_frame,target_frame=new_frame,distance=round(distance,5),copies=[])
   # Composites are references; imports require the same editable layer set.
   ol={e['layer']:(r,e) for r,e in oe if e['layer'] is not None};nl={e['layer']:(r,e) for r,e in ne if e['layer'] is not None}
   reason=None
   if distance>1.5:reason='Silhouette difference requires review'
   elif set(ol)!=set(nl):reason='Editable layers differ between versions'
   # Similar adjacent poses can be ambiguous after a frame insertion.
   neighbors=[float(distances[i,k]) for k in range(max(0,j-2),min(len(new),j+3)) if k!=j]
   if reason is None and old_frame!=new_frame and neighbors and min(neighbors)<=distance+.05:reason='Similar neighboring frames make this pairing uncertain'
   for layer,(sr,se) in ol.items():
    if layer not in nl:continue
    tr,te=nl[layer];sp=safe_path(source/'Output',sr);tp=safe_path(target/'Output',tr)
    with Image.open(sp) as im:source_pixels=pixel_hash(im)
    with Image.open(tp) as im:target_pixels=pixel_hash(im)
    record['copies'].append(dict(source=sr,target=tr,source_sha256=sha(sp),target_sha256=sha(tp),identical_pixels=source_pixels==target_pixels))
   if reason:record['reason']=reason;report['review'].append(record)
   else:report['matches'].append(record)
  report['unmatched'].extend(dict(character=name,source_frame=f,reason='No reliable sequence pairing') for i,(f,_) in enumerate(old) if i not in paired)
 report['status']='matched';folder=unique(report_parent or target/'Matches','Frame matching');write_json(folder/'matches.json',report)
 return folder,report

def copy_matches(report_folder,progress=lambda *a:None,cancel=None):
 folder=Path(report_folder);report=json.loads((folder/'matches.json').read_text(encoding='utf-8'));source,sm=project_info(report['source']);target,tm=project_info(report['target'])
 if sha(source/'project.json')!=report['source_manifest_sha256'] or sha(target/'project.json')!=report['target_manifest_sha256']:raise ValueError('Project metadata changed. Match projects again.')
 copies=[c for r in report['matches'] for c in r['copies'] if not c['identical_pixels']];result=dict(copied=[],replaced_references=[],existing=[],unchanged=sum(c['identical_pixels'] for r in report['matches'] for c in r['copies']))
 # Validate every source/target before creating any Input files.
 for c in copies:
  if c['source'] not in sm['exports'] or c['target'] not in tm['exports']:raise ValueError('A matched route is absent from its project.')
  if sha(safe_path(source/'Output',c['source']))!=c['source_sha256'] or sha(safe_path(target/'Output',c['target']))!=c['target_sha256']:raise ValueError('An exported PNG changed. Match projects again.')
 for i,c in enumerate(copies):
  stopped(cancel);destination=safe_path(target/'Input',c['target']);destination.parent.mkdir(parents=True,exist_ok=True)
  # Stage and verify first; exclusive publication never exposes a partial PNG.
  temporary=None
  try:
   with tempfile.NamedTemporaryFile(dir=destination.parent,suffix='.matching.tmp',delete=False) as out:
    temporary=Path(out.name)
    with safe_path(source/'Output',c['source']).open('rb') as inp:shutil.copyfileobj(inp,out)
   if sha(temporary)!=c['source_sha256']:raise ValueError('An exported PNG changed while copying. Match projects again.')
   stopped(cancel)
   try:
    # Windows rename is exclusive and also works on volumes without hard links.
    if os.name=='nt':os.rename(temporary,destination)
    else:os.link(temporary,destination)
    result['copied'].append(c['target'])
   except FileExistsError:
    # Only replace an exact unchanged Output reference.
    try:
     original_hash=sha(destination)
     with Image.open(destination) as image:unchanged=pixel_hash(image)==tm['exports'][c['target']].get('pixel_sha256')
    except (OSError,ValueError):unchanged=False
    if unchanged and sha(destination)==original_hash:
     temporary.replace(destination);result['copied'].append(c['target']);result['replaced_references'].append(c['target'])
    else:result['existing'].append(c['target'])
  finally:
   if temporary is not None:temporary.unlink(missing_ok=True)
  if i%25==0:progress(i+1,len(copies),f'Copying matched sprites: {i+1:,} / {len(copies):,}')
 write_json(folder/'copy-result.json',result);return target,result
