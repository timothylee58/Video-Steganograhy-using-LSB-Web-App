"""
VidStega - Production Video Steganography Application
Run this file to start the web server.

This is the main entry point of the application. It:
  1. Creates the Flask app using the factory pattern (create_app)
  2. Registers WebSocket event handlers
  3. Creates required filesystem directories for uploads/outputs
  4. Launches the SocketIO-enabled web server on port 5000
"""

import os
from app import create_app, socketio

# Create Flask application using the factory pattern.
# The FLASK_ENV environment variable selects the config class
# (development, production, testing). Defaults to 'development'.
app = create_app(os.environ.get('FLASK_ENV', 'development'))

# Import websocket module so its @socketio.on event handlers are
# registered with the shared socketio instance before the server starts.
from app import websocket  # noqa

if __name__ == '__main__':
    # Create required directories if they do not already exist.
    # - uploads/  : stores video files uploaded by users
    # - outputs/  : stores processed stego video files ready for download
    # - static/   : holds static frontend assets (CSS, JS, images)
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

    # Gate debug mode and binding on the environment so production
    # deployments are not accidentally started with the Werkzeug debugger.
    debug_mode = os.environ.get('FLASK_ENV', 'development') == 'development'
    host = os.environ.get('HOST', '127.0.0.1' if debug_mode else '0.0.0.0')
    port = int(os.environ.get('PORT', '5000'))

    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug_mode,
        allow_unsafe_werkzeug=debug_mode,
    )
