# CLAUDE.md — Operating Manual for VidStega

VidStega is a Flask web app that hides AES-encrypted messages inside video frames
using LSB steganography, with Reed-Solomon error correction. Final-year project,
single maintainer, deployed on **Fly.io** (NOT Render, NOT Cloudflare Workers —
see "Deployment" below before touching anything deploy-related).

## Architecture in 60 seconds

- `run.py` → `app/__init__.py:create_app()` (app factory) → blueprints in `app/routes.py`
- `app/routes.py` — all HTTP endpoints (`/api/*`). Every processing endpoint has TWO
  execution paths: Celery async (`task.delay(...)`) with a **sync fallback**
  (`run_*_pipeline(...)`) used when the Redis broker is unavailable. Both paths call
  the same `run_embed_pipeline` / `run_extract_pipeline` functions in `app/tasks.py`.
- `app/tasks.py` — Celery tasks + the shared pipeline functions. Progress is reported
  via `self.update_state(meta={...})`, read back by `/api/task/<id>` polling.
- `app/websocket.py` — Socket.IO push path. Only functional with a Redis message
  broker; polling `/api/task/<id>` is the always-working fallback. Async mode comes
  from `SOCKETIO_ASYNC_MODE` env (must be `threading` in production — see Deployment).
- `app/services/` — stateless service classes with classmethods:
  `steganography_service.py` (LSB embed/extract + Reed-Solomon),
  `video_service.py` (OpenCV frame I/O, capacity), `crypto_service.py` (AES/PBKDF2),
  `ai_service.py` (frame selection, platform presets), `batch_service.py`, `metadata_service.py`.
- Root-level `*.py` files with spaces in their names (`VidStega - Embed text.py`, etc.)
  are **standalone thesis demo scripts**. They are not imported by the app, they have
  intentionally incomplete imports, and flake8 ignores their F821s via `.flake8`.
  Never "fix" them, never import from them, never delete them.

## Conventions I follow (and ones you must adopt)

1. **Branch discipline.** All work goes on the designated `claude/*` feature branch,
   pushed with `git push -u origin <branch>`, then a **draft PR** to `master`.
   Never push to `master` directly.
2. **Shared pipeline functions.** Any behavior change to embed/extract MUST go into
   `run_embed_pipeline` / `run_extract_pipeline`, never into the Celery task bodies,
   so the sync fallback stays identical to the async path.
3. **Services stay stateless.** Service classes use classmethods and take everything
   as parameters. Never mutate class attributes (e.g. `RS_ECC_SYMBOLS`) at runtime —
   the app runs multi-threaded under gunicorn and that is a race condition. Add an
   optional parameter that defaults to the class constant instead.
4. **Parameter clamping at the edge.** User-supplied numeric knobs (e.g. `ecc_symbols`)
   are parsed with `try/except (TypeError, ValueError) → 400`, then clamped
   (`max(2, min(x, 30))`) in `routes.py`. Pipelines may re-clamp defensively.
5. **API backward compatibility.** The single-page frontend (`templates/index.html`)
   consumes these endpoints. Never change the shape of an existing response field;
   add new fields alongside. If a field must become richer, nest the new data and
   keep the old key working.
6. **CI mirrors the Dockerfile.** Both strip `opencv-python` and keep only
   `opencv-python-headless` (`grep -v '^opencv-python>='`). If you change one,
   change the other in the same commit.
7. **Pin GitHub Actions to release tags** (`@v4`, `@v1.5`), never `@master`.
8. **Commit messages**: conventional-ish prefixes (`feat:`, `fix:`, `ci:`), body
   explains the why per file when the diff spans layers.

## Mistakes a weaker model WILL make here — and the rule that prevents each

1. **Mistake:** Assuming `VideoService.calculate_capacity()` returns a number.
   **It returns a dict** (`total_capacity_bytes`, `usable_capacity_bytes`, ...).
   **Rule:** Before doing arithmetic on any service return value, read the service
   method's actual return statement. Docstrings here say "Dictionary with capacity
   information" — believe them.

2. **Mistake:** Adding a knob to the embed path and forgetting the extract path.
   Embed and extract are a symmetric codec: any parameter that changes the embedded
   byte stream (ECC symbols, bit position, channel mode) MUST thread through
   `/api/extract` → `extract_message_task` → `run_extract_pipeline` →
   `SteganographyService.extract_message`, or round-trips silently corrupt.
   **Rule:** any new embed parameter ships with its extract twin in the same commit,
   plus a round-trip test (`/roundtrip-test` skill).

