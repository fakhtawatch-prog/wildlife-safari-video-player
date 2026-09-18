import json, os, re, subprocess, tempfile
from pathlib import Path
import requests

INDEX_URL = os.environ['DRIVE_INDEX_URL']
MAX_FILES = int(os.getenv('MAX_FILES', '3'))
REPO = os.environ['GITHUB_REPOSITORY']
MANIFEST = Path('data/transfer-manifest.json')
INDEX = Path('data/wildlife-index.json')


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def list_files():
    r = requests.get(INDEX_URL, timeout=60)
    r.raise_for_status()
    data = r.json()
    if isinstance(data, dict) and 'files' in data:
        data = data['files']
    return [x for x in data if x.get('name', '').lower().endswith('.mp4')]


def timestamp(name):
    m = re.search(r'(\d{4}-\d{2}-\d{2})[_-](\d{2})-(\d{2})-(\d{2})', name)
    return f'{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}' if m else None


def duration(path):
    p = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True, text=True)
    try:
        return round(float(p.stdout.strip()), 3)
    except Exception:
        return None


def download_public_file(file):
    file_id = file['id']
    urls = [file.get('downloadUrl'), f'https://drive.usercontent.google.com/download?id={file_id}&export=download&confirm=t']
    last = None
    for url in urls:
        if not url:
            continue
        try:
            with requests.get(url, stream=True, timeout=180, allow_redirects=True) as r:
                r.raise_for_status()
                return r
        except Exception as exc:
            last = exc
    raise RuntimeError(f'Unable to download {file.get("name")}: {last}')


def main():
    manifest = load_json(MANIFEST, {'version': 1, 'files': {}})
    files = list_files()
    print(f'Found {len(files)} MP4 files')
    pending = [f for f in files if f.get('id') not in manifest['files']]
    print(f'{len(pending)} new MP4 files pending')

    for f in pending[:MAX_FILES]:
        name = f['name']
        ts = timestamp(name)
        if not ts:
            print(f'SKIP timestamp: {name}')
            continue
        day = ts[:10]
        tag = day
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / name
            print(f'Downloading {name}')
            with download_public_file(f) as response, path.open('wb') as out:
                for chunk in response.iter_content(1024 * 1024):
                    if chunk:
                        out.write(chunk)
            actual = path.stat().st_size
            expected = f.get('size')
            if expected and actual != int(expected):
                raise RuntimeError(f'Size mismatch for {name}: {actual} != {expected}')

            exists = subprocess.run(
                ['gh', 'release', 'view', tag, '--repo', REPO],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
            if not exists:
                subprocess.run([
                    'gh', 'release', 'create', tag, '--repo', REPO,
                    '--title', f'Wildlife {day}',
                    '--notes', f'Wildlife camera recordings for {day}.'
                ], check=True)

            subprocess.run(['gh', 'release', 'upload', tag, str(path), '--repo', REPO], check=True)
            d = duration(path)
            asset = f'https://github.com/{REPO}/releases/download/{tag}/{name}'
            manifest['files'][f['id']] = {
                'id': f['id'], 'name': name, 'size': actual,
                'modifiedTime': f.get('modifiedTime'), 'startTime': ts,
                'duration': d, 'releaseTag': tag, 'url': asset, 'verified': True
            }
            MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
            build_index(manifest)
            subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
            subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
            subprocess.run(['git', 'add', str(MANIFEST), str(INDEX)], check=True)
            subprocess.run(['git', 'commit', '-m', f'Index migrated recording {name}'], check=False)
            subprocess.run(['git', 'push'], check=True)


def build_index(manifest):
    days = {}
    for x in manifest.get('files', {}).values():
        if not x.get('verified') or not x.get('startTime'):
            continue
        days.setdefault(x['startTime'][:10], []).append({
            k: x[k] for k in ('name', 'startTime', 'duration', 'url')
        })
    for d in days:
        days[d].sort(key=lambda x: x['startTime'])
    INDEX.write_text(json.dumps({'version': 1, 'days': dict(sorted(days.items()))}, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
