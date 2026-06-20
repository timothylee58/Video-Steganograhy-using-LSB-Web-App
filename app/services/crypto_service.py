"""
Cryptography Service - Handles encryption and decryption operations
Supports AES-128/192/256 with CBC, CTR, GCM, and CFB modes

Why AES?
  AES (Advanced Encryption Standard) is the NIST-approved symmetric cipher
  used worldwide for securing sensitive data.  It is fast in hardware and
  software, and has no known practical attacks at the key sizes used here.

Why PBKDF2?
  Passwords entered by users are weak compared to random keys.  PBKDF2
  stretches the password through 100,000 iterations of HMAC-SHA256, making
  brute-force dictionary attacks ~100,000x slower without impacting legitimate
  decryption performance.  A fresh 16-byte random salt is generated for every
  encryption operation so that the same password yields a different key each
  time, defeating precomputed rainbow-table attacks.

Cipher mode comparison:
  GCM  : Authenticated encryption.  Provides confidentiality AND integrity;
         the 16-byte auth tag will cause decryption to fail if the ciphertext
         is tampered with.  Recommended default.
  CTR  : Stream-cipher mode.  No padding required.  Does not authenticate.
  CBC  : Classic padded block mode.  Requires PKCS7 padding.  Does not
         authenticate (susceptible to padding-oracle attacks if misused).
  CFB  : Self-synchronising stream mode.  No padding required.

Binary format of encrypted_data (the bytes stored in the video):
  GCM : [salt 16B][nonce 16B][tag 16B][ciphertext NB]
  CTR : [salt 16B][nonce  8B][ciphertext NB]
  CBC : [salt 16B][iv    16B][ciphertext NB] (ciphertext padded to block size)
  CFB : [salt 16B][iv    16B][ciphertext NB]
"""

import secrets
import base64
from typing import Tuple, Optional
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad


