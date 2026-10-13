package httpapi

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/ai"
	"github.com/gathered/kitframe/apps/api/internal/auth"
	"github.com/gathered/kitframe/apps/api/internal/config"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/permissions"
	"github.com/gathered/kitframe/apps/api/internal/sse"
	"github.com/gathered/kitframe/apps/api/internal/storage"
	"github.com/go-chi/chi/v5"
	chimw "github.com/go-chi/chi/v5/middleware"
	"github.com/go-chi/cors"
	"github.com/prometheus/client_golang/prometheus/promhttp"
)

type JobEnqueuer interface {
	EnqueueExtract(ctx context.Context, sourceDocumentID string) error
	EnqueueQC(ctx context.Context, assetID, goldenSetImageID string) error
	EnqueueGenerate(ctx context.Context, generationRequestID string) error
	EnqueueGenerateSEO(ctx context.Context, productID string) error
	EnqueueTrainAvatar(ctx context.Context, avatarID string) error
	EnqueueExport(ctx context.Context, productID, channel string) error
}

type Server struct {
	cfg     config.Config
	db      *db.DB
	tokens  *auth.TokenService
	ai      *ai.Client
	hub     *sse.Hub
	jobs    JobEnqueuer
	store   *storage.Store
	openapi []byte
}

func NewServer(cfg config.Config, database *db.DB, tokens *auth.TokenService, aiClient *ai.Client, hub *sse.Hub, jobs JobEnqueuer, openapi []byte) *Server {
	store := storage.New(storage.Config{
		Endpoint:     cfg.S3Endpoint,
		AccessKey:    cfg.S3AccessKey,
		SecretKey:    cfg.S3SecretKey,
		Bucket:       cfg.S3Bucket,
		UsePathStyle: cfg.S3UsePathStyle,
		Region:       cfg.S3Region,
		LocalDir:     ".uploads",
		PublicBase:   cfg.PublicAPIURL,
	})
	return &Server{
		cfg:     cfg,
		db:      database,
		tokens:  tokens,
		ai:      aiClient,
		hub:     hub,
		jobs:    jobs,
		store:   store,
		openapi: openapi,
	}
}

