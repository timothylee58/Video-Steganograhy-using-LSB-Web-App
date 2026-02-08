"""
VidStega Stress Testing Suite
Tests performance across different resolutions, encryption strengths, and video sizes
"""

import os
import time
import json
import psutil
import numpy as np
import cv2
from datetime import datetime
from typing import Dict, List, Tuple
import tracemalloc
import gc


class VideoStressTest:
    """Comprehensive stress testing for video steganography application."""

    # Test configurations
    RESOLUTIONS = {
        '480p': (854, 480),
        '720p': (1280, 720),
        '1080p': (1920, 1080),
        '1440p': (2560, 1440)
    }

    ENCRYPTION_STRENGTHS = ['AES-128', 'AES-192', 'AES-256']
    CIPHER_MODES = ['CBC', 'CTR', 'GCM', 'CFB']

    # Test parameters
    FRAME_COUNTS = [30, 60, 120, 300, 600]  # Different video lengths (1s to 20s at 30fps)
    MESSAGE_SIZES = [100, 1024, 10240, 51200, 102400]  # 100B to 100KB

    def __init__(self, output_dir='stress_test_results'):
        """Initialize stress testing environment."""
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

        self.results = []
        self.process = psutil.Process()

    def generate_test_video(self, resolution: Tuple[int, int],
                           frame_count: int,
                           fps: int = 30) -> str:
        """
        Generate a synthetic test video.

        Args:
            resolution: (width, height)
            frame_count: Number of frames
            fps: Frames per second

        Returns:
            Path to generated video
        """
        width, height = resolution
        filename = f"test_video_{width}x{height}_{frame_count}f.mp4"
        filepath = os.path.join(self.output_dir, filename)

        # Skip if already exists
        if os.path.exists(filepath):
            print(f"  Using existing test video: {filename}")
            return filepath

        print(f"  Generating test video: {width}x{height}, {frame_count} frames...")

        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        out = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

        for i in range(frame_count):
            # Generate frame with varying content (important for realistic testing)
            frame = np.random.randint(0, 256, (height, width, 3), dtype=np.uint8)

            # Add some structure (text overlay for variety)
            cv2.putText(frame, f"Frame {i}", (50, 50),
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

            out.write(frame)

        out.release()

        file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
        print(f"  Generated: {filename} ({file_size_mb:.2f} MB)")

        return filepath

    def measure_memory(self) -> Dict:
        """Get current memory usage."""
        mem_info = self.process.memory_info()
        return {
            'rss_mb': mem_info.rss / (1024 * 1024),
            'vms_mb': mem_info.vms / (1024 * 1024),
            'percent': self.process.memory_percent()
        }

    def test_embed_performance(self, video_path: str,
                              message_size: int,
                              encryption_strength: str,
                              cipher_mode: str,
                              frames_to_use: List[int]) -> Dict:
        """
        Test embedding performance for specific configuration.

        Returns:
            Dictionary with performance metrics
        """
        from app.services import VideoService, CryptoService, SteganographyService

        # Generate test message
        message = 'A' * message_size
        password = 'test_password_123'

        # Start monitoring
        tracemalloc.start()
        gc.collect()
        mem_before = self.measure_memory()
        start_time = time.time()

        try:
            # Step 1: Encryption
            encrypt_start = time.time()
            encrypted_data, metadata = CryptoService.encrypt(
                message, password, encryption_strength, cipher_mode
            )
            encrypt_time = time.time() - encrypt_start
            encrypted_size = len(encrypted_data)

            # Step 2: Read frames
            read_start = time.time()
            frame_data = VideoService.read_frames(video_path, frames_to_use)
            read_time = time.time() - read_start
            mem_after_read = self.measure_memory()

            # Step 3: Embed
            embed_start = time.time()
            protected_data = SteganographyService.apply_error_correction(encrypted_data)
            result = SteganographyService.embed_message(
                frame_data,
                encrypted_data,
                progress_callback=None
            )
            embed_time = time.time() - embed_start

            # Step 4: Write video (simulate)
            write_start = time.time()
            # Note: We skip actual video writing to save disk space during tests
            # Just measure the time for frame processing
            write_time = time.time() - write_start

            total_time = time.time() - start_time

            # Memory metrics
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            mem_after = self.measure_memory()

            # Video info
            video_info = VideoService.get_video_info(video_path)

            return {
                'success': True,
                'total_time': total_time,
                'encrypt_time': encrypt_time,
                'read_time': read_time,
                'embed_time': embed_time,
                'write_time': write_time,
                'memory_before_mb': mem_before['rss_mb'],
                'memory_after_read_mb': mem_after_read['rss_mb'],
                'memory_after_mb': mem_after['rss_mb'],
                'memory_peak_mb': peak / (1024 * 1024),
                'memory_increase_mb': mem_after['rss_mb'] - mem_before['rss_mb'],
                'message_size': message_size,
                'encrypted_size': encrypted_size,
                'protected_size': len(protected_data),
                'bits_embedded': result['bits_embedded'],
                'frames_used': result['frames_used'],
                'video_info': video_info,
                'error': None
            }

        except Exception as e:
            tracemalloc.stop()
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__,
                'traceback': traceback.format_exc()
            }

    def test_extract_performance(self, video_path: str,
                                encryption_strength: str,
                                cipher_mode: str,
                                start_frame: int,
                                end_frame: int) -> Dict:
        """Test extraction performance."""
        from app.services import VideoService, CryptoService, SteganographyService

        password = 'test_password_123'

        tracemalloc.start()
        gc.collect()
        mem_before = self.measure_memory()
        start_time = time.time()

        try:
            # Read frames
            read_start = time.time()
            frame_indices = list(range(start_frame, end_frame))
            frame_data = VideoService.read_frames(video_path, frame_indices)
            read_time = time.time() - read_start

            # Extract (this will fail without embedded data, but we measure the attempt)
            extract_start = time.time()
            try:
                extracted_data = SteganographyService.extract_message(frame_data)
                extract_time = time.time() - extract_start

                # Decrypt
                decrypt_start = time.time()
                decrypted = CryptoService.decrypt(
                    extracted_data, password, encryption_strength, cipher_mode
                )
                decrypt_time = time.time() - decrypt_start
            except Exception as inner_e:
                # Expected to fail on test videos without embedded data
                extract_time = time.time() - extract_start
                decrypt_time = 0

            total_time = time.time() - start_time
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            mem_after = self.measure_memory()

            return {
                'success': True,
                'total_time': total_time,
                'read_time': read_time,
                'extract_time': extract_time,
                'decrypt_time': decrypt_time,
                'memory_before_mb': mem_before['rss_mb'],
                'memory_after_mb': mem_after['rss_mb'],
                'memory_peak_mb': peak / (1024 * 1024),
                'frames_processed': len(frame_data),
                'error': None
            }

        except Exception as e:
            tracemalloc.stop()
            return {
                'success': False,
                'error': str(e),
                'error_type': type(e).__name__
            }

    def run_comprehensive_test(self):
        """Run comprehensive stress tests across all configurations."""
        print("\n" + "="*80)
        print("VIDSTEGA COMPREHENSIVE STRESS TEST")
        print("="*80)
        print(f"Start Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"System: {psutil.cpu_count()} CPUs, {psutil.virtual_memory().total / (1024**3):.1f}GB RAM")
        print("="*80 + "\n")

        total_tests = (len(self.RESOLUTIONS) * len(self.ENCRYPTION_STRENGTHS) *
                      len(self.CIPHER_MODES) * len(self.FRAME_COUNTS))
        current_test = 0

        for res_name, resolution in self.RESOLUTIONS.items():
            print(f"\n{'='*60}")
            print(f"TESTING RESOLUTION: {res_name} ({resolution[0]}x{resolution[1]})")
            print(f"{'='*60}")

            for frame_count in self.FRAME_COUNTS:
                # Generate test video
                video_path = self.generate_test_video(resolution, frame_count)
                video_info = None

                try:
                    from app.services import VideoService
                    video_info = VideoService.get_video_info(video_path)

                    print(f"\nVideo Info:")
                    print(f"  File Size: {video_info['file_size_bytes'] / (1024*1024):.2f} MB")
                    print(f"  Capacity per Frame: {video_info['capacity_per_frame_bytes']} bytes")
                    print(f"  Total Capacity: {video_info['total_capacity_bytes'] / 1024:.2f} KB")

                except Exception as e:
                    print(f"  Error getting video info: {e}")
                    continue

                # Test each encryption configuration
                for encryption_strength in self.ENCRYPTION_STRENGTHS:
                    for cipher_mode in self.CIPHER_MODES:
                        current_test += 1

                        print(f"\n  [{current_test}/{total_tests}] Testing: {encryption_strength} {cipher_mode}")

                        # Determine appropriate message size
                        max_capacity = video_info['capacity_per_frame_bytes'] * min(10, frame_count)
                        message_size = min(1024, max_capacity // 2)  # Use 50% of capacity

                        # Select frames to use
                        frames_to_use = list(range(0, min(10, frame_count)))

                        # Run embed test
                        embed_result = self.test_embed_performance(
                            video_path,
                            message_size,
                            encryption_strength,
                            cipher_mode,
                            frames_to_use
                        )

                        # Store result
                        test_record = {
                            'timestamp': datetime.now().isoformat(),
                            'resolution': res_name,
                            'width': resolution[0],
                            'height': resolution[1],
                            'frame_count': frame_count,
                            'encryption_strength': encryption_strength,
                            'cipher_mode': cipher_mode,
                            'operation': 'embed',
                            **embed_result
                        }

                        self.results.append(test_record)

                        # Print summary
                        if embed_result['success']:
                            print(f"    ✓ Success: {embed_result['total_time']:.2f}s")
                            print(f"      Memory: {embed_result['memory_increase_mb']:.1f}MB increase")
                            print(f"      Breakdown: Read={embed_result['read_time']:.2f}s, "
                                  f"Embed={embed_result['embed_time']:.2f}s")
                        else:
                            print(f"    ✗ Failed: {embed_result['error']}")

                        # Save incremental results
                        if current_test % 10 == 0:
                            self.save_results()

        # Final save and analysis
        self.save_results()
        self.generate_analysis()

        print("\n" + "="*80)
        print("STRESS TEST COMPLETE")
        print(f"Results saved to: {self.output_dir}")
        print("="*80 + "\n")

    def save_results(self):
        """Save test results to JSON file."""
        results_file = os.path.join(self.output_dir, 'stress_test_results.json')
        with open(results_file, 'w') as f:
            json.dump(self.results, f, indent=2)
        print(f"\n  Results saved: {results_file}")

    def generate_analysis(self):
        """Generate comprehensive analysis report."""
        analysis_file = os.path.join(self.output_dir, 'analysis_report.md')

        successful_tests = [r for r in self.results if r.get('success')]
        failed_tests = [r for r in self.results if not r.get('success')]

        with open(analysis_file, 'w') as f:
            f.write("# VidStega Stress Test Analysis Report\n\n")
            f.write(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## Executive Summary\n\n")
            f.write(f"- **Total Tests:** {len(self.results)}\n")
            f.write(f"- **Successful:** {len(successful_tests)} ({len(successful_tests)/len(self.results)*100:.1f}%)\n")
            f.write(f"- **Failed:** {len(failed_tests)} ({len(failed_tests)/len(self.results)*100:.1f}%)\n\n")

            if successful_tests:
                avg_time = np.mean([r['total_time'] for r in successful_tests])
                max_time = max([r['total_time'] for r in successful_tests])
                avg_memory = np.mean([r['memory_increase_mb'] for r in successful_tests])
                max_memory = max([r['memory_increase_mb'] for r in successful_tests])

                f.write("## Performance Metrics\n\n")
                f.write(f"- **Average Processing Time:** {avg_time:.2f}s\n")
                f.write(f"- **Maximum Processing Time:** {max_time:.2f}s\n")
                f.write(f"- **Average Memory Increase:** {avg_memory:.1f}MB\n")
                f.write(f"- **Maximum Memory Increase:** {max_memory:.1f}MB\n\n")

                # Performance by resolution
                f.write("## Performance by Resolution\n\n")
                for res in self.RESOLUTIONS.keys():
                    res_tests = [r for r in successful_tests if r['resolution'] == res]
                    if res_tests:
                        avg_time = np.mean([r['total_time'] for r in res_tests])
                        avg_mem = np.mean([r['memory_increase_mb'] for r in res_tests])
                        f.write(f"### {res}\n")
                        f.write(f"- Average Time: {avg_time:.2f}s\n")
                        f.write(f"- Average Memory: {avg_mem:.1f}MB\n")
                        f.write(f"- Tests: {len(res_tests)}\n\n")

                # Performance by encryption
                f.write("## Performance by Encryption\n\n")
                for enc in self.ENCRYPTION_STRENGTHS:
                    enc_tests = [r for r in successful_tests if r['encryption_strength'] == enc]
                    if enc_tests:
                        avg_time = np.mean([r['encrypt_time'] for r in enc_tests])
                        f.write(f"- **{enc}:** {avg_time:.4f}s average encryption time\n")

            if failed_tests:
                f.write("\n## Failed Tests\n\n")
                error_types = {}
                for test in failed_tests:
                    error_type = test.get('error_type', 'Unknown')
                    error_types[error_type] = error_types.get(error_type, 0) + 1

                for error_type, count in error_types.items():
                    f.write(f"- **{error_type}:** {count} occurrences\n")

        print(f"  Analysis saved: {analysis_file}")


def main():
    """Run stress testing."""
    tester = VideoStressTest()
    tester.run_comprehensive_test()


if __name__ == '__main__':
    main()
