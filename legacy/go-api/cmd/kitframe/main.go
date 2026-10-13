package main

import (
	"context"
	"embed"
	"flag"
	"log/slog"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/ai"
	"github.com/gathered/kitframe/apps/api/internal/auth"
	"github.com/gathered/kitframe/apps/api/internal/config"
	"github.com/gathered/kitframe/apps/api/internal/db"
	"github.com/gathered/kitframe/apps/api/internal/httpapi"
	"github.com/gathered/kitframe/apps/api/internal/jobs"
	"github.com/gathered/kitframe/apps/api/internal/seed"
	"github.com/gathered/kitframe/apps/api/internal/sse"
	"github.com/gathered/kitframe/apps/api/internal/storage"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/riverqueue/river/riverdriver/riverpgxv5"
	"github.com/riverqueue/river/rivermigrate"
)

//go:embed openapi.json
var openapiFS embed.FS

func main() {
	mode := flag.String("mode", "api", "api|worker")
	flag.Parse()

	cfg, err := config.Load()
	if err != nil {
		slog.Error("config", "err", err)
		os.Exit(1)
	}

	ctx, cancel := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer cancel()

	database, err := db.Connect(ctx, cfg.DatabaseURL)
	if err != nil {
		slog.Error("database", "err", err)
		os.Exit(1)
	}
	defer database.Close()

	if err := migrateRiver(ctx, database.Pool); err != nil {
		slog.Error("river migrate", "err", err)
		os.Exit(1)
	}

	if cfg.SeedPasswords && cfg.Env != "production" {
		if err := seed.RehashDevPasswords(ctx, database); err != nil {
			slog.Error("seed passwords", "err", err)
			os.Exit(1)
		}
	}

	aiClient := ai.NewClient(cfg.AIServiceURL)
	tokens := auth.NewTokenService(cfg.JWTAccessSecret, cfg.JWTRefreshSecret, cfg.AccessTokenTTL, cfg.RefreshTokenTTL)
	store := newStore(cfg)

	switch *mode {
	case "worker":
		runWorker(ctx, database, aiClient, store)
	default:
		runAPI(ctx, cfg, database, aiClient, tokens, store)
	}
}

func newStore(cfg config.Config) *storage.Store {
	return storage.New(storage.Config{
		Endpoint:     cfg.S3Endpoint,
		AccessKey:    cfg.S3AccessKey,
		SecretKey:    cfg.S3SecretKey,
		Bucket:       cfg.S3Bucket,
		UsePathStyle: cfg.S3UsePathStyle,
		Region:       cfg.S3Region,
		LocalDir:     ".uploads",
		PublicBase:   cfg.PublicAPIURL,
	})
}

func migrateRiver(ctx context.Context, pool *pgxpool.Pool) error {
	migrator, err := rivermigrate.New(riverpgxv5.New(pool), nil)
	if err != nil {
		return err
	}
	_, err = migrator.Migrate(ctx, rivermigrate.DirectionUp, nil)
	return err
}

func runAPI(ctx context.Context, cfg config.Config, database *db.DB, aiClient *ai.Client, tokens *auth.TokenService, store *storage.Store) {
	_, enqueuer, err := jobs.NewAPIClient(database, aiClient, store)
	if err != nil {
		slog.Error("river client", "err", err)
		os.Exit(1)
	}
	openapi, err := openapiFS.ReadFile("openapi.json")
	if err != nil {
		slog.Error("openapi", "err", err)
		os.Exit(1)
	}
	hub := sse.NewHub()
	srv := httpapi.NewServer(cfg, database, tokens, aiClient, hub, enqueuer, openapi)
	httpServer := &http.Server{
		Addr:              cfg.HTTPAddr,
		Handler:           srv.Router(),
		ReadHeaderTimeout: 10 * time.Second,
	}
	go func() {
		slog.Info("api listening", "addr", cfg.HTTPAddr)
		if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			slog.Error("http", "err", err)
			os.Exit(1)
		}
	}()
	<-ctx.Done()
	shutdownCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = httpServer.Shutdown(shutdownCtx)
}

func runWorker(ctx context.Context, database *db.DB, aiClient *ai.Client, store *storage.Store) {
	client, _, err := jobs.NewWorkerClient(database, aiClient, store)
	if err != nil {
		slog.Error("river worker client", "err", err)
		os.Exit(1)
	}
	if err := client.Start(ctx); err != nil {
		slog.Error("river start", "err", err)
		os.Exit(1)
	}
	slog.Info("worker started")
	<-ctx.Done()
	stopCtx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	_ = client.Stop(stopCtx)
}
