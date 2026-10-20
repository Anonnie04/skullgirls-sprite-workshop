"""Relocate art streams and update their FOIT references and memory sizes."""
from pathlib import Path
import hashlib,os,shutil,struct,tempfile
from decoder import GFS,Reader,parse_frames_data,decode_image


def art_memory_fields(metadata,name):
 """Locate VRSN 9 art-size fields using the validated palette-name table."""
 if len(metadata)<12 or metadata[4:8]!=b'VRSN' or struct.unpack_from('<I',metadata,8)[0]!=9:return {}
 label=(name+'_1p.pal').encode('ascii')
 if len(label)>255:return {}
 marker=bytes([len(label)])+label;at=metadata.find(marker)
 if at<34 or metadata.find(marker,at+len(marker))>=0:return {}
 table=at-22
 if any(size<0 for size in struct.unpack_from('<5i',metadata,table)):return {}
 count=struct.unpack_from('<H',metadata,at-2)[0]
 if not 1<=count<=256:return {}
 cursor=at
 for _ in range(count):
  if cursor>=len(metadata):return {}
  length=metadata[cursor];cursor+=1
  if length<5 or length>len(metadata)-cursor:return {}
  value=metadata[cursor:cursor+length]
  if not value.endswith(b'.pal') or any(ch<32 or ch>126 for ch in value):return {}
  cursor+=length
 return {5:table+8,4:table+12}


def refresh_project_metadata(project,source,characters):
 from workshop import project_info,data_folder,write_json,sha
 project,manifest=project_info(project)
 if data_folder(manifest['game'])!=source:raise ValueError('Project game changed during import.')
 with GFS(source/'characters-foits.gfs') as archive:
  for name in characters:manifest['characters'][name]['foit_sha256']=hashlib.sha256(archive.read(f'characters/{name}.foit')).hexdigest()
 manifest['palette_archive_sha256']=sha(source/'sprites.gfs')
 write_json(project/'project.json',manifest)


def character_assets(source,prepared,name,records):
 from workshop import ART_FILES,safe_path
 assets={}
 with GFS(source/'characters-foits.gfs') as foits,GFS(source/'characters-art.gfs') as art:
  location=foits.entries[f'characters/{name}.foit']
  internal=next(k for k,v in foits.entries.items() if v==location)
  metadata=bytearray(foits.read(internal))
  memory_fields=art_memory_fields(metadata,name)
  frames,positions=parse_frames_data(name,metadata,art.entries[f'characters/{name}.art'][1],with_locations=True)
  for bank in sorted({r['art_bank'] for r in records}):
   archive_name,suffix=ART_FILES[bank]
   with GFS(source/archive_name) as archive:
    location=archive.entries[f'characters/{name}{suffix}']
    art_internal=next(k for k,v in archive.entries.items() if v==location)
    content=bytearray(archive.read(art_internal))
    for record in records:
     if record['art_bank']!=bank:continue
     old=frames[record['frame']]['images'][record['layer']]
     payload=safe_path(prepared,record['payload']).read_bytes()
     if hashlib.sha256(payload).hexdigest()!=record['payload_sha256']:raise ValueError('A prepared payload was altered.')
     new_offset=len(content);sizes=record['encoded_sizes']
     if new_offset+len(payload)>0x7fffffff:raise ValueError('Character art exceeds the supported pointer range.')
     references=[]
     for j,frame in enumerate(frames):
      if frame['art_bank']!=bank:continue
      for k,meta in frame['images'].items():
       if meta==old:references.append((j,k))
     if not references:raise ValueError('Missing art reference.')
     for key in references:
      pos=positions[key]
      if pos is None:raise ValueError('Cannot relocate an empty image.')
      struct.pack_into('<4i',metadata,pos,new_offset,*sizes)
      flag_pos=pos-len(bytes.fromhex(old['mask']))-(8 if old['flags']&4 else 0)-1
      metadata[flag_pos]=record['encoded_flags']
     content.extend(payload)
     # The runtime checks this byte before decoding streamed (bank 4) art.
     # It is outside the three channel sizes and must survive relocation.
     if bank==4:content.append(0xbb)
     decode_image({**old,'offset':new_offset,'sizes':sizes,'flags':record['encoded_flags']},content)
    # The game uses these header values for art memory sizing. The preview
    # decoder only follows pointers, so it cannot catch an undersized budget.
    if bank in memory_fields:
     position=memory_fields[bank];reserved=struct.unpack_from('<i',metadata,position)[0]
     if len(content)>reserved:struct.pack_into('<i',metadata,position,len(content))
    assets[archive_name+'/'+art_internal]=bytes(content)
  # Other FOIT bytes stay supplied: timing, hits, origins, masks and palettes.
  assets['characters-foits.gfs/'+internal]=bytes(metadata)
  from select_preview import sync_preview
  assets.update(sync_preview(source,name,frames,art.read(f'characters/{name}.art'),assets))
 return assets


