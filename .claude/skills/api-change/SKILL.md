---
name: api-change
description: Checklist-driven workflow for adding or modifying any /api/* endpoint or pipeline parameter in VidStega. Use BEFORE writing the change whenever a task touches routes.py, tasks.py signatures, or service method parameters. Prevents the four recurring review findings — dual-path drift, embed/extract asymmetry, response-shape breaks, and unguarded input parsing.
---

# API/pipeline change workflow

Every substantive bot-review finding on this repo has been one of four bug shapes.
Work through the phases in order; each one exists because skipping it produced a
real defect that shipped to review.

## Phase 1 — map the blast radius (read, don't write yet)

1. Read the actual return statement of every service method you'll consume.
   Several return **dicts, not scalars** (`VideoService.calculate_capacity` returns
   `{'total_capacity_bytes': ..., 'usable_capacity_bytes': ...}`). Arithmetic on an
   assumed-scalar dict was a shipped P1.
2. In the route you're touching, locate BOTH call sites: `task.delay(...)` and the
   sync fallback `run_*_pipeline(...)` in the `except` branch. List them.
3. Decide: does this parameter change the **embedded byte stream**? (ECC symbols,
   bit position, channel mode, header format ⇒ yes. Progress reporting, logging,
   output naming ⇒ no.) If yes, the change is a *codec* change and Phase 3 is
   mandatory.

## Phase 2 — implement, edge-in

Order of edits (outermost first keeps signatures honest):

1. **routes.py** — parse with guard, then clamp, at the top of the route:
   ```python
   try:
       ecc_symbols = int(data.get('ecc_symbols', SteganographyService.RS_ECC_SYMBOLS))
   except (TypeError, ValueError):
       return jsonify({'error': 'ecc_symbols must be an integer'}), 400
   ecc_symbols = max(2, min(ecc_symbols, 30))
   ```
   Pass the value to **both** the `.delay(...)` and the fallback pipeline call with
   identical kwargs. (An unguarded `int()` and a fallback-only wiring were both
   shipped P2s.)
2. **tasks.py** — parameter goes on the *shared pipeline function*
   (`run_embed_pipeline`/`run_extract_pipeline`) AND the Celery task signature,
   task forwarding it verbatim. Re-clamp defensively in the pipeline.
3. **services** — thread it as an explicit method parameter defaulting to the class
   constant. **Never assign to a class attribute at runtime**
   (`SteganographyService.RS_ECC_SYMBOLS = x` was a shipped thread-safety P1;
   gunicorn runs multi-threaded).

Response-shape rule: existing JSON keys keep their exact type. Add new fields
beside old ones; if a field must become richer, nest the new data and preserve the
old key (`'capacity'` stayed a dict for the frontend while flat
`usable_capacity`/`raw_capacity` fields were added alongside — copy that pattern).

## Phase 3 — symmetry (codec changes only)

A codec parameter is incomplete until its extract twin exists **in the same commit**:

- `/api/extract` route: same parse-guard + clamp + dual-path wiring as embed
- `extract_message_task` and `run_extract_pipeline`: same parameter, forwarded
- `SteganographyService.extract_message`: consumes it identically to embed

Then run `/roundtrip-test` including one case at each clamp bound and one
deliberate embed/extract mismatch (which must fail).

## Phase 4 — verify before pushing

```bash
flake8 . --count --select=E9,F63,F7,F82     # the CI gate
pytest                                       # exit 5 (none collected) is OK
grep -n "task.delay\|run_.*_pipeline" app/routes.py   # eyeball kwarg parity
```

Confirm with a diff read: every parameter appears the same number of times in the
async and sync paths. Commit with a `feat:`/`fix:` message whose body explains the
change per file; push to the `claude/*` branch; draft PR to master.

## Known formula (do not re-derive wrong)

Reed–Solomon RS(255, 255−n): usable capacity = `raw * (255 - n) / 255`.
The `/ (1 + n/255)` form is wrong and overestimates — it was a shipped P1.
