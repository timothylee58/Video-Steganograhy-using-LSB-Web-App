"""
Video Service - Handles video file operations and metadata extraction
Supports resolutions up to 1440p
"""

import cv2
import os
from typing import Dict, List, Optional, Tuple, Callable
import numpy as np


class VideoService:
    """Service for video operations."""
    
    # Resolution definitions
    RESOLUTIONS = {
        '480p': (854, 480),
        '720p': (1280, 720),
        '1080p': (1920, 1080),
        '1440p': (2560, 1440)
    }
    
    # Bits per pixel per channel for LSB
    BITS_PER_CHANNEL = 1
    
    @classmethod
    def get_video_info(cls, video_path: str) -> Dict:
        """
        Get comprehensive video metadata.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary with video information
        """
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video file not found: {video_path}")
        
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError("Could not open video file")
        
        try:
            # Extract metadata
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            duration = total_frames / fps if fps > 0 else 0
            
            # Determine resolution category
            resolution = cls._categorize_resolution(width, height)
            
            # Calculate capacity per frame (bits)
            capacity_per_frame_bits = width * height * 3 * cls.BITS_PER_CHANNEL
            capacity_per_frame_bytes = capacity_per_frame_bits // 8
            
            # File size
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
        """Categorize video resolution."""
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
        """Get codec name from fourcc code."""
        fourcc = int(cap.get(cv2.CAP_PROP_FOURCC))
        codec = "".join([chr((fourcc >> 8 * i) & 0xFF) for i in range(4)])
        return codec.strip() or 'Unknown'
    
    @classmethod
    def calculate_capacity(cls, video_path: str, 
                          frames: Optional[List[int]] = None) -> Dict:
        """
        Calculate embedding capacity for specified frames.
        
        Args:
            video_path: Path to video file
            frames: List of frame indices (if None, calculate for all frames)
            
        Returns:
            Dictionary with capacity information
        """
        video_info = cls.get_video_info(video_path)
        
        if frames is None or len(frames) == 0:
            frame_count = video_info['total_frames']
        else:
            # Validate frames
            valid_frames = [f for f in frames if 0 <= f < video_info['total_frames']]
            frame_count = len(valid_frames)
        
        capacity_per_frame = video_info['capacity_per_frame_bytes']
        total_capacity = capacity_per_frame * frame_count
        
        # Account for error correction overhead (Reed-Solomon)
        # Approximately 10% overhead for RS(255, 223)
        usable_capacity = int(total_capacity * 0.9)
        
        # Account for encryption overhead (salt, IV, tag for GCM)
        # Approximately 48 bytes fixed overhead
        encryption_overhead = 48
        
        return {
            'total_capacity_bytes': total_capacity,
            'usable_capacity_bytes': max(0, usable_capacity - encryption_overhead),
            'usable_capacity_kb': round((usable_capacity - encryption_overhead) / 1024, 2),
            'usable_capacity_mb': round((usable_capacity - encryption_overhead) / (1024 * 1024), 4),
            'frame_count': frame_count,
            'capacity_per_frame_bytes': capacity_per_frame,
            'max_characters': max(0, usable_capacity - encryption_overhead)  # UTF-8 chars
        }
    
    @classmethod
    def read_frames(cls, video_path: str, 
                   frame_indices: List[int],
                   progress_callback: Optional[Callable] = None) -> List[Tuple[int, np.ndarray]]:
        """
        Read specific frames from video.
        
        Args:
            video_path: Path to video file
            frame_indices: List of frame indices to read
            progress_callback: Optional callback for progress updates
            
        Returns:
            List of (frame_index, frame_data) tuples
        """
        cap = cv2.VideoCapture(video_path)
        
        if not cap.isOpened():
            raise ValueError("Could not open video file")
        
        frames = []
        frame_indices = sorted(set(frame_indices))  # Unique and sorted
        
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
        """
        Write frames back to video, preserving unmodified frames.
        
        Args:
            output_path: Output video file path
            frames: Dictionary of {frame_index: frame_data} for modified frames
            source_video_path: Original video path
            progress_callback: Optional callback for progress updates
            
        Returns:
            Path to output video
        """
        cap = cv2.VideoCapture(source_video_path)
        
        if not cap.isOpened():
            raise ValueError("Could not open source video")
        
        try:
            # Get video properties
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            fps = cap.get(cv2.CAP_PROP_FPS)
            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            
            # Ensure output has .mp4 extension
            if not output_path.lower().endswith('.mp4'):
                output_path += '.mp4'
            
            # Create video writer with H.264 codec
            fourcc = cv2.VideoWriter_fourcc(*'avc1')
            out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            if not out.isOpened():
                # Fallback to mp4v codec
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(output_path, fourcc, fps, (width, height))
            
            # Write frames
            for frame_idx in range(total_frames):
                if frame_idx in frames:
                    # Use modified frame
                    out.write(frames[frame_idx])
                else:
                    # Read and write original frame
                    ret, frame = cap.read()
                    if ret:
                        out.write(frame)
                
                if progress_callback:
                    progress = ((frame_idx + 1) / total_frames) * 100
                    progress_callback(progress, f"Writing frame {frame_idx + 1}/{total_frames}")
            
            out.release()
            
        finally:
            cap.release()
        
        # Handle audio (using moviepy if available)
        try:
            cls._copy_audio(source_video_path, output_path)
        except Exception as e:
            print(f"Warning: Could not copy audio: {e}")
        
        return output_path
    
    @classmethod
    def _copy_audio(cls, source_path: str, dest_path: str):
        """Copy audio from source video to destination."""
        try:
            from moviepy.editor import VideoFileClip
            
            source_clip = VideoFileClip(source_path)
            
            if source_clip.audio is not None:
                dest_clip = VideoFileClip(dest_path)
                final_clip = dest_clip.set_audio(source_clip.audio)
                
                # Create temp path
                temp_path = dest_path.replace('.mp4', '_with_audio.mp4')
                final_clip.write_videofile(temp_path, codec='libx264', audio_codec='aac',
                                          verbose=False, logger=None)
                
                # Replace original with audio version
                dest_clip.close()
                source_clip.close()
                final_clip.close()
                
                os.replace(temp_path, dest_path)
            else:
                source_clip.close()
                
        except ImportError:
            pass  # moviepy not available
    
    @classmethod
    def validate_frame_range(cls, video_path: str, 
                            start_frame: int, 
                            end_frame: int) -> bool:
        """
        Validate if frame range is valid for the video.
        
        Args:
            video_path: Path to video file
            start_frame: Start frame index
            end_frame: End frame index
            
        Returns:
            True if valid, False otherwise
        """
        try:
            video_info = cls.get_video_info(video_path)
            total_frames = video_info['total_frames']
            
            return (0 <= start_frame < total_frames and
                    0 <= end_frame <= total_frames and
                    start_frame < end_frame)
        except Exception:
            return False
