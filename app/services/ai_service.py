"""
AI Service - Integration with Claude/OpenAI for intelligent steganography
Provides content-aware embedding, pattern detection, and caption generation
"""

import os
import base64
import httpx
from typing import List, Dict, Optional, Tuple
import numpy as np
import cv2


class AIService:
    """AI-powered enhancements for video steganography."""
    
    # API configurations
    ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
    OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"

    # Platform-specific compression awareness
    PLATFORM_CONFIGS = {
        'youtube': {
            'quality_threshold': 0.7,
            'use_second_lsb': True,
            'prefer_luma': True,
            'min_block_texture': 30
        },
        'instagram': {
            'quality_threshold': 0.6,
            'use_second_lsb': True,
            'prefer_luma': True,
            'min_block_texture': 40
        },
        'twitter': {
            'quality_threshold': 0.5,
            'use_second_lsb': True,
            'prefer_luma': True,
            'min_block_texture': 50
        },
        'generic': {
            'quality_threshold': 0.65,
            'use_second_lsb': False,
            'prefer_luma': True,
            'min_block_texture': 25
        }
    }
    
    def __init__(self):
        self.anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
        self.openai_key = os.environ.get('OPENAI_API_KEY')
    
    # ================== Content-Aware Embedding ==================
    
    @classmethod
    def analyze_frame_for_embedding(cls, frame: np.ndarray) -> Dict:
        """
        Analyze a video frame to find optimal regions for data hiding.
        High-texture areas are better for hiding data without visual artifacts.
        
        Args:
            frame: Video frame as numpy array
            
        Returns:
            Dictionary with optimal regions and quality scores
        """
        # Convert to grayscale for analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Calculate texture using Laplacian variance (higher = more texture)
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        texture_map = np.abs(laplacian)
        
        # Calculate local variance in 16x16 blocks
        block_size = 16
        height, width = gray.shape
        blocks_y = height // block_size
        blocks_x = width // block_size
        
        block_scores = []
        optimal_regions = []
        
        for by in range(blocks_y):
            for bx in range(blocks_x):
                y1, y2 = by * block_size, (by + 1) * block_size
                x1, x2 = bx * block_size, (bx + 1) * block_size
                
                block = texture_map[y1:y2, x1:x2]
                variance = np.var(block)
                mean_texture = np.mean(block)
                
                # Higher score = better for embedding
                score = variance * 0.5 + mean_texture * 0.5
                
                block_scores.append({
                    'x': x1, 'y': y1,
                    'width': block_size, 'height': block_size,
                    'score': float(score)
                })
        
        # Sort by score and get top regions
        block_scores.sort(key=lambda x: x['score'], reverse=True)
        optimal_regions = block_scores[:len(block_scores) // 3]  # Top 33%
        
        # Calculate overall frame quality for embedding
        avg_score = np.mean([b['score'] for b in block_scores])
        
        return {
            'optimal_regions': optimal_regions,
            'average_score': float(avg_score),
            'total_blocks': len(block_scores),
            'recommended_capacity': len(optimal_regions) * block_size * block_size * 3
        }
    
    @classmethod
    def select_best_frames(cls, video_path: str, 
                          num_frames: int = 10) -> List[int]:
        """
        Analyze video and select frames best suited for data embedding.
        
        Args:
            video_path: Path to video file
            num_frames: Number of frames to select
            
        Returns:
            List of frame indices sorted by embedding quality
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("Could not open video file")
        
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        
        # Sample frames uniformly across video
        sample_interval = max(1, total_frames // 100)
        frame_scores = []
        
        for frame_idx in range(0, total_frames, sample_interval):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            
            if ret:
                analysis = cls.analyze_frame_for_embedding(frame)
                frame_scores.append({
                    'frame_index': frame_idx,
                    'score': analysis['average_score']
                })
        
        cap.release()
        
        # Sort by score and return top frames
        frame_scores.sort(key=lambda x: x['score'], reverse=True)
        return [f['frame_index'] for f in frame_scores[:num_frames]]
    
    # ================== AI Caption Generation ==================
    
    async def generate_innocent_caption(self, video_path: str,
                                        style: str = 'casual') -> str:
        """
        Use AI to generate an innocent-looking video description.
        
        Args:
            video_path: Path to video file
            style: Caption style ('casual', 'professional', 'social_media')
            
        Returns:
            Generated caption string
        """
        # Extract a representative frame
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            return "A wonderful moment captured on video 🎬"
        
        # Encode frame to base64
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_b64 = base64.b64encode(buffer).decode('utf-8')
        
        style_prompts = {
            'casual': "Generate a casual, friendly caption for this video frame. Keep it natural and relatable.",
            'professional': "Generate a professional, polished caption for this video content.",
            'social_media': "Generate an engaging social media caption with relevant emojis and hashtags."
        }
        
        prompt = style_prompts.get(style, style_prompts['casual'])
        
        # Try Claude first, fallback to OpenAI
        if self.anthropic_key:
            return await self._generate_with_claude(frame_b64, prompt)
        elif self.openai_key:
            return await self._generate_with_openai(frame_b64, prompt)
        else:
            return self._generate_fallback_caption(style)
    
    async def _generate_with_claude(self, image_b64: str, prompt: str) -> str:
        """Generate caption using Claude API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.ANTHROPIC_API_URL,
                headers={
                    "x-api-key": self.anthropic_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json"
                },
                json={
                    "model": "claude-3-sonnet-20240229",
                    "max_tokens": 150,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_b64
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }]
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['content'][0]['text']
            else:
                return self._generate_fallback_caption('casual')
    
    async def _generate_with_openai(self, image_b64: str, prompt: str) -> str:
        """Generate caption using OpenAI API."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.OPENAI_API_URL,
                headers={
                    "Authorization": f"Bearer {self.openai_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gpt-4-vision-preview",
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "text",
                                "text": prompt
                            },
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            }
                        ]
                    }],
                    "max_tokens": 150
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                data = response.json()
                return data['choices'][0]['message']['content']
            else:
                return self._generate_fallback_caption('casual')
    
    def _generate_fallback_caption(self, style: str) -> str:
        """Generate fallback caption without AI."""
        captions = {
            'casual': [
                "Just a regular day, captured perfectly! 📹",
                "Making memories, one frame at a time ✨",
                "Life's little moments are the best 🎬"
            ],
            'professional': [
                "Professional video content for your viewing",
                "Quality footage captured with precision",
                "Documenting excellence in motion"
            ],
            'social_media': [
                "Vibes on point today! 🔥 #content #video #lifestyle",
                "Check this out! 👀✨ #amazing #mustwatch",
                "When life gives you moments, record them! 📱🎬 #memories"
            ]
        }
        import random
        return random.choice(captions.get(style, captions['casual']))
    
    # ================== Pattern Detection ==================
    
    @classmethod
    def detect_steganography_patterns(cls, frame: np.ndarray) -> Dict:
        """
        Analyze if a frame shows signs of steganographic modification.
        Uses statistical analysis to detect anomalies.
        
        Args:
            frame: Video frame to analyze
            
        Returns:
            Dictionary with detection results and confidence
        """
        # Convert to different color spaces for analysis
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        
        # Chi-square attack detection (LSB analysis)
        chi_square_score = cls._chi_square_test(gray)
        
        # Sample pairs analysis
        spa_score = cls._sample_pairs_analysis(gray)
        
        # RS analysis (Regular/Singular groups)
        rs_score = cls._rs_analysis(gray)
        
        # Histogram analysis
        hist_score = cls._histogram_analysis(gray)
        
        # Combined suspicion score (0-100, higher = more suspicious)
        suspicion_score = (
            chi_square_score * 0.3 +
            spa_score * 0.25 +
            rs_score * 0.25 +
            hist_score * 0.2
        )
        
        # Determine risk level
        if suspicion_score < 20:
            risk_level = 'low'
        elif suspicion_score < 50:
            risk_level = 'medium'
        else:
            risk_level = 'high'
        
        return {
            'suspicion_score': round(suspicion_score, 2),
            'risk_level': risk_level,
            'chi_square_score': round(chi_square_score, 2),
            'spa_score': round(spa_score, 2),
            'rs_score': round(rs_score, 2),
            'histogram_score': round(hist_score, 2),
            'is_likely_stego': suspicion_score > 40,
            'recommendation': 'Safe for embedding' if suspicion_score < 30 else 'Consider different cover video'
        }
    
    @classmethod
    def _chi_square_test(cls, gray_image: np.ndarray) -> float:
        """Perform chi-square test on LSBs."""
        flat = gray_image.flatten()
        
        # Count pairs of values (2i, 2i+1)
        pairs = {}
        for val in flat:
            pair_key = val // 2
            if pair_key not in pairs:
                pairs[pair_key] = [0, 0]
            pairs[pair_key][val % 2] += 1
        
        # Calculate chi-square statistic
        chi_square = 0
        for pair_key, counts in pairs.items():
            expected = sum(counts) / 2
            if expected > 0:
                for count in counts:
                    chi_square += ((count - expected) ** 2) / expected
        
        # Normalize to 0-100 scale
        # Lower chi-square = more uniform = likely steganography
        normalized = min(100, max(0, 100 - (chi_square / len(pairs)) * 10))
        return normalized
    
    @classmethod
    def _sample_pairs_analysis(cls, gray_image: np.ndarray) -> float:
        """Sample pairs analysis for LSB detection."""
        flat = gray_image.flatten()
        
        # Compare adjacent pixel pairs
        diff_sum = 0
        for i in range(0, len(flat) - 1, 2):
            diff_sum += abs(int(flat[i]) - int(flat[i + 1]))
        
        avg_diff = diff_sum / (len(flat) // 2)
        
        # Natural images typically have higher pixel differences
        # Stego images might show unusual patterns
        if avg_diff < 5:
            return 70  # Very low difference - suspicious
        elif avg_diff < 15:
            return 30  # Normal range
        else:
            return 10  # High variance - natural
    
    @classmethod
    def _rs_analysis(cls, gray_image: np.ndarray) -> float:
        """RS (Regular/Singular) analysis."""
        # Simplified RS analysis
        flat = gray_image.flatten().astype(np.int32)
        
        # Calculate local variance patterns
        regular = 0
        singular = 0
        
        for i in range(0, len(flat) - 4, 4):
            group = flat[i:i + 4]
            variance = np.var(group)
            
            # Flip LSBs and recalculate
            flipped = group.copy()
            flipped = flipped ^ 1  # Flip LSB
            flipped_variance = np.var(flipped)
            
            if flipped_variance > variance:
                regular += 1
            else:
                singular += 1
        
        # In natural images, R and S should be roughly equal
        total = regular + singular
        if total == 0:
            return 50
        
        ratio = abs(regular - singular) / total
        return min(100, ratio * 200)
    
    @classmethod
    def _histogram_analysis(cls, gray_image: np.ndarray) -> float:
        """Analyze histogram for anomalies."""
        hist = cv2.calcHist([gray_image], [0], None, [256], [0, 256])
        hist = hist.flatten()
        
        # Check for unusual patterns in adjacent bins
        anomaly_score = 0
        for i in range(0, 256, 2):
            if i + 1 < 256:
                diff = abs(hist[i] - hist[i + 1])
                expected_diff = (hist[i] + hist[i + 1]) * 0.1
                if diff < expected_diff:
                    anomaly_score += 1
        
        # Normalize
        return min(100, (anomaly_score / 128) * 100)
    
    # ================== Smart Compression ==================
    
    @classmethod
    def optimize_for_social_media(cls, frame: np.ndarray,
                                  platform: str = 'generic') -> Tuple[np.ndarray, Dict]:
        """
        Optimize embedding to survive social media re-encoding.
        Uses higher bit planes and robust embedding regions.
        
        Args:
            frame: Video frame
            platform: Target platform ('youtube', 'instagram', 'twitter', 'generic')
            
        Returns:
            Tuple of (optimized frame regions, optimization metadata)
        """
        config = cls.PLATFORM_CONFIGS.get(platform, cls.PLATFORM_CONFIGS['generic'])
        
        # Analyze frame for robust regions
        analysis = cls.analyze_frame_for_embedding(frame)
        
        # Filter regions based on texture threshold
        robust_regions = [
            r for r in analysis['optimal_regions']
            if r['score'] >= config['min_block_texture']
        ]
        
        # If using luma preference, convert to YCrCb
        if config['prefer_luma']:
            frame_ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
            # Y channel is more robust to compression
            embedding_channel = 0
        else:
            frame_ycrcb = frame
            embedding_channel = None
        
        return frame, {
            'platform': platform,
            'config': config,
            'robust_regions': robust_regions,
            'embedding_channel': embedding_channel,
            'estimated_survival_rate': config['quality_threshold'],
            'use_second_lsb': config['use_second_lsb']
        }

    @classmethod
    def get_platform_config(cls, platform: str = 'generic') -> Dict:
        """Return platform compression config used by the service."""
        return cls.PLATFORM_CONFIGS.get(platform, cls.PLATFORM_CONFIGS['generic'])
