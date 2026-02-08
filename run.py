"""
VidStega - Production Video Steganography Application
Run this file to start the web server.
"""

import os
from app import create_app, socketio

# Create Flask application
app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Import websocket events
from app import websocket  # noqa

if __name__ == '__main__':
    # Create required directories
    os.makedirs('uploads', exist_ok=True)
    os.makedirs('outputs', exist_ok=True)
    os.makedirs('static', exist_ok=True)

    print("""
    ================================================================

        VidStega - Video Steganography Platform
        Production Ready | LSB Embedding | AES Encryption

    ================================================================
    Features:
      * Multiple Resolutions: 480p, 720p, 1080p, 1440p
      * Encryption: AES-128/192/256 with CBC, CTR, GCM, CFB
      * PBKDF2 Key Derivation: 100,000 iterations
      * Reed-Solomon Error Correction
      * Async Processing with Celery
      * Real-time WebSocket Progress Updates
    ================================================================
    """)
    
    # Run with SocketIO
    socketio.run(app, 
                 host='0.0.0.0', 
                 port=5000, 
                 debug=True,
                 allow_unsafe_werkzeug=True)
