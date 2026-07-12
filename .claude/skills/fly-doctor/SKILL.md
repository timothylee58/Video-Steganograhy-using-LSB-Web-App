---
name: fly-doctor
description: Diagnose and fix Fly.io deployment failures for VidStega. Use when a fly deploy fails, health checks time out, machines won't start, volume errors appear, or the user pastes flyctl output/errors. Encodes every failure mode already hit in this project so they are fixed in one pass instead of rediscovered.
---

# Fly.io deploy doctor for VidStega

App name: `video-steganograhy-using-lsb-web-app` · region `sin` · ONE volume: `vidstega_data`.
The committed `fly.toml` on master is the source of truth. The user deploys from a
Windows PowerShell machine; you usually only see pasted output.

## Step 0 — validate fly.toml BEFORE any deploy advice

Check the local file against these invariants (each was violated at least once):

- [ ] exactly **one** `[[mounts]]` block (`vidstega_data` → `/app/uploads`) — Fly
      machines support one volume; a second mount fails with "only 1 volume supported"
- [ ] `OUTPUT_FOLDER = '/app/uploads/outputs'` in `[env]` (outputs live INSIDE the mount)
- [ ] `SOCKETIO_ASYNC_MODE = 'threading'` (gunicorn ≥23 removed eventlet; switching
      this back causes worker boot ImportError → health check timeout)
- [ ] `app = 'video-steganograhy-using-lsb-web-app'` (not `vidstega`)
- [ ] `internal_port = 8080`, health check `GET /health`, `grace_period` ≥ 60s
- [ ] file starts with `app =` — no BOM. PowerShell's `Set-Content -Encoding UTF8`
      adds a BOM the TOML parser rejects ("invalid character at start of key").
      Tell the user to use `-Encoding ascii`, or better: `git checkout -- fly.toml`.

If the file drifted: `flyctl launch`/`deploy` sometimes regenerates fly.toml.
The fix is `git checkout master -- fly.toml` (or `git pull`), never hand-rewriting.

## Failure → fix table

| Symptom in output | Root cause | Fix |
|---|---|---|
| `only 1 volume supported` | second `[[mounts]]` in fly.toml | restore fly.toml from git; then check for a stray `vidstega_outputs` volume |
| `vidstega_outputs` appears in `fly volumes list` | Fly auto-created it for the bogus mount in the WEB app's fly.toml | Check it's empty/expendable first — `fly-worker.toml` legitimately mounts a `vidstega_outputs` for the worker app. If it belongs to the web app and holds no data, `fly volumes destroy <vol_id>` (no `-y`; let the prompt guard). It may be recreated on each bad deploy — fix fly.toml FIRST |
| health check timeout + logs show `Error: class uri 'eventlet' invalid` | gunicorn ≥23 has no eventlet worker | Dockerfile CMD must be `gunicorn -w 1 --threads 4 --bind 0.0.0.0:8080 --timeout 300 run:app`; env `SOCKETIO_ASYNC_MODE=threading` |
| `libGL.so.1: cannot open shared object` | opencv non-headless or missing lib | Dockerfile installs `libgl1` (NOT `libgl1-mesa-glx` — gone on Bookworm) and strips `opencv-python`, keeping headless |
| `machine still active, refusing to start` / machine stuck with old config | machine created under a bad fly.toml cannot be updated across mount changes | `fly machines list` to identify; then, with the user's explicit OK, `fly machines destroy <id> --force` → redeploy |
| `invalid character at start of key` parsing fly.toml | UTF-8 BOM from PowerShell | rewrite with `-Encoding ascii` or restore from git |
| deploy succeeds, app 502s on upload paths | OUTPUT_FOLDER missing → writing outside the mount to an ephemeral/readonly path | set `OUTPUT_FOLDER=/app/uploads/outputs`; `app/config.py` reads it from env |
| CI deploy job fails with auth error | `FLY_API_TOKEN` secret missing | user runs `fly tokens create deploy` and adds repo secret `FLY_API_TOKEN` |

## Standard recovery sequence (when state is tangled)

Non-destructive steps first — order matters because Fly recreates volumes/machines
from whatever fly.toml it sees:

```powershell
git fetch origin master                    # 1. force-restore the committed fly.toml
git checkout origin/master -- fly.toml     #    (git pull won't discard a locally drifted file)
fly volumes list                           # 2. diagnose: list volumes and machines
fly machines list
fly deploy                                 # 3. plain deploy, no --image, no launch
```

Destructive steps (`fly volumes destroy`, `fly machines destroy`) are NOT part of
the standard sequence. Propose them only when the diagnosis shows they are needed
(a stray web-app `vidstega_outputs`, a machine stuck on an old mount config), name
the exact target ID, and get the user's explicit go-ahead first. Before a volume
destroy, confirm the volume is unattached and empty — the worker app
(`fly-worker.toml`) legitimately uses a volume named `vidstega_outputs`. Never use
`-y`; let Fly's confirmation prompt stand.

Never suggest `fly launch` on this app (regenerates fly.toml). Never suggest
destroying `vidstega_data` — it holds user uploads and its loss is irreversible;
that action is user-only, by explicit instruction.

## After it deploys

Verify: `fly status` all green, then
`curl.exe https://video-steganograhy-using-lsb-web-app.fly.dev/health`
(or `Invoke-RestMethod <url>` — plain `curl` in PowerShell 5.1 aliases
Invoke-WebRequest and prints a response object, not the JSON body)
returns `{"status": "healthy", ...}`. If health is green but uploads fail, re-check
the OUTPUT_FOLDER row above.
