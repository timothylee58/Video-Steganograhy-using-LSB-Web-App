# Final Year Project - Video Steganography Using LSB Technique

Video steganography is a vital medium for covert communication, which enables the hiding of confidential and secret data within video files while preserving their visual quality. The Least Significant Bit (LSB) technique has been widely used in video steganography due to its simplicity and efficiency. However, existing LSB-based systems suffer from limitations such as low embedding capacity and vulnerability to steganalysis attacks.

One of the primary objectives of the project is to increase the embedding capacity further while maintaining the visual integrity of the video. Additionally, with advanced LSB embedding techniques and encryption mechanisms, the systems maximise the amount of data hidden within the video while safeguarding its security and confidentiality. Rigorous testing and evaluation validate the system's performance and demonstrate its effectiveness in securely embedding and extracting hidden data within video files. The developed video steganography system utilizing the LSB technique offers an efficient and reliable solution for covert communication.

Built on the research technique, a production-ready web application for hiding encrypted messages within videos using the LSB (Least Significant Bit) technique was created.
It supports resolutions up to 1440p with configurable encryption strength and cipher modes.

---

## Features

- **Multiple Resolutions:** Support for 480p, 720p, 1080p, and 1440p videos
- **Flexible Encryption:** Choose from AES-128/192/256 with CBC, CTR, GCM, or CFB modes
- **Robust Security:** PBKDF2 key derivation with 100,000 iterations
- **Scalable Architecture:** Async processing with Celery and Redis
- **Capacity Calculator:** Check how much data can be hidden before encoding
- **Real-time Progress:** WebSocket updates for long-running operations
- **RESTful API:** Easy integration with any frontend or mobile app

---

## Getting Started

### Prerequisites

- **Python 3.8+** (Python 3.10+ recommended)
- **pip** (Python package manager)
- **4GB RAM minimum** (8GB recommended)
- **2GB free disk space**

**Optional (for full features):**
- Redis (for async processing with Celery)
- FFmpeg (for enhanced video processing)
- AI API Keys (for Claude/OpenAI-powered features)

### Installation

#### Automated Setup (Recommended)

**Windows:**
```cmd
setup_demo.bat
```

**Linux/Mac:**
```bash
chmod +x setup_demo.sh
./setup_demo.sh
```

#### Manual Setup

1. **Create a virtual environment:**
   ```bash
   # Windows
   python -m venv venv
   venv\Scripts\activate

   # Linux/Mac
   python3 -m venv venv
   source venv/bin/activate
   ```

2. **Install dependencies:**
   ```bash
   pip install --upgrade pip
   pip install -r requirements.txt
   ```

3. **Create required directories:**
   ```bash
   mkdir uploads outputs static
   ```

4. **Set environment variables (optional):**
   ```bash
   # Windows
   set FLASK_ENV=development
   set FLASK_DEBUG=1

   # Linux/Mac
   export FLASK_ENV=development
   export FLASK_DEBUG=1
   ```

---

## Running the Application

### Demo Mode (No Redis/Celery Required)

Ideal for quick demonstrations, testing, and single-user use. Processing runs synchronously without task queues.

```bash
python run.py
```

Open your browser at **http://localhost:5000**

### Production Mode (With Redis and Celery)

Suitable for multi-user environments and showcasing async processing capabilities.

**Terminal 1 - Start Redis:**
```bash
redis-server
# Or via Docker: docker run -d -p 6379:6379 redis:latest
```

