import json, os, re, subprocess, tempfile
from pathlib import Path

import gdown
from gdown.download_folder import _GoogleDriveFile, _get_session, _parse_embedded_folder_view

FOLDER_URL = os.environ.get(
    'DRIVE_FOLDER_URL',
    'https://drive.google.com/drive/folders/11Z1EHFmU9Qj64CpHgD6uM2MG-SLc9YTI?usp=drive_link'
)
MAX_FILES = int(os.getenv('MAX_FILES', '10'))
REPO = os.environ['GITHUB_REPOSITORY']
MANIFEST = Path('data/transfer-manifest.json')
INDEX = Path('data/wildlife-index.json')


def load_json(path, default):
    try:
        return json.loads(path.read_text())
    except Exception:
        return default


def folder_id_from_url(url):
    m = re.search(r'/folders/([A-Za-z0-9_-]+)', url)
    if not m:
        raise RuntimeError(f'Could not extract Google Drive folder ID from {url}')
    return m.group(1)


def list_files():
    """List only top-level MP4s from the public Drive folder.

    This uses gdown's embedded-folder parser only for discovery. It does not
    recursively enter child folders, and it does not resolve download URLs
    until an individual MP4 is actually selected for migration.
    """
    folder_id = folder_id_from_url(FOLDER_URL)
    sess, _ = _get_session(
        proxy=None,
        use_cookies=False,
        user_agent=None,
        cookies_file=None,
    )
    try:
        result = _parse_embedded_folder_view(
            sess=sess,
            folder_id=folder_id,
            verify=True,
            timeout=30,
        )
    finally:
        sess.close()

    if not result:
        raise RuntimeError('Google Drive returned no folder contents')

    _folder_name, children = result
    files = []
    skipped = []
    for file_id, name, file_type in children:
        if file_type == _GoogleDriveFile.TYPE_FOLDER:
            skipped.append((name, 'folder'))
            continue
        if not name.lower().endswith('.mp4'):
            skipped.append((name, 'non-mp4'))
            continue
        files.append({
            'id': file_id,
            'name': Path(name).name,
            'downloadUrl': f'https://drive.google.com/uc?id={file_id}',
        })

    print(f'Found {len(files)} top-level MP4 files in Drive')
    print(f'Ignored {len(skipped)} folders/non-MP4 entries')
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
    """Download one public Drive file with gdown."""
    try:
        result = gdown.download(
            url=file['downloadUrl'],
            output=str(path),
            quiet=False,
            resume=True,
            use_cookies=False,
            timeout=60,
            retries=2,
        )
        if not result:
            raise RuntimeError('gdown returned no output path')
    except Exception as exc:
        raise RuntimeError(f'Unable to download {file["name"]}: {exc}') from exc


def main():
    manifest = load_json(MANIFEST, {'version': 1, 'files': {}})
    manifest.setdefault('files', {})
    files = list_files()
    pending = [f for f in files if f.get('id') not in manifest['files']]
    print(f'{len(pending)} new MP4 files pending')

    migrated = 0
    failed = 0
    for f in pending:
        if migrated >= MAX_FILES:
            break
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
            try:
                download_public_file(f, path)
                actual = path.stat().st_size
                if actual <= 0:
                    raise RuntimeError('downloaded file is empty')
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

                subprocess.run([
                    'gh', 'release', 'upload', tag, str(path), '--repo', REPO
                ], check=True)
                d = duration(path)
                asset = f'https://github.com/{REPO}/releases/download/{tag}/{name}'
                manifest['files'][f['id']] = {
                    'id': f['id'], 'name': name, 'size': actual,
                    'modifiedTime': None, 'startTime': ts,
                    'duration': d, 'releaseTag': tag, 'url': asset, 'verified': True
                }
                MANIFEST.write_text(
                    json.dumps(manifest, indent=2, ensure_ascii=False) + '\n'
                )
                build_index(manifest)
                migrated += 1
                print(f'MIGRATED {migrated}/{MAX_FILES}: {name}')
            except Exception as exc:
                failed += 1
                print(f'FAILED {name}: {exc}')
                print('Continuing to the next MP4 instead of aborting the whole batch.')

    if migrated or failed:
        subprocess.run(['git', 'config', 'user.name', 'github-actions[bot]'], check=True)
        subprocess.run(['git', 'config', 'user.email', '41898282+github-actions[bot]@users.noreply.github.com'], check=True)
        subprocess.run(['git', 'add', str(MANIFEST), str(INDEX)], check=True)
        subprocess.run(['git', 'commit', '-m', f'Migrate {migrated} wildlife recordings'], check=False)
        subprocess.run(['git', 'push'], check=True)

    print(f'Batch complete: migrated={migrated}, failed={failed}, requested={MAX_FILES}')


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
    INDEX.write_text(
        json.dumps({'version': 1, 'days': dict(sorted(days.items()))}, indent=2, ensure_ascii=False) + '\n'
    )


if __name__ == '__main__':
    main()
