# clip-arena-engine

Free, cloud-run clipping pipeline for approved clipping campaigns. GitHub Actions finds moments and renders vertical clips; a daily Claude task picks moments, checks the renders and posts them through vidIQ.

- **How it works and how to run it:** [CLIPPING_BUSINESS_SKILL.md](CLIPPING_BUSINESS_SKILL.md)
- **Campaigns and their rules:** [config/campaigns.yaml](config/campaigns.yaml)
- **Accounts, storage and posting settings:** [config/operations.yaml](config/operations.yaml)

## Run by hand
- **Scan a video now:** Actions → `scan` → Run workflow, set `video` to a YouTube link.
- **Render clips:** add a file to `requests/` (format in the manual, section 8.1). The `render` workflow runs on push.
- **Finished clips:** the repo's Releases page, one release per request.

## If YouTube blocks downloads
Export `cookies.txt` from a browser signed in to YouTube and save its contents as the repository secret `YT_COOKIES` (Settings → Secrets and variables → Actions). The workflows pick it up automatically.

## Local test
```
pip install -r requirements.txt
python -m engine.scan --campaign tomo_gta6 --video <youtube link>
python -m engine.render requests/<file>.json
```

Clips use footage only from sources the campaign authorizes. Credit goes to the original creator in every clip and caption.
