#!/usr/bin/env python3
"""
Generate a synthetic 1080p MP4 for embed/extract stress testing.

Requires: opencv-python (cv2), numpy (already in requirements.txt)

Usage (Windows, from repo root):
    cd C:\\Users\\ASUS\\Video-Steganograhy-using-LSB-Web-App
    python generate_stress_1080p_video.py

Output:
    stress_test_results/stress_1080p_300f_24fps.mp4

Optional:
    python generate_stress_1080p_video.py --frames 600 --fps 30 --output stress_test_results/my_stress.mp4
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate 1080p stress-test MP4")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--frames", type=int, default=300, help="Total frames to write")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path (default: stress_test_results/stress_1080p_<frames>f_<fps>fps.mp4)",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    try:
        import cv2
        import numpy as np
    except ImportError as e:
        print("Missing dependency:", e, file=sys.stderr)
        print("Install with: pip install opencv-python numpy", file=sys.stderr)
        return 1

    repo_root = Path(__file__).resolve().parent
    out_dir = repo_root / "stress_test_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.output is None:
        fps_tag = int(args.fps) if args.fps == int(args.fps) else args.fps
        out_path = out_dir / f"stress_1080p_{args.frames}f_{fps_tag}fps.mp4"
    else:
        out_path = args.output.resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(out_path), fourcc, args.fps, (args.width, args.height))
    if not writer.isOpened():
        print("ERROR: Could not open VideoWriter for", out_path, file=sys.stderr)
        return 1

    rng = np.random.default_rng(args.seed)
    total = args.frames
    t0 = time.time()

    for i in range(total):
        yy = np.linspace(0, 255, args.height, dtype=np.float32)[:, None]
        xx = np.linspace(0, 255, args.width, dtype=np.float32)[None, :]
        t = i / max(total - 1, 1)
        frame = np.zeros((args.height, args.width, 3), dtype=np.uint8)
        frame[:, :, 0] = ((xx + i * 7 + t * 40) % 256).astype(np.uint8)
        frame[:, :, 1] = ((yy + i * 11 + t * 60) % 256).astype(np.uint8)
        frame[:, :, 2] = (((xx + yy) / 2 + i * 13) % 256).astype(np.uint8)
        noise = rng.integers(-28, 29, (args.height, args.width, 3), dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        cv2.putText(
            frame,
            f"Stress 1080p frame {i + 1}/{total}",
            (48, 96),
            cv2.FONT_HERSHEY_SIMPLEX,
            1.4,
            (255, 255, 255),
            3,
            cv2.LINE_AA,
        )
        writer.write(frame)
        if (i + 1) % 60 == 0:
            print(f"  {i + 1}/{total} frames ({time.time() - t0:.1f}s)", flush=True)

    writer.release()

    cap = cv2.VideoCapture(str(out_path))
    if cap.isOpened():
        fc = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fw = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        fh = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps_r = cap.get(cv2.CAP_PROP_FPS)
        cap.release()
        probe = f"probe: {fw}x{fh} @ {fps_r:.2f} fps, frames={fc}"
    else:
        probe = "probe: failed"

    mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Done: {out_path}")
    print(f"  {args.width}x{args.height}, {total} frames @ {args.fps} fps (~{total / args.fps:.2f}s)")
    print(f"  Size: {mb:.2f} MB  Wall: {time.time() - t0:.1f}s")
    print(f"  {probe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