3. **Mistake:** Wiring a change into the Celery task but not the sync fallback (or
   vice versa). The `except` branch in each route re-invokes the pipeline directly.
   **Rule:** grep the route for both `task.delay(` and `run_*_pipeline(` and update
   both call sites with identical kwargs.

4. **Mistake:** Treating the **Cloudflare Workers** check as meaningful. A leftover
   Cloudflare Git integration builds on every push. Historically it always failed;
   since `wrangler.jsonc` landed (with `"assets": {"directory": "."}`) it can
   "succeed" — but that success only uploads the repo as static files to
   workers.dev. The Flask backend does not run there; the preview URL is not the app.
   **Rule:** ignore `Workers Builds:` results, pass or fail. The checks that matter
   are `Python application` / `build` (lint + pytest) and, on master, the Fly.io
   deploy job. Never point users at workers.dev URLs.

5. **Mistake:** Editing `fly.toml` from memory or re-adding a second `[[mounts]]`.
   Fly machines support exactly ONE volume; outputs live at
   `/app/uploads/outputs` inside the single `vidstega_data` mount, selected via the
   `OUTPUT_FOLDER` env var. Also `flyctl launch/deploy` can regenerate fly.toml and
   clobber it. **Rule:** treat the committed `fly.toml` as the source of truth; never
   add mounts; never switch `SOCKETIO_ASYNC_MODE` off `threading` (gunicorn ≥23
   removed the eventlet worker).

6. **Mistake:** Guessing Reed-Solomon math. RS(255, 255−n) expands data by
   255/(255−n); usable capacity = `raw * (255 - n) / 255`. Not `raw / (1 + n/255)`.
   **Rule:** when touching capacity/ECC math, derive from the codeword definition and
   state the formula in a comment.

7. **Mistake:** Letting pytest or flake8 trip over the repo's odd files.
   `stress_test.py` is a load-test script, not a test (pytest.ini restricts
   collection to `tests/test_*.py`); the thesis scripts have deliberate F821s
   (suppressed in `.flake8`). **Rule:** never rename these files to "fix" tooling;
   the tooling config already handles them.

8. **Mistake:** Doing per-pixel work in new Python loops. Frames are numpy arrays;
   the existing per-pixel loops in `steganography_service.py` are already the
   bottleneck. **Rule:** new frame-level code must be vectorized numpy unless it is
   modifying the existing embed/extract loops, in which case match their structure.

## Quality bar per deliverable (checkable, not adjectives)

**A code change is done when:**
- [ ] `flake8 . --count --select=E9,F63,F7,F82` passes (this is the CI gate)
- [ ] `pytest` passes (or exits 5 = no tests collected, which CI tolerates)
- [ ] Both Celery and sync-fallback call sites updated if a pipeline signature changed
- [ ] Extract mirrors embed for any codec-affecting parameter
- [ ] No existing JSON response key changed type or disappeared
- [ ] New user inputs are parse-guarded (400 on garbage) and clamped

**A PR is done when:**
- [ ] Draft PR opened against `master` with summary + files-changed + test plan
- [ ] `Python application` check green (Cloudflare Workers check ignored)
- [ ] Every bot review finding either fixed, or answered in a comment with a reason
- [ ] Round-trip verified for stego changes (embed → extract → message matches)

**A deploy change is done when:**
- [ ] `fly.toml` still has exactly one `[[mounts]]`, `internal_port = 8080`,
      `SOCKETIO_ASYNC_MODE = 'threading'`, health check on `/health`
- [ ] Dockerfile and CI dependency handling still match each other
- [ ] `FLY_API_TOKEN` requirement noted to the maintainer if CI deploy is touched

## When uncertain — exact escalation rules

- **Proceed without asking** when: fixing a reviewer-confirmed bug; keeping embed/
  extract symmetric; adding validation/clamping; pinning versions; updating docs.
- **Ask first (AskUserQuestion / PR comment)** when: changing any public API response
  shape beyond additive fields; changing the embedded byte format (breaks existing
  stego videos); adding a new infra dependency (queue, DB, external service);
  anything touching `master` branch protection or deploy credentials.
- **Never do** without an explicit instruction: force-push over unmerged commits;
  destroy Fly volumes/machines; disconnect integrations; delete the thesis scripts
  or Word documents (they are the actual academic deliverable this repo exists for).
- **Reviewer bots** (Gemini, cubic, CodeRabbit): verify each finding against the code
  before acting — they are usually right here but confirm the claimed return types /
  call sites yourself. Rate-limit and draft-skip notices require no action.
- **If a CI signal contradicts this file** (e.g. a new required check appears),
  believe CI, then update this file in the same PR.
