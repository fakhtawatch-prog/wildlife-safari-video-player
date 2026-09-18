import json, os, re, subprocess, tempfile
from pathlib import Path
import requests
import gdown

FOLDER_URL = os.environ.get(
    'DRIVE_FOLDER_URL',
    'https://drive.google.com/drive/folders/11Z1EHFmU9Qj64CpHgD6uM2MG-SLc9YTI?usp=drive_link'
)
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
    """List only top-level MP4s in the shared Drive folder.

    gdown uses Drive's embedded folder view and supports folders larger than
    the old 50-file limit. Subfolders are deliberately excluded by requiring
    a top-level path (no '/').
    """
    result = subprocess.run(
        ['gdown', FOLDER_URL, '--json', '--quiet'],
        capture_output=True, text=True, timeout=180
    )
    if result.returncode != 0:
        raise RuntimeError(
            'Google Drive folder listing failed. '
            f'exit={result.returncode}\nstdout={result.stdout[-2000:]}\nstderr={result.stderr[-4000:]}'
        )
    try:
        entries = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            'Google Drive folder listing did not return JSON. '
            f'stdout={result.stdout[-4000:]}\nstderr={result.stderr[-2000:]}'
        ) from exc

    files = []
    for entry in entries:
        name = entry.get('path', '')
        url = entry.get('url', '')
        # Ignore all subfolders and non-MP4 files.
        if '/' in name or not name.lower().endswith('.mp4'):
            continue
        m = re.search(r'[?&]id=([\w-]+)', url)
        if not m:
            continue
        files.append({'id': m.group(1), 'name': Path(name).name, 'downloadUrl': url})
    return files


def timestamp(name):
    m = re.search(r'(\d{4}-\d{2}-\d{2})[_-](\d{2})-(\d{2})-(\d{2})', name)
    return f'{m.group(1)}T{m.group(2)}:{m.group(3)}:{m.group(4)}' if m else None


def duration(path):
    p = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration',
         '-of', 'default=noprint_wrappers=1:nokey=1', str(path)],
        capture_output=True, text=True
    )
    try:
        return round(float(p.stdout.strip()), 3)
    except Exception:
        return None


def download_public_file(file, path):
    """Download a public Drive file with gdown, including large-file confirmation handling."""
    try:
        result = gdown.download(
            url=file['downloadUrl'],
            output=str(path),
            quiet=False,
            resume=True,
            use_cookies=False,
        )
        if not result:
            raise RuntimeError('gdown returned no output path')
    except Exception as exc:
        raise RuntimeError(f'Unable to download {file["name"]}: {exc}') from exc


def main():
    manifest = load_json(MANIFEST, {'version': 1, 'files': {}})
    files = list_files()
    print(f'Found {len(files)} top-level MP4 files in Drive')
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
            download_public_file(f, path)
            actual = path.stat().st_size
            print(f'Downloaded {name}: {actual} bytes')

            exists = subprocess.run(
                ['gh', 'release', 'view', tag, '--repo', REPO],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            ).returncode == 0
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