**Terminal 2 - Start Celery Worker:**
```bash
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

**Terminal 3 - Start Flask App:**
```bash
python run.py
```

---

## How to Use VidStega

### Embedding a Secret Message

1. Open **http://localhost:5000** and navigate to the **Embed (Encode)** section
2. Upload a video file (supported formats: MP4, AVI, MOV, MKV, WEBM; max 2GB)
3. Specify frame numbers for embedding (e.g., `0, 5, 10, 15, 20`) or use **Auto-Select** for AI-powered frame selection
4. Type your secret message or choose a file to embed
5. Set a strong password
6. Choose encryption settings:
   - **Strength:** AES-128, AES-192, or AES-256
   - **Cipher Mode:** CBC, CTR, GCM, or CFB
7. Click **Embed & Download** and save the output stego-video

### Extracting a Hidden Message

1. Navigate to the **Extract (Decode)** section
2. Upload the stego-video
3. Set the frame range used during embedding
4. Enter the same password and encryption settings used during embedding
5. Click **Extract Hidden Message** to reveal the original content

> **Note:** Extraction requires the exact password, encryption strength, and cipher mode used during embedding. Incorrect settings will produce unreadable output or an error, confirming the security of the system.

---

## Demo Walkthrough

### Quick Demo (2 Minutes)

1. Run `setup_demo.bat` (Windows) or `./setup_demo.sh` (Linux/Mac)
2. Open **http://localhost:5000**
3. Upload a small video (under 100MB)
4. Enter a message such as `This is a hidden message!`
5. Set a password, click **Embed & Download**
6. Re-upload the stego-video, enter the same password, and extract the message

### Generating Test Videos

Use the included script to create sample videos at various resolutions:
```bash
python generate_demo_video.py
```

### Demonstrating Security

- **Wrong password:** Produces an error, confirming encryption protection
- **Wrong cipher mode:** Returns garbled output, proving settings must match exactly
- **Wrong frame range:** Extraction fails, showing data is tied to specific frames

### Comparing Original and Stego-Video

Play the original and stego-video side by side. The visual difference is imperceptible, demonstrating the effectiveness of the LSB technique.

---

## Architecture Overview

VidStega is built with a modular service-oriented architecture:

| Component | Purpose |
|-----------|---------|
| `app/routes.py` | Flask API endpoints for embed/extract operations |
| `app/services/steganography_service.py` | Core LSB steganography logic |
| `app/services/crypto_service.py` | AES encryption and key derivation |
| `app/services/video_service.py` | Video processing with OpenCV |
| `app/services/ai_service.py` | AI-powered frame analysis |
| `app/services/batch_service.py` | Batch processing support |
| `app/services/metadata_service.py` | Video metadata handling |
| `app/tasks.py` | Celery async task definitions |
| `app/websocket.py` | Real-time progress via WebSocket |
| `templates/index.html` | Frontend UI |

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Module not found errors | Run `pip install -r requirements.txt` |
| Port 5000 already in use | Kill the existing process or change the port in `run.py` |
| Video upload fails | Verify file format and size; ensure `uploads/` directory exists |
| Celery unavailable warning | Safe to ignore for demos; app falls back to synchronous mode |
| Slow processing | Use smaller videos (480p, 10-30 seconds) and fewer frames |
| AI features not working | AI features require API keys (optional); app works fully without them |

---

## Additional Documentation

- [QUICK_START.md](QUICK_START.md) - Condensed setup instructions
- [QUICK_SUMMARY.md](QUICK_SUMMARY.md) - Architecture overview
- [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) - System design diagrams
- [SCALABILITY_ANALYSIS.md](SCALABILITY_ANALYSIS.md) - Performance and scalability details
- [STRESS_TEST_README.md](STRESS_TEST_README.md) - Stress testing guide
- [DEMO_GUIDE.md](DEMO_GUIDE.md) - Detailed demonstration guide with audience-specific tips

---

## License

MIT License - see LICENSE file for details.

## Legal Disclaimer

This software is provided for educational and legitimate privacy purposes only. Users are responsible for complying with local laws and regulations. The authors assume no liability for misuse.

**Appropriate Uses:**
- Personal privacy protection
- Secure business communication
- Digital watermarking
- Data backup and recovery

**Inappropriate Uses:**
- Illegal communication
- Circumventing lawful surveillance
- Copyright infringement
- Distribution of illegal content

## Acknowledgments

- OpenCV for video processing
- Cryptography library for encryption
- Flask for the web framework
- The steganography research community

---

*Built for privacy-conscious users worldwide*
