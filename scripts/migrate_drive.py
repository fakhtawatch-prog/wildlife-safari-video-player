import json, os, re, subprocess, sys, tempfile
from datetime import datetime
from pathlib import Path
import requests

FOLDER_ID=os.environ['DRIVE_FOLDER_ID']
API_KEY=os.environ['DRIVE_API_KEY']
MAX_FILES=int(os.getenv('MAX_FILES','3'))
REPO=os.environ['GITHUB_REPOSITORY']
MANIFEST=Path('data/transfer-manifest.json')
INDEX=Path('data/wildlife-index.json')

def load_json(p, default):
    try:return json.loads(p.read_text())
    except Exception:return default

def list_files():
    out=[]; token=None
    while True:
        params={'key':API_KEY,'q':f"'{FOLDER_ID}' in parents and trashed=false",'pageSize':1000,'fields':'nextPageToken,files(id,name,size,mimeType,modifiedTime,createdTime)','orderBy':'name'}
        if token: params['pageToken']=token
        r=requests.get('https://www.googleapis.com/drive/v3/files',params=params,timeout=60); r.raise_for_status()
        data=r.json(); out += [x for x in data.get('files',[]) if x.get('mimeType')=='video/mp4' or x.get('name','').lower().endswith('.mp4')]
        token=data.get('nextPageToken')
        if not token:return out

def timestamp(name):
    m=re.search(r'(\d{4}-\d{2}-\d{2})[_-](\d{2})-(\d{2})-(\d{2})',name)
    if not m:return None
    return f'{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}'

def duration(path):
    p=subprocess.run(['ffprobe','-v','error','-show_entries','format=duration','-of','default=noprint_wrappers=1:nokey=1',str(path)],capture_output=True,text=True)
    try:return round(float(p.stdout.strip()),3)
    except:return None

def main():
    manifest=load_json(MANIFEST,{'version':1,'files':{}})
    files=list_files(); print(f'Found {len(files)} MP4 files')
    pending=[f for f in files if f['id'] not in manifest['files']]
    for f in pending[:MAX_FILES]:
        name=f['name']; ts=timestamp(name)
        if not ts:
            print(f'SKIP timestamp: {name}'); continue
        day=ts[:10]; tag=day
        with tempfile.TemporaryDirectory() as td:
            path=Path(td)/name
            print(f'Downloading {name}')
            url=f'https://www.googleapis.com/drive/v3/files/{f["id"]}'
            with requests.get(url,params={'alt':'media','key':API_KEY},stream=True,timeout=120) as r:
                r.raise_for_status()
                with path.open('wb') as out:
                    for chunk in r.iter_content(1024*1024):
                        if chunk: out.write(chunk)
            actual=path.stat().st_size
            if f.get('size') and actual != int(f['size']): raise RuntimeError(f'Size mismatch for {name}: {actual} != {f["size"]}')
            subprocess.run(['gh','release','view',tag,'--repo',REPO],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            exists=subprocess.run(['gh','release','view',tag,'--repo',REPO],capture_output=True).returncode==0
            if not exists:
                subprocess.run(['gh','release','create',tag,'--repo',REPO,'--title',f'Wildlife {day}','--notes',f'Wildlife camera recordings for {day}.'],check=True)
            subprocess.run(['gh','release','upload',tag,str(path),'--repo',REPO,'--clobber'],check=True)
            d=duration(path)
            asset=f'https://github.com/{REPO}/releases/download/{tag}/{name}'
            manifest['files'][f['id']]={'id':f['id'],'name':name,'size':actual,'modifiedTime':f.get('modifiedTime'),'startTime':ts,'duration':d,'releaseTag':tag,'url':asset,'verified':True}
            MANIFEST.parent.mkdir(exist_ok=True)
            MANIFEST.write_text(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n')
            build_index(manifest)
            subprocess.run(['git','config','user.name','github-actions[bot]'],check=True)
            subprocess.run(['git','config','user.email','41898282+github-actions[bot]@users.noreply.github.com'],check=True)
            subprocess.run(['git','add',str(MANIFEST),str(INDEX)],check=True)
            subprocess.run(['git','commit','-m',f'Index migrated recording {name}'],check=False)
            subprocess.run(['git','push'],check=True)

def build_index(manifest):
    days={}
    for x in manifest.get('files',{}).values():
        if not x.get('verified') or not x.get('startTime'):continue
        days.setdefault(x['startTime'][:10],[]).append({k:x[k] for k in ('name','startTime','duration','url')})
    for d in days:days[d].sort(key=lambda x:x['startTime'])
    INDEX.write_text(json.dumps({'version':1,'days':dict(sorted(days.items()))},indent=2,ensure_ascii=False)+'\n')

if __name__=='__main__':main()
