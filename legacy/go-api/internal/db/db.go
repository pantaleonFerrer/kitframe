package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

type DB struct {
	Pool *pgxpool.Pool
}

func Connect(ctx context.Context, databaseURL string) (*DB, error) {
	cfg, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, err
	}
	cfg.MaxConns = 20
	pool, err := pgxpool.NewWithConfig(ctx, cfg)
	if err != nil {
		return nil, err
	}
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, err
	}
	return &DB{Pool: pool}, nil
}

func (d *DB) Close() {
	d.Pool.Close()
}

func (d *DB) WithTx(ctx context.Context, fn func(pgx.Tx) error) error {
	tx, err := d.Pool.Begin(ctx)
	if err != nil {
		return err
	}
	defer tx.Rollback(ctx)
	if err := fn(tx); err != nil {
		return err
	}
	return tx.Commit(ctx)
}

type Pagination struct {
	Page     int
	PageSize int
}

func ParsePagination(page, pageSize int) Pagination {
	if page < 1 {
		page = 1
	}
	if pageSize < 1 {
		pageSize = 25
	}
	if pageSize > 100 {
		pageSize = 100
	}
	return Pagination{Page: page, PageSize: pageSize}
}

func (p Pagination) Offset() int {
	return (p.Page - 1) * p.PageSize
}

type User struct {
	ID                  string
	Email               string
	PasswordHash        string
	DisplayName         *string
	RefreshTokenVersion int
	CreatedAt           time.Time
}

type BrandMembership struct {
	ID        string
	UserID    string
	BrandID   string
	Role      string
	Team      *string
	CreatedAt time.Time
}

type Brand struct {
	ID                              string
	Name                            string
	TaxonomySchema                  []byte
	TranslationGlossary             []byte
	ShopifyStoreDomain              *string
	ShopifyAccessTokenEncrypted     *string
	ShopifyLiveStoreDomain          *string
	ShopifyLiveAccessTokenEncrypted *string
	ShopifyEnvironment              string
	QCPassThreshold                 float64
	QCFailThreshold                 float64
	QCCheckFloor                    float64
	CreatedAt                       time.Time
	UpdatedAt                       time.Time
}

type Collection struct {
	ID                string
	BrandID           string
	Name              string
	SampleArrivalDate *time.Time
	MustShipDate      *time.Time
	SaleDate          *time.Time
	CreatedAt         time.Time
	UpdatedAt         time.Time
}

type Product struct {
	ID                   string
	CollectionID         string
	InternalReference    string
	Category             *string
	Status               string
	StructuredData       []byte
	ExtractionConfidence []byte
	SEO                  []byte
	Translations         []byte
	AssignedTeam         *string
	ShopifyProductID     *string
	CreatedAt            time.Time
	UpdatedAt            time.Time
}

type Asset struct {
	ID                 string
	ProductID          string
	VariantID          *string
	Type               string
	Origin             string
	ImageRole          string
	FileURL            string
	GenerationProvider *string
	QCStatus           string
	CreatedAt          time.Time
}
