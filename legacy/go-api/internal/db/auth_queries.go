package db

import (
	"context"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgconn"
)

type Querier interface {
	Exec(ctx context.Context, sql string, arguments ...any) (pgconn.CommandTag, error)
	Query(ctx context.Context, sql string, args ...any) (pgx.Rows, error)
	QueryRow(ctx context.Context, sql string, args ...any) pgx.Row
}

func (d *DB) GetUserByEmail(ctx context.Context, email string) (*User, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, email, password_hash, display_name, refresh_token_version, created_at
		FROM users WHERE email = $1`, email)
	var u User
	if err := row.Scan(&u.ID, &u.Email, &u.PasswordHash, &u.DisplayName, &u.RefreshTokenVersion, &u.CreatedAt); err != nil {
		return nil, err
	}
	return &u, nil
}

func (d *DB) GetUserByID(ctx context.Context, id string) (*User, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, email, password_hash, display_name, refresh_token_version, created_at
		FROM users WHERE id = $1`, id)
	var u User
	if err := row.Scan(&u.ID, &u.Email, &u.PasswordHash, &u.DisplayName, &u.RefreshTokenVersion, &u.CreatedAt); err != nil {
		return nil, err
	}
	return &u, nil
}

func (d *DB) UpdatePasswordHash(ctx context.Context, userID, hash string) error {
	_, err := d.Pool.Exec(ctx, `UPDATE users SET password_hash = $2 WHERE id = $1`, userID, hash)
	return err
}

func (d *DB) IncrementRefreshVersion(ctx context.Context, q Querier, userID string) error {
	_, err := q.Exec(ctx, `UPDATE users SET refresh_token_version = refresh_token_version + 1 WHERE id = $1`, userID)
	return err
}

func (d *DB) RecordLoginAttempt(ctx context.Context, email, ip string, succeeded bool) error {
	_, err := d.Pool.Exec(ctx, `
		INSERT INTO login_attempts (email, ip_address, succeeded) VALUES ($1, $2, $3)`, email, ip, succeeded)
	return err
}

func (d *DB) CountLoginAttemptsByEmail(ctx context.Context, email string, since time.Time) (int, error) {
	var n int
	err := d.Pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM login_attempts
		WHERE email = $1 AND succeeded = false AND created_at >= $2`, email, since).Scan(&n)
	return n, err
}

func (d *DB) CountLoginAttemptsByIP(ctx context.Context, ip string, since time.Time) (int, error) {
	var n int
	err := d.Pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM login_attempts
		WHERE ip_address = $1 AND succeeded = false AND created_at >= $2`, ip, since).Scan(&n)
	return n, err
}

func (d *DB) OldestLoginAttemptByEmail(ctx context.Context, email string, since time.Time) (*time.Time, error) {
	var t *time.Time
	err := d.Pool.QueryRow(ctx, `
		SELECT MIN(created_at) FROM login_attempts
		WHERE email = $1 AND succeeded = false AND created_at >= $2`, email, since).Scan(&t)
	return t, err
}

func (d *DB) OldestLoginAttemptByIP(ctx context.Context, ip string, since time.Time) (*time.Time, error) {
	var t *time.Time
	err := d.Pool.QueryRow(ctx, `
		SELECT MIN(created_at) FROM login_attempts
		WHERE ip_address = $1 AND succeeded = false AND created_at >= $2`, ip, since).Scan(&t)
	return t, err
}

func (d *DB) DenylistRefresh(ctx context.Context, q Querier, jti, userID string, expiresAt time.Time) error {
	_, err := q.Exec(ctx, `
		INSERT INTO refresh_token_denylist (jti, user_id, expires_at)
		VALUES ($1, $2, $3) ON CONFLICT (jti) DO NOTHING`, jti, userID, expiresAt)
	return err
}

func (d *DB) IsRefreshDenylisted(ctx context.Context, jti string) (bool, error) {
	var exists bool
	err := d.Pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM refresh_token_denylist WHERE jti = $1)`, jti).Scan(&exists)
	return exists, err
}

func (d *DB) ListMembershipsByUser(ctx context.Context, userID string) ([]BrandMembership, error) {
	rows, err := d.Pool.Query(ctx, `
		SELECT id::text, user_id::text, brand_id::text, role, team, created_at
		FROM brand_memberships WHERE user_id = $1`, userID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []BrandMembership
	for rows.Next() {
		var m BrandMembership
		if err := rows.Scan(&m.ID, &m.UserID, &m.BrandID, &m.Role, &m.Team, &m.CreatedAt); err != nil {
			return nil, err
		}
		out = append(out, m)
	}
	return out, rows.Err()
}

func (d *DB) GetMembership(ctx context.Context, userID, brandID string) (*BrandMembership, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, user_id::text, brand_id::text, role, team, created_at
		FROM brand_memberships WHERE user_id = $1 AND brand_id = $2`, userID, brandID)
	var m BrandMembership
	if err := row.Scan(&m.ID, &m.UserID, &m.BrandID, &m.Role, &m.Team, &m.CreatedAt); err != nil {
		return nil, err
	}
	return &m, nil
}

func (d *DB) GetMembershipByID(ctx context.Context, id string) (*BrandMembership, error) {
	row := d.Pool.QueryRow(ctx, `
		SELECT id::text, user_id::text, brand_id::text, role, team, created_at
		FROM brand_memberships WHERE id = $1`, id)
	var m BrandMembership
	if err := row.Scan(&m.ID, &m.UserID, &m.BrandID, &m.Role, &m.Team, &m.CreatedAt); err != nil {
		return nil, err
	}
	return &m, nil
}

func (d *DB) InsertAudit(ctx context.Context, q Querier, userID, brandID *string, entityType, entityID, action string, detail []byte) error {
	_, err := q.Exec(ctx, `
		INSERT INTO audit_log (user_id, brand_id, entity_type, entity_id, action, detail)
		VALUES ($1, $2, $3, $4, $5, $6)`, userID, brandID, entityType, entityID, action, detail)
	return err
}
