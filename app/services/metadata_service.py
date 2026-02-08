"""
Metadata Service - Preserve and manage video metadata
"""

import os
import json
import subprocess
from typing import Dict, Optional, List
from datetime import datetime


class MetadataService:
    """Service for preserving and managing video metadata."""
    
    # Common metadata fields to preserve
    PRESERVE_FIELDS = [
        'title', 'artist', 'album', 'date', 'comment',
        'genre', 'copyright', 'description', 'synopsis',
        'creation_time', 'encoder', 'language'
    ]
    
    @classmethod
    def extract_metadata(cls, video_path: str) -> Dict:
        """
        Extract metadata from video file.
        
        Args:
            video_path: Path to video file
            
        Returns:
            Dictionary of metadata
        """
        metadata = {
            'file_info': cls._get_file_info(video_path),
            'video_metadata': {},
            'technical_info': {}
        }
        
        try:
            # Try using ffprobe for detailed metadata
            result = subprocess.run([
                'ffprobe', '-v', 'quiet',
                '-print_format', 'json',
                '-show_format', '-show_streams',
                video_path
            ], capture_output=True, text=True)
            
            if result.returncode == 0:
                probe_data = json.loads(result.stdout)
                
                # Extract format metadata
                if 'format' in probe_data:
                    fmt = probe_data['format']
                    metadata['video_metadata'] = fmt.get('tags', {})
                    metadata['technical_info'] = {
                        'format_name': fmt.get('format_name'),
                        'duration': float(fmt.get('duration', 0)),
                        'size': int(fmt.get('size', 0)),
                        'bit_rate': int(fmt.get('bit_rate', 0))
                    }
                
                # Extract stream info
                if 'streams' in probe_data:
                    for stream in probe_data['streams']:
                        if stream.get('codec_type') == 'video':
                            metadata['technical_info']['video'] = {
                                'codec': stream.get('codec_name'),
                                'width': stream.get('width'),
                                'height': stream.get('height'),
                                'fps': eval(stream.get('r_frame_rate', '0/1')),
                                'pixel_format': stream.get('pix_fmt')
                            }
                        elif stream.get('codec_type') == 'audio':
                            metadata['technical_info']['audio'] = {
                                'codec': stream.get('codec_name'),
                                'sample_rate': stream.get('sample_rate'),
                                'channels': stream.get('channels')
                            }
        except (subprocess.SubprocessError, FileNotFoundError):
            # ffprobe not available, use basic metadata
            import cv2
            cap = cv2.VideoCapture(video_path)
            if cap.isOpened():
                metadata['technical_info'] = {
                    'width': int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                    'height': int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                    'fps': cap.get(cv2.CAP_PROP_FPS),
                    'frame_count': int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                }
                cap.release()
        
        return metadata
    
    @classmethod
    def _get_file_info(cls, video_path: str) -> Dict:
        """Get basic file information."""
        stat = os.stat(video_path)
        return {
            'filename': os.path.basename(video_path),
            'size_bytes': stat.st_size,
            'created': datetime.fromtimestamp(stat.st_ctime).isoformat(),
            'modified': datetime.fromtimestamp(stat.st_mtime).isoformat()
        }
    
    @classmethod
    def apply_metadata(cls, video_path: str, metadata: Dict,
                      output_path: Optional[str] = None) -> str:
        """
        Apply metadata to a video file.
        
        Args:
            video_path: Source video path
            metadata: Metadata dictionary to apply
            output_path: Output path (if None, modifies in place)
            
        Returns:
            Path to output video with metadata
        """
        if output_path is None:
            output_path = video_path.replace('.mp4', '_meta.mp4')
        
        try:
            # Build ffmpeg command
            cmd = ['ffmpeg', '-i', video_path, '-c', 'copy']
            
            # Add metadata tags
            for key, value in metadata.get('video_metadata', {}).items():
                if key in cls.PRESERVE_FIELDS and value:
                    cmd.extend(['-metadata', f'{key}={value}'])
            
            cmd.extend(['-y', output_path])
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode == 0:
                return output_path
            else:
                # Fallback: just copy the file
                import shutil
                shutil.copy2(video_path, output_path)
                return output_path
                
        except (subprocess.SubprocessError, FileNotFoundError):
            # ffmpeg not available, just copy
            import shutil
            shutil.copy2(video_path, output_path)
            return output_path
    
    @classmethod
    def preserve_metadata(cls, source_path: str, dest_path: str) -> bool:
        """
        Copy metadata from source video to destination.
        
        Args:
            source_path: Original video with metadata
            dest_path: Processed video to receive metadata
            
        Returns:
            True if successful
        """
        try:
            # Extract source metadata
            source_meta = cls.extract_metadata(source_path)
            
            # Apply to destination
            temp_path = dest_path.replace('.mp4', '_temp.mp4')
            result_path = cls.apply_metadata(dest_path, source_meta, temp_path)
            
            # Replace original with metadata version
            if result_path != dest_path and os.path.exists(result_path):
                os.replace(result_path, dest_path)
            
            return True
        except Exception as e:
            print(f"Warning: Could not preserve metadata: {e}")
            return False
    
    @classmethod
    def add_stego_metadata(cls, video_path: str, stego_info: Dict) -> Dict:
        """
        Add hidden metadata about steganography operation.
        This is stored in a separate JSON file, not in the video.
        
        Args:
            video_path: Path to stego video
            stego_info: Information about the embedding
            
        Returns:
            Complete stego metadata
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
                'message_hash': stego_info.get('message_hash')  # For verification
            },
            'video_info': cls.extract_metadata(video_path)
        }
        
        with open(meta_path, 'w') as f:
            json.dump(stego_metadata, f, indent=2)
        
        return stego_metadata
    
    @classmethod
    def read_stego_metadata(cls, video_path: str) -> Optional[Dict]:
        """
        Read stego metadata file if it exists.
        
        Args:
            video_path: Path to stego video
            
        Returns:
            Stego metadata or None
        """
        meta_path = video_path + '.meta.json'
        
        if os.path.exists(meta_path):
            with open(meta_path, 'r') as f:
                return json.load(f)
        
        return None
