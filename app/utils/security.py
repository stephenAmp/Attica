from pwdlib import PasswordHash
from typing import Any
import hashlib
import json

password_hash = PasswordHash.recommended()

def hash_password(password:str):
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) ->bool:
 is_valid = password_hash.verify(password, hashed_password)
 return is_valid


def hash_payload(data: Any) -> str:
   payload = json.dumps(
        data.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
   )
 
   return hashlib.sha256(
      payload.encode("utf-8")
   ).hexdigest()