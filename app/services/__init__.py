"""
VidStega Services

This package exposes the three core service classes used throughout the
application.  Importing from this package (rather than from individual
modules) keeps import paths short and makes it easy to swap implementations.

  CryptoService       : AES encryption/decryption with PBKDF2 key derivation
  VideoService        : Video I/O, metadata extraction, and capacity calculation
  SteganographyService: LSB embedding/extraction with Reed-Solomon error correction
"""

from app.services.crypto_service import CryptoService
from app.services.video_service import VideoService
from app.services.steganography_service import SteganographyService

# Explicitly list public symbols so `from app.services import *` only
# exposes the three intended service classes.
__all__ = ['CryptoService', 'VideoService', 'SteganographyService']
