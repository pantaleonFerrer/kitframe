package apperr

import "net/http"

const (
	CodeInvalidRequest         = "invalid_request"
	CodeUnauthorized           = "unauthorized"
	CodeForbidden              = "forbidden"
	CodeNotFound               = "not_found"
	CodeConflict               = "conflict"
	CodeRateLimited            = "rate_limited"
	CodeInvalidCredentials     = "invalid_credentials"
	CodeInvalidStepTransition  = "invalid_step_transition"
	CodeQCRequired             = "qc_required"
	CodeRightsNotCleared       = "rights_not_cleared"
	CodeInternal               = "internal_error"
	CodePasswordTooShort       = "password_too_short"
	CodeTokenRevoked           = "token_revoked"
	CodeWebhookInvalid         = "webhook_invalid"
)

type Error struct {
	Code       string         `json:"code"`
	Message    string         `json:"message"`
	Details    map[string]any `json:"details"`
	HTTPStatus int            `json:"-"`
}

func (e *Error) Error() string {
	return e.Message
}

func New(code, message string, status int, details map[string]any) *Error {
	if details == nil {
		details = map[string]any{}
	}
	return &Error{Code: code, Message: message, Details: details, HTTPStatus: status}
}

func InvalidRequest(message string, details map[string]any) *Error {
	return New(CodeInvalidRequest, message, http.StatusBadRequest, details)
}

func Unauthorized(message string) *Error {
	return New(CodeUnauthorized, message, http.StatusUnauthorized, nil)
}

func Forbidden(message string) *Error {
	return New(CodeForbidden, message, http.StatusForbidden, nil)
}

func NotFound(message string) *Error {
	return New(CodeNotFound, message, http.StatusNotFound, nil)
}

func Conflict(message string) *Error {
	return New(CodeConflict, message, http.StatusConflict, nil)
}

func RateLimited(retryAfter int) *Error {
	return New(CodeRateLimited, "Too many requests", http.StatusTooManyRequests, map[string]any{
		"retry_after": retryAfter,
	})
}

func InvalidCredentials() *Error {
	return New(CodeInvalidCredentials, "Incorrect email or password", http.StatusUnauthorized, nil)
}

func InvalidStepTransition(from, to string) *Error {
	return New(CodeInvalidStepTransition, "Cannot move from '"+from+"' to '"+to+"'", http.StatusConflict, map[string]any{
		"from": from,
		"to":   to,
	})
}

func QCRequired() *Error {
	return New(CodeQCRequired, "All assets must pass QC or an admin override is required", http.StatusConflict, nil)
}

func RightsNotCleared() *Error {
	return New(CodeRightsNotCleared, "Rights record is not cleared", http.StatusConflict, nil)
}

func Internal(message string) *Error {
	return New(CodeInternal, message, http.StatusInternalServerError, nil)
}

func PasswordTooShort() *Error {
	return New(CodePasswordTooShort, "Password must be at least 12 characters", http.StatusBadRequest, nil)
}

func TokenRevoked() *Error {
	return New(CodeTokenRevoked, "Refresh token has been revoked", http.StatusUnauthorized, nil)
}

func WebhookInvalid() *Error {
	return New(CodeWebhookInvalid, "Invalid webhook signature", http.StatusUnauthorized, nil)
}