func (s *Server) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(chimw.RequestID)
	r.Use(chimw.RealIP)
	r.Use(chimw.Recoverer)
	r.Use(cors.Handler(cors.Options{
		AllowedOrigins:   s.cfg.CORSOrigins,
		AllowedMethods:   []string{"GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"},
		AllowedHeaders:   []string{"Accept", "Authorization", "Content-Type", "X-Brand-Id"},
		AllowCredentials: true,
		MaxAge:           300,
	}))

	r.Get("/healthz", func(w http.ResponseWriter, _ *http.Request) {
		writeJSON(w, http.StatusOK, map[string]string{"status": "ok"})
	})
	r.Handle("/metrics", promhttp.Handler())
	r.Get("/openapi.json", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusOK)
		_, _ = w.Write(s.openapi)
	})

	r.Route("/v1", func(r chi.Router) {
		r.Post("/auth/login", s.handleLogin)
		r.Post("/auth/refresh", s.handleRefresh)
		r.Post("/auth/logout", s.handleLogout)
		r.Post("/webhooks/shopify", s.handleShopifyWebhook)
		r.Get("/uploads/*", s.handleGetUpload)

		r.Group(func(r chi.Router) {
			r.Use(s.authenticate)
			r.Get("/me", s.handleMe)

			r.With(s.loadMembershipForBrandParam("id")).Get("/brands/{id}", s.handleGetBrand)
			r.With(s.loadMembershipForBrandParam("id"), s.requirePermissionOwner()).Patch("/brands/{id}", s.handlePatchBrand)
			r.With(s.loadMembershipForBrandParam("id"), s.requirePermissionOwner()).Post("/brands/{id}/channel-specs", s.handleCreateChannelSpec)
			r.With(s.loadMembershipForBrandParam("id")).Get("/brands/{id}/channel-specs", s.handleListChannelSpecs)
			r.With(s.loadMembershipForBrandParam("id")).Get("/brands/{id}/collections", s.handleListBrandCollections)
			r.Patch("/channel-specs/{id}", s.handlePatchChannelSpec)

			r.With(s.resolveBrandFromCollection).Get("/collections/{id}", s.handleGetCollection)
			r.With(s.resolveBrandFromCollection).Get("/collections/{id}/products", s.handleListCollectionProducts)
			r.With(s.resolveBrandFromCollection).Get("/collections/{id}/bottlenecks", s.handleBottlenecks)
			r.With(s.resolveBrandFromCollection).Get("/collections/{id}/events", s.handleCollectionEvents)

			r.With(s.loadMembershipForBrandParam("id"), s.requirePermissionOwner()).Post("/brands/{id}/alert-rules", s.handleCreateAlertRule)
			r.With(s.loadMembershipForBrandParam("id")).Get("/brands/{id}/alert-rules", s.handleListAlertRules)

			r.Post("/source-documents", s.handleCreateSourceDocument)
			r.Get("/source-documents/{id}", s.handleGetSourceDocument)

			r.With(s.resolveBrandFromProduct).Get("/products/{id}", s.handleGetProduct)
			r.With(s.resolveBrandFromProduct).Patch("/products/{id}", s.handlePatchProduct)
			r.With(s.resolveBrandFromProduct).Post("/products/{id}/generate-seo", s.handleGenerateSEO)
			r.With(s.resolveBrandFromProduct).Post("/products/{id}/advance-step", s.handleAdvanceStep)
			r.With(s.resolveBrandFromProduct).Post("/products/{id}/publish-shopify", s.handlePublishShopify)
			r.With(s.resolveBrandFromProduct).Post("/products/{id}/export", s.handleExportProduct)

			r.With(s.resolveBrandFromProduct).Post("/products/{id}/generate-finals", s.handleGenerateProductFinals)
			r.With(s.resolveBrandFromAsset).Post("/assets/{id}/apply-to-avatar", s.handleApplyFinalToAvatar)

			r.Get("/reference-library", s.handleListReferenceLibrary)
			r.Post("/reference-library", s.handleCreateReferenceLibrary)
			r.Get("/avatar-studio-sessions/{id}", s.handleGetAvatarStudioSession)
			r.Post("/avatar-studio-sessions/{id}/iterate", s.handleIterateAvatarStudio)

			r.Post("/assets", s.handleCreateAsset)
			r.Get("/assets/search", s.handleSearchAssets)
			r.With(s.resolveBrandFromAsset).Get("/assets/{id}", s.handleGetAsset)
			r.With(s.resolveBrandFromAsset).Post("/assets/{id}/run-qc", s.handleRunQC)
			r.With(s.resolveBrandFromAsset).Post("/assets/{id}/approve", s.handleApproveAsset)
			r.With(s.resolveBrandFromAsset).Post("/assets/{id}/reindex", s.handleReindexAsset)

			r.Get("/golden-set", s.handleListGoldenSet)
			r.Post("/golden-set", s.handleCreateGoldenSet)

			r.Get("/rights-records", s.handleListRights)
			r.Post("/rights-records", s.handleCreateRights)
			r.Patch("/rights-records/{id}", s.handlePatchRights)

			r.Post("/uploads", s.handleUpload)

			r.Get("/avatars", s.handleListAvatars)
			r.Post("/avatars", s.handleCreateAvatar)
			r.Get("/avatars/{id}", s.handleGetAvatar)
			r.Get("/pose-references", s.handleListPoseReferences)
			r.Post("/pose-references", s.handleCreatePoseReference)
			r.Post("/generation-requests", s.handleCreateGenerationRequest)
			r.Get("/generation-requests/{id}", s.handleGetGenerationRequest)

			r.Post("/provider-benchmarks/run", s.handleRunBenchmark)
			r.Get("/provider-benchmarks", s.handleListBenchmarks)

			r.Get("/notification-preferences", s.handleGetNotificationPrefs)
			r.Patch("/notification-preferences", s.handlePatchNotificationPrefs)
			r.Get("/notifications", s.handleListNotifications)
			r.Post("/notifications/mark-all-read", s.handleMarkAllNotificationsRead)
			r.Patch("/notifications/{id}/read", s.handleMarkNotificationRead)

			r.Get("/audit-log", s.handleListAuditLog)

			r.Get("/jobs/{id}", s.handleGetJob)
			r.Get("/jobs", s.handleListJobs)

			r.With(s.loadMembershipForBrandParam("id"), s.requirePermission(permissions.PermManageUsers)).Get("/brands/{id}/users", s.handleListBrandUsers)
			r.With(s.loadMembershipForBrandParam("id"), s.requirePermission(permissions.PermManageUsers)).Post("/brands/{id}/users/invite", s.handleInviteUser)
			r.Patch("/brand-memberships/{id}", s.handlePatchMembership)
			r.Delete("/brand-memberships/{id}", s.handleDeleteMembership)

			r.Get("/briefs", s.handleListBriefs)
			r.Post("/briefs", s.handleCreateBrief)
			r.Get("/briefs/{id}", s.handleGetBrief)
			r.Patch("/briefs/{id}", s.handlePatchBrief)
			r.Post("/briefs/{id}/send-for-validation", s.handleSendBriefValidation)

			r.Get("/library-projects", s.handleListLibraryProjects)
			r.Get("/library-assignees", s.handleListLibraryAssignees)
			r.Post("/library-projects", s.handleCreateLibraryProject)
			r.With(s.resolveBrandFromLibraryProject).Get("/library-projects/{id}/contents", s.handleGetLibraryContents)
			r.With(s.resolveBrandFromLibraryProject).Post("/library-projects/{id}/folders", s.handleCreateLibraryFolder)
			r.With(s.resolveBrandFromLibraryProject).Post("/library-projects/{id}/files", s.handleCreateLibraryFile)
			r.With(s.resolveBrandFromLibraryFile).Patch("/library-files/{id}", s.handlePatchLibraryFile)
			r.With(s.resolveBrandFromLibraryFile).Get("/library-files/{id}/comments", s.handleListLibraryFileComments)
			r.With(s.resolveBrandFromLibraryFile).Post("/library-files/{id}/comments", s.handleCreateLibraryFileComment)
			r.Post("/library-shares", s.handleCreateLibraryShare)
			r.Get("/library-shares", s.handleListLibraryShares)
		})

		r.Get("/share/{token}", s.handleGetPublicShare)
		r.Post("/share/{token}/comments", s.handleCreatePublicShareComment)
	})

	return r
}

