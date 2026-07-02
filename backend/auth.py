import hashlib
import os

def hash_password(password: str) -> str:
    salt = os.urandom(16)
    db_rounds = 100000
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, db_rounds)
    return f"{salt.hex()}:{key.hex()}"

def verify_password(password: str, hashed_password: str) -> bool:
    try:
        salt_hex, key_hex = hashed_password.split(':')
        salt = bytes.fromhex(salt_hex)
        db_rounds = 100000
        key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, db_rounds)
        return key.hex() == key_hex
    except ValueError:
        return False
