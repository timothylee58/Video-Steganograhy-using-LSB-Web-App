"""
VidStega - Video Steganography Web Application
Production-ready application for hiding encrypted messages in videos using LSB technique.
"""

from flask import Flask
from flask_cors import CORS
from flask_socketio import SocketIO

socketio = SocketIO()


def create_app(config_name='default'):
    """Application factory for creating Flask app instances."""
    app = Flask(__name__, 
                template_folder='../templates',
                static_folder='../static')
    
    # Load configuration
    app.config.from_object(get_config(config_name))
    
    # Initialize extensions
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')
    
    # Register blueprints
    from app.routes import main_bp, api_bp
    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp, url_prefix='/api')
    
    return app


def get_config(config_name):
    """Get configuration class based on environment."""
    from app.config import config
    return config.get(config_name, config['default'])
