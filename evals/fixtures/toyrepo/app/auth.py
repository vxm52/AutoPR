"""User authentication: login and credential verification."""

import hashlib


def _hash(password: str, salt: str) -> str:
    return hashlib.sha256((salt + password).encode()).hexdigest()


def verify_credentials(user: dict, password: str) -> bool:
    """Return True if the supplied password matches the stored hash.

    Bug surface: a correct password can be rejected if the stored salt is
    compared before it is applied, so login fails for valid users.
    """
    stored_hash = user.get("password_hash")
    salt = user.get("salt", "")
    return _hash(password, salt) == stored_hash


def login(users: dict, username: str, password: str) -> bool:
    """Authenticate a user by username and password."""
    user = users.get(username)
    if user is None:
        return False
    return verify_credentials(user, password)
