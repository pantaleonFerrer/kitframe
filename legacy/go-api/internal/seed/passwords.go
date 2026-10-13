package seed

import (
	"context"
	"log/slog"

	"github.com/gathered/kitframe/apps/api/internal/auth"
	"github.com/gathered/kitframe/apps/api/internal/db"
)

const DevPassword = "Password123!"

var seedEmails = []string{
	"owner@kitframe.local",
	"admin@kitframe.local",
	"editor@kitframe.local",
	"viewer@kitframe.local",
}

func RehashDevPasswords(ctx context.Context, database *db.DB) error {
	hash, err := auth.HashPassword(DevPassword)
	if err != nil {
		return err
	}
	for _, email := range seedEmails {
		u, err := database.GetUserByEmail(ctx, email)
		if err != nil {
			slog.Warn("seed password skip", "email", email, "err", err)
			continue
		}
		if err := database.UpdatePasswordHash(ctx, u.ID, hash); err != nil {
			return err
		}
		slog.Info("seed password updated", "email", email)
	}
	return nil
}
