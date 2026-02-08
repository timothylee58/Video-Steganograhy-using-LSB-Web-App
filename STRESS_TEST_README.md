# VidStega Stress Testing Guide

## 🎯 Overview

This stress testing suite evaluates VidStega's performance across different resolutions, encryption configurations, and video sizes to identify scalability limitations and bottlenecks.

## 📋 What Gets Tested

### Resolutions
- ✅ **480p** (854x480) - Low resolution baseline
- ✅ **720p** (1280x720) - Standard HD
- ✅ **1080p** (1920x1080) - Full HD
- ✅ **1440p** (2560x1440) - 2K/QHD - **Critical test**

### Encryption Configurations
- **Strengths:** AES-128, AES-192, AES-256
- **Cipher Modes:** CBC, CTR, GCM, CFB
- **Total Combinations:** 12 encryption configurations

### Video Lengths
- 30 frames (1 second @ 30fps)
- 60 frames (2 seconds)
- 120 frames (4 seconds)
- 300 frames (10 seconds)
- 600 frames (20 seconds)

### Measured Metrics
1. **Processing Time:** Total, encryption, read, embed, write
2. **Memory Usage:** RSS, VMS, peak memory, memory increase
3. **Resource Utilization:** CPU, disk I/O
4. **Success/Failure Rates**
5. **Error Types and Frequencies**

## 🚀 Quick Start

### Option 1: Windows (Batch File)
```cmd
run_stress_test.bat
```

### Option 2: Linux/Mac (Shell Script)
```bash
chmod +x run_stress_test.sh
./run_stress_test.sh
```

### Option 3: Manual Python
```bash
# Activate virtual environment
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install numpy opencv-python psutil reedsolo

# Run tests
python stress_test.py
```

## ⏱️ Expected Duration

- **Full Test Suite:** 45-60 minutes
- **Per Resolution:** 10-15 minutes
- **Quick Test (480p only):** 5-10 minutes

## 💾 System Requirements

### Minimum
- **CPU:** 4 cores
- **RAM:** 8 GB
- **Disk Space:** 10 GB free
- **Python:** 3.8+

### Recommended
- **CPU:** 8+ cores
- **RAM:** 16 GB
- **Disk Space:** 20 GB free
- **Python:** 3.10+

### For Full 1440p Testing
- **RAM:** 16 GB+ (32 GB recommended)
- **Disk Space:** 30 GB free

## 📊 Output Files

After running tests, you'll find:

```
stress_test_results/
├── stress_test_results.json     # Raw test data
├── analysis_report.md            # Automated analysis
├── test_video_854x480_30f.mp4   # Generated test videos
├── test_video_1280x720_60f.mp4
├── test_video_1920x1080_120f.mp4
└── test_video_2560x1440_300f.mp4
```

### stress_test_results.json
Complete test results in JSON format. Each entry contains:
```json
{
  "timestamp": "2025-02-08T10:30:45",
  "resolution": "1440p",
  "width": 2560,
  "height": 1440,
  "frame_count": 300,
  "encryption_strength": "AES-256",
  "cipher_mode": "GCM",
  "operation": "embed",
  "success": true,
  "total_time": 123.45,
  "memory_increase_mb": 1024.5,
  ...
}
```

### analysis_report.md
Automated analysis including:
- Success/failure rates
- Average and maximum performance metrics
- Performance breakdown by resolution
- Performance breakdown by encryption
- Common failure patterns

## 📈 Interpreting Results

### Memory Usage Thresholds
- **< 500 MB:** ✅ Safe - No concerns
- **500 MB - 2 GB:** ⚠️ Monitor - May cause issues with concurrent requests
- **2-4 GB:** ⚠️ High Risk - Limit concurrent processing
- **> 4 GB:** 🔴 Critical - Immediate optimization required

### Processing Time Thresholds
- **< 30s:** ✅ Excellent
- **30-60s:** ✅ Good
- **60-120s:** ⚠️ Acceptable - May hit timeouts with retries
- **> 120s:** 🔴 Slow - Risk of timeout (3600s limit)

### Success Rate Benchmarks
- **100%:** ✅ Excellent
- **95-99%:** ✅ Good - Investigate failures
- **90-94%:** ⚠️ Concerning - Significant issues
- **< 90%:** 🔴 Critical - Major architectural problems

## 🔍 Analyzing Results

### Step 1: Check Overall Success Rate
```bash
# Count successful tests
grep '"success": true' stress_test_results/stress_test_results.json | wc -l

# Count failed tests
grep '"success": false' stress_test_results/stress_test_results.json | wc -l
```

### Step 2: Identify Bottlenecks
Look for:
1. **Memory spikes** (memory_increase_mb > 2000)
2. **Slow operations** (total_time > 120)
3. **Failures at specific resolutions** (check 1440p first)

### Step 3: Review analysis_report.md
Open `stress_test_results/analysis_report.md` for:
- Performance by resolution
- Performance by encryption
- Common error types

## 🐛 Common Issues

### Issue 1: Out of Memory (OOM)
**Symptom:** Tests fail with "MemoryError" or system freezes

**Solution:**
1. Close other applications
2. Reduce test parameters in `stress_test.py`:
   ```python
   FRAME_COUNTS = [30, 60]  # Reduce from [30, 60, 120, 300, 600]
   ```
3. Skip 1440p tests if RAM < 16 GB

### Issue 2: Disk Space Full
**Symptom:** "No space left on device"

**Solution:**
1. Free up disk space
2. Clear old test videos:
   ```bash
   rm stress_test_results/test_video_*.mp4
   ```

### Issue 3: Import Errors
**Symptom:** "ModuleNotFoundError: No module named 'app'"

**Solution:**
1. Ensure you're in the project root directory
2. Install all requirements:
   ```bash
   pip install -r requirements.txt
   ```
3. Set PYTHONPATH:
   ```bash
   export PYTHONPATH=$PYTHONPATH:$(pwd)
   ```

### Issue 4: OpenCV Codec Issues
**Symptom:** "Could not open video writer"

**Solution:**
1. Install system codecs:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install libx264-dev

   # macOS
   brew install x264

   # Windows: Usually included with opencv-python
   ```
2. The test will fallback to 'mp4v' codec automatically

## 🎛️ Customizing Tests

### Test Specific Resolutions Only
Edit `stress_test.py`:
```python
RESOLUTIONS = {
    '720p': (1280, 720),
    '1080p': (1920, 1080)
    # Remove 480p and 1440p for faster testing
}
```

### Test Specific Encryption
```python
ENCRYPTION_STRENGTHS = ['AES-256']  # Test only AES-256
CIPHER_MODES = ['GCM']               # Test only GCM
```

### Quick Test Mode
```python
FRAME_COUNTS = [30, 60]              # Only short videos
MESSAGE_SIZES = [1024, 10240]        # Only small messages
```

## 📞 Support

If you encounter issues:

1. Check `stress_test_results/analysis_report.md` for automated diagnostics
2. Review `SCALABILITY_ANALYSIS.md` for known limitations
3. Examine error tracebacks in `stress_test_results.json`
4. Check system resources (RAM, disk, CPU)

## 🎯 Next Steps After Testing

1. **Review Results:** Check success rates and performance metrics
2. **Read Analysis:** Open `SCALABILITY_ANALYSIS.md` for detailed bottleneck analysis
3. **Prioritize Fixes:** Focus on critical issues (memory, performance)
4. **Implement Solutions:** Follow recommendations in SCALABILITY_ANALYSIS.md

---

**Happy Testing! 🚀**
