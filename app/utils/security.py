from pwdlib import PasswordHash

password_hash = PasswordHash.recommended()

def hash_password(password:str):
    return password_hash.hash(password)


def verify_password(password: str, hashed_password: str) ->bool:
 is_valid = password_hash.verify(password, hashed_password)
 return is_valid