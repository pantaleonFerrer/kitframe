package storage

import (
	"bytes"
	"context"
	"fmt"
	"io"
	"mime"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	"github.com/aws/aws-sdk-go-v2/service/s3"
	"github.com/google/uuid"
)

type Config struct {
	Endpoint     string
	AccessKey    string
	SecretKey    string
	Bucket       string
	UsePathStyle bool
	Region       string
	LocalDir     string
	PublicBase   string
}

type PutResult struct {
	Key         string
	URL         string
	Filename    string
	ContentType string
	Size        int64
	Local       bool
}

type Store struct {
	cfg    Config
	client *s3.Client
}

func New(cfg Config) *Store {
	if cfg.LocalDir == "" {
		cfg.LocalDir = ".uploads"
	}
	if cfg.Region == "" {
		cfg.Region = "eu-west-1"
	}
	if cfg.Bucket == "" {
		cfg.Bucket = "kitframe-assets"
	}
	s := &Store{cfg: cfg}
	if cfg.Endpoint != "" && cfg.AccessKey != "" && cfg.SecretKey != "" {
		awsCfg, err := awsconfig.LoadDefaultConfig(context.Background(),
			awsconfig.WithRegion(cfg.Region),
			awsconfig.WithCredentialsProvider(credentials.NewStaticCredentialsProvider(
				cfg.AccessKey, cfg.SecretKey, "",
			)),
		)
		if err == nil {
			s.client = s3.NewFromConfig(awsCfg, func(o *s3.Options) {
				o.BaseEndpoint = aws.String(strings.TrimRight(cfg.Endpoint, "/"))
				o.UsePathStyle = cfg.UsePathStyle
			})
		}
	}
	_ = os.MkdirAll(cfg.LocalDir, 0o755)
	return s
}

func (s *Store) Put(ctx context.Context, filename string, contentType string, r io.Reader, size int64) (PutResult, error) {
	if contentType == "" {
		contentType = mime.TypeByExtension(filepath.Ext(filename))
		if contentType == "" {
			contentType = "application/octet-stream"
		}
	}
	safeName := sanitizeFilename(filename)
	key := fmt.Sprintf("%s/%s-%s", time.Now().UTC().Format("2006/01/02"), uuid.NewString(), safeName)

	data, err := io.ReadAll(r)
	if err != nil {
		return PutResult{}, err
	}
	if size <= 0 {
		size = int64(len(data))
	}

	localPath := filepath.Join(s.cfg.LocalDir, filepath.FromSlash(key))
	if err := os.MkdirAll(filepath.Dir(localPath), 0o755); err != nil {
		return PutResult{}, err
	}
	if err := os.WriteFile(localPath, data, 0o644); err != nil {
		return PutResult{}, err
	}

	if s.client != nil {
		_, _ = s.client.PutObject(ctx, &s3.PutObjectInput{
			Bucket:        aws.String(s.cfg.Bucket),
			Key:           aws.String(key),
			Body:          bytes.NewReader(data),
			ContentType:   aws.String(contentType),
			ContentLength: aws.Int64(size),
		})
	}

	return PutResult{
		Key:         key,
		URL:         s.localPublicURL(key),
		Filename:    filename,
		ContentType: contentType,
		Size:        size,
		Local:       true,
	}, nil
}

func (s *Store) PublicURL(key string) string {
	if s.cfg.PublicBase != "" {
		return strings.TrimRight(s.cfg.PublicBase, "/") + "/" + strings.TrimLeft(key, "/")
	}
	endpoint := strings.TrimRight(s.cfg.Endpoint, "/")
	if endpoint == "" {
		return s.localPublicURL(key)
	}
	if s.cfg.UsePathStyle {
		return fmt.Sprintf("%s/%s/%s", endpoint, s.cfg.Bucket, key)
	}
	u, err := url.Parse(endpoint)
	if err != nil {
		return fmt.Sprintf("%s/%s/%s", endpoint, s.cfg.Bucket, key)
	}
	host := u.Host
	return fmt.Sprintf("%s://%s.%s/%s", u.Scheme, s.cfg.Bucket, host, key)
}

func (s *Store) SignedURL(ctx context.Context, key string, expiry time.Duration) (string, error) {
	if s.client == nil {
		return s.localPublicURL(key), nil
	}
	presign := s3.NewPresignClient(s.client)
	out, err := presign.PresignGetObject(ctx, &s3.GetObjectInput{
		Bucket: aws.String(s.cfg.Bucket),
		Key:    aws.String(key),
	}, s3.WithPresignExpires(expiry))
	if err != nil {
		return "", err
	}
	return out.URL, nil
}

func (s *Store) OpenLocal(key string) (*os.File, string, error) {
	clean := filepath.Clean("/" + key)
	clean = strings.TrimPrefix(clean, "/")
	path := filepath.Join(s.cfg.LocalDir, filepath.FromSlash(clean))
	absLocal, err := filepath.Abs(s.cfg.LocalDir)
	if err != nil {
		return nil, "", err
	}
	absPath, err := filepath.Abs(path)
	if err != nil {
		return nil, "", err
	}
	if !strings.HasPrefix(absPath, absLocal+string(os.PathSeparator)) && absPath != absLocal {
		return nil, "", os.ErrNotExist
	}
	f, err := os.Open(absPath)
	if err != nil {
		return nil, "", err
	}
	ct := mime.TypeByExtension(filepath.Ext(absPath))
	if ct == "" {
		ct = "application/octet-stream"
	}
	return f, ct, nil
}

func (s *Store) LocalDir() string {
	return s.cfg.LocalDir
}

func (s *Store) localPublicURL(key string) string {
	escaped := pathEscapeKey(key)
	if s.cfg.PublicBase != "" {
		return strings.TrimRight(s.cfg.PublicBase, "/") + "/v1/uploads/" + escaped
	}
	return "/v1/uploads/" + escaped
}

func (s *Store) AbsoluteLocalURL(r *http.Request, key string) string {
	escaped := pathEscapeKey(key)
	if s.cfg.PublicBase != "" {
		return strings.TrimRight(s.cfg.PublicBase, "/") + "/v1/uploads/" + escaped
	}
	scheme := "http"
	if r.TLS != nil {
		scheme = "https"
	}
	if proto := r.Header.Get("X-Forwarded-Proto"); proto != "" {
		scheme = proto
	}
	host := r.Host
	if host == "" {
		host = "localhost:8080"
	}
	return fmt.Sprintf("%s://%s/v1/uploads/%s", scheme, host, escaped)
}

func pathEscapeKey(key string) string {
	parts := strings.Split(key, "/")
	for i, p := range parts {
		parts[i] = url.PathEscape(p)
	}
	return strings.Join(parts, "/")
}

func sanitizeFilename(name string) string {
	base := filepath.Base(name)
	base = strings.ReplaceAll(base, " ", "-")
	var b strings.Builder
	for _, r := range base {
		if (r >= 'a' && r <= 'z') || (r >= 'A' && r <= 'Z') || (r >= '0' && r <= '9') || r == '.' || r == '-' || r == '_' {
			b.WriteRune(r)
		}
	}
	out := b.String()
	if out == "" {
		return "file"
	}
	return out
}
