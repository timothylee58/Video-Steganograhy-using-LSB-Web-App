# VidStega - Quick Start Guide

## 🚀 30-Second Setup

### Windows:
```cmd
setup_demo.bat
run_demo.bat
```

### Linux/Mac:
```bash
chmod +x setup_demo.sh run_demo.sh
./setup_demo.sh
./run_demo.sh
```

### Open Browser:
```
http://localhost:5000
```

---

## 📋 System Requirements

**Minimum:**
- Python 3.8+
- 4GB RAM
- 2GB disk space

**Recommended:**
- Python 3.10+
- 8GB RAM
- Fast internet (for uploads)

---

## 🎯 Quick Demo (2 Minutes)

### 1. Generate Test Video
```bash
python generate_demo_video.py
# Select option 2 (medium, 10s)
```

### 2. Embed a Message
1. Go to http://localhost:5000
2. **Embed Section:**
   - Upload: `demo_videos/demo_720p_10s.mp4`
   - Frames: `0, 5, 10, 15, 20`
   - Message: `"Hello World! This is hidden!"`
   - Password: `demo123`
   - Click **"🚀 Embed & Download"**

### 3. Extract the Message
1. **Extract Section:**
   - Upload the downloaded stego-video
   - Start: `0`, End: `25`
   - Password: `demo123`
   - Click **"🔓 Extract Hidden Message"**
   - ✅ See your message!

---

## 🔧 Troubleshooting

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Port 5000 in use"
```bash
# Windows
netstat -ano | findstr :5000
taskkill /PID <PID> /F

# Linux/Mac
lsof -ti:5000 | xargs kill -9
```

### "Upload failed"
- Check file size (< 2GB)
- Verify format (MP4, AVI, MOV, MKV, WEBM)
- Ensure `uploads/` folder exists

---

## 🎨 Features to Showcase

### Security
- ✅ AES-256 encryption
- ✅ Multiple cipher modes (GCM, CBC, CTR, CFB)
- ✅ PBKDF2 key derivation (100,000 iterations)

### Reliability
- ✅ Reed-Solomon error correction
- ✅ Metadata preservation
- ✅ Multi-frame distribution

### Intelligence
- ✅ AI-powered frame selection
- ✅ Content-aware embedding
- ✅ Suspicion detection
- ✅ Smart compression for social media

### User Experience
- ✅ Beautiful modern UI (Tailwind CSS)
- ✅ Drag & drop file upload (Dropzone.js)
- ✅ Real-time progress tracking
- ✅ Responsive design (mobile-friendly)

---

## 📊 Supported Formats

### Video Formats
- MP4 (recommended)
- AVI
- MOV
- MKV
- WEBM

### Resolutions
- 480p (854x480) - ✅ Best for demos
- 720p (1280x720) - ✅ Recommended
- 1080p (1920x1080) - ⚠️ Slower
- 1440p (2560x1440) - ⚠️ Requires 16GB+ RAM

### Encryption
- **Strengths:** AES-128, AES-192, AES-256
- **Modes:** CBC, CTR, GCM (recommended), CFB

---

## 📖 Documentation

- **Full Demo Guide:** [DEMO_GUIDE.md](DEMO_GUIDE.md)
- **Scalability Analysis:** [SCALABILITY_ANALYSIS.md](SCALABILITY_ANALYSIS.md)
- **Quick Summary:** [QUICK_SUMMARY.md](QUICK_SUMMARY.md)
- **Architecture:** [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md)

---

## 🆘 Need Help?

### Common Questions

**Q: Do I need Redis/Celery?**
A: No! The app runs in synchronous mode without them. Perfect for demos.

**Q: Can I use AI features?**
A: Yes, but requires API keys (optional). App works fully without them.

**Q: How long does processing take?**
A:
- 480p (10s video): ~10-15 seconds
- 720p (10s video): ~20-30 seconds
- 1080p (10s video): ~40-60 seconds

**Q: What's the maximum file size?**
A: 2GB upload limit (configurable in `app/config.py`)

**Q: Can I process multiple videos?**
A: Yes, but sequentially in demo mode. Use Celery for concurrent processing.

---

## 🎬 Demo Tips

### Do's
✅ Use small videos (< 100MB) for faster demos
✅ Show before/after comparison
✅ Emphasize security features
✅ Demonstrate wrong password = garbled output
✅ Keep demo under 10 minutes

### Don'ts
❌ Don't use 1440p without 16GB RAM
❌ Don't forget your demo password
❌ Don't rely on internet for local demos
❌ Don't process very long videos (> 1 min)
❌ Don't skip testing before live demo

---

## 📞 Quick Commands Reference

### Setup
```bash
# Windows
setup_demo.bat

# Linux/Mac
./setup_demo.sh
```

### Run
```bash
# Windows
run_demo.bat

# Linux/Mac
./run_demo.sh
```

### Generate Demo Videos
```bash
python generate_demo_video.py
```

### Stress Test (Optional)
```bash
# Windows
run_stress_test.bat

# Linux/Mac
./run_stress_test.sh
```

---

## 🌟 Success Checklist

Before your demo:
- [ ] Run `setup_demo.bat` / `setup_demo.sh`
- [ ] Test with `run_demo.bat` / `run_demo.sh`
- [ ] Generate demo videos
- [ ] Test embed → extract flow
- [ ] Prepare talking points
- [ ] Have backup plan (screenshots/video)

---

**You're ready! Good luck with your showcase! 🚀**

**For detailed instructions, see:** [DEMO_GUIDE.md](DEMO_GUIDE.md)
