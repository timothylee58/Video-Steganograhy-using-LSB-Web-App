"""
Generate Demo Videos for VidStega Showcasing
Creates sample videos in various resolutions for testing
"""

import cv2
import numpy as np
import os
from datetime import datetime


def generate_demo_video(resolution_name, width, height, duration_seconds=10, fps=30):
    """
    Generate a colorful demo video with text overlays.

    Args:
        resolution_name: Name of the resolution (e.g., '480p', '720p')
        width: Video width
        height: Video height
        duration_seconds: Length of video in seconds
        fps: Frames per second
    """
    output_dir = 'demo_videos'
    os.makedirs(output_dir, exist_ok=True)

    filename = f'demo_{resolution_name}_{duration_seconds}s.mp4'
    filepath = os.path.join(output_dir, filename)

    print(f"Generating {resolution_name} demo video ({width}x{height})...")
    print(f"  Duration: {duration_seconds}s")
    print(f"  Frames: {duration_seconds * fps}")

    # Create video writer
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    out = cv2.VideoWriter(filepath, fourcc, fps, (width, height))

    total_frames = duration_seconds * fps

    for frame_num in range(total_frames):
        # Create colorful gradient background
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        # Animated gradient
        progress = frame_num / total_frames
        hue = int(progress * 179)  # HSV hue range 0-179

        # Create gradient
        for y in range(height):
            for x in range(width):
                h = (hue + x // 10 + y // 10) % 180
                s = 150 + (x + y) % 100
                v = 200 + (x * y) % 55
                frame[y, x] = [h, min(s, 255), min(v, 255)]

        # Convert HSV to BGR
        frame = cv2.cvtColor(frame, cv2.COLOR_HSV2BGR)

        # Add noise for texture (important for steganography)
        noise = np.random.randint(-20, 20, (height, width, 3), dtype=np.int16)
        frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)

        # Add text overlays
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = max(width / 1000, 0.5)
        thickness = max(int(width / 500), 1)

        # Title
        title = "VidStega Demo Video"
        title_size = cv2.getTextSize(title, font, font_scale * 1.5, thickness * 2)[0]
        title_x = (width - title_size[0]) // 2
        title_y = height // 4

        cv2.putText(frame, title, (title_x, title_y),
                   font, font_scale * 1.5, (255, 255, 255), thickness * 2, cv2.LINE_AA)

        # Resolution info
        info = f"{resolution_name} ({width}x{height})"
        info_size = cv2.getTextSize(info, font, font_scale, thickness)[0]
        info_x = (width - info_size[0]) // 2
        info_y = height // 2

        cv2.putText(frame, info, (info_x, info_y),
                   font, font_scale, (255, 255, 255), thickness, cv2.LINE_AA)

        # Frame counter
        frame_text = f"Frame: {frame_num + 1}/{total_frames}"
        cv2.putText(frame, frame_text, (20, height - 60),
                   font, font_scale * 0.7, (255, 255, 255), thickness, cv2.LINE_AA)

        # Time
        time_text = f"Time: {frame_num / fps:.2f}s"
        cv2.putText(frame, time_text, (20, height - 30),
                   font, font_scale * 0.7, (255, 255, 255), thickness, cv2.LINE_AA)

        # Timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        timestamp_size = cv2.getTextSize(timestamp, font, font_scale * 0.6, 1)[0]
        cv2.putText(frame, timestamp, (width - timestamp_size[0] - 20, height - 30),
                   font, font_scale * 0.6, (200, 200, 200), 1, cv2.LINE_AA)

        # Progress bar
        bar_width = width - 100
        bar_height = 20
        bar_x = 50
        bar_y = height - height // 8

        # Background
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height),
                     (50, 50, 50), -1)

        # Progress
        progress_width = int(bar_width * progress)
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + progress_width, bar_y + bar_height),
                     (0, 255, 0), -1)

        # Border
        cv2.rectangle(frame, (bar_x, bar_y), (bar_x + bar_width, bar_y + bar_height),
                     (255, 255, 255), 2)

        # Write frame
        out.write(frame)

        # Progress indicator
        if (frame_num + 1) % (fps * 2) == 0:  # Every 2 seconds
            print(f"  Progress: {frame_num + 1}/{total_frames} frames ({progress * 100:.0f}%)")

    out.release()

    file_size_mb = os.path.getsize(filepath) / (1024 * 1024)
    print(f"✓ Generated: {filename}")
    print(f"  Size: {file_size_mb:.2f} MB")
    print(f"  Path: {filepath}\n")

    return filepath


def main():
    """Generate demo videos in multiple resolutions."""
    print("=" * 60)
    print("VidStega Demo Video Generator")
    print("=" * 60)
    print()

    # Resolution configurations
    resolutions = {
        '480p': (854, 480),
        '720p': (1280, 720),
        '1080p': (1920, 1080),
    }

    durations = {
        'short': 5,   # 5 seconds
        'medium': 10, # 10 seconds
        'long': 30,   # 30 seconds (optional)
    }

    print("Select videos to generate:")
    print("  1. Short (5s) - Quick demos")
    print("  2. Medium (10s) - Standard demos")
    print("  3. Long (30s) - Extended demos")
    print("  4. All durations")
    print()

    try:
        choice = input("Enter choice (1-4) [default: 2]: ").strip() or "2"

        if choice == "1":
            selected_durations = {'short': 5}
        elif choice == "2":
            selected_durations = {'medium': 10}
        elif choice == "3":
            selected_durations = {'long': 30}
        elif choice == "4":
            selected_durations = durations
        else:
            print("Invalid choice, using medium (10s)")
            selected_durations = {'medium': 10}

        print()
        print("Generating videos...")
        print()

        generated_files = []

        for duration_name, duration in selected_durations.items():
            for res_name, (width, height) in resolutions.items():
                filepath = generate_demo_video(res_name, width, height, duration)
                generated_files.append(filepath)

        print("=" * 60)
        print("Generation Complete!")
        print("=" * 60)
        print()
        print("Generated files:")
        for filepath in generated_files:
            print(f"  - {filepath}")
        print()
        print("These videos are ready for your VidStega demo!")
        print()

    except KeyboardInterrupt:
        print("\n\nGeneration cancelled by user.")
    except Exception as e:
        print(f"\nError: {e}")


if __name__ == '__main__':
    main()