func (s *Server) requirePermissionOwner() func(http.Handler) http.Handler {
	return s.requirePermission(permissions.PermManageBrandSettings)
}

func (s *Server) setRefreshCookie(w http.ResponseWriter, token string, exp time.Time) {
	sameSite := http.SameSiteLaxMode
	switch s.cfg.RefreshCookieSameSite {
	case "strict":
		sameSite = http.SameSiteStrictMode
	case "none":
		sameSite = http.SameSiteNoneMode
	}
	http.SetCookie(w, &http.Cookie{
		Name:     s.cfg.RefreshCookieName,
		Value:    token,
		Path:     "/v1/auth",
		Expires:  exp,
		HttpOnly: true,
		Secure:   s.cfg.RefreshCookieSecure,
		SameSite: sameSite,
	})
}

func (s *Server) clearRefreshCookie(w http.ResponseWriter) {
	http.SetCookie(w, &http.Cookie{
		Name:     s.cfg.RefreshCookieName,
		Value:    "",
		Path:     "/v1/auth",
		Expires:  time.Unix(0, 0),
		MaxAge:   -1,
		HttpOnly: true,
		Secure:   s.cfg.RefreshCookieSecure,
	})
}

func jsonRaw(v any) json.RawMessage {
	b, _ := json.Marshal(v)
	return b
}