class CryptoService:
    """Service for cryptographic operations."""

    # AES block size in bytes (fixed at 16 for all AES variants).
    BLOCK_SIZE = 16

    # PBKDF2 iteration count.  100,000 is the minimum recommended by NIST
    # SP 800-132 (2023 update) for password-based key derivation.
    ITERATIONS = 100000

    # Maps user-facing AES variant names to the corresponding key byte lengths.
    KEY_SIZES = {
        'AES-128': 16,
        'AES-192': 24,
        'AES-256': 32
    }

    # Maps cipher mode name strings to PyCryptodome mode constants.
    CIPHER_MODES = {
        'CBC': AES.MODE_CBC,
        'CTR': AES.MODE_CTR,
        'GCM': AES.MODE_GCM,
        'CFB': AES.MODE_CFB
    }

    @classmethod
    def derive_key(cls, password: str, salt: bytes, key_length: int) -> bytes:
        """Derive an encryption key from a user password using PBKDF2-HMAC-SHA256.

        The salt ensures that two users with the same password get different
        keys, and that pre-computed lookup tables cannot be used.

        Args:
            password: User-provided password (will be UTF-8 encoded)
            salt: Random 16-byte salt (generated fresh for each encryption)
            key_length: Desired key length in bytes (16, 24, or 32)

        Returns:
            Derived key bytes of the requested length
        """
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=key_length,
            salt=salt,
            iterations=cls.ITERATIONS,
            backend=default_backend()
        )
        return kdf.derive(password.encode('utf-8'))

    @classmethod
    def encrypt(cls, plaintext: str, password: str,
                encryption_strength: str = 'AES-256',
                cipher_mode: str = 'GCM') -> Tuple[bytes, dict]:
        """Encrypt plaintext using the specified AES configuration.

        A fresh salt and IV/nonce are generated for every call using
        secrets.token_bytes(), which uses the OS CSPRNG.  This means the
        same message encrypted twice produces different ciphertext, preventing
        pattern analysis.

        The entire encrypted bundle (salt + IV + optional tag + ciphertext) is
        returned as a single bytes object so it can be embedded into the video
        as a contiguous bit stream.

        Args:
            plaintext: Message to encrypt (must be non-empty)
            password: Encryption password
            encryption_strength: 'AES-128', 'AES-192', or 'AES-256'
            cipher_mode: 'CBC', 'CTR', 'GCM', or 'CFB'

        Returns:
            Tuple of (encrypted_data bytes, metadata dict).
            metadata describes the byte layout for debugging/logging.
        """
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")

        if encryption_strength not in cls.KEY_SIZES:
            raise ValueError(f"Unsupported encryption strength: {encryption_strength}")

        if cipher_mode not in cls.CIPHER_MODES:
            raise ValueError(f"Unsupported cipher mode: {cipher_mode}")

        # Generate cryptographically random salt (16 bytes) and IV/nonce.
        # CTR mode uses an 8-byte nonce (counter starts at 0); all others use 16.
        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(16) if cipher_mode != 'CTR' else secrets.token_bytes(8)

        # Derive the AES key from the password and the fresh salt.
        key_length = cls.KEY_SIZES[encryption_strength]
        key = cls.derive_key(password, salt, key_length)

        mode = cls.CIPHER_MODES[cipher_mode]

        if cipher_mode == 'GCM':
            # GCM provides authenticated encryption: encrypt_and_digest()
            # returns both the ciphertext and a 16-byte authentication tag.
            # The tag must be verified during decryption to detect tampering.
            cipher = AES.new(key, mode, nonce=iv)
            ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))

            # Pack all components into a single byte string.
            # Layout: [salt 16B][nonce 16B][tag 16B][ciphertext NB]
            encrypted_data = salt + iv + tag + ciphertext
            metadata = {
                'encryption_strength': encryption_strength,
                'cipher_mode': cipher_mode,
                'salt_length': 16,
                'nonce_length': len(iv),
                'tag_length': 16
            }

        elif cipher_mode == 'CTR':
            # CTR converts AES into a stream cipher; no padding needed.
            # Layout: [salt 16B][nonce 8B][ciphertext NB]
            cipher = AES.new(key, mode, nonce=iv)
            ciphertext = cipher.encrypt(plaintext.encode('utf-8'))

            encrypted_data = salt + iv + ciphertext
            metadata = {
                'encryption_strength': encryption_strength,
                'cipher_mode': cipher_mode,
                'salt_length': 16,
                'nonce_length': len(iv)
            }

        else:
            # CBC and CFB both use a 16-byte IV.
            cipher = AES.new(key, mode, iv)

            if cipher_mode == 'CBC':
                # CBC requires the plaintext length to be a multiple of BLOCK_SIZE.
                # PKCS7 padding adds 1-16 bytes to achieve this.
                padded_text = pad(plaintext.encode('utf-8'), cls.BLOCK_SIZE)
                ciphertext = cipher.encrypt(padded_text)
            else:
                # CFB operates on arbitrary-length plaintext; no padding needed.
                ciphertext = cipher.encrypt(plaintext.encode('utf-8'))

            # Layout: [salt 16B][iv 16B][ciphertext NB]
            encrypted_data = salt + iv + ciphertext
            metadata = {
                'encryption_strength': encryption_strength,
                'cipher_mode': cipher_mode,
                'salt_length': 16,
                'iv_length': 16
            }

        return encrypted_data, metadata

    @classmethod
    def decrypt(cls, encrypted_data: bytes, password: str,
                encryption_strength: str = 'AES-256',
                cipher_mode: str = 'GCM') -> str:
        """Decrypt data using the specified AES configuration.

        Reverses the packing done by encrypt(): extracts the salt and
        IV/nonce from the fixed-size header, re-derives the key with
        PBKDF2, and decrypts the ciphertext.

        For GCM mode, decrypt_and_verify() raises ValueError if the
        authentication tag does not match, signalling that the password
        is wrong or the data has been tampered with.

        Args:
            encrypted_data: Encrypted bytes (salt + IV + [tag] + ciphertext)
            password: Decryption password
            encryption_strength: 'AES-128', 'AES-192', or 'AES-256'
            cipher_mode: 'CBC', 'CTR', 'GCM', or 'CFB'

        Returns:
            Decrypted plaintext string (UTF-8 decoded)
        """
        if encryption_strength not in cls.KEY_SIZES:
            raise ValueError(f"Unsupported encryption strength: {encryption_strength}")

        if cipher_mode not in cls.CIPHER_MODES:
            raise ValueError(f"Unsupported cipher mode: {cipher_mode}")

        # The first 16 bytes are always the salt (used to re-derive the key).
        salt = encrypted_data[:16]

        key_length = cls.KEY_SIZES[encryption_strength]
        key = cls.derive_key(password, salt, key_length)

        mode = cls.CIPHER_MODES[cipher_mode]

        if cipher_mode == 'GCM':
            # Unpack the fixed-size header fields.
            # Layout: [salt 16B][nonce 16B][tag 16B][ciphertext NB]
            nonce = encrypted_data[16:32]
            tag = encrypted_data[32:48]
            ciphertext = encrypted_data[48:]

            cipher = AES.new(key, mode, nonce=nonce)
            # decrypt_and_verify raises ValueError if the tag is invalid.
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)

        elif cipher_mode == 'CTR':
            # Layout: [salt 16B][nonce 8B][ciphertext NB]
            nonce = encrypted_data[16:24]
            ciphertext = encrypted_data[24:]

            cipher = AES.new(key, mode, nonce=nonce)
            plaintext = cipher.decrypt(ciphertext)

        else:
            # CBC and CFB layout: [salt 16B][iv 16B][ciphertext NB]
            iv = encrypted_data[16:32]
            ciphertext = encrypted_data[32:]

            cipher = AES.new(key, mode, iv)
            decrypted = cipher.decrypt(ciphertext)

            if cipher_mode == 'CBC':
                # Remove PKCS7 padding that was added before encryption.
                plaintext = unpad(decrypted, cls.BLOCK_SIZE)
            else:
                plaintext = decrypted

        return plaintext.decode('utf-8')

    @classmethod
    def encrypt_to_base64(cls, plaintext: str, password: str,
                          encryption_strength: str = 'AES-256',
                          cipher_mode: str = 'GCM') -> str:
        """Encrypt and return as a base64-encoded string.

        Useful when the encrypted bytes need to be stored or transmitted
        in a text-safe format (e.g. in JSON responses or log files).

        Args:
            plaintext: Message to encrypt
            password: Encryption password
            encryption_strength: AES key size
            cipher_mode: Block cipher mode

        Returns:
            Base64 encoded string of the encrypted data
        """
        encrypted_data, _ = cls.encrypt(
            plaintext, password, encryption_strength, cipher_mode
        )
        return base64.b64encode(encrypted_data).decode('utf-8')

    @classmethod
    def decrypt_from_base64(cls, encrypted_b64: str, password: str,
                            encryption_strength: str = 'AES-256',
                            cipher_mode: str = 'GCM') -> str:
        """Decrypt base64-encoded encrypted data.

        Decodes the base64 string back to raw bytes before passing to
        the standard decrypt() method.

        Args:
            encrypted_b64: Base64 encoded encrypted data string
            password: Decryption password
            encryption_strength: AES key size used during encryption
            cipher_mode: Block cipher mode used during encryption

        Returns:
            Decrypted plaintext string
        """
        encrypted_data = base64.b64decode(encrypted_b64)
        return cls.decrypt(encrypted_data, password, encryption_strength, cipher_mode)
