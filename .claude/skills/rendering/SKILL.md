---
name: rendering
description: That 1 Painter social/SEO rendering skill — build on-brand before/after reveal reels and clips from job footage. Use when asked to "make a reveal from [job name]", "clip [talking video]", batch reveals, or score/QA content against the brand rubric.
---

# That 1 Painter — Rendering Skill

Automated, on-brand content generation for That 1 Painter (Oregon). Two
engines, one brand standard, one QA rubric. Proven end-to-end on job #319
(Scott Kristensen, Hillsboro): scanner ranked the job → candidates narrowed
frames → Claude vision picked the matched before/after → assembly rendered
on-brand with a real Hillsboro CTA from CompanyCam.

## The two engines

| Engine | For | Entry point |
| ------ | --- | ----------- |
| OpusClip auto-loop | Talking-head / UGC / testimonials | `run_clip_job` (Drive → YouTube → on-brand clip) |
| Reveal assembly | Before/after job footage | `reveal_builder` + `auto_pair` |

Backbone (all live): scanner over 362 job folders · YouTube bridge · brand
template · QA rubric.

**Where the tools run (production = standalone, no laptop):**
- **Orchestrator** — a Claude cloud session (hourly routine "T1P Render
  Queue Drain"): judgment only — vision pair-pick, hook, copy pack, QA,
  dashboard writes.
- **Worker** — Render.com `t1p-render-worker` (srv-db5requ7bikc73dq8f9g,
  https://t1p-render-worker.onrender.com), Docker: ffmpeg engines from
  this repo. Job kick: the orchestrator sets env var `RENDER_JOB` via the
  Render connector (direct HTTPS to *.onrender.com is egress-blocked in
  cloud sessions); callers with real egress may instead POST /render with
  header `X-T1P-Signature: hex(hmac_sha256(RENDER_SHARED_SECRET, body))`.
  Job JSON: `{id, engine: reveal|preview, city, hook?, color?, colorHex?,
  formats?, reviews?, photos: {before_url, after_url} | {photo_url}}`.
  Results: Postgres `t1p-render-jobs` (dpg-db5reaks728c738povmg-a), table
  `render_jobs(id, payload, status, files, log, …)`, read back with
  `query_render_postgres`; output files at the worker's public /files URLs.
- **Env vars (names only, never values):** `GEMINI_API_KEY`,
  `RENDER_SHARED_SECRET`, `DATABASE_URL`, `PUBLIC_BASE_URL`,
  `MOTION_BUDGET_USD_MONTH`, `BIRDEYE_API_KEY` (live reviews, Phase 3),
  GBP / YouTube / GHL credentials (Phase 5).
- `render_core/` is shared by every engine: `brand.json` (single brand
  source), `palettes.json` (single palette source — Studio presets +
  Chip 3.0 PNW palettes), `color_engine.py` (`recolor(photo, palette_id,
  surfaces)` — the one recolor; always stamps the "Color concept"
  disclosure).
- **Status flow:** Queued → Rendering → Needs approval → Approved |
  Changes requested → Posted (approver default Juan Castillo; "Changes
  requested" re-queues with the note). Nothing posts without a human yes.
- **copy.json / copyPack schema:** caption_ig, caption_fb,
  caption_linkedin, gbp_post (≤1,500 chars + CTA button suggestion),
  alt_text, keywords, hashtags (max 5, local first).
- **Engine options:** Reveal · Generative reveal (Veo 3.1, Phase 6) ·
  AI Color Preview · Clip (OpusClip bridge).
- **Extra QA checks (with the rubric):** hook burned in 0–1.5s · live
  review count (Birdeye/GBP; cached 351 + flag if unreachable) · licensed
  or original audio only (assets/music/licensed/) · "Color concept" label
  on every AI preview · CTA card has city + CCB #249983.
- **Trigger phrases:** "make a reveal from [job]" · "run the render
  queue" · "approve renders" · "post approved renders" · "render
  performance report".

Local dev only: the original content-factory box (scanner, `auto_pair`,
OpusClip `run_clip_job`) at `http://127.0.0.1:8787` — never a production
dependency. The portable builder:

```bash
python3 tools/reveal_builder.py \
  --before before.jpg --after after.jpg --city Hillsboro \
  --music track.mp3 [--logo logo.png] [--out reveal.mp4]
```

It produces the full v2 render plus the v3 upgrades: Ken Burns motion,
swipe (wipeleft) transition, `--hook` burn-in for the first 1.5s,
blue-gradient chips, auto-picked licensed music, and the navy CTA/proof
card. The vision-judgment and QA steps of this playbook apply wherever it
runs.

## Reveal pipeline (before/after)

1. **Scan & rank** — scanner ranks job folders for reveal potential.
2. **Narrow frames** — `auto_pair` produces candidate before/after frames.
   (Open item: wire `auto_pair.candidates()` so the shortlist is handed over
   automatically each run.)
3. **Vision judgment** — the one un-automatable step. Claude visually picks
   the matched before/after pair (same angle, same framing, real
   transformation). If a composite is supplied, split it. Prefer dramatic
   transformations (faded → bold recolor) over subtle ones (trim + refresh);
   subtle jobs work but pop less.
4. **Assemble** — `reveal_builder` renders: BEFORE beat → AFTER beat → CTA
   card, to the brand standard below.
5. **QA** — score against the rubric before shipping.

## Brand standard (v2 — all five upgrades are mandatory)

- **Format:** 1080×1920 (9:16 vertical), ~10–14 s, ends on CTA/proof card.
- **Motion:** Ken Burns (slow zoom/pan) on every still beat — never static.
  Use real video B-roll when available.
- **Music:** always a music bed (AAC). Never ship silent.
- **Labels:** BLUE "Before" / "After" chips matching the logo gradient —
  never navy/orange. Labels animate in (fade/slide/scale), not static.
- **Logo:** persistent brand logo; van/brand outro where footage allows.
- **CTA/proof close (the automated edge — never drop it):**
  `FREE ESTIMATE · [City], OR · 351 FIVE-STAR REVIEWS · CCB #249983`
  Geo-anchor to the job's real city (from CompanyCam). Refresh the review
  count at build time if a live source is available.
- Static graphics variant: navy swirl-texture header with
  "THAT 1 PAINTER · OREGON", stacked before/after, blue rounded chips.
- "LinkedIn" versions are caption/copy variants of the same 9:16 render, not
  a format change.

## QA rubric ($100M / Hormozi-weighted)

| Dimension | Weight | What ship-quality looks like |
| --------- | ------ | ---------------------------- |
| Hook / first 1.5 s | 25 | Motion + a bold hook line immediately |
| Retention | 20 | Motion + music carry the middle |
| Payoff | 15 | The transformation reads instantly |
| CTA & local | 15 | One obvious geo-anchored free-estimate ask |
| Visual/Audio | 15 | Music bed, real footage, clean render |
| Brand/Proof/Compliance | 10 | Logo, review count, CCB license number |

Score before posting. ~63–67 = Major Rewrite; close the gaps and re-render
rather than shipping. The historical failure modes to check first: hand-made
reels ending with **no CTA/city/proof**, and automated renders shipping
**static/silent** — they fail on opposite dimensions.

## Open polish / roadmap

- Swipe transition between the before and after beats.
- Auto-wire `auto_pair.candidates()` shortlist handoff.
- Batch mode: pick the top 5 jobs with clean before/afters, build all 5
  reveals for approval in one run.
- Posting: route approved clips to GHL/social on a schedule.

## Invocation examples

- "make a reveal from [job name]" → reveal pipeline above.
- "clip [talking video]" → OpusClip auto-loop (`run_clip_job`).
- "batch a week's worth" → batch mode (top 5 jobs → 5 reveals for approval).

## Render Studio dashboard (the control panel)

Live at **https://claude.ai/artifact/WEiFRiBnGg6ZFhbiNBRmyi** — the team
queues render jobs there; this skill is what drains the queue.

- The page's shared database holds everything: `requests` (one doc per
  render job: job, city, engine `reveal|preview|clip`, color/colorHex,
  formats, priority, folder, notes, status
  `queued|rendering|delivered|needs_input|canceled`, qa, resultNote) and
  `meta/status` (pipeline health chips: drive/ffmpeg/gemini/opusclip,
  review count).
- **"Run the render queue"** means: `ArtifactData` query `requests` where
  status == queued → for each, set status `rendering`, run the matching
  engine from this skill (reveal pipeline, `tools/preview_engine.py`, or
  OpusClip), QA it, deliver the files, then update the doc to `delivered`
  with `qa` + `resultNote` (pin writes with `if_version`).
- Keep `meta/status` honest whenever backends change (e.g. GEMINI_API_KEY
  added → `gemini: "ok"`; refresh the live review count when available).
- The page itself can verify Drive job folders (viewer's Google Drive
  connector); a request may carry a confirmed `folder` {id, title}.