def repack_archive(original,output,replacements):
 """Preserve entry order, names, alignment and all untouched payload bytes."""
 with GFS(original) as archive:
  r=Reader(archive.data)
  def number(fmt):return struct.unpack('>'+fmt,r.read(struct.calcsize('>'+fmt)))[0]
  def text():return r.read(number('Q'))
  number('I');identifier=text();version=text();count=number('Q');entries=[]
  for _ in range(count):entries.append((text(),number('Q'),number('I')))
  def string(value):return struct.pack('>Q',len(value))+value
  table=string(identifier)+string(version)+struct.pack('>Q',count)
  seen=set()
  for raw,size,align in entries:
   name=raw.decode().rstrip('\0');seen.add(name)
   if name in replacements:size=len(replacements[name])
   table+=string(raw)+struct.pack('>QI',size,align)
  if set(replacements)-seen:raise ValueError('Replacement is not in the original archive.')
  with Path(output).open('wb') as out:
   out.write(struct.pack('>I',len(table)+4));out.write(table)
   for raw,size,align in entries:
    name=raw.decode().rstrip('\0')
    if align>1:out.write(bytes((-out.tell())%align))
    if name in replacements:out.write(replacements[name])
    else:
     offset,length=archive.entries[name]
     for start in range(offset,offset+length,1024*1024):out.write(archive.data[start:min(start+1024*1024,offset+length)])
   out.flush();os.fsync(out.fileno())
  with GFS(output) as result:
   for raw,_,_ in entries:
    name=raw.decode().rstrip('\0')
    if name in replacements:
     if result.read(name)!=replacements[name]:raise ValueError('Repacked replacement differs.')
    else:
     offset,length=archive.entries[name];new_offset,new_length=result.entries[name]
     if length!=new_length:raise ValueError('Repacked asset length differs.')
     for chunk in range(0,length,1024*1024):
      stop=min(chunk+1024*1024,length)
      if archive.data[offset+chunk:offset+stop]!=result.data[new_offset+chunk:new_offset+stop]:raise ValueError('Untouched asset differs.')


def apply_relocated(prepared,plan,source,project,progress,check_running):
 from workshop import unique,write_json,sha,game_running,validate_prepared
 assets={}
 for name in sorted({r['character'] for r in plan['patches']}):
  progress(0,1,f'Building {name} art without storage color fitting…')
  assets.update(character_assets(source,prepared,name,[r for r in plan['patches'] if r['character']==name]))
 before=dict(plan['source_hashes']);protected=dict(plan['protected_hashes'])
 if any(path.startswith('sprites.gfs/') for path in assets):before['sprites.gfs']=protected.pop('sprites.gfs')
 backup=unique(project/'Backups','Import')
 receipt=dict(schema=plan['schema'],storage='relocatable',characters=sorted({r['character'] for r in plan['patches']}),game=str(source),before=before,after={},frames=len(plan['patches']),protected=protected,status='backing_up')
 write_json(backup/'restore.json',receipt)
 with tempfile.TemporaryDirectory(dir=source,prefix='.workshop-import-') as staging:
  staging=Path(staging)
  for name,digest in before.items():
   shutil.copy2(source/name,backup/name)
   if sha(backup/name)!=digest:raise ValueError('Backup verification failed; no archives were changed.')
   replacements={p.split('/',1)[1]:content for p,content in assets.items() if p.split('/',1)[0]==name}
   repack_archive(source/name,staging/name,replacements)
  # Detect edits during the potentially lengthy staging operation before writes.
  validate_prepared(prepared,check_running)
  installed=[]
  try:
   for name in before:
    if check_running and game_running():raise ValueError('Close Skullgirls before applying an import.')
    if sha(source/name)!=before[name]:raise ValueError('Game files changed during import.')
    installed.append(name);(staging/name).replace(source/name)
    receipt['after'][name]=sha(source/name)
   for name,digest in protected.items():
    if sha(source/name)!=digest:raise ValueError('A protected archive changed unexpectedly.')
   refresh_project_metadata(project,source,receipt['characters'])
  except Exception:
   for name in installed:shutil.copy2(backup/name,source/name)
   receipt['status']='rolled_back';write_json(backup/'restore.json',receipt);raise
 receipt['status']='installed';write_json(backup/'restore.json',receipt)
 plan['status']='applied';plan['backup']=str(backup);write_json(prepared/'plan.json',plan)
 progress(1,1,f'Installed {len(plan["patches"])} replacements; backup verified')
 return backup,receipt
