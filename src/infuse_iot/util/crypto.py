#!/usr/bin/env python3

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def hkdf_derive(input_key, salt, info):
    """Derive a cryptographic key using HKDF-SHA256"""
    hkdf = HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=info,
    )
    return hkdf.derive(input_key)


def chachapoly_encrypt(key: bytes, associated_data: bytes, nonce: bytes, payload: bytes) -> bytes:
    """Encrypt a payload using ChaCha20-Poly1305"""
    cipher = ChaCha20Poly1305(key)
    return cipher.encrypt(nonce, payload, associated_data)


def chachapoly_decrypt(key: bytes, associated_data: bytes, nonce: bytes, payload: bytes) -> bytes:
    """Decrypt a payload using ChaCha20-Poly1305"""
    cipher = ChaCha20Poly1305(key)
    return cipher.decrypt(nonce, payload, associated_data)
