from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    VALIDATION_ERROR = "validation_error"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    CONFLICT = "conflict"
    RATE_LIMITED = "rate_limited"
    INVALID_TRANSITION = "invalid_transition"
    EXIT_CRITERIA_NOT_MET = "exit_criteria_not_met"
    PHASE_LOCKED = "phase_locked"
    RIGHTS_NOT_CLEARED = "rights_not_cleared"
    REQUIREMENTS_NOT_CHECKED = "requirements_not_checked"
    SELF_REVIEW_NOT_ALLOWED = "self_review_not_allowed"
    QC_NOT_PASSED = "qc_not_passed"
    GOLDEN_CONFLICT = "golden_conflict"
    UPLOAD_INVALID = "upload_invalid"
    FILE_TOO_LARGE = "file_too_large"
    PROVIDER_ERROR = "provider_error"
    PROVIDER_MODERATED = "provider_moderated"
    LLM_INVALID_OUTPUT = "llm_invalid_output"
    SHOPIFY_ERROR = "shopify_error"
    SHOPIFY_NOT_CONFIGURED = "shopify_not_configured"
    SHOPIFY_LOCALE_MISSING = "shopify_locale_missing"
    INVITATION_INVALID = "invitation_invalid"
    TOKEN_INVALID = "token_invalid"
    INTERNAL_ERROR = "internal_error"


class AppError(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        status_code: int = 400,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or {}
