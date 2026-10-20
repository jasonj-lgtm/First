#!/usr/bin/env python3
"""T1P render worker — the deterministic half of the pipeline (Phase 2).

Runs on Render.com. The Claude orchestrator is the judgment half; this
service does the heavy, repeatable work: download the chosen photos, run
the repo engines (reveal_builder / color_engine), and publish results.

Job channels (both feed the same processor):
  1. Env kick — the orchestrator cannot reach this service over HTTPS
     from its sandbox, but it CAN set env vars through the Render
     connector, which redeploys the service. On boot we read RENDER_JOB
     (a JSON job) and process it if its id hasn't been done yet.
  2. POST /render — HMAC-signed (X-T1P-Signature, hex sha256 HMAC of the
     raw body with RENDER_SHARED_SECRET) for callers with real egress
     (Make.com bridge, local dev).

Results: rows in Render Postgres (DATABASE_URL) — the one store the
orchestrator can read back through the connector — and files served from
GET /files/<name> on this service's public URL (phone-clickable).

Env: DATABASE_URL, RENDER_SHARED_SECRET, RENDER_JOB (optional kick),
     PUBLIC_BASE_URL (e.g. https://t1p-render-worker.onrender.com),
     GEMINI_API_KEY (optional — photoreal color previews),
     OUTPUT_DIR (default /var/data/renders).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import psycopg
import requests
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(os.environ.get("OUTPUT_DIR", "/var/data/renders"))
OUT.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="T1P render worker")


def db():
    return psycopg.connect(os.environ["DATABASE_URL"], autocommit=True)


def ensure_table() -> None:
    with db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS render_jobs (
              id text PRIMARY KEY,
              payload jsonb NOT NULL,
              status text NOT NULL,
              files jsonb NOT NULL DEFAULT '[]',
              log text NOT NULL DEFAULT '',
              created timestamptz NOT NULL DEFAULT now(),
              updated timestamptz NOT NULL DEFAULT now()
            )""")


def safe_upsert(job_id: str, **fields) -> None:
    """DB write that never kills the job thread — results must still reach
    the logs (the orchestrator's channel) when Postgres is down."""
    try:
        upsert(job_id, **fields)
    except Exception as e:  # noqa: BLE001
        print(f"T1P_DB_WARN {job_id} {e}", flush=True)


def upsert(job_id: str, **fields) -> None:
    sets = ", ".join(f"{k} = %s" for k in fields) + ", updated = now()"
    with db() as conn:
        conn.execute(
            f"""INSERT INTO render_jobs (id, payload, status)
                VALUES (%s, '{{}}', 'queued')
                ON CONFLICT (id) DO NOTHING""", (job_id,))
        conn.execute(
            f"UPDATE render_jobs SET {sets} WHERE id = %s",
            (*[json.dumps(v) if isinstance(v, (dict, list)) else v
               for v in fields.values()], job_id))


def validate(job: dict) -> list[str]:
    """Names every problem with a job payload (empty list = valid)."""
    problems = []
    engine = job.get("engine", "reveal")
    if engine == "clip":
        if not job.get("video_url"):
            problems.append("clip needs video_url (public link to the source video)")
    elif engine not in ("reveal", "preview"):
        problems.append(f"unknown engine {engine!r}")
    photos = job.get("photos") or {}
    def has(kind):
        return photos.get(f"{kind}_url") or photos.get(f"{kind}_path")
    if engine == "reveal" and not (has("before") and has("after")):
        problems.append("reveal needs photos.before_url/_path and after_url/_path")
    if engine == "preview" and not has("photo"):
        problems.append("preview needs photos.photo_url or photo_path")
    if not isinstance(job.get("city", ""), str):
        problems.append("city must be a string")
    return problems


def fetch(url: str, dst: Path) -> Path:
    r = requests.get(url, timeout=120, allow_redirects=True)
    r.raise_for_status()
    dst.write_bytes(r.content)
    return dst


def resolve_photo(photos: dict, kind: str, workdir: Path) -> Path:
    """A photo arrives as <kind>_url (fetched) or <kind>_path (bundled in
    the image under the repo root — the no-credentials delivery channel)."""
    path_spec = photos.get(f"{kind}_path")
    if path_spec:
        p = (ROOT / path_spec).resolve()
        if ROOT not in p.parents or not p.is_file():
            raise FileNotFoundError(f"{kind}_path not bundled: {path_spec}")
        return p
    return fetch(photos[f"{kind}_url"], workdir / f"{kind}.jpg")


