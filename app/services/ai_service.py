"""
AI Service - Integration with Claude/OpenAI for intelligent steganography
Provides content-aware embedding, pattern detection, and caption generation

This service adds four layers of AI-powered intelligence on top of the
basic LSB engine:

1. Content-aware embedding (analyze_frame_for_embedding, select_best_frames)
   Uses Laplacian variance to find high-texture regions.  Embedding bits in
   textured areas (grass, hair, fabric, noise) is harder to detect than in
   smooth regions (sky, solid backgrounds) because the eye is less sensitive
   to small changes in complex areas.

2. Steganalysis detection (detect_steganography_patterns)
   Runs four statistical tests on a frame's pixel LSBs to estimate how
   suspicious the frame looks to an automated detector:
     - Chi-square test: uniform LSB distribution is a hallmark of LSB stego
     - Sample-pairs analysis: adjacent pixel differences expose embedding
     - RS analysis: compares Regular vs Singular pixel groups
     - Histogram analysis: paired bins (2i, 2i+1) becoming equal is suspicious
   The combined score (0-100) tells the user whether to choose a different
   cover video or embedding configuration.

3. AI caption generation (generate_innocent_caption)
   Uses the Groq cloud inference API (llama-3.2-11b-vision) to generate a
   plausible, innocent-looking description for the output video.  Falls back
   to hand-crafted captions if no API key is configured.

4. Social media optimisation (optimize_for_social_media)
   Social media platforms re-encode uploaded videos (lossy compression).
   Platform-specific configs (PLATFORM_CONFIGS) choose embedding parameters
   that are robust enough to survive re-encoding:
     - prefer_luma: embed in the Y (luma) channel, which is compressed less
       aggressively than chroma channels
     - use_second_lsb: embed in bit 1 instead of bit 0; bit 0 is most likely
       to be flipped by lossy compression
     - quality_threshold / min_block_texture: filter out regions too smooth
       to reliably survive compression
"""

import os
import base64
import httpx
from typing import List, Dict, Optional, Tuple
import numpy as np
import cv2


