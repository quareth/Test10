"""Password hashing and verification using bcrypt."""

import bcrypt


def hash_password(plain: str) -> str:
    """Hash a plaintext password using bcrypt.

    A unique salt is generated for each call, so hashing the same
    password twice produces different outputs.
    """
    hashed = bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt())
    return hashed.decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a bcrypt hash.

    Returns True if the password matches, False otherwise.
    """
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
