import os
from cryptography.fernet import Fernet
from dotenv import load_dotenv

load_dotenv("config/.env")

FERNET_KEY = os.getenv("FERNET_KEY")
if not FERNET_KEY:
    raise ValueError("FERNET_KEY not set in environment")

fernet = Fernet(FERNET_KEY.encode())

def encrypt_file(data: bytes) -> bytes:
    return fernet.encrypt(data)

def decrypt_file(data: bytes) -> bytes:
    return fernet.decrypt(data)