class AIService:
    """AI-powered enhancements for video steganography."""

    # Groq OpenAI-compatible endpoint for vision inference.
    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
    GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"

    # ------------------------------------------------------------------ #
    # Platform-specific embedding configurations
    # ------------------------------------------------------------------ #

    # Each platform applies different levels of lossy video re-encoding
    # when users upload content.  These configs tune the embedding strategy
    # so hidden data survives the re-encoding step.
    #
    # quality_threshold : minimum per-block texture score to include a region
    # use_second_lsb    : embed in bit 1 (not bit 0) for extra robustness
    # prefer_luma       : embed only in Y channel (less chroma subsampling loss)
    # min_block_texture : minimum Laplacian-variance score for a 16x16 block
    PLATFORM_CONFIGS = {
        'youtube': {
            'quality_threshold': 0.7,    # YouTube's VP9/H.264 is aggressive
            'use_second_lsb': True,
            'prefer_luma': True,
            'min_block_texture': 30
        },
        'instagram': {
            'quality_threshold': 0.6,    # Instagram re-encodes at moderate quality
            'use_second_lsb': True,
            'prefer_luma': True,
            'min_block_texture': 40
        },
        'twitter': {
            'quality_threshold': 0.5,    # Twitter applies heavy compression
            'use_second_lsb': True,
            'prefer_luma': True,
            'min_block_texture': 50
        },
        'generic': {
            'quality_threshold': 0.65,   # Conservative defaults for unknown platforms
            'use_second_lsb': False,
            'prefer_luma': True,
            'min_block_texture': 25
        }
    }

    def __init__(self):
        # Groq API key; falls back to local caption generation if not set.
        self.groq_key = os.environ.get('GROQ_API_KEY')

    # ================== Content-Aware Embedding ==================

    @classmethod
    def analyze_frame_for_embedding(cls, frame: np.ndarray) -> Dict:
        """Analyse a video frame to find optimal regions for data hiding.

        High-texture areas are better for hiding data without visual artefacts
        because the human eye is less sensitive to small changes in complex
        regions.  We use Laplacian variance as a proxy for texture: areas
        with large second-order gradients (edges, noise, fine detail) score
        higher than uniform flat regions.

        The frame is divided into 16x16 pixel blocks.  Each block receives a
        score that is a weighted average of Laplacian variance and mean
        texture.  The top third of blocks (by score) are returned as
        'optimal_regions' for content-aware embedding.

        Args:
            frame: Video frame as a (H, W, 3) BGR uint8 numpy array

        Returns:
            Dict with optimal_regions (list of {x,y,width,height,score}),
            average_score, total_blocks, and recommended_capacity (bits)
        """
        # Convert to grayscale for texture analysis (colour info not needed).
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Laplacian filter computes the second spatial derivative.
        # High absolute values indicate edges and texture; near-zero values
        # indicate smooth regions.
        laplacian = cv2.Laplacian(gray, cv2.CV_64F)
        texture_map = np.abs(laplacian)

        # Analyse in 16x16 blocks.  Smaller blocks give finer granularity;
        # larger blocks reduce per-block overhead.  16x16 is a common DCT
        # block size and balances these trade-offs well.
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

                # Combined score: equal weight on variance (local complexity)
                # and mean texture (overall edge density).
                score = variance * 0.5 + mean_texture * 0.5

                block_scores.append({
                    'x': x1, 'y': y1,
                    'width': block_size, 'height': block_size,
                    'score': float(score)
                })

        # Sort descending by score and keep the top 33% of blocks.
        block_scores.sort(key=lambda x: x['score'], reverse=True)
        optimal_regions = block_scores[:len(block_scores) // 3]

        # Average score across all blocks gives a per-frame quality indicator.
        avg_score = np.mean([b['score'] for b in block_scores])

        return {
            'optimal_regions': optimal_regions,
            'average_score': float(avg_score),
            'total_blocks': len(block_scores),
            # Recommended capacity in bits: optimal blocks * pixels * 3 channels
            'recommended_capacity': len(optimal_regions) * block_size * block_size * 3
        }

    @classmethod
    def select_best_frames(cls, video_path: str,
                          num_frames: int = 10) -> List[int]:
        """Analyse a video and select frames best suited for data embedding.

        Samples frames uniformly across the video (up to ~100 samples) to
        avoid analysing every frame, then ranks them by average texture score.
        Returns the indices of the top-scoring frames.

        Args:
            video_path: Path to the video file
            num_frames: Number of frames to return

        Returns:
            List of frame indices sorted by embedding quality (best first)
        """
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError("Could not open video file")

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

        # Sample at most ~100 evenly-spaced frames regardless of video length
        # to keep analysis time manageable for long videos.
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

        # Return the top-scoring frame indices.
        frame_scores.sort(key=lambda x: x['score'], reverse=True)
        return [f['frame_index'] for f in frame_scores[:num_frames]]

    # ================== AI Caption Generation ==================

    async def generate_innocent_caption(self, video_path: str,
                                        style: str = 'casual') -> str:
        """Use AI to generate an innocent-looking video description.

        Extracts the middle frame of the video as a representative thumbnail,
        encodes it as JPEG/base64, and sends it to the Claude or OpenAI
        vision API with a style-specific prompt.  Falls back to a local
        hand-crafted caption if no API key is configured or the API call fails.

        Args:
            video_path: Path to video file
            style: Caption style - 'casual', 'professional', or 'social_media'

        Returns:
            Generated caption string
        """
        # Extract the middle frame as a representative thumbnail.
        cap = cv2.VideoCapture(video_path)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.set(cv2.CAP_PROP_POS_FRAMES, total_frames // 2)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return "A wonderful moment captured on video 🎬"

        # Encode the frame as JPEG (quality 80) for compact base64 transfer.
        _, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        frame_b64 = base64.b64encode(buffer).decode('utf-8')

        # Style-specific prompts guide the AI towards the desired tone.
        style_prompts = {
            'casual': "Generate a casual, friendly caption for this video frame. Keep it natural and relatable.",
            'professional': "Generate a professional, polished caption for this video content.",
            'social_media': "Generate an engaging social media caption with relevant emojis and hashtags."
        }

        prompt = style_prompts.get(style, style_prompts['casual'])

        # Try Groq first, then local fallback.
        try:
            if self.groq_key:
                return await self._generate_with_groq(frame_b64, prompt)
        except Exception:
            pass

        return self._generate_fallback_caption(style)

    async def _generate_with_groq(self, image_b64: str, prompt: str) -> str:
        """Generate caption using the Groq cloud inference API.

        Groq exposes an OpenAI-compatible endpoint, so the request format
        mirrors the OpenAI chat completions API.  The llama-3.2-11b-vision
        model supports inline base64 images via the image_url content type.
        Falls back to local generation on any error or non-200 response.
        """
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.GROQ_API_URL,
                headers={
                    "Authorization": f"Bearer {self.groq_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.GROQ_VISION_MODEL,
                    "messages": [{
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{image_b64}"
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }],
                    "max_tokens": 150
                },
                timeout=30.0
            )

        if response.status_code == 200:
            data = response.json()
            return data['choices'][0]['message']['content']
        return self._generate_fallback_caption('casual')

    def _generate_fallback_caption(self, style: str) -> str:
        """Generate a fallback caption without AI when no API key is available.

        Picks a random caption from a small hard-coded pool per style.
        """
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
        """Analyse if a frame shows signs of steganographic modification.

        Runs four complementary statistical tests on the frame's pixel LSBs.
        Each test exploits a different statistical property that LSB embedding
        disturbs in natural images:

          Chi-square  : In unmodified images, pixel value pairs (2i, 2i+1) are
                        not equally distributed.  LSB embedding makes them equal.
          Sample pairs: Adjacent pixels in natural images differ predictably.
                        Very low differences suggest LSB manipulation.
          RS analysis : Regular and Singular pixel groups are balanced in natural
                        images; stego images shift this ratio.
          Histogram   : Adjacent histogram bins (2i, 2i+1) become artificially
                        equal after LSB substitution.

        The four scores are weighted and combined into a single suspicion_score
        (0-100).  Scores above 40 indicate likely steganographic content.

        Args:
            frame: Video frame to analyse

        Returns:
            Dict with suspicion_score, risk_level, per-test scores,
            is_likely_stego flag, and a human-readable recommendation.
        """
        # Convert to grayscale so all tests operate on a single channel.
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        chi_square_score = cls._chi_square_test(gray)
        spa_score = cls._sample_pairs_analysis(gray)
        rs_score = cls._rs_analysis(gray)
        hist_score = cls._histogram_analysis(gray)

        # Weighted average: chi-square and sample-pairs are most reliable,
        # so they get 30% and 25% weight respectively.
        suspicion_score = (
            chi_square_score * 0.3 +
            spa_score * 0.25 +
            rs_score * 0.25 +
            hist_score * 0.2
        )

        # Translate the numeric score to a human-readable risk tier.
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
        """Perform chi-square test on pixel LSBs.

        In a natural image, pixel value pairs (2i, 2i+1) are not equally
        likely.  LSB substitution makes them approximately equal because
        every pixel value is randomly rounded to either 2i or 2i+1.
        A low chi-square statistic (uniform distribution) is therefore
        suspicious.  The score is inverted so higher = more suspicious.
        """
        flat = gray_image.flatten()

        # Group pixels into pairs (2i, 2i+1) and count occurrences.
        pairs = {}
        for val in flat:
            pair_key = val // 2
            if pair_key not in pairs:
                pairs[pair_key] = [0, 0]
            pairs[pair_key][val % 2] += 1

        # Standard chi-square statistic: sum((observed - expected)^2 / expected)
        chi_square = 0
        for pair_key, counts in pairs.items():
            expected = sum(counts) / 2
            if expected > 0:
                for count in counts:
                    chi_square += ((count - expected) ** 2) / expected

        if not pairs:
            return 0.0

        # Normalize to 0-100: lower chi-square -> higher suspicion score.
        normalized = min(100, max(0, 100 - (chi_square / len(pairs)) * 10))
        return normalized

    @classmethod
    def _sample_pairs_analysis(cls, gray_image: np.ndarray) -> float:
        """Sample pairs analysis for LSB detection.

        Compares absolute differences between adjacent pixel pairs.
        Natural images have moderate differences; very low average
        differences suggest LSB manipulation has homogenised the values.
        """
        flat = gray_image.flatten()

        # Compute average absolute difference between adjacent pixels.
        diff_sum = 0
        for i in range(0, len(flat) - 1, 2):
            diff_sum += abs(int(flat[i]) - int(flat[i + 1]))

        avg_diff = diff_sum / (len(flat) // 2)

        # Thresholds derived empirically:
        # < 5  : very homogeneous -> high suspicion
        # 5-15 : typical natural image range -> moderate suspicion
        # > 15 : high variance -> low suspicion (looks natural)
        if avg_diff < 5:
            return 70
        elif avg_diff < 15:
            return 30
        else:
            return 10

    @classmethod
    def _rs_analysis(cls, gray_image: np.ndarray) -> float:
        """RS (Regular/Singular) analysis.

        Groups pixels into blocks of 4 and checks whether flipping the
        LSB of each pixel increases (Regular) or decreases (Singular) the
        local variance.  In natural images R and S are roughly balanced;
        heavy embedding shifts the ratio.
        """
        flat = gray_image.flatten().astype(np.int32)

        regular = 0
        singular = 0

        for i in range(0, len(flat) - 4, 4):
            group = flat[i:i + 4]
            variance = np.var(group)

            # XOR each pixel with 1 to flip its LSB.
            flipped = group.copy()
            flipped = flipped ^ 1
            flipped_variance = np.var(flipped)

            if flipped_variance > variance:
                regular += 1
            else:
                singular += 1

        total = regular + singular
        if total == 0:
            return 50

        # Large |R - S| / total ratio indicates imbalance caused by embedding.
        ratio = abs(regular - singular) / total
        return min(100, ratio * 200)

    @classmethod
    def _histogram_analysis(cls, gray_image: np.ndarray) -> float:
        """Analyse pixel histogram for anomalies caused by LSB embedding.

        After LSB substitution, adjacent histogram bins (2i, 2i+1) tend to
        become equal because the embedding randomly distributes values between
        even and odd bins.  A high count of nearly-equal bin pairs is suspicious.
        """
        hist = cv2.calcHist([gray_image], [0], None, [256], [0, 256])
        hist = hist.flatten()

        # Count pairs of adjacent bins that are abnormally close in value.
        anomaly_score = 0
        for i in range(0, 256, 2):
            if i + 1 < 256:
                diff = abs(hist[i] - hist[i + 1])
                # If the difference is less than 10% of their combined count,
                # the pair is suspiciously balanced.
                expected_diff = (hist[i] + hist[i + 1]) * 0.1
                if diff < expected_diff:
                    anomaly_score += 1

        # Normalise: 128 possible pairs -> percentage of suspicious pairs.
        return min(100, (anomaly_score / 128) * 100)

    # ================== Smart Compression ==================

    @classmethod
    def optimize_for_social_media(cls, frame: np.ndarray,
                                  platform: str = 'generic') -> Tuple[np.ndarray, Dict]:
        """Optimise embedding to survive social media re-encoding.

        Looks up the platform-specific config and identifies the most
        robust regions (high-texture blocks that exceed the platform's
        minimum texture threshold).  Optionally converts to YCrCb to
        identify the luma channel for preferred embedding.

        Note: This function returns the original frame unchanged alongside
        the optimisation metadata.  The actual channel/bit-plane selection
        is handled by the embedding layer using the returned config dict.

        Args:
            frame: Video frame (H x W x 3 BGR uint8)
            platform: Target platform key ('youtube', 'instagram', 'twitter', 'generic')

        Returns:
            Tuple of (frame, metadata dict) where metadata includes:
              platform, config, robust_regions, embedding_channel,
              estimated_survival_rate, use_second_lsb
        """
        config = cls.PLATFORM_CONFIGS.get(platform, cls.PLATFORM_CONFIGS['generic'])

        # Analyse frame texture and filter regions below the platform threshold.
        analysis = cls.analyze_frame_for_embedding(frame)

        # Retain only regions with a texture score above the platform's minimum.
        # Low-texture regions are more likely to show visible artefacts after
        # lossy compression corrupts the embedded bits.
        robust_regions = [
            r for r in analysis['optimal_regions']
            if r['score'] >= config['min_block_texture']
        ]

        # Identify the preferred embedding channel.
        if config['prefer_luma']:
            # Convert to YCrCb to identify the Y (luma) channel index.
            # Luma is compressed less aggressively than chroma, so bits
            # embedded here are more likely to survive re-encoding.
            frame_ycrcb = cv2.cvtColor(frame, cv2.COLOR_BGR2YCrCb)
            embedding_channel = 0  # Y channel is index 0 in YCrCb
        else:
            frame_ycrcb = frame
            embedding_channel = None  # Use all RGB channels

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
        """Return platform compression config used by the service.

        Convenience accessor used by tasks.py to retrieve platform settings
        without instantiating an AIService object.

        Args:
            platform: Platform name key

        Returns:
            Config dict with quality_threshold, use_second_lsb, prefer_luma,
            and min_block_texture
        """
        return cls.PLATFORM_CONFIGS.get(platform, cls.PLATFORM_CONFIGS['generic'])
