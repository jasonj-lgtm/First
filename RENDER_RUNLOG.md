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
