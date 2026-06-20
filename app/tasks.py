"""
Celery Tasks - Async processing for video steganography operations

This module defines:
  - celery_app : the Celery application instance (broker = Redis)
  - run_embed_pipeline()   : shared embed logic (used by both Celery and sync fallback)
  - run_extract_pipeline() : shared extract logic (same dual-path pattern)
  - embed_message_task     : @celery_app.task wrapper around run_embed_pipeline
  - extract_message_task   : @celery_app.task wrapper around run_extract_pipeline

Why separate pipeline functions from Celery tasks?
  When Redis is unavailable (e.g. in local dev without Docker) the route
  handlers call run_*_pipeline() directly and return results synchronously.
  This avoids requiring Redis for basic functionality while still supporting
  fully async operation in production.

Progress reporting:
  Celery tasks accept optional callback functions (read_progress,
  embed_progress, write_progress) so each pipeline stage can report
  its own 0-100% sub-progress.  The task maps these onto the overall
  0-100% scale and pushes updates via self.update_state().
"""

import os
from celery import Celery
from typing import List
from typing import Optional, Dict, Callable, Tuple

# ------------------------------------------------------------------ #
# Celery application setup
# ------------------------------------------------------------------ #

# Create the Celery application and connect it to the Redis broker.
# The same Redis instance is used as the result backend so task
# outcomes (success payloads / error messages) can be queried later.
celery_app = Celery('vidstega',
                    broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
                    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'))

# Configure serialization and time limits.
# json serializer is used instead of pickle for safety (no arbitrary
# Python object deserialization from the broker).
# task_time_limit=3600 hard-kills tasks that exceed 1 hour to prevent
# runaway workers from blocking queue slots.
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,      # 1 hour hard limit
    task_soft_time_limit=3300, # 55 min soft limit (raises SoftTimeLimitExceeded)
)


# ------------------------------------------------------------------ #
# Helper: normalize AI embed parameters
# ------------------------------------------------------------------ #

def _build_ai_embed_params(ai_options: Optional[Dict]) -> Tuple[Optional[Dict], int, str, Optional[str], Optional[str]]:
    """Normalize AI-related embed parameters.

    Resolves platform-level defaults (bit_position, channel_mode) and
    applies any explicit per-request overrides from the ai_options dict.

    Returns:
        regions_by_frame: Always None here (populated later in pipeline)
        bit_position: 0 for standard LSB, 1 for the 2nd-least-significant bit
        channel_mode: 'rgb' (all channels) or 'luma' (Y channel of YCrCb only)
        caption_style: Optional style string for caption generation
        platform: Optional platform name ('youtube', 'instagram', etc.)
    """
    if not ai_options:
        return None, 0, 'rgb', None, None

    platform = ai_options.get('smart_compression_platform') or None

    # Start with defaults, then apply platform-specific config.
    bit_position = 0
    channel_mode = 'rgb'
    if platform:
        try:
            from app.services.ai_service import AIService
            cfg = AIService.get_platform_config(platform)
            # Platforms like YouTube/Instagram prefer the 2nd LSB (more
            # robust against lossy re-encoding) and the luma channel
            # (less affected by chroma subsampling).
            bit_position = 1 if cfg.get('use_second_lsb') else 0
            channel_mode = 'luma' if cfg.get('prefer_luma') else 'rgb'
        except Exception:
            bit_position = 0
            channel_mode = 'rgb'

    # Allow the caller to override platform defaults explicitly.
    if ai_options.get('use_second_lsb') is True:
        bit_position = 1
    if ai_options.get('prefer_luma') is True:
        channel_mode = 'luma'
    if ai_options.get('prefer_luma') is False and 'prefer_luma' in ai_options:
        channel_mode = 'rgb'

    caption_style = ai_options.get('caption_style') or None
    return None, bit_position, channel_mode, caption_style, platform


