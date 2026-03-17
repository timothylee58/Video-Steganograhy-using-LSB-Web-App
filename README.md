# 🎬 VidStega — Video Steganography Using LSB

> Final Year Project — Hide encrypted secret messages inside video files using the Least Significant Bit (LSB) technique, with a production-ready web application.

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![Flask](https://img.shields.io/badge/Flask-2.3%2B-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Deployment](https://img.shields.io/badge/Deployed%20on-Render-purple)

---

## 📖 About

Video steganography is a vital medium for covert communication, enabling the hiding of confidential data within video files while preserving their visual quality. The **Least Significant Bit (LSB)** technique is widely used due to its simplicity and efficiency.

This project addresses key limitations of existing LSB systems — low embedding capacity and vulnerability to steganalysis — by combining **advanced LSB embedding** with **AES encryption** (128/192/256-bit) to maximize hidden data capacity while ensuring security and confidentiality.

The result is a full-stack, production-ready web application supporting videos up to 1440p with configurable encryption strength and cipher modes.

---

## 📋 Table of Contents

- [Features](#features)
- [Tech Stack](#tech-stack)
- [Project Structure](#project-structure)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [How to Use](#how-to-use)
- [API Endpoints](#api-endpoints)
- [Authentication](#authentication)
- [Database](#database)
- [Testing](#testing)
- [Deployment](#deployment)
- [Troubleshooting](#troubleshooting)
- [Additional Documentation](#additional-documentation)
- [Legal Disclaimer](#legal-disclaimer)
- [Acknowledgments](#acknowledgments)

---

## ✨ Features

- **Multiple Resolutions** — Supports 480p, 720p, 1080p, and 1440p videos
- **Flexible Encryption** — AES-128/192/256 with CBC, CTR, GCM, or CFB modes
- **PBKDF2 Key Derivation** — 100,000 iterations for robust password-based encryption
- **Reed-Solomon Error Correction** — Protects hidden data integrity
- **Scalable Architecture** — Async processing with Celery and Redis
- **Capacity Calculator** — Check how much data can be hidden before encoding
- **Real-time Progress** — WebSocket updates for long-running operations
- **OAuth2 Authentication** — Login with Google or GitHub
- **JWT Sessions** — Secure token-based authentication with refresh token rotation
- **RESTful API** — Easy integration with any frontend or mobile app
- **AI-powered Frame Selection** — Intelligent frame analysis for optimal embedding
- **Batch Processing** — Embed/extract across multiple videos
- **Docker Support** — Containerized for consistent deployment

---

## 🛠️ Tech Stack

### Backend
| Technology | Purpose |
|---|---|
| Python 3.8+ | Core language |
| Flask | Web framework |
| Flask-SocketIO | Real-time WebSocket communication |
| Flask-SQLAlchemy | ORM and database management |
| Celery | Async task queue |
| Redis | Message broker for Celery |
| Gunicorn + Eventlet | Production WSGI server |
| Alembic | Database migrations |

### Security & Auth
| Technology | Purpose |
|---|---|
| Authlib | OAuth2 client (Google, GitHub) |
| PyJWT | JWT token generation and validation |
| cryptography / pycryptodome | AES encryption |
| reedsolo | Reed-Solomon error correction |

### Video & Media
| Technology | Purpose |
|---|---|
| OpenCV | Video frame extraction and processing |
| MoviePy | Video encoding and format handling |
| NumPy | Pixel-level data manipulation |
| Pillow | Image processing |

### Frontend
| Technology | Purpose |
|---|---|
| HTML/CSS/JavaScript | UI |
| Socket.IO (client) | Real-time progress updates |

### Database
| Technology | Purpose |
|---|---|
| PostgreSQL 15 | Production database |
| SQLite | Development/demo fallback |

### DevOps
| Technology | Purpose |
|---|---|
| Docker | Containerization |
| Render | Cloud deployment |
| pytest / supertest | Testing |

---

## 📁 Project Structure

```
Video-Steganograhy-using-LSB-Web-App/
├── app/
│   ├── __init__.py
│   ├── config.py                         # App configuration
│   ├── db.py                             # Database initialization
│   ├── decorators.py                     # Auth decorators
│   ├── models.py                         # SQLAlchemy models
│   ├── routes.py                         # Core embed/extract API routes
│   ├── routes_auth.py                    # OAuth2 & JWT auth routes
│   ├── routes_user.py                    # User management routes
│   ├── scheduled_tasks.py                # Periodic background tasks
│   ├── tasks.py                          # Celery task definitions
│   ├── websocket.py                      # WebSocket event handlers
│   └── services/
│       ├── steganography_service.py      # Core LSB steganography logic
│       ├── crypto_service.py             # AES encryption & key derivation
│       ├── video_service.py              # Video processing with OpenCV
│       ├── ai_service.py                 # AI-powered frame analysis
│       ├── batch_service.py              # Batch processing support
│       ├── metadata_service.py           # Video metadata handling
│       ├── oauth_service.py              # OAuth2 provider integration
│       ├── token_service.py              # JWT token management
│       ├── token_refresh_lock_service.py # Concurrent refresh protection
│       ├── password_hash_service.py      # Password hashing utilities
│       └── session_cleanup_service.py    # Expired session cleanup
├── templates/
│   └── index.html                        # Frontend UI
├── run.py                                # App entry point
├── celery_worker.py                      # Celery worker entry point
├── requirements.txt
├── Dockerfile
├── render.yaml                           # Render deployment config
├── alembic.ini                           # DB migration config
├── conftest.py
├── stress_test.py
└── generate_demo_video.py
```

---

## ✅ Prerequisites

- **Python 3.8+** (3.10+ recommended)
- **pip**
- **4GB RAM minimum** (8GB recommended)
- **2GB free disk space**

**Optional (for full features):**
- Redis (for async processing with Celery)
- FFmpeg (for enhanced video processing)
- Docker (for containerized deployment)
- Google/GitHub OAuth credentials (for OAuth2 login)

---

## 🚀 Installation

### Automated Setup (Recommended)

**Windows:**
```cmd
setup_demo.bat
```

**Linux/Mac:**
```bash
chmod +x setup_demo.sh
./setup_demo.sh
```

### Manual Setup

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

4. **Set up environment variables** (see [Configuration](#configuration))

5. **Run database migrations:**
   ```bash
   alembic upgrade head
   ```

---

## ⚙️ Configuration

Create a `.env` file in the root directory:

```env
# Flask
FLASK_ENV=development
FLASK_DEBUG=1
SECRET_KEY=your-secret-key

# Database
DATABASE_URL=sqlite:///vidstega.db
# For PostgreSQL: postgresql://user:password@localhost:5432/vidstega

# JWT
JWT_SECRET_KEY=your-jwt-secret-key

# OAuth2 - Google
GOOGLE_CLIENT_ID=your-google-client-id
GOOGLE_CLIENT_SECRET=your-google-client-secret

# OAuth2 - GitHub
GITHUB_CLIENT_ID=your-github-client-id
GITHUB_CLIENT_SECRET=your-github-client-secret

# Celery / Redis
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0

# Upload limits
MAX_UPLOAD_MB=500

# WebSocket
SOCKETIO_ASYNC_MODE=eventlet

# Session security
SESSION_COOKIE_SECURE=False
SESSION_COOKIE_HTTPONLY=True
SESSION_COOKIE_SAMESITE=Lax
```

---

## ▶️ Running the Application

### Demo Mode (No Redis/Celery Required)

Ideal for quick demos, testing, and single-user use. Processing runs synchronously.

```bash
python run.py
```

Open your browser at **http://localhost:5000**

### Production Mode (With Redis and Celery)

Suitable for multi-user environments with async processing.

**Terminal 1 — Start Redis:**
```bash
redis-server
# Or via Docker:
docker run -d -p 6379:6379 redis:latest
```

**Terminal 2 — Start Celery Worker:**
```bash
celery -A app.tasks.celery_app worker --loglevel=info --pool=solo
```

**Terminal 3 — Start Flask App:**
```bash
python run.py
```

### Docker

```bash
docker build -t vidstega .
docker run -p 5000:5000 vidstega
```

---

## 📖 How to Use

### Embedding a Secret Message

1. Open **http://localhost:5000** and go to the **Embed (Encode)** section
2. Upload a video file (MP4, AVI, MOV, MKV, WEBM; max 500MB)
3. Specify frame numbers (e.g. `0, 5, 10, 15, 20`) or use **Auto-Select** for AI-powered frame selection
4. Type your secret message or upload a file to embed
5. Set a strong password
6. Choose encryption settings:
   - **Strength:** AES-128, AES-192, or AES-256
   - **Cipher Mode:** CBC, CTR, GCM, or CFB
7. Click **Embed & Download** and save the output stego-video

### Extracting a Hidden Message

1. Go to the **Extract (Decode)** section
2. Upload the stego-video
3. Set the same frame range used during embedding
4. Enter the same password and encryption settings
5. Click **Extract Hidden Message** to reveal the content

> **Important:** Extraction requires the exact password, encryption strength, cipher mode, and frame range used during embedding. Incorrect settings will produce an error or garbled output — confirming the system's security.

---

## 🔌 API Endpoints

### Core

| Method | Endpoint | Description |
|---|---|---|
| GET | `/` | Serves the frontend UI |
| GET | `/health` | Health check |
| POST | `/embed` | Embed a secret message into a video |
| POST | `/extract` | Extract a hidden message from a video |
| GET | `/capacity` | Calculate embedding capacity for a video |
| GET | `/task/<task_id>` | Check async task status |

### Authentication

| Method | Endpoint | Description |
|---|---|---|
| POST | `/auth/register` | Register a new user |
| POST | `/auth/login` | Login with email/password |
| POST | `/auth/refresh` | Refresh JWT access token |
| POST | `/auth/logout` | Logout and revoke token |
| GET | `/auth/google` | Initiate Google OAuth2 flow |
| GET | `/auth/google/callback` | Google OAuth2 callback |
| GET | `/auth/github` | Initiate GitHub OAuth2 flow |
| GET | `/auth/github/callback` | GitHub OAuth2 callback |

### User

| Method | Endpoint | Description |
|---|---|---|
| GET | `/user/profile` | Get current user profile |
| PUT | `/user/profile` | Update user profile |
| GET | `/user/history` | Get processing history |

---

## 🔐 Authentication

VidStega supports two authentication methods:

### Email/Password
- Passwords hashed with bcrypt
- JWT access tokens (short-lived) + refresh tokens (long-lived)
- Concurrent refresh token rotation with lock protection

### OAuth2
- **Google** and **GitHub** social login via Authlib
- Tokens stored securely, session cookies are `HttpOnly` and `SameSite=Lax`

---

## 🗄️ Database

- **Development:** SQLite (auto-created, no setup needed)
- **Production:** PostgreSQL 15

Run migrations:
```bash
alembic upgrade head
```

Create a new migration after model changes:
```bash
alembic revision --autogenerate -m "description"
```

---

## 🧪 Testing

```bash
# Run all tests
pytest

# Auth integration tests
pytest test_auth_integration.py

# OAuth security tests
pytest test_oauth_security.py

# User isolation tests
pytest test_user_isolation.py

# Stress tests
python stress_test.py
# Or on Windows:
run_stress_test.bat
```

Generate test videos for testing:
```bash
python generate_demo_video.py
```

### Security Demonstration

| Test | Expected Result |
|---|---|
| Wrong password | Error — confirms encryption protection |
| Wrong cipher mode | Garbled output — settings must match exactly |
| Wrong frame range | Extraction fails — data is tied to specific frames |

---

## ☁️ Deployment

Configured for **Render** via `render.yaml`:

- **Runtime:** Docker
- **Database:** PostgreSQL 15 (auto-provisioned)
- **Auto-deploy:** On push to main branch
- **Health check:** `GET /health`

**Required environment variables on Render:**
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET`
- `GITHUB_CLIENT_ID` / `GITHUB_CLIENT_SECRET`
- `SECRET_KEY` / `JWT_SECRET_KEY` (auto-generated by Render)
- `DATABASE_URL` (auto-linked from PostgreSQL instance)

---

## 🔧 Troubleshooting

| Problem | Solution |
|---|---|
| Module not found | Run `pip install -r requirements.txt` |
| Port 5000 in use | Kill the existing process or change port in `run.py` |
| Video upload fails | Check format/size and ensure `uploads/` directory exists |
| Celery unavailable | Safe to ignore for demos — app falls back to sync mode |
| Slow processing | Use smaller videos (480p, 10–30 sec) with fewer frames |
| AI features not working | Requires API keys (optional) — app works fully without them |
| Database errors | Run `alembic upgrade head` to apply migrations |
| OAuth login fails | Verify `GOOGLE_CLIENT_ID` / `GITHUB_CLIENT_ID` are set correctly |

---

## 📚 Additional Documentation

| File | Description |
|---|---|
| [QUICK_START.md](QUICK_START.md) | Condensed setup instructions |
| [QUICK_SUMMARY.md](QUICK_SUMMARY.md) | Architecture overview |
| [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) | System design diagrams |
| [SCALABILITY_ANALYSIS.md](SCALABILITY_ANALYSIS.md) | Performance and scalability details |
| [STRESS_TEST_README.md](STRESS_TEST_README.md) | Stress testing guide |
| [DEMO_GUIDE.md](DEMO_GUIDE.md) | Detailed demo guide with audience-specific tips |
| [OAUTH2_SETUP_GUIDE.md](OAUTH2_SETUP_GUIDE.md) | OAuth2 configuration guide |
| [SECURITY_AUDIT_REPORT.md](SECURITY_AUDIT_REPORT.md) | Security audit findings |
| [PRODUCTION_DEPLOYMENT_GUIDE.md](PRODUCTION_DEPLOYMENT_GUIDE.md) | Full production deployment steps |

---

## ⚠️ Legal Disclaimer

This software is provided for **educational and legitimate privacy purposes only**. Users are responsible for complying with local laws and regulations. The authors assume no liability for misuse.

**Appropriate Uses:**
- Personal privacy protection
- Secure business communication
- Digital watermarking
- Academic research

**Inappropriate Uses:**
- Illegal communication
- Circumventing lawful surveillance
- Copyright infringement
- Distribution of illegal content

---

## 🤝 Contributing

1. Fork the repository
2. Create a branch: `git checkout -b feature/your-feature`
3. Commit: `git commit -m 'Add some feature'`
4. Push: `git push origin feature/your-feature`
5. Open a Pull Request

---

## 🙏 Acknowledgments

- [OpenCV](https://opencv.org/) — Video processing
- [cryptography](https://cryptography.io/) — AES encryption
- [Flask](https://flask.palletsprojects.com/) — Web framework
- [Authlib](https://authlib.org/) — OAuth2 integration
- The steganography research community

---

*Built for privacy-conscious users worldwide*
