# Wildlife Safari Video Player

A static GitHub Pages viewer for motion-triggered wildlife camera footage, with GitHub Releases used for MP4 storage and Google Drive used as temporary staging.

## Architecture

- **GitHub Pages**: static HTML/CSS/JavaScript viewer.
- **GitHub Releases**: MP4 release assets, organized by recording date.
- **Google Drive**: temporary source/staging folder.
- **GitHub Actions**: one-file-at-a-time migration from public Drive to Releases.
- **`data/wildlife-index.json`**: compact viewer metadata.
- **`data/transfer-manifest.json`**: restartable migration state.

## Current status

The repository contains the viewer shell, mock dataset, release migration code, Pages deployment workflow, chapter/music data stores, and transfer manifest. Real footage migration requires the two repository Actions secrets below.

## Google Drive migration

The supplied public folder is `11Z1EHFmU9Qj64CpHgD6uM2MG-SLc9YTI`.

The migration uses the Google Drive REST API because a public folder URL by itself is not a reliable enumeration interface for hundreds of files. The workflow lists the folder with pagination, downloads one MP4 at a time, verifies its byte count, creates/uses a date release, uploads the asset, measures duration with `ffprobe`, and commits the updated manifest/index. It never deletes Drive files.

### Required GitHub Actions secrets

1. `DRIVE_FOLDER_ID` — set to `11Z1EHFmU9Qj64CpHgD6uM2MG-SLc9YTI`.
2. `DRIVE_API_KEY` — a Google Cloud API key restricted to the Google Drive API.

Do not commit the API key to the repository or put it in frontend JavaScript.

### Creating the API key

1. Open Google Cloud Console and create/select a Cloud project.
2. Go to **APIs & Services → Library**.
3. Enable **Google Drive API**.
4. Go to **APIs & Services → Credentials**.
5. Choose **Create credentials → API key**.
6. Restrict the key to the **Google Drive API**.
7. Copy the key.
8. In this GitHub repository open **Settings → Secrets and variables → Actions → New repository secret**.
9. Create `DRIVE_API_KEY` and paste the key into the secret value.
10. Create `DRIVE_FOLDER_ID` with value `11Z1EHFmU9Qj64CpHgD6uM2MG-SLc9YTI`.

The API key is only used inside the GitHub Actions runner. Google recommends API-key restrictions for security.

### Run migration

Open **Actions → Migrate wildlife footage → Run workflow**. Start with `max_files=3` to validate the pipeline. Then use larger batches. GitHub-hosted jobs have a maximum execution time of 6 hours, so batching is intentional.

The workflow resumes by checking `data/transfer-manifest.json`; already verified Drive file IDs are skipped.

## GitHub Pages

The repository includes `.github/workflows/pages.yml` using GitHub's Pages deployment action. If Pages has not yet been enabled for the repository, open **Settings → Pages** and choose the GitHub Actions deployment source. After the first successful deployment the viewer will be available at:

`https://fakhtawatch-prog.github.io/wildlife-safari-video-player/`

## Viewer

The viewer supports date selection, a 24-hour timeline, activity zoom, variable-duration recordings, previous/next navigation, automatic next-clip playback, fullscreen, keyboard controls, video volume, music controls, and chapter data storage. The initial index is a mock dataset so the UI can be exercised before the real migration.

## Safety

The migration process does not delete Drive files. Cleanup is intentionally a separate future operation and should only act on manifest entries whose corresponding GitHub Release assets have been verified.

## Filename parsing

The canonical timestamp parser uses `YYYY-MM-DD_HH-MM-SS` within the filename. For example `2_2026-09-15_12-38-45_076.mp4` becomes `2026-09-15T12:38:45` while preserving the original filename.