# ------------------------------------------------------------------ #
# Shared embed pipeline
# ------------------------------------------------------------------ #

def run_embed_pipeline(*,
                       video_path: str,
                       message: str,
                       password: str,
                       frames: List[int],
                       encryption_strength: str,
                       cipher_mode: str,
                       output_folder: str,
                       ai_options: Optional[Dict] = None,
                       read_progress: Optional[Callable] = None,
                       embed_progress: Optional[Callable] = None,
                       write_progress: Optional[Callable] = None) -> Dict:
    """Embed pipeline used by both Celery and synchronous execution.

    Steps:
      1. Encrypt the message with AES (CryptoService.encrypt).
      2. Read the specified video frames into memory (VideoService.read_frames).
      3. Optionally run AI enhancements (detect suspicion, optimize for platform,
         content-aware region analysis, caption generation).
      4. Embed the encrypted bytes across the selected frames using LSB
         (SteganographyService.embed_message).
      5. Write the modified frames back to a new MP4 file, preserving
         the unmodified frames and audio (VideoService.write_video).
      6. Optionally re-run suspicion detection on the output frames.

    Returns a result dict containing output_file_id (used by /api/download),
    embedding statistics, encryption config, and AI metadata.
    """
    from app.services import CryptoService, VideoService, SteganographyService

    # Step 1: Encrypt the message.
    # encrypted_data is the raw ciphertext bundle (salt + IV/nonce + ciphertext).
    encrypted_data, _metadata = CryptoService.encrypt(
        message, password, encryption_strength, cipher_mode
    )

    # Step 2: Read the requested frames from disk.
    # VideoService returns a list of (frame_index, numpy_array) tuples.
    frame_data = VideoService.read_frames(video_path, frames, read_progress)
    if len(frame_data) == 0:
        raise ValueError("No valid frames could be read")

    # Resolve AI embedding parameters (bit plane, channel mode, etc.).
    regions_by_frame = None
    _unused, bit_position, channel_mode, caption_style, platform = _build_ai_embed_params(ai_options)

    caption = None
    suspicion_before = None
    suspicion_after = None

    # Step 3 (optional): Apply AI-powered enhancements.
    if ai_options:
        from app.services.ai_service import AIService

        # Run steganalysis on the first frame before embedding to provide
        # a baseline suspicion score the user can compare against.
        if ai_options.get('detect_suspicious'):
            try:
                suspicion_before = AIService.detect_steganography_patterns(frame_data[0][1])
            except Exception:
                suspicion_before = None

        # Platform optimization converts frames to the most robust color
        # space and region configuration for the target social media platform.
        if platform:
            optimized_frames = []
            for frame_idx, frame in frame_data:
                try:
                    optimized_frame, _cfg = AIService.optimize_for_social_media(frame, platform)
                    optimized_frames.append((frame_idx, optimized_frame))
                except Exception:
                    optimized_frames.append((frame_idx, frame))
            frame_data = optimized_frames

        # Content-aware embedding: analyse each frame to find high-texture
        # regions where hidden bits will be statistically less detectable.
        if ai_options.get('content_aware'):
            regions_by_frame = {}
            for frame_idx, frame in frame_data:
                try:
                    analysis = AIService.analyze_frame_for_embedding(frame)
                    regions_by_frame[frame_idx] = analysis.get('optimal_regions', [])
                except Exception:
                    regions_by_frame[frame_idx] = None

        # Generate an innocent-looking AI caption for the output video
        # so it doesn't arouse suspicion when shared.
        if ai_options.get('generate_caption'):
            try:
                import asyncio
                ai = AIService()
                style = caption_style or 'casual'
                caption = asyncio.run(ai.generate_innocent_caption(video_path, style=style))
            except Exception:
                caption = None

    # Step 4: Embed the encrypted bytes into the selected video frames
    # using Least-Significant-Bit substitution with Reed-Solomon protection.
    result = SteganographyService.embed_message(
        frame_data,
        encrypted_data,
        embed_progress,
        regions_by_frame=regions_by_frame,
        bit_position=bit_position,
        channel_mode=channel_mode
    )

    # Step 5: Write the output video.
    # A UUID output_id is generated to form the file name so it can later be
    # retrieved via GET /api/download/<output_id>.
    import uuid
    output_id = str(uuid.uuid4())
    output_path = os.path.join(output_folder, f"{output_id}_output.avi")
    final_path = VideoService.write_video(output_path, result['modified_frames'], video_path, write_progress)

    # Optional: re-run steganalysis on a sample of the modified frames to
    # show how suspicion score changed after embedding.
    if ai_options and ai_options.get('detect_suspicious'):
        try:
            from app.services.ai_service import AIService
            # Sample up to 3 modified frames to keep this step fast.
            sampled = list(result['modified_frames'].values())[:3]
            if sampled:
                suspicion_after = AIService.detect_steganography_patterns(sampled[0])
        except Exception:
            suspicion_after = None

    return {
        'success': True,
        'output_file_id': output_id,
        'output_path': final_path,
        'bits_embedded': result['bits_embedded'],
        'frames_used': result['frames_used'],
        'encryption_strength': encryption_strength,
        'cipher_mode': cipher_mode,
        'message_length': len(message),
        'ai': {
            'content_aware': bool(ai_options.get('content_aware')) if ai_options else False,
            'smart_compression_platform': platform,
            'bit_position': bit_position,
            'channel_mode': channel_mode,
            'caption': caption,
            'suspicion_before': suspicion_before,
            'suspicion_after': suspicion_after,
        }
    }


