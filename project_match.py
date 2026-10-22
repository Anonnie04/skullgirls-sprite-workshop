"""Align exported animation frame sequences and stage verified copies."""
from pathlib import Path
import json,os,shutil,tempfile
import numpy as np
from PIL import Image,ImageFilter
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
  with Image.open(safe_path(project/'Output',route)) as im:result.append(project_descriptor(im))
  if i%25==0:progress(i,len(frames),f'Reading exported silhouettes: {project.name} {i+1:,} / {len(frames):,}')
 return result


def project_descriptor(image):
 """Compare poses without treating small cross-version edges as new poses."""
 vector=descriptor(image)
 if vector is None:return None
 # The naming catalog needs sharp silhouettes, but cross-version matching
 # must tolerate small outline/emblem revisions and alpha-edge differences.
 # Smooth only the normalized 32px mask; keep the aspect-ratio penalty.
 mask=Image.fromarray(np.rint(vector[:-1].reshape(32,32)*255).astype(np.uint8))
 mask=mask.filter(ImageFilter.GaussianBlur(1))
 return np.concatenate([np.asarray(mask,dtype=np.float32).ravel()/255,vector[-1:]])

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


def pairing_reason(i,j,distance,old,new,distances):
 ol={e['layer'] for _,e in old[i][1] if e['layer'] is not None};nl={e['layer'] for _,e in new[j][1] if e['layer'] is not None}
 if ol!=nl:return 'Editable layers differ between versions'
 if distance>1.5:return 'Silhouette difference requires review'
 neighbors=[float(distances[i,k]) for k in range(max(0,j-2),min(len(new),j+3)) if k!=j]
 if old[i][0]!=new[j][0] and neighbors and min(neighbors)<=distance+.05:return 'Similar neighboring frames make this pairing uncertain'
 return None

def match_projects(source,target,progress=lambda *a:None,cancel=None,report_parent=None,min_overlap=.94):
 if not isinstance(min_overlap,(int,float)) or not .5<=min_overlap<=1:raise ValueError('Minimum shape overlap must be between 50% and 100%.')
 source,sm=project_info(source);target,tm=project_info(target)
 if source==target:raise ValueError('Choose two different exported projects.')
 if not sm['exports'] or not tm['exports']:raise ValueError('Both projects must contain exported Output PNGs. Empty folder trees cannot be matched.')
 report=dict(source=str(source),target=str(target),matching_method='registered-pose-v2',min_overlap=min_overlap,matches=[],review=[],unmatched=[],missing_exports=[],status='matching',source_manifest_sha256=sha(source/'project.json'),target_manifest_sha256=sha(target/'project.json'))
 progress(0,0,'Checking exported PNGs before matching…')
 sg=present_frames(source,frame_groups(sm),'source',report,cancel)
 tg=present_frames(target,frame_groups(tm),'target',report,cancel)
 for name,old in sg.items():
  stopped(cancel)
  if name not in tg:
   report['unmatched'].extend(dict(character=name,source_frame=i,reason='No available exported frames for this character in target') for i,_ in old);continue
  new=tg[name];left=vectors(source,old,progress,cancel);right=vectors(target,new,progress,cancel);progress(0,0,f'Aligning {name} frame order')
  pairs,distances=align_sequences(left,right,cancel);paired=set()
  from pose_recovery import recover,shape,overlap
  shapes=[]
  for project,frames in [(source,old),(target,new)]:
   items=[]
   for _,entries in frames:
    stopped(cancel)
    with Image.open(safe_path(project/'Output',primary(entries)[0])) as im:items.append(shape(im))
   shapes.append(items)
  source_shapes,target_shapes=shapes;overlaps={}
  for count,(i,j,_) in enumerate(pairs):
   stopped(cancel);overlaps[i,j]=overlap(source_shapes[i],target_shapes[j])
   if count%100==0:progress(count,len(pairs),f'Checking {name} shape overlap')
  accepted={i for i,j,d in pairs if pairing_reason(i,j,d,old,new,distances) is None and overlaps[i,j]>=min_overlap}
  needs=set(range(len(old)))-accepted
  recovered=recover(source,target,old,new,pairs,needs,accepted,progress,cancel,min_overlap,source_shapes,target_shapes)
  pairs=[(i,recovered[i]['target'],float(distances[i,recovered[i]['target']])) if i in recovered else (i,j,d) for i,j,d in pairs]
  paired_indices={i for i,_,_ in pairs}
  pairs.extend((i,r['target'],float(distances[i,r['target']])) for i,r in recovered.items() if i not in paired_indices)
  pairs.sort()
  for i,j,distance in pairs:
   paired.add(i);old_frame,oe=old[i];new_frame,ne=new[j];record=dict(character=name,source_frame=old_frame,target_frame=new_frame,distance=round(distance,5),copies=[])
   # Composites are references; imports require the same editable layer set.
   ol={e['layer']:(r,e) for r,e in oe if e['layer'] is not None};nl={e['layer']:(r,e) for r,e in ne if e['layer'] is not None}
   reason=pairing_reason(i,j,distance,old,new,distances)
   if i in recovered:
    recovery=recovered[i];record.update(registered_overlap=recovery['overlap'],recovery=recovery['method'])
    reason=None if recovery['confident'] else recovery['reason']
    if set(ol)!=set(nl):reason='Editable layers differ between versions'
   score=overlaps.get((i,j))
   if score is None:score=overlap(source_shapes[i],target_shapes[j])
   record['registered_overlap']=round(score,5)
   if score<min_overlap:reason=f'Shape overlap {score:.1%} is below the selected {min_overlap:.0%} minimum'
   for layer,(sr,se) in ol.items():
    if layer not in nl:continue
    tr,te=nl[layer];sp=safe_path(source/'Output',sr);tp=safe_path(target/'Output',tr)
    with Image.open(sp) as im:source_pixels=pixel_hash(im);source_empty=not im.convert('RGBA').getchannel('A').getbbox()
    with Image.open(tp) as im:target_pixels=pixel_hash(im);target_empty=not im.convert('RGBA').getchannel('A').getbbox()
    record['copies'].append(dict(source=sr,target=tr,source_sha256=sha(sp),target_sha256=sha(tp),identical_pixels=source_pixels==target_pixels or source_empty and target_empty))
   if reason:record['reason']=reason;report['review'].append(record)
   else:report['matches'].append(record)
  report['unmatched'].extend(dict(character=name,source_frame=f,reason='No reliable sequence pairing') for i,(f,_) in enumerate(old) if i not in paired)
 report['status']='matched';folder=unique(report_parent or target/'Matches','Frame matching');write_json(folder/'matches.json',report)
 return folder,report

