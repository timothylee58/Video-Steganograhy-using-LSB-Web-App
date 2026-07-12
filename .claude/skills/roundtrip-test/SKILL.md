---
name: roundtrip-test
description: Verify a steganography change end-to-end by embedding a message into a generated test video, extracting it back, and asserting equality. Use after ANY change to steganography_service.py, crypto_service.py, the pipelines in tasks.py, or a codec-affecting parameter (ecc_symbols, bit_position, channel_mode). Also invocable as /roundtrip-test [ecc_symbols] [channel_mode].
---

# Round-trip test: embed → extract → compare

The single highest-value check in this repo. Bot reviewers have repeatedly caught
embed/extract asymmetries that lint and unit tests miss; this catches them in one run.

## Steps

1. **Generate a tiny test video** (do not use user uploads; do not commit artifacts).
   Write this to the scratchpad directory, not the repo:

   ```python
   import cv2, numpy as np
   path = "<scratchpad>/rt_test.avi"
   w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"FFV1"), 10, (320, 240))
   assert w.isOpened(), "VideoWriter failed to open — FFV1 codec unavailable?"
   rng = np.random.default_rng(42)
   for _ in range(30):
       w.write(rng.integers(0, 256, (240, 320, 3), dtype=np.uint8))
   w.release()
   ```

   FFV1 (or another **lossless** codec) is mandatory — a lossy codec destroys LSBs
   and the test will fail for the wrong reason. The app itself writes `.avi` output
   for the same reason.

2. **Run the round-trip through the real pipelines** (not the service methods
   directly — the pipelines are where asymmetry bugs live):

   ```python
   from app.tasks import run_embed_pipeline, run_extract_pipeline
   msg = "roundtrip-test: 你好 مرحبا 🎬 " + "x" * 200   # multibyte + length
   res = run_embed_pipeline(
       video_path=path, message=msg, password="test-pass-123",
       frames=list(range(10)), encryption_strength="AES-256",
       cipher_mode="GCM", output_folder="<scratchpad>",
       ecc_symbols=ECC,                       # vary this — see matrix below
   )
   out = run_extract_pipeline(
       video_path=res["output_path"], password="test-pass-123",
       start_frame=0, end_frame=10,
       encryption_strength="AES-256", cipher_mode="GCM",
       ecc_symbols=ECC,                       # must mirror embed
   )
   assert out["message"] == msg, f"MISMATCH: {out['message']!r}"
   ```

3. **Test matrix** — run at minimum:

   | Case | Params | What it catches |
   |---|---|---|
   | default | ecc=10, rgb, GCM | baseline regression |
   | custom ECC | ecc=2 and ecc=30 (the clamp bounds) | embed/extract ECC asymmetry, clamp bugs |
   | whatever you changed | e.g. `channel_mode='luma'`, `bit_position=1` via ai_options | your actual diff |

   If your change added a parameter, also run one case where embed and extract
   *disagree* on it and **assert the extraction FAILS** — silent success there means
   the parameter isn't actually reaching the codec.

4. **Negative check**: extract with a wrong password must raise, not return garbage.

5. **Report**: state pass/fail per matrix row in the final message. On failure, do
   not "fix" by loosening the assertion — the codec is the product; find the
   asymmetric call site (grep for the parameter across routes.py → tasks.py →
   steganography_service.py).

## Cleanup
Delete generated videos from the scratchpad; never `git add` any `.avi`/`.mp4`.