# ------------------------------------------------------------------ #
# Shared extract pipeline
# ------------------------------------------------------------------ #

def run_extract_pipeline(*,
                         video_path: str,
                         password: str,
                         start_frame: int,
                         end_frame: int,
                         encryption_strength: str,
                         cipher_mode: str,
                         ai_options: Optional[Dict] = None,
                         read_progress: Optional[Callable] = None,
                         extract_progress: Optional[Callable] = None) -> Dict:
    """Extract pipeline used by both Celery and synchronous execution.

    Steps:
      1. Validate that start_frame/end_frame are within the video bounds.
      2. Read the specified frame range from the stego video.
      3. Optionally apply the same AI options that were used during embedding
         (content-aware regions, platform settings) so extraction mirrors
         the embedding configuration exactly.
      4. Extract the hidden bit sequence from the frames (SteganographyService).
      5. Decrypt the extracted bytes to recover the original message.

    The caller MUST provide the same encryption_strength, cipher_mode, and
    AI options that were used during embedding, otherwise decryption will fail.
    """
    from app.services import CryptoService, VideoService, SteganographyService
    from app.services.ai_service import AIService

    # Step 1: Validate the frame range before reading any data.
    if not VideoService.validate_frame_range(video_path, start_frame, end_frame):
        raise ValueError("Invalid frame range for this video")

    # Build the list of frame indices to read (contiguous range).
    frame_indices = list(range(start_frame, end_frame))
    frame_data = VideoService.read_frames(video_path, frame_indices, read_progress)
    if len(frame_data) == 0:
        raise ValueError("No valid frames could be read")

    # Default extraction parameters (must match embedding parameters).
    regions_by_frame = None
    bit_position = 0
    channel_mode = 'rgb'
    suspicion = None

    # Step 3 (optional): Mirror the AI options used during embedding.
    if ai_options:
        # Apply platform-specific bit plane / channel mode settings.
        platform = ai_options.get('smart_compression_platform') or None
        if platform:
            cfg = AIService.get_platform_config(platform)
            bit_position = 1 if cfg.get('use_second_lsb') else 0
            channel_mode = 'luma' if cfg.get('prefer_luma') else 'rgb'

        # Explicit overrides take precedence over platform defaults.
        if ai_options.get('use_second_lsb') is True:
            bit_position = 1
        if ai_options.get('prefer_luma') is True:
            channel_mode = 'luma'
        if ai_options.get('prefer_luma') is False and 'prefer_luma' in ai_options:
            channel_mode = 'rgb'

        # Reconstruct the content-aware regions for the same frames.
        # This is necessary only when content_aware was used during embedding.
        if ai_options.get('content_aware'):
            regions_by_frame = {}
            for frame_idx, frame in frame_data:
                try:
                    analysis = AIService.analyze_frame_for_embedding(frame)
                    regions_by_frame[frame_idx] = analysis.get('optimal_regions', [])
                except Exception:
                    regions_by_frame[frame_idx] = None

        # Run steganalysis on the first frame to help the user assess risk.
        if ai_options.get('detect_suspicious'):
            try:
                suspicion = AIService.detect_steganography_patterns(frame_data[0][1])
            except Exception:
                suspicion = None

    # Step 4: Extract the raw (encrypted) bytes from the video frames.
    encrypted_data = SteganographyService.extract_message(
        frame_data,
        extract_progress,
        regions_by_frame=regions_by_frame,
        bit_position=bit_position,
        channel_mode=channel_mode
    )

    # Step 5: Decrypt the extracted bytes to recover the original plaintext.
    decrypted_message = CryptoService.decrypt(
        encrypted_data, password, encryption_strength, cipher_mode
    )

    return {
        'success': True,
        'message': decrypted_message,
        'frames_processed': len(frame_data),
        'data_size_bytes': len(encrypted_data),
        'ai': {
            'content_aware': bool(ai_options.get('content_aware')) if ai_options else False,
            'smart_compression_platform': ai_options.get('smart_compression_platform') if ai_options else None,
            'bit_position': bit_position,
            'channel_mode': channel_mode,
            'suspicion': suspicion
        }
    }