def copy_required(report,copy):
 return not copy['identical_pixels'] or report.get('approved_overwrites',{}).get(copy['target'],{}).get('source_sha256')==copy['source_sha256']


def copy_matches(report_folder,progress=lambda *a:None,cancel=None):
 folder=Path(report_folder);report=json.loads((folder/'matches.json').read_text(encoding='utf-8'));source,sm=project_info(report['source']);target,tm=project_info(report['target'])
 if sha(source/'project.json')!=report['source_manifest_sha256'] or sha(target/'project.json')!=report['target_manifest_sha256']:raise ValueError('Project metadata changed. Match projects again.')
 copies=[c for r in report['matches'] for c in r['copies'] if copy_required(report,c)];result=dict(copied=[],replaced_references=[],existing=[],unchanged=sum(not copy_required(report,c) for r in report['matches'] for c in r['copies']))
 targets={};unique_copies=[]
 # Validate every source/target before creating any Input files.
 for c in copies:
  if c['source'] not in sm['exports'] or c['target'] not in tm['exports']:raise ValueError('A matched route is absent from its project.')
  if sha(safe_path(source/'Output',c['source']))!=c['source_sha256'] or sha(safe_path(target/'Output',c['target']))!=c['target_sha256']:raise ValueError('An exported PNG changed. Match projects again.')
  if c['target'] in targets:
   with Image.open(safe_path(source/'Output',c['source'])) as image:current=pixel_hash(image)
   with Image.open(safe_path(source/'Output',targets[c['target']]['source'])) as image:previous=pixel_hash(image)
   if current!=previous:raise ValueError('Different source artwork would overwrite the same target. Match projects again and review shared frames.')
  else:targets[c['target']]=c;unique_copies.append(c)
 copies=unique_copies
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
    original_hash=None
    try:
     original_hash=sha(destination)
     with Image.open(destination) as image:unchanged=pixel_hash(image)==tm['exports'][c['target']].get('pixel_sha256')
    except (OSError,ValueError):unchanged=False
    grant=report.get('approved_overwrites',{}).get(c['target'],{})
    approved=grant.get('before')==original_hash and grant.get('source_sha256')==c['source_sha256']
    backup_record=None
    if approved and sha(destination)==original_hash:
     if 'approval_backup' not in result:result['approval_backup']=str(unique(folder/'Input backups','Approved choice'))
     backup=Path(result['approval_backup']);saved=safe_path(backup,c['target']);saved.parent.mkdir(parents=True,exist_ok=True)
     shutil.copy2(destination,saved)
     if sha(saved)!=original_hash:raise ValueError('The staged Input changed during backup; it was not replaced.')
     backup_record=dict(path=c['target'],before=original_hash,after=c['source_sha256'])
     write_json(backup/'input-backup.json',dict(target=str(target),files=result.get('approved_replaced',[])+[backup_record]))
    if (unchanged or approved) and sha(destination)==original_hash:
     temporary.replace(destination);result['copied'].append(c['target'])
     if approved:result.setdefault('approved_replaced',[]).append(backup_record)
     else:result['replaced_references'].append(c['target'])
    else:result['existing'].append(c['target'])
  finally:
   if temporary is not None:temporary.unlink(missing_ok=True)
  if i%25==0:progress(i+1,len(copies),f'Copying matched sprites: {i+1:,} / {len(copies):,}')
 write_json(folder/'copy-result.json',result);return target,result
