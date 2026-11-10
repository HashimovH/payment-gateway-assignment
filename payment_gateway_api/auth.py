import hashlib
import secrets

API_KEY_PREFIX = "sk_"


def generate_api_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    # Plain SHA-256 is enough: keys are long random tokens, not passwords,
    # so there is nothing to brute-force or look up in a dictionary.
    return hashlib.sha256(api_key.encode()).hexdigest()
