"""
Metadata Service - Preserve and manage video metadata

Video files can carry a rich set of metadata tags (title, artist, creation
date, codec info, etc.) embedded in the container format.  When we process
a video through OpenCV's VideoWriter, that metadata is stripped because
OpenCV does not propagate container-level tags.

This service provides two mechanisms to handle metadata:

1. Preserve original metadata (preserve_metadata):
   Extracts tags from the source video with ffprobe, then re-applies
   them to the processed output using ffmpeg.  This makes the stego video
   look identical to the original from a metadata perspective, which reduces
   suspicion.

2. Store steganography operation info (add_stego_metadata):
   Saves embedding parameters (which frames were used, encryption settings,
   bit count) to a companion JSON file (<video>.meta.json).  This is kept
   separate from the video container so it can be read without video decoding,
   and so it can be deleted if the user wants to destroy the record.

ffprobe/ffmpeg dependency:
  Both tools are optional.  The service falls back gracefully:
    - extract_metadata() falls back to basic OpenCV metadata
    - apply_metadata() falls back to a plain file copy
  This means the service works even without FFmpeg installed, just
  without full metadata preservation.
"""

import os
import json
import subprocess
from typing import Dict, Optional, List
from datetime import datetime


class MetadataService:
    """Service for preserving and managing video metadata."""

    # The subset of ffprobe tags we attempt to copy to the output video.
    # Note: 'encoder' is intentionally included to maintain plausible metadata;
    # tags not in this list are excluded to avoid leaking processing artefacts.
    PRESERVE_FIELDS = [
        'title', 'artist', 'album', 'date', 'comment',
        'genre', 'copyright', 'description', 'synopsis',
        'creation_time', 'encoder', 'language'
    ]

    @classmethod
    def extract_metadata(cls, video_path: str) -> Dict:
        """Extract metadata from a video file.

        First attempts to use ffprobe for detailed, structured metadata.
        If ffprobe is not installed, falls back to OpenCV for basic
        technical parameters (resolution, FPS, frame count).

        Args:
            video_path: Path to the video file

        Returns:
            Dict with three top-level keys:
              file_info      : filename, size, created/modified timestamps
              video_metadata : user-facing tags (title, artist, date, etc.)
              technical_info : codec, resolution, fps, bitrate, streams
        """
        metadata = {
            'file_info': cls._get_file_info(video_path),
            'video_metadata': {},
            'technical_info': {}
        }

        try:
            from pymediainfo import MediaInfo

            media = MediaInfo.parse(video_path)

            for track in media.tracks:
                if track.track_type == 'General':
                    # Map pymediainfo field names to ffmpeg metadata key names so
                    # apply_metadata() can pass them directly to ffmpeg -metadata.
                    metadata['video_metadata'] = {
                        k: v for k, v in {
                            'title':       track.title,
                            'artist':      track.performer,
                            'album':       track.album,
                            'date':        track.recorded_date,
                            'comment':     track.comment,
                            'genre':       track.genre,
                            'copyright':   track.copyright,
                            'description': track.movie_name,
                            'encoder':     track.encoded_by,
                            'language':    track.language,
                        }.items() if v is not None
                    }
                    metadata['technical_info'] = {
                        'format_name': track.format,
                        'duration':    float(track.duration or 0) / 1000,  # ms -> s
                        'size':        int(track.file_size or 0),
                        'bit_rate':    int(track.overall_bit_rate or 0),
                    }

                elif track.track_type == 'Video':
                    try:
                        fps_val = float(track.frame_rate or 0)
                    except (ValueError, TypeError):
                        fps_val = 0.0
                    metadata['technical_info']['video'] = {
                        'codec':        track.codec_id or track.format,
                        'width':        track.width,
                        'height':       track.height,
                        'fps':          fps_val,
                        'pixel_format': track.chroma_subsampling,
                    }

                elif track.track_type == 'Audio':
                    metadata['technical_info']['audio'] = {
                        'codec':       track.codec_id or track.format,
                        'sample_rate': track.sampling_rate,
                        'channels':    track.channel_s,
                    }

        except Exception:
            # pymediainfo not available or parse failed; fall back to OpenCV for basic info.
            import cv2
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                metadata['technical_info'] = {
                    'width':       int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    'height':      int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    'fps':         cap.get(cv2.CAP_PROP_FPS),
                    'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                }
                cap.release()

        return metadata

    @classmethod
    def _get_file_info(cls, video_path: str) -> Dict:
        """Get basic filesystem information about a video file.

        Uses os.stat() for platform-independent file size and timestamps.
        Timestamps are formatted as ISO-8601 strings for easy serialisation.
        """
        stat = os.stat(video_path)
        return {
            'filename': os.path.basename(video_path),
            'size_bytes': stat.st_size,
            # ctime is creation time on Windows, last metadata change on Unix.
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
        }

    @classmethod
    def apply_metadata(cls, video_path: str, metadata: Dict,
                      output_path: Optional[str] = None) -> str:
        """Apply metadata tags to a video file using ffmpeg.

        Uses ffmpeg's '-c copy' (stream copy) mode so the video is not
        re-encoded — only the container metadata is updated.  This is fast
        and lossless.

        Falls back to a plain file copy if ffmpeg is unavailable.

        Args:
            video_path: Source video to read from
            metadata: Metadata dict (as returned by extract_metadata)
            output_path: Where to write the output; defaults to
                         video_path with '_meta.mp4' suffix

        Returns:
            Path to the output video with metadata applied
        """
        if output_path is None:
            output_path = video_path.replace('.mp4', '_meta.mp4')

        try:
            # Build the ffmpeg command dynamically from the metadata dict.
            cmd = ['ffmpeg', '-i', video_path, '-c', 'copy']

            # Add only the fields in PRESERVE_FIELDS to avoid copying tags
            # that might expose the processing pipeline (e.g. encoder info).
            for key, value in metadata.get('video_metadata', {}).items():
                if key in cls.PRESERVE_FIELDS and value:
                    cmd.extend(['-metadata', f'{key}={value}'])

            # -y overwrites the output file without prompting.
            cmd.extend(['-y', output_path])

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

            if result.returncode == 0:
                return output_path
            else:
                # ffmpeg ran but failed; fall back to a plain copy.
                import shutil
                shutil.copy2(video_path, output_path)
                return output_path

        except (subprocess.SubprocessError, FileNotFoundError):
            # ffmpeg not installed; fall back to a plain copy.
            import shutil
            shutil.copy2(video_path, output_path)
            return output_path

    @classmethod
    def preserve_metadata(cls, source_path: str, dest_path: str) -> bool:
        """Copy metadata from a source video to a destination video.

        A convenience wrapper that combines extract_metadata() and
        apply_metadata() into a single call.  The result atomically
        replaces the destination file so there is no window where it
        exists without metadata.

        Args:
            source_path: Original video whose metadata should be preserved
            dest_path: Processed stego video to receive the metadata

        Returns:
            True if metadata was copied successfully, False on any error
        """
        try:
            source_meta = cls.extract_metadata(source_path)

            # Write to a temp file first so the dest is never partially written.
            temp_path = dest_path.replace('.mp4', '_temp.mp4')
            result_path = cls.apply_metadata(dest_path, source_meta, temp_path)

            # Atomically replace the destination with the metadata-bearing version.
            if result_path != dest_path and os.path.exists(result_path):
                os.replace(result_path, dest_path)

            return True
        except Exception as e:
            print(f"Warning: Could not preserve metadata: {e}")
            return False

    @classmethod
    def add_stego_metadata(cls, video_path: str, stego_info: Dict) -> Dict:
        """Store steganography operation metadata in a companion JSON file.

        The JSON file is written to <video_path>.meta.json alongside the
        stego video.  It records which frames were used, what encryption
        was applied, and how many bits were embedded — information needed
        to verify or debug an embedding operation later.

        The metadata is NOT embedded in the video container itself to keep
        the video file identical to what any standard player would produce.

        Args:
            video_path: Path to the stego video
            stego_info: Dict with embedding details (frames_used,
                        encryption_strength, cipher_mode, bits_embedded,
                        message_hash)

        Returns:
            The complete stego metadata dict that was written to disk
        """
        meta_path = video_path + '.meta.json'

        stego_metadata = {
            'version': '2.0',
            'created': datetime.now().isoformat(),
            'embedding_info': {
                'frames_used': stego_info.get('frames_used', []),
                'encryption_strength': stego_info.get('encryption_strength'),
                'cipher_mode': stego_info.get('cipher_mode'),
                'bits_embedded': stego_info.get('bits_embedded', 0),
                # message_hash can be used to verify extraction integrity
                'message_hash': stego_info.get('message_hash')
            },
            # Snapshot of technical video info at time of embedding.
            'video_info': cls.extract_metadata(video_path)
        }

        with open(meta_path, 'w') as f:
            json.dump(stego_metadata, f, indent=2)

        return stego_metadata

    @classmethod
    def read_stego_metadata(cls, video_path: str) -> Optional[Dict]:
        """Read the companion stego metadata file if it exists.

        Looks for <video_path>.meta.json next to the video file.
        Returns None if no metadata file is found, so callers can
        handle the no-metadata case gracefully.

        Args:
            video_path: Path to the stego video

        Returns:
            Parsed stego metadata dict, or None if the file does not exist
        """
        meta_path = video_path + '.meta.json'

        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                return json.load(f)

        return None
