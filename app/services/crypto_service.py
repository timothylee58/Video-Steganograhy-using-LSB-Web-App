"""
Cryptography Service - Handles encryption and decryption operations
Supports AES-128/192/256 with CBC, CTR, GCM, and CFB modes
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
    
    # Standard block size for AES
    BLOCK_SIZE = 16
    # Number of PBKDF2 iterations for key derivation
    ITERATIONS = 100000
    
    # Key sizes for different AES variants
    KEY_SIZES = {
        'AES-128': 16,
        'AES-192': 24,
        'AES-256': 32
    }
    
    # Supported cipher modes
    CIPHER_MODES = {
        'CBC': AES.MODE_CBC,
        'CTR': AES.MODE_CTR,
        'GCM': AES.MODE_GCM,
        'CFB': AES.MODE_CFB
    }
    
    @classmethod
    def derive_key(cls, password: str, salt: bytes, key_length: int) -> bytes:
        """
        Derive an encryption key from password using PBKDF2.
        
        Args:
            password: User-provided password
            salt: Random salt for key derivation
            key_length: Desired key length in bytes (16, 24, or 32)
            
        Returns:
            Derived key bytes
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
        """
        Encrypt plaintext using specified AES configuration.
        
        Args:
            plaintext: Message to encrypt
            password: Encryption password
            encryption_strength: 'AES-128', 'AES-192', or 'AES-256'
            cipher_mode: 'CBC', 'CTR', 'GCM', or 'CFB'
            
        Returns:
            Tuple of (encrypted_data, metadata)
            metadata contains: salt, iv/nonce, tag (for GCM)
        """
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")
        
        if encryption_strength not in cls.KEY_SIZES:
            raise ValueError(f"Unsupported encryption strength: {encryption_strength}")
        
        if cipher_mode not in cls.CIPHER_MODES:
            raise ValueError(f"Unsupported cipher mode: {cipher_mode}")
        
        # Generate salt and IV/nonce
        salt = secrets.token_bytes(16)
        iv = secrets.token_bytes(16) if cipher_mode != 'CTR' else secrets.token_bytes(8)
        
        # Derive key
        key_length = cls.KEY_SIZES[encryption_strength]
        key = cls.derive_key(password, salt, key_length)
        
        # Create cipher
        mode = cls.CIPHER_MODES[cipher_mode]
        
        if cipher_mode == 'GCM':
            cipher = AES.new(key, mode, nonce=iv)
            # GCM doesn't need padding
            ciphertext, tag = cipher.encrypt_and_digest(plaintext.encode('utf-8'))
            
            # Pack: salt (16) + nonce (16) + tag (16) + ciphertext
            encrypted_data = salt + iv + tag + ciphertext
            metadata = {
                'encryption_strength': encryption_strength,
                'cipher_mode': cipher_mode,
                'salt_length': 16,
                'nonce_length': len(iv),
                'tag_length': 16
            }
        elif cipher_mode == 'CTR':
            cipher = AES.new(key, mode, nonce=iv)
            # CTR doesn't need padding
            ciphertext = cipher.encrypt(plaintext.encode('utf-8'))
            
            # Pack: salt (16) + nonce (8) + ciphertext
            encrypted_data = salt + iv + ciphertext
            metadata = {
                'encryption_strength': encryption_strength,
                'cipher_mode': cipher_mode,
                'salt_length': 16,
                'nonce_length': len(iv)
            }
        else:
            # CBC and CFB
            cipher = AES.new(key, mode, iv)
            
            if cipher_mode == 'CBC':
                # CBC needs padding
                padded_text = pad(plaintext.encode('utf-8'), cls.BLOCK_SIZE)
                ciphertext = cipher.encrypt(padded_text)
            else:
                # CFB doesn't need padding
                ciphertext = cipher.encrypt(plaintext.encode('utf-8'))
            
            # Pack: salt (16) + iv (16) + ciphertext
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
        """
        Decrypt data using specified AES configuration.
        
        Args:
            encrypted_data: Encrypted bytes (including salt, iv, etc.)
            password: Decryption password
            encryption_strength: 'AES-128', 'AES-192', or 'AES-256'
            cipher_mode: 'CBC', 'CTR', 'GCM', or 'CFB'
            
        Returns:
            Decrypted plaintext string
        """
        if encryption_strength not in cls.KEY_SIZES:
            raise ValueError(f"Unsupported encryption strength: {encryption_strength}")
        
        if cipher_mode not in cls.CIPHER_MODES:
            raise ValueError(f"Unsupported cipher mode: {cipher_mode}")
        
        # Extract salt
        salt = encrypted_data[:16]
        
        # Derive key
        key_length = cls.KEY_SIZES[encryption_strength]
        key = cls.derive_key(password, salt, key_length)
        
        # Get cipher mode
        mode = cls.CIPHER_MODES[cipher_mode]
        
        if cipher_mode == 'GCM':
            # Unpack: salt (16) + nonce (16) + tag (16) + ciphertext
            nonce = encrypted_data[16:32]
            tag = encrypted_data[32:48]
            ciphertext = encrypted_data[48:]
            
            cipher = AES.new(key, mode, nonce=nonce)
            plaintext = cipher.decrypt_and_verify(ciphertext, tag)
            
        elif cipher_mode == 'CTR':
            # Unpack: salt (16) + nonce (8) + ciphertext
            nonce = encrypted_data[16:24]
            ciphertext = encrypted_data[24:]
            
            cipher = AES.new(key, mode, nonce=nonce)
            plaintext = cipher.decrypt(ciphertext)
            
        else:
            # CBC and CFB: salt (16) + iv (16) + ciphertext
            iv = encrypted_data[16:32]
            ciphertext = encrypted_data[32:]
            
            cipher = AES.new(key, mode, iv)
            decrypted = cipher.decrypt(ciphertext)
            
            if cipher_mode == 'CBC':
                plaintext = unpad(decrypted, cls.BLOCK_SIZE)
            else:
                plaintext = decrypted
        
        return plaintext.decode('utf-8')
    
    @classmethod
    def encrypt_to_base64(cls, plaintext: str, password: str,
                          encryption_strength: str = 'AES-256',
                          cipher_mode: str = 'GCM') -> str:
        """
        Encrypt and return as base64 encoded string.
        
        Args:
            plaintext: Message to encrypt
            password: Encryption password
            encryption_strength: AES key size
            cipher_mode: Block cipher mode
            
        Returns:
            Base64 encoded encrypted data
        """
        encrypted_data, _ = cls.encrypt(
            plaintext, password, encryption_strength, cipher_mode
        )
        return base64.b64encode(encrypted_data).decode('utf-8')
    
    @classmethod
    def decrypt_from_base64(cls, encrypted_b64: str, password: str,
                            encryption_strength: str = 'AES-256',
                            cipher_mode: str = 'GCM') -> str:
        """
        Decrypt base64 encoded encrypted data.
        
        Args:
            encrypted_b64: Base64 encoded encrypted data
            password: Decryption password
            encryption_strength: AES key size
            cipher_mode: Block cipher mode
            
        Returns:
            Decrypted plaintext
        """
        encrypted_data = base64.b64decode(encrypted_b64)
        return cls.decrypt(encrypted_data, password, encryption_strength, cipher_mode)
