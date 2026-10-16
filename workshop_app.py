from version import __version__
from animation_sequence import animations,plan_sequence,stage_sequence,natural_key
import os,sys,json,threading,queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk,filedialog,messagebox
from PIL import Image,ImageTk,ImageDraw
from decoder import NAMES,available_characters
from project_match import match_projects,copy_matches
from workshop import generate_input_tree,export_project,scan_input,prepare_import,apply_import,restore_import,project_info

# Original art-deco styling: no game artwork or external fonts required.
BG='#181416';PANEL='#292124';TEXT='#f5ead5';MUTED='#c2b39e';ACCENT='#e6bc68'
BURGUNDY='#542733';BORDER='#806345';HOVER='#403038';DISABLED='#8f827b'

def configure_theme(root):
 style=ttk.Style(root);style.theme_use('clam')
 root.option_add('*Font',('Segoe UI',10))
 root.option_add('*Listbox.background',PANEL);root.option_add('*Listbox.foreground',TEXT)
 root.option_add('*Listbox.selectBackground',BURGUNDY);root.option_add('*Listbox.selectForeground',TEXT)
 style.configure('.',background=BG,foreground=TEXT,font=('Segoe UI',10),bordercolor=BORDER,lightcolor=BORDER,darkcolor=BG,focuscolor=ACCENT)
 for name in ('TEntry','TCombobox'):
  style.configure(name,fieldbackground=PANEL,foreground=TEXT,insertcolor=TEXT,padding=7,arrowcolor=ACCENT)
  style.map(name,fieldbackground=[('disabled',BG),('readonly',PANEL)],foreground=[('disabled',DISABLED),('readonly',TEXT)],bordercolor=[('focus',ACCENT)])
 style.configure('TButton',background=PANEL,foreground=TEXT,padding=(12,8),borderwidth=1)
 style.map('TButton',background=[('disabled',BG),('pressed',BURGUNDY),('active',HOVER)],foreground=[('disabled',DISABLED)],bordercolor=[('focus',ACCENT),('active',ACCENT)])
 style.configure('Accent.TButton',background=ACCENT,foreground=BG,font=('Segoe UI',11,'bold'))
 style.map('Accent.TButton',background=[('disabled',PANEL),('pressed','#c79b4e'),('active','#f6d897')],foreground=[('disabled',DISABLED),('!disabled',BG)])
 style.configure('TCheckbutton',background=PANEL,foreground=TEXT,padding=4,indicatorbackground=BG,indicatorforeground=BG)
 style.map('TCheckbutton',background=[('active',HOVER)],foreground=[('disabled',DISABLED)],indicatorbackground=[('disabled',PANEL),('selected',ACCENT)],bordercolor=[('focus',ACCENT)])
 style.configure('TProgressbar',troughcolor=PANEL,background=ACCENT,bordercolor=BORDER,lightcolor=ACCENT,darkcolor=ACCENT)
 style.configure('TNotebook',background=BG,borderwidth=1,tabmargins=(0,0,0,0))
 style.configure('TNotebook.Tab',background=PANEL,foreground=MUTED,padding=(20,10),font=('Segoe UI',10,'bold'))
 style.map('TNotebook.Tab',background=[('selected',BURGUNDY),('active',HOVER)],foreground=[('selected',ACCENT),('active',TEXT)])
 style.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=TEXT,rowheight=28)
 style.map('Treeview',background=[('selected',BURGUNDY)],foreground=[('selected',TEXT)])
 style.configure('Treeview.Heading',background=BURGUNDY,foreground=ACCENT,font=('Segoe UI',10,'bold'),padding=(8,6))
 style.map('Treeview.Heading',background=[('active',HOVER)])
 style.configure('TScrollbar',background=PANEL,troughcolor=BG,arrowcolor=ACCENT)
 style.map('TScrollbar',background=[('active',HOVER),('pressed',BURGUNDY)])