# ------------------------------------------------------------------ #
# Celery task: embed
# ------------------------------------------------------------------ #

@celery_app.task(bind=True)
def embed_message_task(self, video_path: str, message: str, password: str,
                       frames: List[int], encryption_strength: str,
                       cipher_mode: str, output_folder: str,
                       ai_options: Optional[Dict] = None) -> dict:
    """Async Celery task to embed an encrypted message into a video.

    bind=True gives access to `self` so the task can call
    self.update_state() to push progress updates to the result backend.
    Clients poll GET /api/task/<task_id> or receive WebSocket pushes
    to track progress from 0 -> 100%.

    Progress ranges:
      0-10%  : initialization
      10-45% : reading frames  (read_progress callback)
      50-70% : embedding data  (embed_progress callback)
      70-95% : writing video   (write_progress callback)
      100%   : complete

    Args:
        video_path: Path to source video on disk
        message: Plaintext message to embed
        password: Encryption password
        frames: List of frame indices to use for embedding
        encryption_strength: AES key size ('AES-128', 'AES-192', 'AES-256')
        cipher_mode: Block cipher mode ('CBC', 'CTR', 'GCM', 'CFB')
        output_folder: Directory to save the output video
        ai_options: Optional dict of AI feature flags

    Returns:
        Dict with result information (output_file_id, bits_embedded, etc.)
    """
    from app.services import CryptoService, VideoService, SteganographyService

    try:
        # Announce task start to the result backend.
        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'current_step': 'Initializing...'
        })

        # Progress callback for the frame-reading stage (maps to 10-45%).
        self.update_state(state='PROGRESS', meta={
            'progress': 10,
            'current_step': 'Reading video frames...'
        })

        def read_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 10 + (progress * 0.35),  # 10-45%
                'current_step': step
            })

        # Progress callback for the embedding stage (maps to 50-70%).
        self.update_state(state='PROGRESS', meta={
            'progress': 50,
            'current_step': 'Embedding encrypted data...'
        })

        def embed_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 50 + (progress * 0.2),  # 50-70%
                'current_step': step
            })

        # Progress callback for the video-writing stage (maps to 70-95%).
        self.update_state(state='PROGRESS', meta={
            'progress': 70,
            'current_step': 'Writing output video...'
        })

        def write_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 70 + (progress * 0.25),  # 70-95%
                'current_step': step
            })

        # Delegate to the shared pipeline function so the same logic is
        # reused whether executed asynchronously or synchronously.
        pipeline_result = run_embed_pipeline(
            video_path=video_path,
            message=message,
            password=password,
            frames=frames,
            encryption_strength=encryption_strength,
            cipher_mode=cipher_mode,
            output_folder=output_folder,
            ai_options=ai_options,
            read_progress=read_progress,
            embed_progress=embed_progress,
            write_progress=write_progress
        )

        # Mark as fully complete in the result backend.
        self.update_state(state='PROGRESS', meta={
            'progress': 100,
            'current_step': 'Complete!'
        })

        return pipeline_result

    except Exception as e:
        # Return structured error so the route handler can surface it.
        return {
            'success': False,
            'error': str(e)
        }


