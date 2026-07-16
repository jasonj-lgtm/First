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

**Where the tools run:** the pipeline code (`reveal_builder.py`, scanner,
`auto_pair`) lives in the local content-factory environment at
`http://127.0.0.1:8787` — not in this repository. This skill is the playbook:
follow it there, or rebuild the steps with ffmpeg if working from raw footage.

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
