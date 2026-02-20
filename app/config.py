"""
Application Configuration

Defines configuration classes for different deployment environments.
Flask loads one of these classes at startup via app.config.from_object().

Environment selection:
  - Set the FLASK_ENV environment variable to 'development', 'production',
    or 'testing' to pick the matching class.
  - Defaults to DevelopmentConfig when FLASK_ENV is not set.
"""

import os
from datetime import timedelta


class Config:
    """Base configuration shared by all environments.

    Sensitive values (SECRET_KEY, broker URLs) are read from environment
    variables so they are never hard-coded in source control.
    """

    # Used by Flask to sign session cookies and CSRF tokens.
    # MUST be overridden with a strong random value in production.
    SECRET_KEY = os.environ.get('SECRET_KEY', 'vidstega-secret-key-change-in-production')

    # ------------------------------------------------------------------ #
    # File upload settings
    # ------------------------------------------------------------------ #

    # Maximum allowed upload size (2 GB).  Flask rejects larger requests
    # with a 413 error before they reach route handlers.
    MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024  # 2GB max upload

    # Absolute paths to the upload and output directories, derived relative
    # to this config file so they work regardless of the working directory.
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    OUTPUT_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs')

    # Only these video container formats are accepted to reduce the attack
    # surface and ensure OpenCV can decode them reliably.
    ALLOWED_EXTENSIONS = {'mp4', 'avi', 'mov', 'mkv', 'webm'}

    # ------------------------------------------------------------------ #
    # Celery / Redis settings
    # ------------------------------------------------------------------ #

    # Celery uses Redis both as the task broker (queuing jobs) and as the
    # result backend (storing task outcomes that routes.py later queries).
    CELERY_BROKER_URL = os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0')
    CELERY_RESULT_BACKEND = os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')

    # ------------------------------------------------------------------ #
    # Video resolution limits
    # ------------------------------------------------------------------ #

    # Mapping of friendly resolution name -> (width, height) in pixels.
    # Used by the capacity calculator and UI dropdowns.
    SUPPORTED_RESOLUTIONS = {
        '480p': (854, 480),
        '720p': (1280, 720),
        '1080p': (1920, 1080),
        '1440p': (2560, 1440)
    }

    # ------------------------------------------------------------------ #
    # Encryption settings
    # ------------------------------------------------------------------ #

    # Number of PBKDF2 iterations for key derivation.
    # 100,000 iterations makes brute-force attacks computationally expensive.
    PBKDF2_ITERATIONS = 100000

    # Maps user-facing AES variant names to their key sizes in bytes.
    # Larger keys are stronger but marginally slower to derive.
    SUPPORTED_KEY_SIZES = {
        'AES-128': 16,
        'AES-192': 24,
        'AES-256': 32
    }

    # Supported block cipher modes of operation.
    # GCM provides authenticated encryption (integrity + confidentiality).
    # CTR/CFB are stream-like and do not need PKCS7 padding.
    # CBC is the classic padded block mode.
    SUPPORTED_CIPHER_MODES = ['CBC', 'CTR', 'GCM', 'CFB']

    # ------------------------------------------------------------------ #
    # Reed-Solomon error correction
    # ------------------------------------------------------------------ #

    # Number of error-correcting symbols appended to each encoded block.
    # 10 symbols means the decoder can correct up to 5 symbol errors per block,
    # providing resilience against minor video compression artifacts.
    RS_ECC_SYMBOLS = 10


class DevelopmentConfig(Config):
    """Development configuration – verbose errors, hot-reload enabled."""
    DEBUG = True
    TESTING = False


class ProductionConfig(Config):
    """Production configuration – debug output disabled for security."""
    DEBUG = False
    TESTING = False
    # Require the SECRET_KEY to be set explicitly in production.
    # If the environment variable is missing, SECRET_KEY will be None,
    # which will cause Flask to raise an error on startup, preventing an
    # insecure deployment with the default key.
    SECRET_KEY = os.environ.get('SECRET_KEY')


class TestingConfig(Config):
    """Testing configuration – enables Flask test client helpers."""
    DEBUG = True
    TESTING = True


# Registry mapping environment names to config classes.
# create_app() uses this dict to look up the correct class.
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestingConfig,
    'default': DevelopmentConfig
}