# ------------------------------------------------------------------ #
# Celery task: extract
# ------------------------------------------------------------------ #

@celery_app.task(bind=True)
def extract_message_task(self, video_path: str, password: str,
                         start_frame: int, end_frame: int,
                         encryption_strength: str, cipher_mode: str,
                         ai_options: Optional[Dict] = None) -> dict:
    """Async Celery task to extract a hidden message from a video.

    Mirrors embed_message_task in structure.  Decryption requires the
    same password and cipher settings that were used during embedding.

    Progress ranges:
      0-5%   : initialization / frame validation
      10-50% : reading frames  (read_progress callback)
      55-80% : extracting data (extract_progress callback)
      85%    : decryption
      100%   : complete

    Args:
        video_path: Path to the stego video on disk
        password: Decryption password
        start_frame: First frame index to read (inclusive)
        end_frame: Last frame index to read (exclusive)
        encryption_strength: AES key size used during embedding
        cipher_mode: Block cipher mode used during embedding
        ai_options: Optional dict matching the AI options used at embed time

    Returns:
        Dict with the decrypted message and processing statistics
    """
    from app.services import CryptoService, VideoService, SteganographyService

    try:
        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'current_step': 'Initializing...'
        })

        # Validate the frame range before attempting to read any data.
        self.update_state(state='PROGRESS', meta={
            'progress': 5,
            'current_step': 'Validating video...'
        })

        if not VideoService.validate_frame_range(video_path, start_frame, end_frame):
            raise ValueError("Invalid frame range for this video")

        # Progress callback for frame reading (maps to 10-50%).
        self.update_state(state='PROGRESS', meta={
            'progress': 10,
            'current_step': 'Reading video frames...'
        })

        def read_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 10 + (progress * 0.4),  # 10-50%
                'current_step': step
            })

        # Progress callback for the bit-extraction stage (maps to 55-80%).
        self.update_state(state='PROGRESS', meta={
            'progress': 55,
            'current_step': 'Extracting hidden data...'
        })

        def extract_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 55 + (progress * 0.25),  # 55-80%
                'current_step': step
            })

        # Delegate to the shared pipeline function.
        pipeline_result = run_extract_pipeline(
            video_path=video_path,
            password=password,
            start_frame=start_frame,
            end_frame=end_frame,
            encryption_strength=encryption_strength,
            cipher_mode=cipher_mode,
            ai_options=ai_options,
            read_progress=read_progress,
            extract_progress=extract_progress
        )

        # Update state while decryption completes (inside pipeline above).
        self.update_state(state='PROGRESS', meta={
            'progress': 85,
            'current_step': 'Decrypting message...'
        })

        self.update_state(state='PROGRESS', meta={
            'progress': 100,
            'current_step': 'Complete!'
        })

        return pipeline_result

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }
