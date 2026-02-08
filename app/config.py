"""
Application Configuration
"""

import os
from datetime import timedelta


class Config:
    """Base configuration."""
    SECRET_KEY = os.environ.get('SECRET_KEY', 'vidstega-secret-key-change-in-production')
    
    # File upload settings
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB max upload
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')
    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}
    
    # Celery configuration
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
    
    # Video resolution limits
    SUPPORTED_RESOLUTIONS = {
        '480p': (854, 480),
        '720p': (1280, 720),
        '1080p': (1920, 1080),
        '1440p': (2560, 1440)
    }
    
    # Encryption settings
    PBKDF2_ITERATIONS = 100000
    SUPPORTED_KEY_SIZES = {
        'AES-128': 16,
        'AES-192': 24,
        'AES-256': 32
    }
    SUPPORTED_CIPHER_MODES = ['CBC', 'CTR', 'GCM', 'CFB']
    
    # Reed-Solomon error correction
    RS_ECC_SYMBOLS = 10


class DevelopmentConfig(Config):
    """Development configuration."""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration."""
    DEBUG = False
    TESTING = False
    # Use stronger secret key in production
    SECRET_KEY = os.environ.get('SECRET_KEY')


class TestingConfig(Config):
    """Testing configuration."""
    DEBUG = True
    TESTING = True


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
