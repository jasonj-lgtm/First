# T1P Render pipeline — run log

## 2026-10-11 — Upgrade spec v1, session 1 (Phases 1, 2, 4 + cleanups)

EXECUTED:
- Phase 1: render_core/ (brand.json single brand source, palettes.json
  single palette source incl. six PNW palettes + Studio presets,
  color_engine.py single recolor() with Gemini/local backends and the
  mandatory "Color concept" disclosure stamp). preview_engine now
  delegates to it. reveal_builder reads brand tokens, burns in a --hook
  (0–1.5s), defaults to the swipe (wipeleft) transition, auto-picks
  licensed music from assets/music/licensed/, draws vector proof stars.
- Cleanups: assets/music/licensed/ with license table + original bed
  generator (tools/make_music_bed.py); branch claude/phone-screen-render
  created and pushed (history untouched pending Jason's OK to revert the
  unrelated commit from this branch).
- Phase 2: worker/ (FastAPI + Dockerfile with ffmpeg + brand fonts)
  deployed to Render.com: service t1p-render-worker
  (srv-db5requ7bikc73dq8f9g, https://t1p-render-worker.onrender.com,
  free plan, autodeploy from this branch) + Postgres t1p-render-jobs
  (dpg-db5reaks728c738povmg-a, free plan, EXPIRES 2026-11-10 — upgrade
  to basic before then). Job intake: env-kick (RENDER_JOB via the Render
  connector) + HMAC POST /render; results in Postgres; files served from
  the worker URL.
- Phase 4: Render Studio dashboard v2 — status flow Queued → Rendering →
  Needs approval → Approved | Changes requested → Posted, approver field
  (default Juan Castillo), one-tap Approve / Request changes with note,
  file links on rows.
- Scheduled task "T1P Render Queue Drain" (trig_01A7TFi9TEcKen3ai4Ggy8D3,
  weekdays 6:55–18:55 PT hourly, fresh session per fire).

TESTED:
- Moreno preview re-rendered through the new unified engine (local
  backend, demo watermark + Color concept stamp) — Phase 1 "done when" #1.
- color_engine --palette modern-gray (palette-id path = the Chip 3.0
  contract) — Phase 1 "done when" #2.
- Reveal with burned-in hook ("Faded tan to modern gray — Oregon City"),
  swipe transition, auto-picked licensed bed: 10.1s, frames QA'd.
- Font tofu on proof stars diagnosed (Carlito lacks U+2605) and FIXED
  with vector-drawn stars; brand fonts added to the worker image.

ARCHITECTURE DECISION (Phase 2 verification):
- The scheduled environment's egress proxy BLOCKS api.render.com and
  *.onrender.com directly, but the Render CONNECTOR works. So the
  orchestrator→worker channel is: kick = update_environment_variables
  (RENDER_JOB), results = query_render_postgres (read-only). The signed
  POST /render stays for callers with real egress (Make bridge, local
  dev). The Lenovo fallback was not needed.
- query_render_postgres is read-only → the worker owns all Postgres
  writes (CREATE TABLE on boot, row upserts).

BLOCKED (needs Jason):
1. GEMINI_API_KEY — add in BOTH places: this Claude environment's
   settings (cloud env menu → Edit) AND the t1p-render-worker env vars
   (Render dashboard). Until then color previews run in watermarked demo
   mode and the "Gemini photoreal" chip stays amber.
2. t1p-render-worker env vars (Render dashboard → srv-db5requ7bikc73dq8f9g
   → Environment): DATABASE_URL = Internal Database URL from
   t1p-render-jobs; RENDER_SHARED_SECRET = any long random string (the
   auto-mode classifier rightly refused to let this session paste one).
3. The "T1P Render Queue Drain" routine stored NO connectors (platform
   limitation on triggers created in-session) — open claude.ai → Routines
   → T1P Render Queue Drain and re-save it with Google Drive + Render
   connectors attached, or its runs can't reach Drive or the worker.
