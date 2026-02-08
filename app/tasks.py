"""
Celery Tasks - Async processing for video steganography operations
"""

import os
from celery import Celery
from typing import List
from typing import Optional, Dict, Callable, Tuple

# Create Celery app
celery_app = Celery('vidstega',
                    broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
                    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'))

# Celery configuration
celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour max
    task_soft_time_limit=3300,  # 55 minutes soft limit
)


def _build_ai_embed_params(ai_options: Optional[Dict]) -> Tuple[Optional[Dict], int, str, Optional[str], Optional[str]]:
    """Normalize AI-related embed parameters.

    Returns:
        regions_by_frame: Optional mapping frame_index -> regions list
        bit_position: 0 for LSB, 1 for 2nd LSB
        channel_mode: 'rgb' or 'luma'
        caption_style: Optional string
        platform: Optional platform name
    """
    if not ai_options:
        return None, 0, 'rgb', None, None

    platform = ai_options.get('smart_compression_platform') or None

    bit_position = 0
    channel_mode = 'rgb'
    if platform:
        try:
            from app.services.ai_service import AIService
            cfg = AIService.get_platform_config(platform)
            bit_position = 1 if cfg.get('use_second_lsb') else 0
            channel_mode = 'luma' if cfg.get('prefer_luma') else 'rgb'
        except Exception:
            bit_position = 0
            channel_mode = 'rgb'

    # Allow explicit overrides
    if ai_options.get('use_second_lsb') is True:
        bit_position = 1
    if ai_options.get('prefer_luma') is True:
        channel_mode = 'luma'
    if ai_options.get('prefer_luma') is False and 'prefer_luma' in ai_options:
        channel_mode = 'rgb'

    caption_style = ai_options.get('caption_style') or None
    return None, bit_position, channel_mode, caption_style, platform


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
    """Embed pipeline used by both Celery and synchronous execution."""
    from app.services import CryptoService, VideoService, SteganographyService

    encrypted_data, _metadata = CryptoService.encrypt(
        message, password, encryption_strength, cipher_mode
    )

    frame_data = VideoService.read_frames(video_path, frames, read_progress)
    if len(frame_data) == 0:
        raise ValueError("No valid frames could be read")

    regions_by_frame = None
    _unused, bit_position, channel_mode, caption_style, platform = _build_ai_embed_params(ai_options)

    caption = None
    suspicion_before = None
    suspicion_after = None

    if ai_options:
        from app.services.ai_service import AIService

        if ai_options.get('detect_suspicious'):
            try:
                suspicion_before = AIService.detect_steganography_patterns(frame_data[0][1])
            except Exception:
                suspicion_before = None

        if platform:
            optimized_frames = []
            for frame_idx, frame in frame_data:
                try:
                    optimized_frame, _cfg = AIService.optimize_for_social_media(frame, platform)
                    optimized_frames.append((frame_idx, optimized_frame))
                except Exception:
                    optimized_frames.append((frame_idx, frame))
            frame_data = optimized_frames

        if ai_options.get('content_aware'):
            regions_by_frame = {}
            for frame_idx, frame in frame_data:
                try:
                    analysis = AIService.analyze_frame_for_embedding(frame)
                    regions_by_frame[frame_idx] = analysis.get('optimal_regions', [])
                except Exception:
                    regions_by_frame[frame_idx] = None

        if ai_options.get('generate_caption'):
            try:
                import asyncio
                ai = AIService()
                style = caption_style or 'casual'
                caption = asyncio.run(ai.generate_innocent_caption(video_path, style=style))
            except Exception:
                caption = None

    result = SteganographyService.embed_message(
        frame_data,
        encrypted_data,
        embed_progress,
        regions_by_frame=regions_by_frame,
        bit_position=bit_position,
        channel_mode=channel_mode
    )

    import uuid
    output_id = str(uuid.uuid4())
    output_path = os.path.join(output_folder, f"{output_id}_output.mp4")
    final_path = VideoService.write_video(output_path, result['modified_frames'], video_path, write_progress)

    if ai_options and ai_options.get('detect_suspicious'):
        try:
            from app.services.ai_service import AIService
            # sample up to 3 modified frames
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
    """Extract pipeline used by both Celery and synchronous execution."""
    from app.services import CryptoService, VideoService, SteganographyService
    from app.services.ai_service import AIService

    if not VideoService.validate_frame_range(video_path, start_frame, end_frame):
        raise ValueError("Invalid frame range for this video")

    frame_indices = list(range(start_frame, end_frame))
    frame_data = VideoService.read_frames(video_path, frame_indices, read_progress)
    if len(frame_data) == 0:
        raise ValueError("No valid frames could be read")

    regions_by_frame = None
    bit_position = 0
    channel_mode = 'rgb'
    suspicion = None

    if ai_options:
        platform = ai_options.get('smart_compression_platform') or None
        if platform:
            cfg = AIService.get_platform_config(platform)
            bit_position = 1 if cfg.get('use_second_lsb') else 0
            channel_mode = 'luma' if cfg.get('prefer_luma') else 'rgb'

        if ai_options.get('use_second_lsb') is True:
            bit_position = 1
        if ai_options.get('prefer_luma') is True:
            channel_mode = 'luma'
        if ai_options.get('prefer_luma') is False and 'prefer_luma' in ai_options:
            channel_mode = 'rgb'

        if ai_options.get('content_aware'):
            regions_by_frame = {}
            for frame_idx, frame in frame_data:
                try:
                    analysis = AIService.analyze_frame_for_embedding(frame)
                    regions_by_frame[frame_idx] = analysis.get('optimal_regions', [])
                except Exception:
                    regions_by_frame[frame_idx] = None

        if ai_options.get('detect_suspicious'):
            try:
                suspicion = AIService.detect_steganography_patterns(frame_data[0][1])
            except Exception:
                suspicion = None

    encrypted_data = SteganographyService.extract_message(
        frame_data,
        extract_progress,
        regions_by_frame=regions_by_frame,
        bit_position=bit_position,
        channel_mode=channel_mode
    )

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


