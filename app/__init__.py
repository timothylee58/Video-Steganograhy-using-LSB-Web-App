"""
VidStega - Video Steganography Web Application
Production-ready application for hiding encrypted messages in videos using LSB technique.

This module implements the Application Factory Pattern, which allows the Flask app
to be created with different configurations (development, production, testing) and
makes unit testing easier by instantiating a fresh app for each test run.
"""

import os
from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

# Declare SocketIO at module level so other modules (e.g. websocket.py) can
# import it directly without triggering a circular import. It is initialized
# (attached to the Flask app) inside create_app().
socketio = SocketIO()


def create_app(config_name='default'):
    """Application factory for creating Flask app instances.

    Separating app creation into a factory allows the same codebase to:
      - Run with different settings per environment (dev vs. prod)
      - Be instantiated multiple times in test suites without state leaking
    """
    # Point Flask to the templates/static folders one level up from app/
    app = Flask(__name__,
                template_folder='../templates',
                static_folder='../static')

    # Load configuration values (SECRET_KEY, upload limits, Celery URLs, etc.)
    # from the appropriate config class defined in app/config.py.
    app.config.from_object(get_config(config_name))

    # Enable Cross-Origin Resource Sharing (CORS) for the /api/* routes.
    # This lets browser-based clients hosted on a different origin call the API.
    CORS(app, resources={r"/api/*": {"origins": "*"}})

    # Choose the async mode for SocketIO based on the environment variable.
    # 'threading' mode works without eventlet/gevent and is the safe default.
    async_mode = os.environ.get('SOCKETIO_ASYNC_MODE', 'threading')
    socketio.init_app(app, cors_allowed_origins="*", async_mode=async_mode)

    # Register Flask blueprints.
    # main_bp: serves the HTML page at '/'
    # api_bp:  provides the REST API under '/api/'
    from app.routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')

    return app


def get_config(config_name):
    """Get configuration class based on environment name.

    Returns the matching Config subclass from app/config.py.
    Falls back to the 'default' (DevelopmentConfig) if the name is unknown.
    """
    from app.config import config
    return config.get(config_name, config['default'])
