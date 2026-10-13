package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"
)

type Config struct {
	DatabaseURL           string
	HTTPAddr              string
	AIServiceURL          string
	JWTAccessSecret       string
	JWTRefreshSecret      string
	AccessTokenTTL        time.Duration
	RefreshTokenTTL       time.Duration
	CORSOrigins           []string
	ShopifyWebhookSecret  string
	SeedPasswords         bool
	Env                   string
	S3Endpoint            string
	S3AccessKey           string
	S3SecretKey           string
	S3Bucket              string
	S3UsePathStyle        bool
	S3Region              string
	PublicAPIURL          string
	SMTPHost              string
	SMTPPort              int
	RefreshCookieName     string
	RefreshCookieSecure   bool
	RefreshCookieSameSite string
}

func Load() (Config, error) {
	cfg := Config{
		DatabaseURL:           os.Getenv("DATABASE_URL"),
		HTTPAddr:              getenv("HTTP_ADDR", ":8080"),
		AIServiceURL:          getenv("AI_SERVICE_URL", "http://localhost:8000"),
		JWTAccessSecret:       os.Getenv("JWT_ACCESS_SECRET"),
		JWTRefreshSecret:      os.Getenv("JWT_REFRESH_SECRET"),
		AccessTokenTTL:        15 * time.Minute,
		RefreshTokenTTL:       30 * 24 * time.Hour,
		CORSOrigins:           splitCSV(getenv("CORS_ORIGINS", "http://localhost:3000")),
		ShopifyWebhookSecret:  os.Getenv("SHOPIFY_WEBHOOK_SECRET"),
		SeedPasswords:         strings.EqualFold(os.Getenv("SEED_PASSWORDS"), "true"),
		Env:                   getenv("APP_ENV", "development"),
		S3Endpoint:            os.Getenv("S3_ENDPOINT"),
		S3AccessKey:           os.Getenv("S3_ACCESS_KEY"),
		S3SecretKey:           os.Getenv("S3_SECRET_KEY"),
		S3Bucket:              getenv("S3_BUCKET", "kitframe-assets"),
		S3UsePathStyle:        strings.EqualFold(os.Getenv("S3_USE_PATH_STYLE"), "true"),
		S3Region:              getenv("S3_REGION", "eu-west-1"),
		PublicAPIURL:          os.Getenv("PUBLIC_API_URL"),
		SMTPHost:              os.Getenv("SMTP_HOST"),
		SMTPPort:              getenvInt("SMTP_PORT", 1025),
		RefreshCookieName:     getenv("REFRESH_COOKIE_NAME", "kitframe_refresh"),
		RefreshCookieSecure:   strings.EqualFold(os.Getenv("REFRESH_COOKIE_SECURE"), "true"),
		RefreshCookieSameSite: getenv("REFRESH_COOKIE_SAMESITE", "lax"),
	}
	if cfg.DatabaseURL == "" {
		return Config{}, fmt.Errorf("DATABASE_URL is required")
	}
	if cfg.JWTAccessSecret == "" {
		return Config{}, fmt.Errorf("JWT_ACCESS_SECRET is required")
	}
	if cfg.JWTRefreshSecret == "" {
		return Config{}, fmt.Errorf("JWT_REFRESH_SECRET is required")
	}
	return cfg, nil
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

func getenvInt(key string, fallback int) int {
	v := os.Getenv(key)
	if v == "" {
		return fallback
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return fallback
	}
	return n
}

func splitCSV(s string) []string {
	parts := strings.Split(s, ",")
	out := make([]string, 0, len(parts))
	for _, p := range parts {
		p = strings.TrimSpace(p)
		if p != "" {
			out = append(out, p)
		}
	}
	return out
}