def public_url(name: str) -> str:
    base = os.environ.get("PUBLIC_BASE_URL", "").rstrip("/")
    return f"{base}/files/{name}" if base else f"/files/{name}"


OPUS_BASE = "https://api.opus.pro"


def opusclip_clip(job: dict, jid: str) -> list[dict]:
    """Submit the source video to OpusClip, wait for the clips, return file
    entries. Stages run PENDING->...->COMPLETE; STALLED is the terminal
    failure. Clip URLs are signed GCS links served by OpusClip (uriForExport)."""
    key = os.environ.get("OPUSCLIP_API_KEY")
    if not key:
        raise RuntimeError("OPUSCLIP_API_KEY not set on this service")
    hdrs = {"Authorization": f"Bearer {key}"}
    pid = job.get("opusProjectId")  # re-attach to a finished project: no new credits
    if pid:
        stage = "PENDING"
    else:
        body: dict = {"videoUrl": job["video_url"],
                      "curationPref": {"clipDurations": [[15, 60]]}}
        if job.get("keywords"):
            body["curationPref"]["topicKeywords"] = list(job["keywords"])[:5]
        r = requests.post(f"{OPUS_BASE}/api/clip-projects", json=body,
                          headers=hdrs, timeout=60)
        if r.status_code >= 400:
            raise RuntimeError(f"OpusClip submit HTTP {r.status_code}: {r.text[:300]}")
        pid = r.json().get("projectId") or r.json().get("id")
        stage = r.json().get("stage", "PENDING")
    print("T1P_CLIP " + json.dumps({"id": jid, "projectId": pid,
                                    "stage": stage}), flush=True)
    deadline = time.time() + 45 * 60
    first = True
    while time.time() < deadline:
        time.sleep(5 if first else 60)
        first = False
        pr = requests.get(f"{OPUS_BASE}/api/clip-projects/{pid}",
                          headers=hdrs, timeout=60)
        pr.raise_for_status()
        p = pr.json()
        if p.get("stage") != stage:
            stage = p.get("stage", "?")
            print("T1P_CLIP " + json.dumps({"id": jid, "projectId": pid,
                                            "stage": stage}), flush=True)
        if stage == "STALLED":
            raise RuntimeError(
                f"OpusClip project {pid} STALLED: {str(p.get('error', ''))[:200]}")
        if stage == "COMPLETE":
            cr = requests.get(f"{OPUS_BASE}/api/exportable-clips",
                              params={"q": "findByProjectId", "projectId": pid,
                                      "pageNum": 1, "pageSize": 50},
                              headers=hdrs, timeout=60)
            cr.raise_for_status()
            clips = cr.json() or []
            if isinstance(clips, dict):
                # The live API wraps the list; find it under common keys.
                found = None
                for k in ("items", "content", "data", "clips", "records", "results"):
                    if isinstance(clips.get(k), list):
                        found = clips[k]
                        break
                if found is None:
                    found = next((v for v in clips.values()
                                  if isinstance(v, list)), None)
                if found is None:
                    raise RuntimeError("unexpected exportable-clips shape: "
                                       + json.dumps(clips)[:300])
                clips = found
            clips.sort(key=lambda c: c.get("viralityScore") or c.get("score") or 0,
                       reverse=True)
            files = []
            for i, c in enumerate(clips[:5], 1):
                url = c.get("uriForExport") or c.get("uriForPreview")
                if url:
                    files.append({"name": c.get("title") or f"clip {i}",
                                  "url": url, "kind": "clip",
                                  "durationSec": round((c.get("durationMs") or 0) / 1000),
                                  "viralityScore": c.get("viralityScore")})
            if not files:
                raise RuntimeError(f"OpusClip project {pid} completed "
                                   "with no exportable clips")
            return files
    raise RuntimeError(f"OpusClip project {pid} still {stage} after 45 min — "
                       "it keeps processing on their side; requeue to re-check")


