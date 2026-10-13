from __future__ import annotations

import re
from typing import Annotated

from pydantic import AfterValidator

# Pydantic EmailStr rejects reserved TLDs like .local (RFC 6762), which we use for local seed users.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_app_email(value: str) -> str:
    v = value.strip().lower()
    if len(v) > 254 or not _EMAIL_RE.match(v):
        raise ValueError("Invalid email address")
    local, _, domain = v.partition("@")
    if not local or not domain or ".." in v:
        raise ValueError("Invalid email address")
    return v


AppEmail = Annotated[str, AfterValidator(_validate_app_email)]
