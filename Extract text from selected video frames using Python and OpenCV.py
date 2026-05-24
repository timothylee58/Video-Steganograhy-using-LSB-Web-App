from Crypto.Cipher import AES
from Crypto.Random import get_random_bytes
from Crypto.Util.Padding import pad, unpad
import base64


def encrypt_aes(data, key):
    """AES-256-CBC encrypt; output matches decrypt_aes format (base64(iv||ciphertext))."""
    iv = get_random_bytes(16)
    cipher = AES.new(key, AES.MODE_CBC, iv)
    padded = pad(data.encode("utf-8"), AES.block_size)
    encrypted_bytes = iv + cipher.encrypt(padded)
    return base64.b64encode(encrypted_bytes).decode("utf-8")


def decrypt_aes(encrypted_base64_data, key):
    # Decode the base64 encoded data
    encrypted_bytes = base64.b64decode(encrypted_base64_data)

    # Extract the IV and the encrypted message
    iv = encrypted_bytes[:16]
    encrypted_message = encrypted_bytes[16:]

    # Create a new AES cipher object with the given key and IV in CBC mode
    cipher = AES.new(key, AES.MODE_CBC, iv)

    # Decrypt the data and unpad it
    decrypted_padded_data = cipher.decrypt(encrypted_message)
    decrypted_data = unpad(decrypted_padded_data, AES.block_size)

    return decrypted_data.decode('utf-8')

# Example usage
key = get_random_bytes(32)  # 32 bytes key for AES-256
data = "This is a secret message."

# Encrypt the message
encrypted_message = encrypt_aes(data, key)
print("Encrypted message:", encrypted_message)

# Decrypt the message
decrypted_message = decrypt_aes(encrypted_message, key)
print("Decrypted message:", decrypted_message)