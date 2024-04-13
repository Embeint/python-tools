#!/usr/bin/env python3

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

def hkdf_derive(input_key, salt, info):
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    )
    return hkdf.derive(input_key)

def chachapoly_encrypt(key: bytes, associated_data: bytes, nonce: bytes, payload: bytes) -> bytes:
    cipher = ChaCha20Poly1305(key)
    return cipher.encrypt(nonce, payload, associated_data)

def chachapoly_decrypt(key: bytes, associated_data: bytes, nonce: bytes, payload: bytes) -> bytes:
    cipher = ChaCha20Poly1305(key)
    return cipher.decrypt(nonce, payload, associated_data)
