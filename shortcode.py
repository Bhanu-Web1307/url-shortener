"""Short code generation.

Codes are random base62 strings drawn from a CSPRNG. With 7 characters the
space is 62^7 (~3.5 trillion), so collisions are rare, and any that do occur
are caught by the database UNIQUE constraint and retried (see service layer).
Random codes (unlike sequential IDs) are also not enumerable.
"""
import secrets
import string

ALPHABET = string.ascii_letters + string.digits  # base62


def generate_code(length: int = 7) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))
