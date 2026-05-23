FROM python:3.11-slim

# Install system dependencies for OpenCV and FFmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1-mesa-glx \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy and install Python dependencies
COPY requirements.txt .

# Remove non-headless opencv to avoid conflicts (headless version is sufficient)
RUN grep -v '^opencv-python>=' requirements.txt > requirements-prod.txt && \
    pip install --no-cache-dir -r requirements-prod.txt

# Copy application code
COPY . .

# Create required directories (volumes will be mounted over uploads/outputs at runtime)
RUN mkdir -p uploads outputs static

EXPOSE 8080

CMD gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:8080 --timeout 300 run:app
