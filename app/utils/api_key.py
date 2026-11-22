import hashlib
import hmac
import secrets
from uuid import UUID

def generate_api_key(key_id: UUID) -> tuple[str, str]:
    secret = secrets.token_urlsafe(32)
    raw_key = f"attica_ak_{key_id}.{secret}"

    secret_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()

    return raw_key, secret_hash


def parse_api_key(raw_key: str) -> tuple[UUID, str] | None:
    if not raw_key.startswith("attica_ak_"):
        return None

    try:
        key_id, secret = raw_key.removeprefix("attica_ak_").split(".", 1)
        if not secret:
            return None
        return UUID(key_id), secret
    
    except ValueError:
        return None


def verify_api_key(secret: str, stored_hash: str)-> bool: 
    candidate_hash = hashlib.sha256(secret.encode("utf-8")).hexdigest()

    return hmac.compare_digest(candidate_hash , stored_hash)