def tail_error(stderr: str) -> str:
    """Last meaningful lines of a subprocess traceback — Render's log
    pipeline truncates long lines, so the punchline must come first."""
    lines = [l for l in stderr.strip().splitlines() if l.strip()]
    return " | ".join(lines[-3:])[-700:] if lines else "no stderr"


def process(job: dict) -> None:
    """Run one job end to end; record status + file links in Postgres."""
    jid = job["id"]
    print(f"T1P_START {jid}", flush=True)
    problems = validate(job)
    if problems:
        print("T1P_RESULT " + json.dumps(
            {"id": jid, "status": "error",
             "error": "invalid job: " + ", ".join(problems)}), flush=True)
        safe_upsert(jid, payload=job, status="error",
                    log="validation: " + ", ".join(problems))
        return
    safe_upsert(jid, payload=job, status="rendering")
    try:
        workdir = OUT / jid
        workdir.mkdir(parents=True, exist_ok=True)
        files: list[dict] = []
        engine = job.get("engine", "reveal")
        city = job.get("city", "Portland")
        logo = ROOT / "assets" / "brand" / "logo.png"
        logo_args = ["--logo", str(logo)] if logo.exists() else []

        if engine == "reveal":
            before = resolve_photo(job["photos"], "before", workdir)
            after = resolve_photo(job["photos"], "after", workdir)
            out = workdir / f"{jid}_reveal.mp4"
            cmd = ["nice", "-n", "19", sys.executable, str(ROOT / "tools" / "reveal_builder.py"),
                   "--before", str(before), "--after", str(after),
                   "--city", city, "--out", str(out), *logo_args]
            if job.get("hook"):
                cmd += ["--hook", job["hook"]]
            if job.get("reviews"):
                cmd += ["--reviews", str(job["reviews"])]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=2700)
            if r.returncode != 0:
                raise RuntimeError(tail_error(r.stderr))
            files.append({"name": out.name, "url": public_url(f"{jid}/{out.name}"),
                          "kind": "reel_9x16"})
            comp = out.with_name(out.stem + "_composite.jpg")
            if comp.exists():
                files.append({"name": comp.name,
                              "url": public_url(f"{jid}/{comp.name}"),
                              "kind": "composite_4x5"})

        elif engine == "preview":
            photo = resolve_photo(job["photos"], "photo", workdir)
            cmd = ["nice", "-n", "19", sys.executable, str(ROOT / "tools" / "preview_engine.py"),
                   "--photo", str(photo),
                   "--color", job.get("color", "custom"),
                   "--hex", (job.get("colorHex") or "#79746D").lstrip("#"),
                   "--city", city, "--out-dir", str(workdir), *logo_args]
            music = ROOT / "assets" / "music" / "licensed" / "t1p-bed-01.wav"
            if music.exists() and "reel" in job.get("formats", ["reel"]):
                cmd += ["--music", str(music)]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=2700)
            if r.returncode != 0:
                raise RuntimeError(tail_error(r.stderr))
            for name, kind in [("preview_recolor.png", "concept_image"),
                               ("preview_card.jpg", "card_4x5"),
                               ("preview_reveal.mp4", "reel_9x16")]:
                if (workdir / name).exists():
                    files.append({"name": name, "url": public_url(f"{jid}/{name}"),
                                  "kind": kind})
        elif engine == "clip":
            files = opusclip_clip(job, jid)

        else:
            raise ValueError(f"engine {engine!r} not handled by the worker")

        print("T1P_RESULT " + json.dumps({"id": jid, "status": "done",
                                          "files": files}), flush=True)
        (workdir / ".done").write_text("ok")
        safe_upsert(jid, status="done", files=files,
                    log=f"ok {datetime.now(timezone.utc).isoformat()}")
    except Exception as e:  # noqa: BLE001 — job errors land in the row
        print("T1P_RESULT " + json.dumps({"id": jid, "status": "error",
                                          "error": str(e)[:600]}), flush=True)
        safe_upsert(jid, status="error",
                    log=f"{e}\n{traceback.format_exc()[-1200:]}")