def workshop_header(parent):
 banner=tk.Canvas(parent,height=100,bg=BG,highlightthickness=0)
 # Supersample the straight diamond edges; Tk canvas polygons are not antialiased.
 scale=4
 diamond=Image.new('RGB',(24*scale,34*scale),BURGUNDY)
 ImageDraw.Draw(diamond).polygon([(12*scale,3*scale),(21*scale,17*scale),(12*scale,31*scale),(3*scale,17*scale)],fill=ACCENT)
 banner.diamond=ImageTk.PhotoImage(diamond.resize((24,34),Image.Resampling.LANCZOS),master=banner)
 def draw(event):
  banner.delete('all');w=event.width
  banner.create_polygon(0,0,w,0,w,76,w-24,100,24,100,0,76,fill=BURGUNDY,outline=BORDER)
  banner.create_line(14,12,w-14,12,fill=ACCENT)
  banner.create_line(28,88,w-28,88,fill=BORDER)
  for x in (32,w-32):
   banner.create_image(x,50,image=banner.diamond)
   banner.create_line(x,20,x,31,fill=ACCENT);banner.create_line(x,69,x,80,fill=ACCENT)
  banner.create_text(w/2,30,text='S K U L L G I R L S',fill=ACCENT,font=('Georgia',12,'bold'))
  banner.create_text(w/2,58,text='SPRITE WORKSHOP',fill=TEXT,font=('Georgia',25,'bold'))
  banner.create_text(w/2,80,text='E X P O R T   /   E D I T   /   I M P O R T',fill=MUTED,font=('Segoe UI',8))
 banner.bind('<Configure>',draw)
 return banner

