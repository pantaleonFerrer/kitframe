package httpapi

import (
	"net/http"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/auth"
	"github.com/google/uuid"
)

type loginRequest struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

func (s *Server) handleLogin(w http.ResponseWriter, r *http.Request) {
	var req loginRequest
	if err := decodeJSON(r, &req); err != nil {
		writeError(w, err)
		return
	}
	if req.Email == "" || req.Password == "" {
		writeError(w, apperr.InvalidRequest("email and password required", nil))
		return
	}
	if len(req.Password) < auth.MinPasswordLength {
		writeError(w, apperr.PasswordTooShort())
		return
	}

	ip := clientIP(r)
	since := time.Now().UTC().Add(-15 * time.Minute)
	emailCount, err := s.db.CountLoginAttemptsByEmail(r.Context(), req.Email, since)
	if err != nil {
		writeError(w, apperr.Internal("rate limit check failed"))
		return
	}
	ipCount, err := s.db.CountLoginAttemptsByIP(r.Context(), ip, since)
	if err != nil {
		writeError(w, apperr.Internal("rate limit check failed"))
		return
	}
	if emailCount >= 5 {
		oldest, _ := s.db.OldestLoginAttemptByEmail(r.Context(), req.Email, since)
		retry := 900
		if oldest != nil {
			retry = int(oldest.Add(15 * time.Minute).Sub(time.Now().UTC()).Seconds())
			if retry < 1 {
				retry = 1
			}
		}
		writeError(w, apperr.RateLimited(retry))
		return
	}
	if ipCount >= 20 {
		oldest, _ := s.db.OldestLoginAttemptByIP(r.Context(), ip, since)
		retry := 900
		if oldest != nil {
			retry = int(oldest.Add(15 * time.Minute).Sub(time.Now().UTC()).Seconds())
			if retry < 1 {
				retry = 1
			}
		}
		writeError(w, apperr.RateLimited(retry))
		return
	}

	user, err := s.db.GetUserByEmail(r.Context(), req.Email)
	if err != nil {
		_ = s.db.RecordLoginAttempt(r.Context(), req.Email, ip, false)
		writeError(w, apperr.InvalidCredentials())
		return
	}
	ok, err := auth.VerifyPassword(user.PasswordHash, req.Password)
	if err != nil || !ok {
		_ = s.db.RecordLoginAttempt(r.Context(), req.Email, ip, false)
		writeError(w, apperr.InvalidCredentials())
		return
	}
	_ = s.db.RecordLoginAttempt(r.Context(), req.Email, ip, true)

	uid, err := uuid.Parse(user.ID)
	if err != nil {
		writeError(w, apperr.Internal("invalid user id"))
		return
	}
	access, _, err := s.tokens.IssueAccess(uid, user.Email)
	if err != nil {
		writeError(w, apperr.Internal("token issue failed"))
		return
	}
	refresh, _, exp, err := s.tokens.IssueRefresh(uid, user.RefreshTokenVersion)
	if err != nil {
		writeError(w, apperr.Internal("token issue failed"))
		return
	}
	s.setRefreshCookie(w, refresh, exp)
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token": access,
		"token_type":   "Bearer",
		"expires_in":   int(s.cfg.AccessTokenTTL.Seconds()),
	})
}

func (s *Server) handleRefresh(w http.ResponseWriter, r *http.Request) {
	c, err := r.Cookie(s.cfg.RefreshCookieName)
	if err != nil || c.Value == "" {
		writeError(w, apperr.Unauthorized("missing refresh token"))
		return
	}
	claims, err := s.tokens.ParseRefresh(c.Value)
	if err != nil {
		writeError(w, apperr.Unauthorized("invalid refresh token"))
		return
	}
	denied, err := s.db.IsRefreshDenylisted(r.Context(), claims.ID)
	if err != nil {
		writeError(w, apperr.Internal("denylist check failed"))
		return
	}
	if denied {
		writeError(w, apperr.TokenRevoked())
		return
	}
	user, err := s.db.GetUserByID(r.Context(), claims.UserID.String())
	if err != nil {
		writeError(w, apperr.Unauthorized("user not found"))
		return
	}
	if user.RefreshTokenVersion != claims.Version {
		writeError(w, apperr.TokenRevoked())
		return
	}
	access, _, err := s.tokens.IssueAccess(claims.UserID, user.Email)
	if err != nil {
		writeError(w, apperr.Internal("token issue failed"))
		return
	}
	refresh, _, exp, err := s.tokens.IssueRefresh(claims.UserID, user.RefreshTokenVersion)
	if err != nil {
		writeError(w, apperr.Internal("token issue failed"))
		return
	}
	expAt := time.Now().UTC().Add(s.cfg.RefreshTokenTTL)
	if claims.ExpiresAt != nil {
		expAt = claims.ExpiresAt.Time
	}
	_ = s.db.DenylistRefresh(r.Context(), s.db.Pool, claims.ID, claims.UserID.String(), expAt)
	s.setRefreshCookie(w, refresh, exp)
	writeJSON(w, http.StatusOK, map[string]any{
		"access_token": access,
		"token_type":   "Bearer",
		"expires_in":   int(s.cfg.AccessTokenTTL.Seconds()),
	})
}

func (s *Server) handleLogout(w http.ResponseWriter, r *http.Request) {
	c, err := r.Cookie(s.cfg.RefreshCookieName)
	if err == nil && c.Value != "" {
		if claims, err := s.tokens.ParseRefresh(c.Value); err == nil {
			expAt := time.Now().UTC().Add(s.cfg.RefreshTokenTTL)
			if claims.ExpiresAt != nil {
				expAt = claims.ExpiresAt.Time
			}
			_ = s.db.DenylistRefresh(r.Context(), s.db.Pool, claims.ID, claims.UserID.String(), expAt)
			_ = s.db.IncrementRefreshVersion(r.Context(), s.db.Pool, claims.UserID.String())
		}
	}
	s.clearRefreshCookie(w)
	writeJSON(w, http.StatusOK, map[string]string{"status": "logged_out"})
}

func (s *Server) handleMe(w http.ResponseWriter, r *http.Request) {
	uid := userIDFrom(r.Context())
	user, err := s.db.GetUserByID(r.Context(), uid.String())
	if err != nil {
		writeError(w, apperr.NotFound("user not found"))
		return
	}
	memberships, err := s.db.ListMembershipsByUser(r.Context(), user.ID)
	if err != nil {
		writeError(w, apperr.Internal("failed to load memberships"))
		return
	}
	ms := make([]map[string]any, 0, len(memberships))
	for _, m := range memberships {
		ms = append(ms, map[string]any{
			"id":       m.ID,
			"brand_id": m.BrandID,
			"role":     m.Role,
			"team":     m.Team,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"user": map[string]any{
			"id":           user.ID,
			"email":        user.Email,
			"display_name": user.DisplayName,
		},
		"memberships": ms,
	})
}