@celery_app.task(bind=True)
def embed_message_task(self, video_path: str, message: str, password: str,
                       frames: List[int], encryption_strength: str,
                       cipher_mode: str, output_folder: str,
                       ai_options: Optional[Dict] = None) -> dict:
    """
    Async task to embed encrypted message into video.
    
    Args:
        video_path: Path to source video
        message: Message to embed
        password: Encryption password
        frames: List of frame indices to use
        encryption_strength: AES key size (AES-128, AES-192, AES-256)
        cipher_mode: Block cipher mode (CBC, CTR, GCM, CFB)
        output_folder: Folder for output video
        
    Returns:
        Dict with result information
    """
    from app.services import CryptoService, VideoService, SteganographyService
    
    try:
        # Update state: Starting
        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'current_step': 'Initializing...'
        })
        
        # Step 1: Read frames from video
        self.update_state(state='PROGRESS', meta={
            'progress': 10,
            'current_step': 'Reading video frames...'
        })
        
        def read_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 10 + (progress * 0.35),  # 10-45%
                'current_step': step
            })

        # Step 2: Embed message in frames
        self.update_state(state='PROGRESS', meta={
            'progress': 50,
            'current_step': 'Embedding encrypted data...'
        })
        
        def embed_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 50 + (progress * 0.2),  # 50-70%
                'current_step': step
            })

        # Step 3: Write output video
        self.update_state(state='PROGRESS', meta={
            'progress': 70,
            'current_step': 'Writing output video...'
        })
        
        def write_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 70 + (progress * 0.25),  # 70-95%
                'current_step': step
            })

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
        
        # Step 5: Complete
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


@celery_app.task(bind=True)
def extract_message_task(self, video_path: str, password: str,
                         start_frame: int, end_frame: int,
                         encryption_strength: str, cipher_mode: str,
                         ai_options: Optional[Dict] = None) -> dict:
    """
    Async task to extract message from video.
    
    Args:
        video_path: Path to stego video
        password: Decryption password
        start_frame: Starting frame index
        end_frame: Ending frame index
        encryption_strength: AES key size used during embedding
        cipher_mode: Block cipher mode used during embedding
        
    Returns:
        Dict with extracted message
    """
    from app.services import CryptoService, VideoService, SteganographyService
    
    try:
        # Update state: Starting
        self.update_state(state='PROGRESS', meta={
            'progress': 0,
            'current_step': 'Initializing...'
        })
        
        # Step 1: Validate video
        self.update_state(state='PROGRESS', meta={
            'progress': 5,
            'current_step': 'Validating video...'
        })
        
        if not VideoService.validate_frame_range(video_path, start_frame, end_frame):
            raise ValueError("Invalid frame range for this video")
        
        # Step 2: Read frames
        self.update_state(state='PROGRESS', meta={
            'progress': 10,
            'current_step': 'Reading video frames...'
        })

        def read_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 10 + (progress * 0.4),  # 10-50%
                'current_step': step
            })

        # Step 3: Extract encrypted data
        self.update_state(state='PROGRESS', meta={
            'progress': 55,
            'current_step': 'Extracting hidden data...'
        })
        
        def extract_progress(progress, step):
            self.update_state(state='PROGRESS', meta={
                'progress': 55 + (progress * 0.25),  # 55-80%
                'current_step': step
            })

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

        # Step 4: Decrypt message
        self.update_state(state='PROGRESS', meta={
            'progress': 85,
            'current_step': 'Decrypting message...'
        })

        # Step 5: Complete
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
