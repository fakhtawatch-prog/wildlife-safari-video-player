# Wildlife Safari Video Player

A static GitHub Pages viewer for motion-triggered wildlife camera footage, with GitHub Releases used for MP4 storage and Google Drive used as temporary staging.

## Architecture

- **GitHub Pages**: static HTML/CSS/JavaScript viewer.
- **GitHub Releases**: MP4 release assets, organized by recording date.
- **Google Drive**: temporary source/staging folder.
- **GitHub Actions**: one-file-at-a-time migration from public Drive to Releases.
- **`data/wildlife-index.json`**: compact viewer metadata.

## Current status

The repository contains the working viewer, mock dataset, and migration workflow. The workflow deliberately requires an explicit GitHub Actions secret for the public Drive folder ID/API key before it can migrate real footage.

## Local / Pages viewer

Open `index.html` locally or enable GitHub Pages for the `main` branch and root directory.

The viewer starts in mock mode using `data/wildlife-index.json`. It demonstrates variable durations, daily timelines, activity zoom, chapters, keyboard controls, fullscreen, and music controls.

## Google Drive migration setup

The migration workflow is `.github/workflows/migrate-drive.yml`.

Required repository Actions secrets:

- `DRIVE_API_KEY`: Google Drive API key permitted to read public Drive files.
- `DRIVE_FOLDER_ID`: `11Z1EHFmU9Qj64CpHgD6uM2MG-SLc9YTI` (the supplied wildlife folder).

The folder must be publicly readable as specified by the project. The workflow lists MP4s through the Drive API, streams one file at a time to the runner, uploads it to a date-specific GitHub Release with `gh release upload`, verifies the asset size, and records migration state.

**Safety:** the workflow does not delete Drive files. Cleanup is intentionally a separate manual workflow and is only allowed for manifest entries already verified against a GitHub Release asset.

### Google Drive API key

The Drive API must be enabled for the Google Cloud project that owns the API key. Restrict the key to the Drive API where practical. Do not put the key in the repository or frontend.

### First migration test

Run the migration workflow manually with `max_files=3`. Confirm the resulting release assets and `data/transfer-manifest.json`. Then increase the batch size. The workflow is designed to be restartable and skips an asset if the verified manifest already matches its source size.

## GitHub Pages

Repository Settings → Pages → Deploy from branch → `main` / `/ (root)`.

The site URL will be:

`https://fakhtawatch-prog.github.io/wildlife-safari-video-player/`

## Important GitHub release constraint

GitHub release assets have platform-specific per-asset limits. The migration workflow checks the source size before upload and reports oversized files rather than silently corrupting or skipping them. The viewer architecture keeps videos outside the Git tree and uses release-asset URLs.

## Filename parsing

The canonical timestamp parser uses:

`YYYY-MM-DD_HH-MM-SS`

For example `2_2026-09-15_12-38-45_076.mp4` becomes `2026-09-15T12:38:45` while preserving the original filename.
