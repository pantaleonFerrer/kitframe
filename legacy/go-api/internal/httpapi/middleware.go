package httpapi

import (
	"context"
	"net/http"
	"strings"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/permissions"
	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"
)

type ctxKey string

const (
	ctxUserID      ctxKey = "user_id"
	ctxUserEmail   ctxKey = "user_email"
	ctxMembership  ctxKey = "membership"
	ctxBrandID     ctxKey = "brand_id"
)

type AuthUser struct {
	ID    uuid.UUID
	Email string
}

func (s *Server) authenticate(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		token := ""
		header := r.Header.Get("Authorization")
		if strings.HasPrefix(header, "Bearer ") {
			token = strings.TrimPrefix(header, "Bearer ")
		} else if q := r.URL.Query().Get("access_token"); q != "" {
			token = q
		}
		if token == "" {
			writeError(w, apperr.Unauthorized("missing bearer token"))
			return
		}
		claims, err := s.tokens.ParseAccess(token)
		if err != nil {
			writeError(w, apperr.Unauthorized("invalid access token"))
			return
		}
		ctx := context.WithValue(r.Context(), ctxUserID, claims.UserID)
		ctx = context.WithValue(ctx, ctxUserEmail, claims.Email)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func userIDFrom(ctx context.Context) uuid.UUID {
	v, _ := ctx.Value(ctxUserID).(uuid.UUID)
	return v
}

func userEmailFrom(ctx context.Context) string {
	v, _ := ctx.Value(ctxUserEmail).(string)
	return v
}

func membershipFrom(ctx context.Context) *db.BrandMembership {
	v, _ := ctx.Value(ctxMembership).(*db.BrandMembership)
	return v
}

func (s *Server) requirePermission(perm permissions.Permission) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			m := membershipFrom(r.Context())
			if m == nil {
				writeError(w, apperr.Forbidden("brand membership required"))
				return
			}
			role := permissions.Role(m.Role)
			team := ""
			if m.Team != nil {
				team = *m.Team
			}
			if !permissions.CanActOnTeam(role, perm, team, team) {
				if !permissions.Has(role, perm) {
					writeError(w, apperr.Forbidden("insufficient permissions"))
					return
				}
			}
			if !permissions.Has(role, perm) {
				writeError(w, apperr.Forbidden("insufficient permissions"))
				return
			}
			next.ServeHTTP(w, r)
		})
	}
}

func (s *Server) loadMembershipForBrandParam(param string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			brandID := chi.URLParam(r, param)
			if brandID == "" {
				writeError(w, apperr.InvalidRequest("brand id required", nil))
				return
			}
			uid := userIDFrom(r.Context())
			m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
			if err != nil {
				writeError(w, apperr.Forbidden("not a member of this brand"))
				return
			}
			ctx := context.WithValue(r.Context(), ctxMembership, m)
			ctx = context.WithValue(ctx, ctxBrandID, brandID)
			next.ServeHTTP(w, r.WithContext(ctx))
		})
	}
}

func (s *Server) resolveBrandFromProduct(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		productID := chi.URLParam(r, "id")
		if productID == "" {
			productID = chi.URLParam(r, "productID")
		}
		brandID, err := s.db.ProductBrandID(r.Context(), productID)
		if err != nil {
			writeError(w, apperr.NotFound("product not found"))
			return
		}
		uid := userIDFrom(r.Context())
		m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
		if err != nil {
			writeError(w, apperr.Forbidden("not a member of this brand"))
			return
		}
		ctx := context.WithValue(r.Context(), ctxMembership, m)
		ctx = context.WithValue(ctx, ctxBrandID, brandID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (s *Server) resolveBrandFromCollection(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		colID := chi.URLParam(r, "id")
		col, err := s.db.GetCollection(r.Context(), colID)
		if err != nil {
			writeError(w, apperr.NotFound("collection not found"))
			return
		}
		uid := userIDFrom(r.Context())
		m, err := s.db.GetMembership(r.Context(), uid.String(), col.BrandID)
		if err != nil {
			writeError(w, apperr.Forbidden("not a member of this brand"))
			return
		}
		ctx := context.WithValue(r.Context(), ctxMembership, m)
		ctx = context.WithValue(ctx, ctxBrandID, col.BrandID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (s *Server) resolveBrandFromAsset(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		assetID := chi.URLParam(r, "id")
		a, err := s.db.GetAsset(r.Context(), assetID)
		if err != nil {
			writeError(w, apperr.NotFound("asset not found"))
			return
		}
		brandID, err := s.db.ProductBrandID(r.Context(), a.ProductID)
		if err != nil {
			writeError(w, apperr.NotFound("product not found"))
			return
		}
		uid := userIDFrom(r.Context())
		m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
		if err != nil {
			writeError(w, apperr.Forbidden("not a member of this brand"))
			return
		}
		ctx := context.WithValue(r.Context(), ctxMembership, m)
		ctx = context.WithValue(ctx, ctxBrandID, brandID)
		ctx = context.WithValue(ctx, ctxKey("asset"), a)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func clientIP(r *http.Request) string {
	if xff := r.Header.Get("X-Forwarded-For"); xff != "" {
		parts := strings.Split(xff, ",")
		return strings.TrimSpace(parts[0])
	}
	host := r.RemoteAddr
	if i := strings.LastIndex(host, ":"); i >= 0 {
		return host[:i]
	}
	return host
}