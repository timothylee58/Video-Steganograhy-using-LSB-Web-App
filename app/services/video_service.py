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
from typing import Dict, List, Optional, Tuple, Callable
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

        try:
            # Read video properties to configure the output writer.
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Force .mp4 extension so the container format is consistent.
            if not output_path.lower().endswith('.mp4'):
                output_path += '.mp4'

            # Try H.264 first; fall back to MPEG-4 if avc1 is unavailable.
            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            if not out.isOpened():
                # Fallback to mp4v codec
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))

            # Write all frames: modified or original.
            for frame_idx in range(total_frames):
                if frame_idx in frames:
                    # Write the stego frame (LSB-modified version).
                    out.write(frames[frame_idx])
                else:
                    # Read and write the unmodified original frame.
                    ret, frame = cap.read()
                    if ret:
                        out.write(frame)

                if progress_callback:
                    progress = ((frame_idx + 1) / total_frames) * 100
                    progress_callback(progress, f"Writing frame {frame_idx + 1}/{total_frames}")

            out.release()

        finally:
            cap.release()

        # Copy audio from the source video to the output.
        # This is attempted after the video writer is closed to avoid
        # file locking issues on some platforms.
        try:
            cls._copy_audio(source_video_path, output_path)
        except Exception as e:
            print(f"Warning: Could not copy audio: {e}")

        return output_path

    @classmethod
    def _copy_audio(cls, source_path: str, dest_path: str):
        """Copy audio from source video to destination using MoviePy.

        MoviePy loads both videos, attaches the source audio to the
        destination clip, and writes a new file.  The original destination
        file is then atomically replaced with the audio-bearing version.

        Falls back silently if MoviePy is not installed or the source
        has no audio track.
        """
        try:
            from moviepy.editor import VideoFileClip

            source_clip = VideoFileClip(source_path)

            if source_clip.audio is not None:
                dest_clip = VideoFileClip(dest_path)
                final_clip = dest_clip.set_audio(source_clip.audio)

                # Write to a temp path first so we can atomically replace
                # the destination file only if the write succeeds.
                temp_path = dest_path.replace('.mp4', '_with_audio.mp4')
                final_clip.write_videofile(temp_path, codec='libx264', audio_codec='aac',
                                          verbose=False, logger=None)

                # Clean up clips before replacing the file to avoid
                # file-handle conflicts on Windows.
                dest_clip.close()
                source_clip.close()
                final_clip.close()

                os.replace(temp_path, dest_path)
            else:
                source_clip.close()

        except ImportError:
            pass  # moviepy not installed; video will be written without audio.

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