@app.on_event("startup")
def boot() -> None:
    db_ok = False
    if os.environ.get("DATABASE_URL"):
        try:
            ensure_table()
            db_ok = True
        except Exception as e:  # noqa: BLE001
            print(f"T1P_BOOT db_error={e}", flush=True)
    else:
        print("WARNING: DATABASE_URL not set — job state disabled until the "
              "Internal Database URL from t1p-render-jobs is pasted into "
              "this service's env vars.")
    print("T1P_BOOT " + json.dumps({
        "db": db_ok, "gemini": bool(os.environ.get("GEMINI_API_KEY")),
        "opusclip": bool(os.environ.get("OPUSCLIP_API_KEY"))}),
        flush=True)
    raw = os.environ.get("RENDER_JOB", "").strip()
    if not raw:
        return
    try:
        job = json.loads(raw)
    except ValueError:
        return
    jid = job.get("id")
    if not jid:
        return
    if (OUT / jid / ".done").exists():
        return  # this instance already rendered it (works with PG down)
    try:
        with db() as conn:
            row = conn.execute("SELECT status FROM render_jobs WHERE id = %s",
                               (jid,)).fetchone()
        if row and row[0] in ("done", "rendering"):
            return  # already handled; env kick is at-least-once
    except Exception:
        pass  # no DB — the disk marker above is the only dedupe
    threading.Thread(target=process, args=(job,), daemon=True).start()


@app.get("/health")
def health() -> dict:
    return {"ok": True, "ts": datetime.now(timezone.utc).isoformat()}


@app.get("/")
def home():
    """Human-friendly status page for phone checks."""
    from fastapi.responses import HTMLResponse

    db_ok, jobs = False, "–"
    if os.environ.get("DATABASE_URL"):
        try:
            with db() as conn:
                jobs = conn.execute("SELECT count(*) FROM render_jobs").fetchone()[0]
            db_ok = True
        except Exception:
            db_ok = False
    gemini = bool(os.environ.get("GEMINI_API_KEY"))
    row = lambda label, ok, extra="": (
        f"<div style='padding:10px 14px;border-radius:10px;background:#0d2148;"
        f"display:flex;justify-content:space-between;gap:12px'><span>{label}</span>"
        f"<b style='color:{'#4ADE80' if ok else '#FBBF24'}'>"
        f"{'READY' if ok else 'NEEDS SETUP'}{extra}</b></div>")
    html = (
        "<meta name=viewport content='width=device-width,initial-scale=1'>"
        "<body style='margin:0;background:#05132D;color:#EDF0F2;"
        "font-family:system-ui;padding:28px 18px'>"
        "<div style='max-width:460px;margin:0 auto;display:flex;"
        "flex-direction:column;gap:10px'>"
        "<h2 style='margin:0 0 2px;letter-spacing:.04em'>T1P RENDER WORKER</h2>"
        "<div style='color:#8CA3C9;margin-bottom:10px'>That 1 Painter · Oregon — "
        "deterministic render engine. Jobs arrive from the Claude orchestrator; "
        "nothing to do on this page.</div>"
        + row("Service", True)
        + row("Database (DATABASE_URL)", db_ok,
              f" · {jobs} jobs" if db_ok else "")
        + row("Gemini photoreal (GEMINI_API_KEY)", gemini)
        + "</div></body>")
    return HTMLResponse(html)


@app.post("/render")
async def render(request: Request) -> JSONResponse:
    body = await request.body()
    secret = os.environ.get("RENDER_SHARED_SECRET", "")
    sig = request.headers.get("X-T1P-Signature", "")
    want = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    if not secret or not hmac.compare_digest(sig, want):
        raise HTTPException(401, "bad signature")
    job = json.loads(body)
    if not job.get("id"):
        raise HTTPException(400, "job needs an id")
    threading.Thread(target=process, args=(job,), daemon=True).start()
    return JSONResponse({"accepted": job["id"]})


@app.get("/jobs/{jid}")
def job_status(jid: str) -> dict:
    with db() as conn:
        row = conn.execute(
            "SELECT status, files, log, updated FROM render_jobs WHERE id = %s",
            (jid,)).fetchone()
    if not row:
        raise HTTPException(404, "unknown job")
    return {"id": jid, "status": row[0], "files": row[1],
            "log": row[2], "updated": row[3].isoformat()}


@app.get("/files/{jid}/{name}")
def file(jid: str, name: str) -> FileResponse:
    p = (OUT / jid / name).resolve()
    if not p.is_file() or OUT.resolve() not in p.parents:
        raise HTTPException(404, "no such file")
    return FileResponse(p)
