"""
OTP generation and verification utilities.
Plain OTP is never stored; only hashes are persisted.
"""

import secrets

from django.contrib.auth.hashers import check_password, make_password


def generate_otp() -> str:
    """Generate a 6-digit OTP using secrets.randbelow (zero-padded)."""
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_otp(otp: str) -> str:
    """Hash OTP for secure storage using Django's make_password."""
    return make_password(otp)


def verify_otp(otp: str, otp_hash: str) -> bool:
    """Verify OTP against stored hash using check_password."""
    return bool(otp and otp_hash and check_password(otp, otp_hash))
