"""Presentation helpers for passwords and tokens.

NOTE: this module only *formats* password/token strings for display. It shares
vocabulary with authentication issues but contains no login logic.
"""


def mask_password(password: str) -> str:
    """Return a masked form of a password for logging, e.g. 'ab****yz'."""
    if len(password) <= 4:
        return "*" * len(password)
    return password[:2] + "*" * (len(password) - 4) + password[-2:]


def format_token_hint(token: str) -> str:
    """Human-readable hint for an API token without revealing it."""
    return f"token ending in …{token[-4:]}" if token else "no token"


def password_strength_label(password: str) -> str:
    """Rough label describing how strong a password looks."""
    if len(password) >= 12:
        return "strong"
    if len(password) >= 8:
        return "ok"
    return "weak"
