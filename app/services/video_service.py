"""
Video Service - Handles video file operations and metadata extraction
Supports resolutions up to 1440p

Responsibilities:
  - Open and inspect video files with OpenCV (cv2)
  - Calculate how much steganographic data can fit in a set of frames
  - Read specific frames by index for embedding or extraction
  - Write the modified frames back to a new video file, copying unmodified
    frames from the original and re-attaching the audio track

OpenCV is used for frame-level I/O because it supports a wide range of
codecs and provides low-level access to individual frames.  MoviePy is
used optionally for audio transfer because OpenCV's VideoWriter does not
write audio streams.
"""

import cv2
import os
from typing import Callable, Dict, List, Optional, Tuple
import numpy as np


class VideoService:
    """Service for video operations."""

    # Resolution lookup used by _categorize_resolution().
    # Maps human-readable names to (width, height) tuples.
    RESOLUTIONS = {
        '480p': (854, 480),
        '720p': (1280, 720),
        '1080p': (1920, 1080),
        '1440p': (2560, 1440)
    }

    # Number of bits that can be embedded per channel per pixel (LSB = 1).
    BITS_PER_CHANNEL = 1

    @classmethod
    def get_video_info(cls, video_path: str) -> Dict:
        """Get comprehensive video metadata.

        Opens the video with OpenCV, reads property values, and computes
        embedding capacity.  The capacity figures are raw (before ECC and
        encryption overhead); use calculate_capacity() for usable capacity.

        Args:
            video_path: Absolute or relative path to the video file

        Returns:
            Dictionary containing width, height, resolution category, fps,
            total_frames, duration_seconds, capacity_per_frame_bytes,
            total_capacity_bytes, file_size_bytes, and codec name.
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")

        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise ValueError("Could not open video file")

        try:
            # Read core video properties from OpenCV property constants.
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0

            # Map raw dimensions to a human-readable resolution label.
            resolution = cls._categorize_resolution(width, height)

            # Raw LSB capacity: every pixel channel can hold 1 bit.
            # Divide by 8 to convert bits -> bytes.
            capacity_per_frame_bits = width * height * 3 * cls.BITS_PER_CHANNEL
            capacity_per_frame_bytes = capacity_per_frame_bits // 8

            file_size = os.path.getsize(video_path)

            return {
                'width': width,
                'height': height,
                'resolution': resolution,
                'fps': round(fps, 2),
                'total_frames': total_frames,
                'duration_seconds': round(duration, 2),
                'capacity_per_frame_bytes': capacity_per_frame_bytes,
                'total_capacity_bytes': capacity_per_frame_bytes * total_frames,
                'file_size_bytes': file_size,
                'codec': cls._get_codec_name(cap)
            }
        finally:
            cap.release()

    @classmethod
    def _categorize_resolution(cls, width: int, height: int) -> str:
        """Categorize video resolution into a human-readable label.

        Comparison is done on both width and height so portrait-orientation
        videos are handled correctly.
        """
        if height >= 1440 or width >= 2560:
            return '1440p'
        elif height >= 1080 or width >= 1920:
            return '1080p'
        elif height >= 720 or width >= 1280:
            return '720p'
        else:
            return '480p'

    @classmethod
    def _get_codec_name(cls, cap: cv2.VideoCapture) -> str:
        """Decode the fourcc integer into a human-readable codec name.

        OpenCV stores the codec as a 32-bit int; each byte is one ASCII
        character of the four-character code (e.g. 0x34504D58 -> 'XMP4').
        """
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
        return codec.strip() or 'Unknown'

    @classmethod
    def calculate_capacity(cls, video_path: str,
                          frames: Optional[List[int]] = None) -> Dict:
        """Calculate embedding capacity for specified frames.

        Returns both raw and usable capacity figures.  Usable capacity
        subtracts:
          - ~10% for Reed-Solomon ECC overhead
          - 48 bytes fixed overhead for AES salt + IV/nonce + optional tag

        Args:
            video_path: Path to video file
            frames: List of frame indices to include; None means all frames

        Returns:
            Dict with total_capacity_bytes, usable_capacity_bytes,
            usable_capacity_kb, usable_capacity_mb, frame_count,
            capacity_per_frame_bytes, and max_characters.
        """
        video_info = cls.get_video_info(video_path)

        if frames is None or len(frames) == 0:
            # Use all frames in the video.
            frame_count = video_info['total_frames']
        else:
            # Validate each requested frame index against total_frames and
            # count only valid ones (silently ignore out-of-range indices).
            valid_frames = [f for f in frames if 0 <= f < video_info['total_frames']]
            frame_count = len(valid_frames)

        capacity_per_frame = video_info['capacity_per_frame_bytes']
        total_capacity = capacity_per_frame * frame_count

        # Reed-Solomon appends ~10% ECC check symbols, so usable payload
        # is approximately 90% of raw capacity.
        usable_capacity = int(total_capacity * 0.9)

        # AES encryption adds a fixed 48-byte header regardless of message
        # length (16-byte salt + 16-byte IV/nonce + 16-byte GCM auth tag).
        encryption_overhead = 48

        return {
            'total_capacity_bytes': total_capacity,
            'usable_capacity_bytes': max(0, usable_capacity - encryption_overhead),
            'usable_capacity_kb': round((usable_capacity - encryption_overhead) / 1024, 2),
            'usable_capacity_mb': round((usable_capacity - encryption_overhead) / (1024 * 1024), 4),
            'frame_count': frame_count,
            'capacity_per_frame_bytes': capacity_per_frame,
            # Approximate maximum UTF-8 characters (1 byte per ASCII char).
            'max_characters': max(0, usable_capacity - encryption_overhead)
        }

    @classmethod
    def read_frames(cls, video_path: str,
                   frame_indices: List[int],
                   progress_callback: Optional[Callable] = None) -> List[Tuple[int, np.ndarray]]:
        """Read specific frames from a video file.

        Uses CAP_PROP_POS_FRAMES to seek directly to each requested index
        rather than reading every frame sequentially.  Deduplicates and
        sorts the index list to avoid unnecessary seeks.

        Args:
            video_path: Path to video file
            frame_indices: List of frame indices to read (0-based)
            progress_callback: Optional fn(progress%, step_str) for UI updates

        Returns:
            List of (frame_index, frame_data) tuples for successfully read frames.
            Frames that could not be read (seek failure) are silently skipped.
        """
        cap = cv2.VideoCapture(video_path)

        if not cap.isOpened():
            raise ValueError("Could not open video file")

        frames = []
        # Deduplicate and sort so seeks are monotonically increasing,
        # which is more efficient for many container formats.
        frame_indices = sorted(set(frame_indices))

        try:
            for i, frame_idx in enumerate(frame_indices):
                cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
                ret, frame = cap.read()

                if ret:
                    frames.append((frame_idx, frame))

                if progress_callback:
                    progress = ((i + 1) / len(frame_indices)) * 100
                    progress_callback(progress, f"Reading frame {frame_idx}")
        finally:
            cap.release()

        return frames

    @classmethod
    def _read_nth_frame_bgr(cls, path: str, index: int) -> Tuple[bool, Optional[np.ndarray]]:
        """Read frame `index` by sequential decode (seeks are unreliable on some AVI backends)."""
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            return False, None
        try:
            frame = None
            for _ in range(index + 1):
                ok, frame = cap.read()
                if not ok:
                    return False, None
            return True, frame
        finally:
            cap.release()

    @classmethod
    def _verify_lossless_sample(cls, output_path: str, source_path: str,
                                modified: Dict[int, np.ndarray], total_frames: int) -> bool:
        """Confirm one frame survived encode/decode bit-identically (lossless pipeline)."""
        if total_frames <= 0 or not os.path.isfile(output_path):
            return False
        if os.path.getsize(output_path) < 64:
            return False
        pick = next((i for i in range(total_frames) if i not in modified), None)
        if pick is None:
            pick = 0
            ok_e, expected = True, modified[0]
        else:
            ok_e, expected = cls._read_nth_frame_bgr(source_path, pick)
        if not ok_e or expected is None:
            return False
        ok_a, actual = cls._read_nth_frame_bgr(output_path, pick)
        return (
            ok_a and actual is not None
            and expected.shape == actual.shape
            and np.array_equal(actual, expected)
        )

    @classmethod
    def _verify_all_frames_match(cls, output_path: str, expected_frames: List[np.ndarray]) -> bool:
        cap = cv2.VideoCapture(output_path)
        if not cap.isOpened():
            return False
        try:
            for exp in expected_frames:
                ok, fr = cap.read()
                if not ok or fr.shape != exp.shape or not np.array_equal(fr, exp):
                    return False
            return True
        finally:
            cap.release()

    @classmethod
    def write_video(cls, output_path: str,
                   frames: Dict[int, np.ndarray],
                   source_video_path: str,
                   progress_callback: Optional[Callable] = None) -> str:
        """Write frames back to a new video file.

        Iterates over every frame in the source video in order.  If a
        modified frame exists in `frames` for the current index, it is
        written instead of the original.  This preserves all unmodified
        frames perfectly, minimising visual differences between the cover
        and the stego video.

        H.264 (avc1) is preferred as the output codec because it is the
        most widely supported format for web playback.  If avc1 is
        unavailable on the system, the code falls back to mp4v (MPEG-4).

        Audio is copied from the source using MoviePy after the video
        frames have been written.  This is a separate step because OpenCV's
        VideoWriter cannot encode audio streams.

        Args:
            output_path: Desired output file path (will have .mp4 appended)
            frames: Dict of {frame_index: modified_frame_array}
            source_video_path: Original video to copy unmodified frames from
            progress_callback: Optional fn(progress%, step_str) for UI updates

        Returns:
            Path to the written output video file
        """
        cap = cv2.VideoCapture(source_video_path)

        if not cap.isOpened():
            raise ValueError("Could not open source video")

        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        fps = float(cap.get(cv2.CAP_PROP_FPS))
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        # Windows / synthetic clips often report FPS 0; VideoWriter then misbehaves or picks wrong codec path.
        if not fps or fps < 1e-6:
            fps = 30.0

        dest_path = os.path.splitext(output_path)[0] + '.avi'

        out = None
        try:
            # LSB steganography requires lossless output; lossy MP4 codecs corrupt payload bits.
            for codec in ('FFV1', 'HFYU', 'DIB '):
                fourcc = cv2.VideoWriter_fourcc(*codec)
                candidate = cv2.VideoWriter(dest_path, fourcc, fps, (width, height))
                if candidate.isOpened():
                    out = candidate
                    break
                candidate.release()

            if out is not None:
                try:
                    for frame_idx in range(total_frames):
                        ret, frame = cap.read()
                        if not ret:
                            break
                        out.write(frames[frame_idx] if frame_idx in frames else frame)
                        if progress_callback:
                            progress = ((frame_idx + 1) / total_frames) * 100
                            progress_callback(progress, f"Writing frame {frame_idx + 1}/{total_frames}")
                finally:
                    out.release()
                # Windows builds sometimes report an opened writer but emit a broken stream; verify.
                if cls._verify_lossless_sample(dest_path, source_video_path, frames, total_frames):
                    return dest_path
                try:
                    os.remove(dest_path)
                except OSError:
                    pass
        finally:
            cap.release()

        # OpenCV wheel often lacks FFV1/HFYU on Windows; reader path may still probe OpenH264 for MP4 elsewhere.
        cap2 = cv2.VideoCapture(source_video_path)
        composed: List[np.ndarray] = []
        try:
            if not cap2.isOpened():
                raise ValueError("Could not reopen source video for lossless fallback encode")
            for frame_idx in range(total_frames):
                ret, frame = cap2.read()
                if not ret:
                    break
                composed.append(
                    frames[frame_idx].copy() if frame_idx in frames else frame.copy()
                )
        finally:
            cap2.release()

        if not composed:
            raise ValueError("Could not read frames for lossless video fallback")

        try:
            written = cls._write_lossless_imageio_ffv1(dest_path, composed, fps)
            if not cls._verify_all_frames_match(written, composed):
                try:
                    os.remove(written)
                except OSError:
                    pass
                raise ValueError(
                    "imageio FFV1 output failed pixel-identical verification with OpenCV decode"
                )
            return written
        except Exception as e:
            raise ValueError(
                "Could not create lossless stego video (OpenCV codecs unavailable or corrupt output, "
                "and imageio/ffmpeg fallback failed verification). On Windows: pip install -U "
                "imageio imageio-ffmpeg moviepy, or run under WSL/Linux. "
                f"Detail: {e}"
            ) from e

    @classmethod
    def _write_lossless_imageio_ffv1(cls, output_path: str,
                                     composed_frames: List[np.ndarray],
                                     fps: float) -> str:
        """Fallback lossless writer using imageio + bundled ffmpeg (helps Windows OpenCV builds)."""
        import imageio.v2 as imageio

        output_path = os.path.splitext(output_path)[0] + '.avi'
        rgb = [cv2.cvtColor(f, cv2.COLOR_BGR2RGB) for f in composed_frames]
        try:
            imageio.mimwrite(
                output_path,
                rgb,
                fps=fps,
                codec='ffv1',
                format='FFMPEG',
            )
        except Exception:
            writer = imageio.get_writer(
                output_path,
                format='FFMPEG',
                mode='I',
                fps=fps,
                codec='ffv1',
            )
            try:
                for frame in rgb:
                    writer.append_data(frame)
            finally:
                writer.close()
        return output_path

    @classmethod
    def _copy_audio(cls, source_path: str, dest_path: str):
        """Copy audio from source video to destination using ffmpeg stream copy."""
        import subprocess

        # Use ffmpeg to mux audio without re-encoding the video stream
        # -c:v copy preserves the lossless FFV1 video exactly
        # -c:a pcm_s16le uses uncompressed audio suitable for AVI container
        base, ext = os.path.splitext(dest_path)
        temp_path = base + '_with_audio' + ext

        try:
            result = subprocess.run(
                [
                    'ffmpeg', '-y',
                    '-i', dest_path,       # lossless stego video
                    '-i', source_path,      # original video with audio
                    '-c:v', 'copy',         # do NOT re-encode video
                    '-c:a', 'pcm_s16le',    # uncompressed audio for AVI
                    '-map', '0:v:0',        # video from stego file
                    '-map', '1:a:0',        # audio from source file
                    temp_path
                ],
                capture_output=True, text=True, timeout=120
            )

            if result.returncode == 0 and os.path.exists(temp_path):
                os.replace(temp_path, dest_path)
            else:
                # Source may have no audio track; clean up temp file
                if os.path.exists(temp_path):
                    os.remove(temp_path)
        except FileNotFoundError:
            pass  # ffmpeg not installed
        except subprocess.TimeoutExpired:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    
    @classmethod
    def validate_frame_range(cls, video_path: str,
                            start_frame: int,
                            end_frame: int) -> bool:
        """Validate if a frame range is valid for the given video.

        Checks that both indices are within [0, total_frames) and that
        start_frame < end_frame.  Returns False on any error (e.g. the
        file cannot be opened) rather than raising an exception, so
        callers can handle it gracefully.

        Args:
            video_path: Path to video file
            start_frame: First frame index (inclusive)
            end_frame: Last frame index (exclusive)

        Returns:
            True if the range is valid, False otherwise
        """
        try:
            video_info = cls.get_video_info(video_path)
            total_frames = video_info['total_frames']

            return (0 <= start_frame < total_frames and
                    0 <= end_frame <= total_frames and
                    start_frame < end_frame)
        except Exception:
            return False
