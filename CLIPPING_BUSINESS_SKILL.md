# Clip Arena: Clipping Business Operating Manual

This file is the complete set of instructions for running the clipping business. The daily Claude task follows it from top to bottom. It must not depend on anything said in an earlier conversation: everything needed is here, in `config/`, in `data/` and in the tracker sheet.

## 1. What the business does

We cut short vertical clips from long creator videos, for paid clipping campaigns that have given permission to use that creator's content. We post them to our own accounts and submit the links to the campaign, which pays per 1,000 views.

- YouTube Shorts: **@cliparenahq-26** (ClipArena)
- Instagram Reels: **@minicraft.hq**
- Campaign platform: **Content Rewards** (the owner's existing account; never create another one)

## 2. How the system is built (all free)

| Part | Where it runs | What it does |
|---|---|---|
| `engine/scan.py` (workflow `scan`) | GitHub Actions, daily 17:00 IST | Finds new approved source videos and scores every second for clip-worthy moments using live-chat replay, audio loudness spikes and hype words in YouTube's captions. Writes `data/candidates/<campaign>/<video_id>.json`. Downloads only captions, chat and a low-bitrate audio track. |
| `engine/render.py` (workflow `render`) | GitHub Actions, on every new `requests/*.json` | Downloads only the chosen minutes, transcribes them with Whisper (`small.en`, local, free), and renders 1080x1920 MP4s with a hook, word-timed subtitles, the creator tag and the call to action. Publishes MP4, cover JPG and SRT as a GitHub release. Writes `data/rendered/<request_id>.json`. |
| Daily Claude task | Claude cloud, about 20:40 IST | Picks the best moments, writes hooks and captions, requests renders, checks the results, copies clips to Google Drive, posts through vidIQ, updates the tracker and reports to the owner. |
| vidIQ connector | vidIQ | Imports a clip from its public release link and posts it to YouTube and Instagram. Free for these platforms. **Never use vidIQ tools that cost credits** (clip generation, compose, edit, transcripts, search). |
| Windsor.ai connector | Windsor.ai | Reads post views and audience data. Read-only use. |
| Tracker sheet | Claude Sheets: see `config/operations.yaml` | Campaigns, Clips, Publishing, Submissions, Earnings, Errors. |
| GitHub Releases | repo Releases page | The permanent copy of every finished clip (MP4, cover, SRT). Google Drive can't take video uploads from the Claude cloud, so Drive is only for files the owner adds by hand. |

The Claude cloud workspace cannot reach YouTube, Google Drive downloads or Hugging Face. That is why all video work happens on GitHub Actions. The workspace can reach GitHub, including release downloads.

## 3. Money rules (mandatory)

- No purchases of any kind: no API credits, subscriptions, trials, storage, VPS or paid plans. Never enter payment details.
- No vidIQ credit spending (`limits.vidiq_credits_allowed_per_day: 0`). Check each vidIQ tool's stated cost before calling it; only 0-credit tools are allowed.
- If a step needs payment, stop that step, log it in Errors, and tell the owner. Never switch to a paid service silently.

## 4. Campaigns

### 4.1 Discovery (each run, read-only)
1. Search the web for new clipping campaigns, gaming first: queries like `Content Rewards gaming clipping campaign`, `Content Rewards GTA 6 campaign`, and Content Rewards' own articles (contentrewards.com/articles/...). Campaign pages need a login, so the articles and the owner are the main sources.
2. For each campaign record: name, run by, rate per 1K views, min and max payout per clip, budget and amount used, platforms, source content, required captions/hashtags/audio, country limits, application needed, deadline, link, date checked.
3. Add new ones to the **Campaigns** tab with Verdict `Possible` or `Skip`. Never mark a campaign approved yourself.

### 4.2 Evaluation: reject a campaign when
- the source content is not clearly authorized, or commercial use is unclear
- it is closed, paused, or its budget is used up
- payout conditions are unclear
- India-based clippers are excluded
- it requires paying to join
- it needs a platform we don't have (we have YouTube Shorts and Instagram Reels; no TikTok)
- it needs a binding contract, exclusivity or other legal commitment (ask the owner)

Rank the rest by: rate per 1K, max per clip, remaining budget, fit with our two accounts, how much good source material exists, and how hard the audience rules are for us.

### 4.3 Approval
A campaign is processed only when it is in `config/campaigns.yaml` with `status: approved`. Only the owner approves. When the owner approves a new one, add it to the config with its full rules and commit.

### 4.4 Current approved campaign: TOMO GTA VI Clipping (Clipping Nation)
- $1.50 per 1K views, paid from 2,333 views, max $150 per clip, $1,000 budget.
- Source: Tomo's GTA VI YouTube livestreams (main) and GTA VI videos, youtube.com/@Tomovids. Clips must feature Tomo.
- Every clip: mention Tomo, tell viewers to "Subscribe to Tomo on YouTube" (on screen), mention @Tomovids, use #tomovids and #gta6.
- English only. Captions readable without sound. Likes visible. Keep each clip live 30 days. No more than 5 near-identical posts.
- No AI-generated content or thumbnails: real footage only, cover is a real frame, no AI voice or images.
- No clickbait, no fake context, never show Tomo in a negative light. No low-effort clips or plain screen recordings.
- At least 40% of viewers from the USA, UK, Canada or Australia; after 2,333 views the owner sends an audience-country screenshot to the Clipping Nation Discord.
- Each link must be submitted within 30 minutes of posting. Submission is a manual step by the owner (section 9).

### 4.5 Current approved campaign: KreekCraft GTA 6 Clipping (ClipLaunch)
- $1 per 1K views, max $300 per clip, $6,824.60 budget. Campaign: https://contentrewards.com/c/campaigns/2eaa14fb-6927-4136-897e-b096e0d907d6
- Source: only KreekCraft's official GTA 6 livestreams and replays (YouTube @Kreek streams; Twitch is allowed but not scanned automatically yet).
- **The official logo overlay (`assets/overlays/kreekcraft.png`) must be visible for the whole clip.** render.py adds it automatically; check it in every render.
- Caption must include "Watch KreekCraft on YouTube and Twitch" and **#GTA6 #KreekCraft #GrandTheftAutoVI**. **No links or URLs in the caption.**
- Prioritize KreekCraft's reactions and personality. No fake reactions, fabricated context or misleading titles.
- 40% Tier 1 audience, engagement rate at least 0.8%, likes visible, keep 30 days, max 5 near-identical posts, new accounts need warm-up.

### 4.6 Several campaigns at once
Each campaign has its own block in `config/campaigns.yaml` (sources, clip lengths, packaging, rules). Always take caption text, hashtags, overlay, CTA and link rules from the clip's own campaign, never from another one. Share the daily limit of 2 clips across all campaigns; prefer the campaign with the better moment that day, and alternate when they're equal.

## 5. Trend research
Each run, spend at most a few free web searches on what's happening in gaming: GTA VI news, new features players are reacting to, what clips are getting attention. Use it to prefer moments on topics people are searching for right now (a new car, a mission, a glitch everyone is talking about). Note the evidence and source links in the run report. Never claim a trend without a source. Don't keep choosing the same topic just because it worked yesterday.

## 6. Sources
- Only process sources of an approved campaign, matching its `source` rules. Unknown permission = do not process.
- Never bypass DRM, paywalls, members-only or private videos.
- `state/processed_sources.json` records every scanned source; a source that failed 3 times is skipped until someone looks at it.
- To scan a specific video now: run the `scan` workflow manually with `video` set, or ask the owner to.

## 7. Picking moments (the daily task's judgement)
Open the newest `data/candidates/<campaign>/*.json` files that still have unused candidates. For each candidate, read `transcript`, `context_before`, `chat_sample` and `signals_at_peak`. The full timestamped transcript is in `data/transcripts/<campaign>/<video_id>.txt`: search it too (reactions like "oh my god", "no way", "what", laughter, screaming, first looks at new places or cars), because the scores miss moments. Lines with many `>>` speaker changes are usually story cutscenes: skip those.

Choose a candidate when:
- there is one clear funny, chaotic, surprising or first-reaction moment
- it makes sense in the first 2 seconds, with little setup needed
- Tomo is the focus and comes across well
- the speech is English

Reject when: the moment needs long context, it's dead air or a loading screen, it's negative about Tomo, it's another creator's content, or it's near-identical to something already posted. The scores find candidates; they do not decide alone. `visual_analysis` is false: confirm the visuals when checking the render (section 8.3).

Adjust `start`/`end` if the transcript shows the moment starts earlier or the punchline lands later (keep 20–45 s). Pick at most `max_clips_per_day` (2). If nothing is good enough, post nothing and say why.

## 8. Making clips

### 8.1 Request a render
Write `requests/<YYYY-MM-DD>-<NN>.json`:
```json
{"request_id": "2026-11-19-01", "campaign": "tomo_gta6",
 "clips": [{"clip_id": "tomo_<videoId>_<startSeconds>", "video_id": "<videoId>",
            "start": 1234.0, "end": 1266.5,
            "hook": "Tomo's first police chase in GTA 6", "layout": "blur"}]}
```
Commit and push it; the `render` workflow starts automatically. Poll `git pull` every minute (up to 40 minutes) for `data/rendered/<request_id>.json`.

### 8.2 Editing standard (built into render.py)
- 1080x1920, 30 fps, H.264 + AAC, loudness -14 LUFS, 20–45 s.
- `blur` layout: the full gameplay frame across the middle on a blurred copy of itself. Nothing cropped, nothing stretched. Use `zoom` (middle 4:3) only when the action is in the centre and nothing important is at the edges.
- Hook text at the top for the first ~3.5 s; then the campaign's `tag_text` (if any); the last ~3 s show the campaign's `cta_lines`.
- Campaigns with an `overlay` get that logo above the gameplay for the entire clip (`qc.overlay_present` must be true).
- Subtitles come only from Whisper on the clip's real audio, 1–3 words at a time, below the gameplay. Never invent dialogue.
- No music is added. The original audio is kept.

**Hooks:** true to what happens, under 60 characters, no clickbait, no ALL CAPS shouting, never negative about Tomo. Make each hook different, even for clips from the same stream.

### 8.3 Check every render before it goes anywhere
1. `qc.pass` must be true. Read `qc.problems`.
2. Download the MP4 from `files.video` and pull 3 frames (about 1 s, the middle, 2 s before the end). Look at them: hook readable, gameplay visible, subtitles not covering the action, CTA visible at the end.
3. Read the `transcript`: it must match the moment you picked and be English.
4. If anything is wrong, don't post. Fix the request (new times, layout or hook) and render again once, or skip the clip.

## 9. Packaging, posting and submitting

### 9.1 Text for each clip
- **YouTube Shorts title** (under 70 characters): what happens, plus `#tomovids #gta6`.
- **YouTube description**: one line about the moment; the campaign's `caption_required_text`; the source link only if `caption_links_allowed` is true; all `required_hashtags` plus 1–3 from `rotating_hashtags`, varied between posts.
- **Instagram caption**: 1–2 natural lines; the campaign's `caption_required_text`; the same hashtag and link rules.
- Example (Tomo): "Tomo's first minutes in GTA 6 did not go to plan. Subscribe to Tomo on YouTube (@Tomovids) #tomovids #gta6 #gaming"
- Example (KreekCraft): "KreekCraft vs the Vice City police. Watch KreekCraft on YouTube and Twitch! #GTA6 #KreekCraft #GrandTheftAutoVI"
- No keyword stuffing, no repeated captions, no misleading claims.

### 9.2 Publishing through vidIQ (0 credits)
1. `vidiq_social_account_list`: both accounts must show `canPublish: true`. If not, log it and ask the owner to reconnect; don't post.
2. `vidiq_video_upload` with `url` = the release link of the MP4 → `uploadId`.
3. `vidiq_social_post_draft_create` with the shared media, the YouTube destination (title, description, `privacyStatus` from config) and the Instagram destination (caption).
4. **While `publishing.auto_publish` is false:** do NOT publish. Send the owner the clip, cover, title and captions for review and stop.
5. **When `auto_publish` is true** (owner approved the first clip and the workflow): publish with `vidiq_social_post_publish`, then read `vidiq_social_post_status` until each destination reports its real URL. Only call a post "published" when a real URL is returned. If the result is uncertain, check status; never post again blindly (duplicates).
6. Never post from an unapproved campaign or source. Max 2 clips per day.

### 9.3 Submitting to the campaign (manual, owner)
Right after posting, add a row to **Submissions**: post URL, platform, campaign link, posted time, deadline (posted + 30 min), status `To submit`. Send the owner a short message with the URLs to submit now. Never mark a submission done; only the owner changes it.

## 10. Tracking (tracker sheet)
Tabs: **Campaigns**, **Clips**, **Publishing**, **Submissions**, **Earnings**, **Errors**, plus **Posting Options** and **Next Steps** for setup notes. Read before writing, never overwrite the owner's edits, append rows.
- Clips: clip_id, date, hook, status, QC result, source link with time, start, end, layout, release link, notes.
- Publishing: clip_id, platform, account, post URL, title/caption, posted at, status.
- Earnings: clip_id, platform, views, approved views, estimated reward ($1.50 × views/1000, capped at $150, 0 below 2,333), confirmed reward, payout status.
- Errors: date, step, what failed, attempts, manual action needed.
The repo (`data/`, `state/`) keeps the engine's own history, so new runs can see what was already done.

## 11. Analytics and learning
- Each run, read views for posts from the last 30 days with Windsor.ai (`get_data` for `youtube` and `instagram`; call `get_fields` first). Update the Earnings tab.
- When a clip passes 2,333 views, remind the owner to send the audience-country screenshot to the Clipping Nation Discord.
- Every Sunday, compare which moment types, hooks and posting times did best, and write 3 short lessons in the report. Use them when picking moments.

## 12. Errors and recovery
- Temporary failures (network, a workflow run failing once): retry at most twice.
- `YOUTUBE_BOT_CHECK` in a scan or render: stop video work, log it, and ask the owner to add a `YT_COOKIES` secret (cookies.txt exported from a browser signed in to YouTube) in the repo's Settings → Secrets → Actions.
- Expired connector sign-in (vidIQ, Windsor, Drive): log it and ask the owner to reconnect. Don't retry in a loop.
- Campaign closed or budget used up: set its config status to `paused`, log it, tell the owner.
- Never retry anything that costs credits. Never buy a replacement service.
- Keep unfinished work: requests and renders stay in the repo; the next run continues from them.
- Only contact the owner when they really need to act, plus the daily report.

## 13. The daily run (one scheduled task, about 20:40 IST)
1. Clone `Vgauta/clip-arena-engine`, read this file and `config/`.
2. Check connectors: vidIQ accounts can publish, Sheets and Drive reachable.
3. Campaign check (section 4.1) and quick trend check (section 5).
4. Check the `scan` workflow ran today (new commits in `data/candidates` or `state/`); note failures.
5. Pick up to 2 moments (section 7). If none, skip to step 10.
6. Write and push the render request (8.1); wait for results.
7. Check each render (8.3).
8. Add each passing clip to the Clips tab with its release link (the release is the stored copy).
9. Package and post, or send for review while `auto_publish` is false (section 9). Add Publishing and Submissions rows.
10. Update views and earnings (section 11).
11. Send the owner a short report: what was posted (with real URLs), what needs submitting now, views and estimated earnings, errors, and anything the owner must do.