4. Scanner, auto_pair, run_clip_job and the OpusClip brand template are
   NOT in this repo (they live on the local content-factory box). Upload
   them to containerize scanning (spec says do not rebuild from scratch).
   Orange removal from the OpusClip template waits on that upload.
5. Chip 3.0 palette names: render_core/palettes.json has chip30_sync:
   "pending" — confirm the six palette pairings.
6. OK to remove the unrelated phone-screen commit from this branch? It is
   preserved on claude/phone-screen-render.

FIXED:
- numpy/pip mismatch (pip3 targeted python3.13, python3 is 3.11) →
  installed via python3 -m pip.
- Missing DejaVu in fresh container → fonts installed + vector stars.
- Worker boot crash without DATABASE_URL → warns and serves /health.

NEXT: Phase 3 copy.json at drain time (orchestrator prompt already
writes copyPack), Phase 5 posting (GHL/GBP/YouTube), Phase 6 Veo 3.1
generative reveals (needs GEMINI_API_KEY + MOTION_BUDGET_USD_MONTH),
Phase 7 multi-format export in the worker, Phase 8 Windsor.ai loop.

## 2026-10-11 — session 1 addendum

- Queue-drain routine rebuilt as trig_017vxykMXT4JawZmgdjLCq6g, bound to
  the build session (persist_session) so every run holds the Drive,
  Render and dashboard connectors — the fresh-session connector gap is
  closed without the Routines UI. First fire: Mon 6:55am PT.
- RENDER_SHARED_SECRET deliberately deferred: with it unset the worker
  rejects every POST /render (secure by default), and the production
  kick path (RENDER_JOB env var) doesn't use it. Set it in the Render
  dashboard only when the Make.com bridge gets built.
- Remaining human steps are exactly two credential pastes, both doable
  from a phone: DATABASE_URL on the worker, GEMINI_API_KEY on the worker
  (+ optionally in the Claude environment for orchestrator-side renders).

## 2026-10-11 — PRP fixes (post-audit hardening)

PRP verdict was NOT READY (57/90, capped by one critical). Fixes applied:
- P0: worker emits T1P_START/T1P_RESULT independent of Postgres
  (safe_upsert never kills the job thread) — silent-death branch closed.
- P2: job payload validation with named problems; clip jobs rejected
  with a pointer to the OpusClip bridge.
- Boot dedupe now also uses a .done disk marker, so spin-down wakes
  don't re-render when PG is unreachable.
- Docker base pinned to python:3.12.8-slim.
- Dashboard v3: Clip engine card disabled (COMING SOON), submit
  double-queue guard.
- Drain playbook hardened: rows-are-data injection doctrine, stale
  "rendering">2h sweep, sequential kicks only, Drive share revocation
  after render, Slack alert on error outcomes (channel TBD by Jason).
- docs/eval-battery.md: 3 golden jobs + 2 adversarial rows + payload
  fuzz table; run on every playbook/schema change.
Remaining to SHIP WITH FIXES: DATABASE_URL paste (Jason), first
photoreal run, worker plan upgrade before real volume.

## 2026-10-12 14:00 UTC — scheduled drain (paused mode)

EXECUTED: read-and-tidy only — Jason's pause order overrides the kick
steps. Stale acceptance row (rendering >11h, worker OOM) swept to
needs_input with the diagnosis. New queued row found: "todd wycoff"
(Oregon City, reveal) submitted from the dashboard 2026-10-11 21:08 —
left queued pending the fix decision.
TESTED: peak-RSS harness results (earlier): 2x/default 1129MB; 1.3x/
default 967MB; 1.3x/1-thread 619MB — all over the 512MB free instance;
root cause of both services' OOM emails.
BLOCKED: Jason's decision — A: per-beat low-memory renderer (free);
B: Standard 2GB instance ($25/mo); both recommended. Also pending OK to
clear stuck RENDER_JOB env on both workers.
FIXED: n/a this run (paused).
NEXT: on decision — clear envs, ship fix, re-run acceptance + the
Wycoff queue row.