class App(tk.Tk):
 def __init__(self):
  super().__init__();self.title(f'Skullgirls Sprite Workshop {__version__}');self.geometry('1050x900');self.minsize(930,880);self.configure(bg=BG)
  self.events=queue.Queue();self.cancel_event=threading.Event();self.busy=False;self.prepared=None;self.plan=None;self.last_output=None;self.last_backup=None;self.photos=[];self.fields=[]
  configure_theme(self)
  self.columnconfigure(0,weight=1);self.rowconfigure(2,weight=1)
  top=workshop_header(self);top.grid(row=0,column=0,sticky='ew',padx=24,pady=(18,10))
  candidates=[]
  if os.name=='nt':
   import winreg
   try:
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,r'Software\Valve\Steam') as key:candidates.append(Path(winreg.QueryValueEx(key,'SteamPath')[0])/'steamapps'/'common'/'Skullgirls')
   except OSError:pass
  candidates.append(Path(os.environ.get('PROGRAMFILES(X86)','C:/Program Files (x86)'))/'Steam'/'steamapps'/'common'/'Skullgirls')
  guess=next((p for p in candidates if p.is_dir()),Path.home());self.game=tk.StringVar(value=str(guess));self.output=tk.StringVar(value=str(Path.home()/'Pictures'/'Skullgirls Projects'));self.project=tk.StringVar()
  paths=tk.Frame(self,bg=BG);paths.grid(row=1,column=0,sticky='ew',padx=24,pady=(0,10));paths.columnconfigure(1,weight=1);self.path_row(paths,0,'GAME FOLDER',self.game)
  self.tabs=ttk.Notebook(self);self.tabs.grid(row=2,column=0,sticky='nsew',padx=24);export=tk.Frame(self.tabs,bg=BG,padx=12,pady=12);imports=tk.Frame(self.tabs,bg=BG,padx=12,pady=12);self.tabs.add(export,text='Export project');self.tabs.add(imports,text='Import replacements')
  export.columnconfigure(1,weight=1);self.path_row(export,0,'SAVE PROJECTS TO',self.output)
  tk.Label(export,text='Output  /  exported PNGs        Input  /  empty folders for replacements',bg=PANEL,fg=ACCENT,font=('Segoe UI',11,'bold'),padx=14,pady=14,anchor='w').grid(row=1,column=0,columnspan=3,sticky='ew',pady=(14,7))
  tk.Label(export,text='Both use: character / character / data / category / animation / frames',bg=BG,fg=MUTED,anchor='w').grid(row=2,column=0,columnspan=3,sticky='ew',pady=(0,12))
  tools=tk.Frame(export,bg=BG);tools.grid(row=3,column=0,columnspan=3,sticky='ew');tk.Label(tools,text='CHARACTERS',bg=BG,fg=MUTED).pack(side='left')
  ttk.Button(tools,text='Scan game',command=self.scan).pack(side='right',padx=4);ttk.Button(tools,text='Clear',command=lambda:self.select(False)).pack(side='right',padx=4);ttk.Button(tools,text='Select all',command=lambda:self.select(True)).pack(side='right',padx=4)
  selection=tk.Frame(export,bg=PANEL,padx=12,pady=8,highlightbackground=BORDER,highlightthickness=1);selection.grid(row=4,column=0,columnspan=3,sticky='ew',pady=10);self.vars={};self.checks={}
  for i,(name,label) in enumerate(NAMES.items()):
   self.vars[name]=tk.BooleanVar(value=True);check=ttk.Checkbutton(selection,text=label,variable=self.vars[name]);check.grid(row=i//3,column=i%3,sticky='w',padx=8);self.checks[name]=check
  for i in range(3):selection.columnconfigure(i,weight=1)
  tk.Label(export,text='Animation names come from the installed Digital Art Compendium. Unmatched frames stay importable in an unmapped folder.\nLayered frames include individual layer PNGs. The first export builds an animation-name index.',bg=BG,fg=MUTED,justify='left',wraplength=920).grid(row=5,column=0,columnspan=3,sticky='w',pady=12)
  buttons=tk.Frame(export,bg=BG);buttons.grid(row=6,column=0,columnspan=3,sticky='ew');self.tree_button=ttk.Button(buttons,text='Generate full empty Input tree',command=self.start_tree);self.tree_button.pack(side='left')
  self.export_button=ttk.Button(buttons,text='Create Output + empty Input',style='Accent.TButton',command=self.start_export);self.export_button.pack(side='right')
  imports.columnconfigure(1,weight=1);imports.rowconfigure(3,weight=1);self.path_row(imports,0,'PROJECT FOLDER',self.project)
  tk.Label(imports,text='Place only edited PNGs in Input, using the same paths as Output. Empty folders are skipped.\nPrepare and review the previews before applying. The game must be closed when applying or restoring.',bg=BG,fg=MUTED,justify='left',wraplength=920).grid(row=1,column=0,columnspan=3,sticky='ew',pady=10)
  actions=tk.Frame(imports,bg=BG);actions.grid(row=2,column=0,columnspan=3,sticky='ew',pady=(0,8));self.sequence_button=ttk.Button(actions,text='Import animation sequence…',command=self.start_sequence);self.sequence_button.pack(side='left',padx=(0,8));self.scan_button=ttk.Button(actions,text='Check Input',command=self.check_input);self.scan_button.pack(side='left');self.prepare_button=ttk.Button(actions,text='Prepare previews',command=self.start_prepare);self.prepare_button.pack(side='left',padx=8);self.apply_button=ttk.Button(actions,text='Apply ready replacements',style='Accent.TButton',command=self.start_apply,state='disabled');self.apply_button.pack(side='right')
  tableframe=tk.Frame(imports,bg=BG);tableframe.grid(row=3,column=0,columnspan=3,sticky='nsew');tableframe.columnconfigure(0,weight=1);tableframe.rowconfigure(0,weight=1);self.table=ttk.Treeview(tableframe,columns=('path','result'),show='headings',height=4);self.table.heading('path',text='Input file');self.table.heading('result',text='Result');self.table.column('path',width=500);self.table.column('result',width=360);self.table.grid(row=0,column=0,sticky='nsew');scroll=ttk.Scrollbar(tableframe,orient='vertical',command=self.table.yview);scroll.grid(row=0,column=1,sticky='ns');self.table.configure(yscrollcommand=scroll.set);self.table.bind('<<TreeviewSelect>>',self.preview_selection);self.table.bind('<Double-1>',self.open_preview)
  previews=tk.Frame(imports,bg=BG);previews.grid(row=4,column=0,columnspan=3,sticky='ew',pady=(10,4));self.preview_labels=[]
  for col,title in enumerate(['Current game frame','Prepared replacement']):
   previews.columnconfigure(col,weight=1);tk.Label(previews,text=title,bg=BG,fg=MUTED).grid(row=0,column=col,sticky='w');label=tk.Label(previews,bg=PANEL,width=40,height=8);label.grid(row=1,column=col,sticky='ew',padx=5);self.preview_labels.append(label)
  self.details=tk.StringVar(value='Preparation checks fitting and compression without modifying game files.');tk.Label(imports,textvariable=self.details,bg=BG,fg=MUTED,wraplength=920,justify='left').grid(row=5,column=0,columnspan=3,sticky='ew',pady=7)
  restore=tk.Frame(imports,bg=BG);restore.grid(row=6,column=0,columnspan=3,sticky='ew');self.restore_button=ttk.Button(restore,text='Restore an import backup…',command=self.start_restore);self.restore_button.pack(side='left');ttk.Button(restore,text='Open Input',command=lambda:self.open_branch('Input')).pack(side='right');ttk.Button(restore,text='Open Output',command=lambda:self.open_branch('Output')).pack(side='right',padx=8)
  matching=tk.Frame(self.tabs,bg=BG,padx=12,pady=12);matching.columnconfigure(1,weight=1);matching.rowconfigure(4,weight=1);self.tabs.add(matching,text='Sort between projects')
  self.match_source=tk.StringVar();self.match_target=tk.StringVar();self.match_folder=None;self.match_report=None
  self.path_row(matching,0,'SOURCE PROJECT',self.match_source);self.path_row(matching,1,'TARGET PROJECT',self.match_target)
  tk.Label(matching,text='Match exported frame sequences across versions, then copy old art into the target Input layout.\nInserted frames are accounted for. Uncertain matches are skipped; edited Input files are preserved; unchanged reference copies can be replaced.',bg=BG,fg=MUTED,justify='left',wraplength=920).grid(row=2,column=0,columnspan=3,sticky='ew',pady=12)
  match_actions=tk.Frame(matching,bg=BG);match_actions.grid(row=3,column=0,columnspan=3,sticky='ew',pady=8)
  self.match_button=ttk.Button(match_actions,text='Match frames',command=self.start_match);self.match_button.pack(side='left')
  self.copy_button=ttk.Button(match_actions,text='Copy ready PNGs to target Input',style='Accent.TButton',command=self.start_copy,state='disabled');self.copy_button.pack(side='right')
  self.match_table=ttk.Treeview(matching,columns=('old','new','result'),show='headings',height=8)
  for column,title,width in [('old','Source frame',160),('new','Target frame',420),('result','Result',280)]:self.match_table.heading(column,text=title);self.match_table.column(column,width=width)
  self.match_table.grid(row=4,column=0,columnspan=3,sticky='nsew');match_scroll=ttk.Scrollbar(matching,orient='vertical',command=self.match_table.yview);match_scroll.grid(row=4,column=3,sticky='ns');self.match_table.configure(yscrollcommand=match_scroll.set)
  ttk.Button(matching,text='Open matching report',command=lambda:os.startfile(str(self.match_folder)) if self.match_folder else None).grid(row=5,column=0,sticky='w',pady=10)
  self.match_source.trace_add('write',self.invalidate_match);self.match_target.trace_add('write',self.invalidate_match)
  try:
   projects=sorted(Path(self.output.get()).glob('*/project.json'))
   sources=[];targets=[]
   for path in projects:
    m=json.loads(path.read_text(encoding='utf-8'))
    if m.get('exports'):(sources if 'depot_' in m.get('game','') else targets).append(path.parent)
   if sources:self.match_source.set(str(sources[-1]))
   if targets:self.match_target.set(str(targets[-1]))
  except (OSError,ValueError):pass
  bottom=tk.Frame(self,bg=BG);bottom.grid(row=3,column=0,sticky='ew',padx=24,pady=(12,18));bottom.columnconfigure(0,weight=1);self.status=tk.StringVar(value='Ready. Create a project or choose an existing project.');self.count=tk.StringVar();tk.Label(bottom,textvariable=self.status,bg=BG,fg=TEXT,anchor='w',wraplength=1000).grid(row=0,column=0,columnspan=3,sticky='ew');self.progress=ttk.Progressbar(bottom,maximum=100);self.progress.grid(row=1,column=0,columnspan=3,sticky='ew',pady=7);tk.Label(bottom,textvariable=self.count,bg=BG,fg=MUTED,anchor='w').grid(row=2,column=0,sticky='w');self.open_button=ttk.Button(bottom,text='Open project',command=self.open_output,state='disabled');self.open_button.grid(row=2,column=1,padx=8);self.stop_button=ttk.Button(bottom,text='Cancel',command=self.stop,state='disabled');self.stop_button.grid(row=2,column=2)
  self.controls=[self.sequence_button,self.match_button,self.tree_button,self.export_button,self.scan_button,self.prepare_button,self.restore_button]+self.fields;self.game.trace_add('write',self.invalidate);self.project.trace_add('write',self.invalidate);self.protocol('WM_DELETE_WINDOW',self.close);self.poll_after=self.after(100,self.poll)

 def invalidate_match(self,*args):
  self.match_folder=None;self.match_report=None;self.copy_button.state(['disabled'])
 def refresh_copy_button(self):
  ready=bool(self.match_folder and self.match_report and self.match_report.get('matches'))
  self.copy_button.state(['!disabled'] if ready and not self.busy else ['disabled'])
 def start_match(self):
  source=self.match_source.get();target=self.match_target.get();self.invalidate_match();self.status.set('Matching exported projects');self.launch('match',lambda:match_projects(source,target,self.report,self.cancel_event))
 def start_copy(self):
  if self.busy:return
  if not self.match_folder:
   self.status.set('Match the source and target projects before copying.');return
  self.status.set('Copying matched source PNGs into target Input');folder=self.match_folder;self.prepared=None;self.plan=None;self.copy_button.state(['disabled']);self.launch('copy',lambda:copy_matches(folder,self.report,self.cancel_event))
 def path_row(self,parent,row,label,var):
  tk.Label(parent,text=label,bg=BG,fg=MUTED,font=('Segoe UI',9,'bold')).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5);entry=ttk.Entry(parent,textvariable=var);entry.grid(row=row,column=1,sticky='ew',pady=5);button=ttk.Button(parent,text='Browse…',command=lambda:self.browse(var));button.grid(row=row,column=2,padx=(10,0),pady=5);self.fields.extend([entry,button])
 def invalidate(self,*args):
  if not self.busy:self.prepared=None;self.plan=None;self.apply_button.state(['disabled'])
 def browse(self,var):
  if self.busy:return
  p=filedialog.askdirectory(initialdir=var.get() if Path(var.get()).is_dir() else str(Path.home()))
  if p:
   var.set(p)
   if var is self.project:self.prepared=None;self.plan=None;self.apply_button.state(['disabled'])
 def select(self,value):
  if not self.busy:
   for n,v in self.vars.items():
    if 'disabled' not in self.checks[n].state():v.set(value)
 def scan(self):
  if self.busy:return
  try:
   found=available_characters(self.game.get())
   for n,c in self.checks.items():
    c.state(['!disabled'] if n in found else ['disabled'])
    if n not in found:self.vars[n].set(False)
   self.status.set(f'Found {len(found)} character entries.')
  except Exception as exc:messagebox.showerror('Cannot read game folder',str(exc))
 def launch(self,kind,work,cancellable=True):
  if self.busy:return
  self.busy=True;self.kind=kind;self.cancel_event.clear();self.progress['value']=0;self.count.set('');self.apply_button.state(['disabled']);self.copy_button.state(['disabled'])
  for c in self.controls:c.state(['disabled'])
  self.stop_button.state(['!disabled'] if cancellable else ['disabled'])
  def run():
   try:self.events.put((kind,work()))
   except Exception as exc:self.events.put(('error',str(exc) or repr(exc)))
  threading.Thread(target=run,daemon=True).start()
 def report(self,*args):self.events.put(('progress',args))
 def start_tree(self):
  game=self.game.get();output=self.output.get();self.prepared=None;self.plan=None;self.status.set('Creating the full empty Input tree');self.launch('tree',lambda:generate_input_tree(game,output,self.report,self.cancel_event))
 def start_export(self):
  selected=[n for n,v in self.vars.items() if v.get()];game=self.game.get();output=self.output.get()
  if not selected:messagebox.showerror('Choose characters','Select at least one character.');return
  self.prepared=None;self.plan=None;self.status.set('Creating mirrored project…');self.launch('export',lambda:export_project(game,output,selected,self.report,self.cancel_event))
 def check_input(self):
  if self.busy:return
  self.invalidate()
  try:
   found,unknown=scan_input(self.project.get());self.status.set(f'Input: {len(found):,} matching PNGs, {len(unknown):,} unrecognized paths. Empty folders are skipped.');self.table.delete(*self.table.get_children())
   for i,(_,path,entry) in enumerate(found):self.table.insert('',tk.END,iid=f'scan{i}',values=(path,'Ready to prepare' if entry['layer'] is not None else 'Composite: edit individual layers'))
   for i,path in enumerate(unknown):self.table.insert('',tk.END,iid=f'unknown{i}',values=(path,'Path does not match Output'))
  except Exception as exc:messagebox.showerror('Cannot scan Input',str(exc))
 def start_sequence(self):
  if self.busy:return
  try:
   project,_=project_info(self.project.get());groups=animations(project)
   if not groups:raise ValueError('This project has no editable animation routes. Export the character or generate an Input tree first.')
  except Exception as exc:messagebox.showerror('Choose a project',str(exc));return
  files=filedialog.askopenfilenames(title='Select animation PNGs (one frame or a numbered sequence)',filetypes=[('PNG images','*.png')])
  if not files:return
  self.sequence_dialog=SequenceDialog(self,project,files,groups)
 def import_sequence(self,project,files,animation,start,overwrite):
  self.invalidate();self.status.set('Staging animation PNGs into Input')
  self.launch('sequence',lambda:stage_sequence(project,files,animation,start,overwrite,self.report,self.cancel_event))
 def start_prepare(self):
  game=self.game.get();project=self.project.get();self.prepared=None;self.plan=None;self.status.set('Checking replacements…');self.launch('prepare',lambda:prepare_import(game,project,self.report,self.cancel_event))
 def start_apply(self):
  if self.busy or not self.plan or not self.prepared:return
  n=len(self.plan['patches']);warnings=sum(bool(p['warnings']) for p in self.plan['patches']);errors=len(self.plan['errors']);text=f'Apply {n} prepared replacements?\n\n{warnings} have fitting notes; {errors} files will be skipped. Review previews first.\n\nClose Skullgirls. Art archives will be backed up. Metadata, palettes, timing and hitboxes remain unchanged.'
  if messagebox.askokcancel('Apply reviewed replacements',text):
   prepared=self.prepared;self.launch('apply',lambda:apply_import(prepared,self.report),False)
 def start_restore(self):
  if self.busy:return
  initial=str(self.last_backup or (Path(self.project.get())/'Backups'));folder=filedialog.askdirectory(initialdir=initial if Path(initial).is_dir() else str(Path.home()),title='Choose a backup containing restore.json')
  if not folder:return
  try:
   r=json.loads((Path(folder)/'restore.json').read_text());text=f'Restore the art from this backup?\n\nThis undoes {r["frames"]} replacements in {r["game"]}.\n\nClose Skullgirls. Restore will refuse if newer changes are present.'
   if messagebox.askokcancel('Restore import',text):self.launch('restore',lambda:restore_import(folder,self.report),False)
  except Exception as exc:messagebox.showerror('Cannot restore backup',str(exc))
 def preview_selection(self,event=None):
  selection=self.table.selection()
  if not selection or not self.plan or not self.prepared:return
  if not selection[0].startswith('patch'):
   key=selection[0]
   if key.startswith('error'):r=self.plan['errors'][int(key[5:])];self.details.set(r['path']+' — '+r['error'])
   elif key.startswith('skip'):r=self.plan['skipped'][int(key[4:])];self.details.set(r['path']+' — '+r['reason'])
   for label in self.preview_labels:label.configure(image='',width=40,height=8)
   self.photos=[];return
  r=self.plan['patches'][int(selection[0][5:])];self.photos=[]
  for label,name in zip(self.preview_labels,[r['before'],r['after']]):
   with Image.open(self.prepared/name) as image:im=image.convert('RGBA')
   im.thumbnail((430,145),Image.Resampling.NEAREST);canvas=Image.new('RGBA',(440,150),(35,42,53,255));draw=ImageDraw.Draw(canvas)
   for y in range(0,150,16):
    for x in range(0,440,16):
     if (x//16+y//16)%2:draw.rectangle((x,y,x+15,y+15),fill=(43,51,63,255))
   canvas.alpha_composite(im,((440-im.width)//2,(150-im.height)//2));photo=ImageTk.PhotoImage(canvas.convert('RGB'));self.photos.append(photo);label.configure(image=photo,width=440,height=150)
  notes='; '.join(r['warnings']) or 'Original compression space preserved.';self.details.set(f'{NAMES[r["character"]]} · internal frame {r["frame"]} · {r["statistics"]["changed_pixels"]:,} changed pixels · {r["fit"]["mode"]}. {notes}')
 def stop(self):self.cancel_event.set();self.status.set('Stopping after the current frame…');self.stop_button.state(['disabled'])
 def open_preview(self,event=None):
  selection=self.table.selection()
  if selection and selection[0].startswith('patch') and self.plan and self.prepared:
   r=self.plan['patches'][int(selection[0][5:])];os.startfile(str(self.prepared/r['after']))
 def poll(self):
  try:
   while True:
    event,payload=self.events.get_nowait()
    if event=='progress':
     done,total,label=payload;self.status.set(label)
     if total:self.progress['value']=done/total*100;self.count.set(f'{done:,} / {total:,}')
    elif event=='tree':
     self.last_output,m=payload;self.project.set(str(self.last_output));self.finish();self.open_button.state(['!disabled']);self.status.set(f'{m["status"]}: empty Input tree for {len(m["characters"])} characters. No PNGs extracted.');self.progress['value']=100 if m['status']=='complete' else 0;self.tabs.select(1)
    elif event=='export':
     self.last_output,m=payload;self.project.set(str(self.last_output));self.finish();self.open_button.state(['!disabled']);frames=sum(x['exported'] for x in m['characters'].values());unmapped=sum(x['unmapped'] for x in m['characters'].values());self.status.set(f'{m["status"]}: {frames:,} frames exported. Input has empty matching folders.');self.count.set(f'{unmapped:,} frames in unmapped folders; {len(m["errors"]):,} export errors.');self.progress['value']=100 if m['status']=='complete' else self.progress['value']
    elif event=='match':
     self.match_folder,self.match_report=payload;self.finish();self.match_table.delete(*self.match_table.get_children())
     ready_pngs=sum(not c['identical_pixels'] for r in self.match_report['matches'] for c in r['copies']);identical_pngs=sum(c['identical_pixels'] for r in self.match_report['matches'] for c in r['copies'])
     for group,label in [('matches','Ready to copy'),('review','Review required'),('unmatched','Unmatched')]:
      for r in self.match_report[group]:
       targets=', '.join(c['target'] for c in r.get('copies',[]));self.match_table.insert('',tk.END,values=(f'{r["character"]} {r["source_frame"]}',targets or str(r.get('target_frame','')),('Identical pixels — no copy needed' if group=='matches' and all(c['identical_pixels'] for c in r['copies']) else label)+(' — '+r['reason'] if 'reason' in r else '')))
     self.copy_button.state(['!disabled'] if self.match_report['matches'] else ['disabled']);self.status.set(f'{ready_pngs:,} PNGs ready to copy; {identical_pngs:,} identical PNGs skipped; {len(self.match_report["review"]):,} uncertain frames. Nothing copied yet. Click Copy ready PNGs to target Input.');self.progress['value']=100
    elif event=='copy':
     target,result=payload;self.finish();self.project.set(str(target));self.tabs.select(1);self.status.set(f'Copied {len(result["copied"]):,} PNGs to target Input; {len(result["existing"]):,} existing edits preserved; {len(result.get("replaced_references",[])):,} unchanged references replaced; {result["unchanged"]:,} identical PNGs skipped. Prepare previews next.');self.progress['value']=100
    elif event=='sequence':
     target,result=payload;self.finish();self.project.set(str(target));self.check_input();self.status.set(f'Animation staged: {result["copied"]} PNGs; {result["backed_up"]} previous Input frames backed up; {result["unchanged"]} unchanged. Prepare previews next.');self.progress['value']=100
    elif event=='prepare':
     self.prepared,self.plan=payload;self.finish();self.table.delete(*self.table.get_children())
     for i,r in enumerate(self.plan['patches']):self.table.insert('',tk.END,iid=f'patch{i}',values=(r['path'],'Ready · '+('; '.join(r['warnings']) or 'fits original art slot')))
     for i,r in enumerate(self.plan['errors']):self.table.insert('',tk.END,iid=f'error{i}',values=(r['path'],'Skipped: '+r['error']))
     for i,r in enumerate(self.plan['skipped']):self.table.insert('',tk.END,iid=f'skip{i}',values=(r['path'],'Skipped: '+r['reason']))
     n=len(self.plan['patches']);self.apply_button.state(['!disabled'] if n and self.plan['status']=='prepared' else ['disabled']);self.status.set(f'{n} prepared; {len(self.plan["errors"])} errors; {len(self.plan["skipped"])} unchanged/duplicate files skipped.');self.progress['value']=100
     if n:self.table.selection_set('patch0');self.preview_selection()
    elif event=='apply':self.last_backup,r=payload;self.finish();self.prepared=None;self.plan=None;self.status.set(f'Installed {r["frames"]} replacements. Verified backup: {self.last_backup.name}');self.progress['value']=100
    elif event=='restore':self.finish();self.prepared=None;self.plan=None;self.status.set('Original art restored and verified.');self.progress['value']=100
    elif event=='error':
     self.finish();self.status.set('Operation stopped.')
     if self.plan and self.plan['status']=='prepared' and self.plan['patches']:self.apply_button.state(['!disabled'])
     messagebox.showerror('Sprite Workshop',payload)
  except queue.Empty:pass
  self.poll_after=self.after(100,self.poll)
 def finish(self):
  self.busy=False
  for c in self.controls:c.state(['!disabled'])
  self.stop_button.state(['disabled']);self.refresh_copy_button()
 def open_output(self):
  if self.last_output:os.startfile(str(self.last_output))
 def open_branch(self,branch):
  try:p,_=project_info(self.project.get());os.startfile(str(p/branch))
  except Exception as exc:messagebox.showerror('Choose a project',str(exc))
 def destroy(self):
  if getattr(self,'poll_after',None):
   try:self.after_cancel(self.poll_after)
   except tk.TclError:pass
  super().destroy()
 def close(self):
  if self.busy:
   if self.kind in ['export','tree','prepare','match','copy','sequence']:self.stop()
   self.after(200,self.close_when_idle)
  else:self.destroy()
 def close_when_idle(self):
  if self.busy:self.after(200,self.close_when_idle)
  else:self.destroy()

class SequenceDialog(tk.Toplevel):
 def __init__(self,app,project,files,groups):
  super().__init__(app);self.app=app;self.project=project;self.files=sorted(files,key=lambda f:natural_key(Path(f).name));self.groups=groups;self.title('Import animation sequence');self.geometry('950x540');self.configure(bg=BG);self.transient(app);self.grab_set();self.columnconfigure(1,weight=1);self.rowconfigure(4,weight=1)
  tk.Label(self,text=f'{len(files)} PNG(s), sorted by filename number. Sources stay unchanged.',bg=BG,fg=TEXT).grid(row=0,column=0,columnspan=2,sticky='w',padx=14,pady=12)
  tk.Label(self,text='Destination animation / layer',bg=BG,fg=TEXT).grid(row=1,column=0,padx=14,sticky='w')
  self.animation=tk.StringVar();self.animation_box=ttk.Combobox(self,textvariable=self.animation,values=list(groups),state='readonly',width=80);self.animation_box.grid(row=1,column=1,sticky='ew',padx=14,pady=5)
  tk.Label(self,text='First destination frame',bg=BG,fg=TEXT).grid(row=2,column=0,padx=14,sticky='w')
  self.start_box=ttk.Combobox(self,state='readonly');self.start_box.grid(row=2,column=1,sticky='ew',padx=14,pady=5)
  self.overwrite=tk.BooleanVar(value=False);ttk.Checkbutton(self,text='Replace existing Input frames (back up first)',variable=self.overwrite).grid(row=3,column=0,columnspan=2,sticky='w',padx=14,pady=8)
  self.table=ttk.Treeview(self,columns=('source','target'),show='headings');self.table.heading('source',text='Selected PNG');self.table.heading('target',text='Destination frame');self.table.column('source',width=260);self.table.column('target',width=600);self.table.grid(row=4,column=0,columnspan=2,sticky='nsew',padx=14)
  self.note=tk.StringVar();tk.Label(self,textvariable=self.note,bg=BG,fg=MUTED,wraplength=900,justify='left').grid(row=5,column=0,columnspan=2,sticky='w',padx=14,pady=8)
  self.copy_button=ttk.Button(self,text='Copy sequence to Input',command=self.submit);self.copy_button.grid(row=6,column=1,sticky='e',padx=14,pady=12)
  self.animation_box.bind('<<ComboboxSelected>>',self.select_animation);self.start_box.bind('<<ComboboxSelected>>',self.preview);self.overwrite.trace_add('write',self.preview)
  selected=next((key for key in groups if (project/'Input'/key).resolve()==Path(files[0]).parent.resolve()),next((key for key in groups if Path(files[0]).name in [Path(r).name for r,e in groups[key]]),next(iter(groups))))
  self.animation.set(selected);self.select_animation()
 def select_animation(self,event=None):
  entries=self.groups[self.animation.get()];names=[Path(r).name for r,e in entries];self.start_box['values']=names
  self.start_box.current(names.index(Path(self.files[0]).name) if Path(self.files[0]).name in names else 0);self.preview()
 def preview(self,*args):
  self.table.delete(*self.table.get_children());entries=self.groups[self.animation.get()];start=self.start_box.current()
  for source,(route,entry) in zip(self.files,entries[max(0,start):]):self.table.insert('',tk.END,values=(Path(source).name,Path(route).name))
  try:
   mapping=plan_sequence(self.project,self.files,self.animation.get(),start,self.overwrite.get());self.note.set(f'{len(mapping)} frames mapped consecutively. Check the starting frame and mapping before copying. Existing Input backups go into Sequence Imports.');self.copy_button.state(['!disabled'])
  except Exception as exc:self.note.set(str(exc));self.copy_button.state(['disabled'])
 def submit(self):
  try:plan_sequence(self.project,self.files,self.animation.get(),self.start_box.current(),self.overwrite.get())
  except Exception as exc:messagebox.showerror('Cannot stage animation',str(exc),parent=self);return
  self.app.import_sequence(self.project,self.files,self.animation.get(),self.start_box.current(),self.overwrite.get());self.destroy()

def main():
 if '--smoke-test' in sys.argv:
  app=App();app.withdraw();app.update_idletasks();assert len(app.vars)==19 and len(app.tabs.tabs())==3;app.destroy();Path(sys.argv[sys.argv.index('--smoke-test')+1]).write_text(json.dumps(dict(ui='passed',characters=19,tabs=['Export project','Import replacements','Sort between projects'])))
 elif '--self-test' in sys.argv:
  import test_workshop
  test_workshop.run(Path(sys.argv[sys.argv.index('--self-test')+1]))
 elif '--verify' in sys.argv:
  import verify
  verify.run(Path(sys.argv[sys.argv.index('--verify')+1]))
 else:App().mainloop()
