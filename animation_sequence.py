"""Stage arbitrarily named animation PNGs into manifest-backed Input routes."""
from pathlib import Path
import os
import re
import shutil
from PIL import Image
from workshop import project_info, safe_path, sha, unique, write_json, stopped


def natural_key(value):
 return [int(part) if part.isdigit() else part for part in re.split(r'(\d+)', str(value).casefold())]


def animations(project):
 _,manifest=project_info(project);groups={}
 for route,entry in {**manifest.get('reference_files',{}),**manifest['exports']}.items():
  if entry['layer'] is None:continue
  path=Path(route);folder=path.parent
  key=folder.as_posix()+(f' [layer {entry["layer"]}]' if folder.name=='layers' else '')
  groups.setdefault(key,[]).append((route,entry))
 for entries in groups.values():entries.sort(key=lambda pair:natural_key(Path(pair[0]).name))
 return dict(sorted(groups.items()))


def plan_sequence(project,files,animation,start=0,overwrite=False):
 project,_=project_info(project);groups=animations(project)
 if animation not in groups:raise ValueError('Choose a destination animation.')
 files=sorted([Path(f).expanduser().resolve() for f in files],key=lambda p:natural_key(p.name))
 if not files:raise ValueError('Select one or more PNG files.')
 if len({p.name.casefold() for p in files})!=len(files):raise ValueError('Selected files have duplicate names; select one numbered sequence.')
 entries=groups[animation]
 if start<0 or start+len(files)>len(entries):raise ValueError('The sequence exceeds the remaining destination frames. Choose a different starting frame or fewer PNGs.')
 root=(project/'Input').resolve();output=(project/'Output').resolve()
 if not root.is_relative_to(project) or root.is_relative_to(output) or output.is_relative_to(root):raise ValueError('Input and Output must be separate project folders.')
 result=[]
 for source,(route,entry) in zip(files,entries[start:start+len(files)]):
  if source.suffix.lower()!='.png':raise ValueError('Select PNG files only.')
  with Image.open(source) as image:
   if image.format!='PNG':raise ValueError(f'Not a PNG: {source.name}')
   image.verify()
  destination=safe_path(root,route);digest=sha(source);existing=sha(destination) if destination.exists() else None
  same=existing==digest
  if existing is not None and not same and not overwrite:raise ValueError('Input already contains replacements. Enable replacement with backup to update those frames.')
  result.append(dict(source=str(source),target=route,sha256=digest,existing_sha256=existing,unchanged=same))
 return result


def stage_sequence(project,files,animation,start=0,overwrite=False,progress=lambda *a:None,cancel=None):
 project,_=project_info(project);mapping=plan_sequence(project,files,animation,start,overwrite)
 changes=[item for item in mapping if not item['unchanged']]
 stopped(cancel);folder=unique(project/'Sequence Imports','Animation sequence');receipt=dict(status='staging',mapping=mapping)
 write_json(folder/'mapping.json',receipt);committed=[]
 try:
  for i,item in enumerate(changes):
   stopped(cancel);incoming=folder/'Incoming'/f'{i:05d}.png';incoming.parent.mkdir(exist_ok=True)
   shutil.copy2(item['source'],incoming)
   if sha(incoming)!=item['sha256']:raise ValueError('An exported PNG changed while staging. Try again.')
   destination=safe_path(project/'Input',item['target'])
   current=sha(destination) if destination.exists() else None
   if current!=item['existing_sha256']:raise ValueError('An Input frame changed while staging. Try again.')
   if current is not None:
    previous=safe_path(folder/'Previous Input',item['target']);previous.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(destination,previous)
    if sha(previous)!=current:raise ValueError('Input backup verification failed.')
  for i,item in enumerate(changes):
   stopped(cancel);destination=safe_path(project/'Input',item['target'])
   current=sha(destination) if destination.exists() else None
   if current!=item['existing_sha256']:raise ValueError('An Input frame changed before copying. Try again.')
   destination.parent.mkdir(parents=True,exist_ok=True)
   os.replace(folder/'Incoming'/f'{i:05d}.png',destination);committed.append(item)
   progress(i+1,len(changes),f'Staging animation: {i+1} / {len(changes)}')
  receipt['status']='staged';write_json(folder/'mapping.json',receipt)
 except Exception:
  for item in reversed(committed):
   destination=safe_path(project/'Input',item['target'])
   if not destination.exists() or sha(destination)!=item['sha256']:continue
   if item['existing_sha256'] is None:destination.unlink()
   else:shutil.copy2(safe_path(folder/'Previous Input',item['target']),destination)
  receipt['status']='rolled_back';write_json(folder/'mapping.json',receipt);raise
 return project,dict(copied=len(changes),unchanged=len(mapping)-len(changes),backed_up=sum(i['existing_sha256'] is not None for i in changes),folder=str(folder))