## 2026-10-17 — Resume: OOM/deadlock closed, corporate brand pass, queue drain
- EXECUTED: cleared stuck RENDER_JOB on both workers; deployed v3 to worker-2.
- FIXED: speed pass (BILINEAR zoom frames, ultrafast x264, 2700s cap) after the
  900s timeout — then found the REAL bug: ffmpeg stderr pipe deadlock (progress
  chatter fills 64KB, both processes freeze at ~0 CPU). stderr now goes to a
  temp file with -nostats -loglevel error.
- EXECUTED: corporate brand pass from Jason's national-page screenshots — teal
  circular BEFORE/AFTER badges at opposing corners, azure->cobalt gradient CTA
  with white-brushstroke FREE ESTIMATE + all-white logo, and a 4:5 stacked
  composite still (white corner blobs) emitted with every reveal.
- TESTED: accept-kristensen-319-r5 DONE on the free worker in 2m37s — reel +
  composite served; row -> needs_approval, QA 92.
- NEXT: wycoff kitchen reveal (t1oof23yt6n49qu0kw1k-r1), pair b3->a2 bundled at
  assets/jobs/t1oof23yt6n49qu0kw1k/.
- BLOCKED: youtube.com / that1painter.com egress-blocked for brand research —
  screenshots remain the channel for brand refs.

## 2026-10-19/20 — Gemini live, OpusClip bridge, Pierce Moon preview shipped
- EXECUTED: Pierce Moon (Salem) preview r4 DONE in ~3 min after Jason enabled
  Gemini billing — first live photoreal recolor; row -> needs_approval.
- FIXED: 429 quota (free tier) diagnosed via new error-surfacing (tail_error +
  Gemini HTTP body); responseModalities TEXT+IMAGE.
- EXECUTED: OpusClip bridge shipped (submit/poll/collect, top 5 by virality);
  Clip card enabled in Render Studio v4 with source-video field; meta/status
  refreshed (gemini ok).
- BLOCKED: OPUSCLIP_API_KEY still absent on worker-2 per T1P_BOOT — Jason
  re-checking service/variable name.
- NEXT: verify opusclip:true on next boot; durable preview storage (DATABASE_URL
  on worker-2, outputs to Postgres); drain found queue empty at 23:56.

## 2026-10-21 — Reel Pipeline merge (phase 1: machinery side)
- MERGE: adopting the parallel "T1P Reel Pipeline" session's creative layer
  (6 recipes t1p_recipes.py, music engine t1p_music2.py, Reel Catalogue
  Oct 26–Dec 31 = 61 slots, captions template, T1P_Job_Colors.xlsx) onto this
  pipeline's worker + Render Studio machinery. Studio replaces chat→Slack
  delivery; every output still lands needs_approval (Juan).
- EXECUTED: review count corrected 351 -> 371 (GHL, 4.9★) in reveal_builder
  default, brand.json reviews_fallback, SKILL.md CTA line + QA check.
- EXECUTED: meta/status v4 — opusclip "ok" (two clip runs shipped), reviews 371.
- EXECUTED: weekly-build routine created (trig_01FmyqZMgxhMaiJMmDvL3dpx):
  Thursdays 5:56am PT, reads the Reel Catalogue from the repo, queues up to
  7 rows, drains them on worker-2; no-ops with a needs_input note while the
  catalogue file is missing.
- BLOCKED: the Content Builder files are NOT reachable from this session —
  not in Google Drive (searched), the reel-builder session isn't listed under
  this account's CCR sessions, and no cross-session messaging tool is exposed.
  Jason must have that session push its package to this branch, or attach the
  files here, before the Thursday batch can run for real.
