package httpapi

import (
	"context"
	"net/http"
	"strings"
	"time"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/permissions"
	"github.com/go-chi/chi/v5"
)

func (s *Server) resolveBrandFromLibraryProject(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		projectID := chi.URLParam(r, "id")
		if projectID == "" {
			projectID = chi.URLParam(r, "projectId")
		}
		var brandID string
		err := s.db.Pool.QueryRow(r.Context(), `
			SELECT brand_id::text FROM library_projects WHERE id = $1`, projectID).Scan(&brandID)
		if err != nil {
			writeError(w, apperr.NotFound("project not found"))
			return
		}
		uid := userIDFrom(r.Context())
		m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
		if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermViewProduct) {
			writeError(w, apperr.Forbidden("insufficient permissions"))
			return
		}
		ctx := context.WithValue(r.Context(), ctxMembership, m)
		ctx = context.WithValue(ctx, ctxBrandID, brandID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (s *Server) resolveBrandFromLibraryFile(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		fileID := chi.URLParam(r, "id")
		var brandID string
		err := s.db.Pool.QueryRow(r.Context(), `
			SELECT p.brand_id::text
			FROM library_files f
			JOIN library_projects p ON p.id = f.project_id
			WHERE f.id = $1`, fileID).Scan(&brandID)
		if err != nil {
			writeError(w, apperr.NotFound("file not found"))
			return
		}
		uid := userIDFrom(r.Context())
		m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
		if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermViewProduct) {
			writeError(w, apperr.Forbidden("insufficient permissions"))
			return
		}
		ctx := context.WithValue(r.Context(), ctxMembership, m)
		ctx = context.WithValue(ctx, ctxBrandID, brandID)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func (s *Server) handleListLibraryAssignees(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	if brandID == "" {
		writeError(w, apperr.InvalidRequest("brand_id required", nil))
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermViewProduct) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT u.id::text, u.email, u.display_name, m.role
		FROM brand_memberships m
		JOIN users u ON u.id = m.user_id
		WHERE m.brand_id = $1 AND m.role IN ('owner','admin','editor')
		ORDER BY u.email`, brandID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, email, role string
		var display *string
		if err := rows.Scan(&id, &email, &display, &role); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		name := email
		if display != nil && *display != "" {
			name = *display
		}
		data = append(data, map[string]any{
			"id": id, "email": email, "name": name, "role": role,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": data})
}

func (s *Server) handleListLibraryProjects(w http.ResponseWriter, r *http.Request) {
	brandID := r.URL.Query().Get("brand_id")
	if brandID == "" {
		writeError(w, apperr.InvalidRequest("brand_id required", nil))
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermViewProduct) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	p := paginationFrom(r)
	var total int
	_ = s.db.Pool.QueryRow(r.Context(), `
		SELECT COUNT(*) FROM library_projects WHERE brand_id = $1`, brandID).Scan(&total)
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, brand_id::text, name, description, collection_id::text, created_by::text, created_at, updated_at
		FROM library_projects
		WHERE brand_id = $1
		ORDER BY updated_at DESC
		LIMIT $2 OFFSET $3`, brandID, p.PageSize, p.Offset())
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		item, err := scanLibraryProject(rows.Scan)
		if err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, item)
	}
	writePage(w, data, total, p.Page)
}

func (s *Server) handleCreateLibraryProject(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID      string  `json:"brand_id"`
		Name         string  `json:"name"`
		Description  *string `json:"description"`
		CollectionID *string `json:"collection_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if strings.TrimSpace(body.Name) == "" {
		writeError(w, apperr.InvalidRequest("name required", nil))
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), body.BrandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO library_projects (brand_id, name, description, collection_id, created_by)
		VALUES ($1,$2,$3,$4,$5) RETURNING id::text`,
		body.BrandID, body.Name, body.Description, body.CollectionID, uid.String()).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "name": body.Name})
}

func (s *Server) handleGetLibraryContents(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "id")
	folderID := r.URL.Query().Get("folder_id")
	breadcrumbs := make([]map[string]any, 0)
	breadcrumbs = append(breadcrumbs, map[string]any{"id": nil, "name": "root"})

	if folderID != "" {
		var currentID *string = &folderID
		path := make([]map[string]any, 0)
		for currentID != nil {
			var id, name string
			var parentID *string
			err := s.db.Pool.QueryRow(r.Context(), `
				SELECT id::text, name, parent_folder_id::text
				FROM library_folders WHERE id = $1 AND project_id = $2`, *currentID, projectID).
				Scan(&id, &name, &parentID)
			if err != nil {
				writeError(w, apperr.NotFound("folder not found"))
				return
			}
			path = append([]map[string]any{{"id": id, "name": name}}, path...)
			currentID = parentID
		}
		breadcrumbs = append(breadcrumbs, path...)
	}

	var folderRows interface {
		Close()
		Next() bool
		Scan(dest ...any) error
	}
	var err error
	if folderID == "" {
		folderRows, err = s.db.Pool.Query(r.Context(), `
			SELECT id::text, name, parent_folder_id::text, created_at
			FROM library_folders WHERE project_id = $1 AND parent_folder_id IS NULL ORDER BY name`, projectID)
	} else {
		folderRows, err = s.db.Pool.Query(r.Context(), `
			SELECT id::text, name, parent_folder_id::text, created_at
			FROM library_folders WHERE project_id = $1 AND parent_folder_id = $2 ORDER BY name`, projectID, folderID)
	}
	if err != nil {
		writeError(w, apperr.Internal("folder query failed"))
		return
	}
	defer folderRows.Close()
	folders := make([]map[string]any, 0)
	for folderRows.Next() {
		var id, name string
		var parentID *string
		var created time.Time
		if err := folderRows.Scan(&id, &name, &parentID, &created); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		folders = append(folders, map[string]any{
			"id": id, "name": name, "parent_folder_id": parentID, "created_at": created,
		})
	}

	var fileRows interface {
		Close()
		Next() bool
		Scan(dest ...any) error
	}
	if folderID == "" {
		fileRows, err = s.db.Pool.Query(r.Context(), `
			SELECT f.id::text, f.name, f.file_url, f.content_type, f.size_bytes,
			       f.assigned_user_id::text, u.display_name, u.email, f.created_at
			FROM library_files f
			LEFT JOIN users u ON u.id = f.assigned_user_id
			WHERE f.project_id = $1 AND f.folder_id IS NULL
			ORDER BY f.name`, projectID)
	} else {
		fileRows, err = s.db.Pool.Query(r.Context(), `
			SELECT f.id::text, f.name, f.file_url, f.content_type, f.size_bytes,
			       f.assigned_user_id::text, u.display_name, u.email, f.created_at
			FROM library_files f
			LEFT JOIN users u ON u.id = f.assigned_user_id
			WHERE f.project_id = $1 AND f.folder_id = $2
			ORDER BY f.name`, projectID, folderID)
	}
	if err != nil {
		writeError(w, apperr.Internal("file query failed"))
		return
	}
	defer fileRows.Close()
	files := make([]map[string]any, 0)
	for fileRows.Next() {
		item, err := scanLibraryFileRow(fileRows.Scan)
		if err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		files = append(files, item)
	}

	var projectName string
	_ = s.db.Pool.QueryRow(r.Context(), `SELECT name FROM library_projects WHERE id = $1`, projectID).Scan(&projectName)

	writeJSON(w, http.StatusOK, map[string]any{
		"project_id":   projectID,
		"project_name": projectName,
		"folder_id":    nullIfEmpty(folderID),
		"breadcrumbs":  breadcrumbs,
		"folders":      folders,
		"files":        files,
	})
}

func (s *Server) handleCreateLibraryFolder(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "id")
	var body struct {
		Name           string  `json:"name"`
		ParentFolderID *string `json:"parent_folder_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if strings.TrimSpace(body.Name) == "" {
		writeError(w, apperr.InvalidRequest("name required", nil))
		return
	}
	uid := userIDFrom(r.Context())
	m := membershipFrom(r.Context())
	if !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err := s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO library_folders (project_id, parent_folder_id, name, created_by)
		VALUES ($1,$2,$3,$4) RETURNING id::text`,
		projectID, body.ParentFolderID, body.Name, uid.String()).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "name": body.Name})
}

func (s *Server) handleCreateLibraryFile(w http.ResponseWriter, r *http.Request) {
	projectID := chi.URLParam(r, "id")
	var body struct {
		Name        string  `json:"name"`
		FileURL     string  `json:"file_url"`
		FolderID    *string `json:"folder_id"`
		ContentType *string `json:"content_type"`
		SizeBytes   *int64  `json:"size_bytes"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if body.Name == "" || body.FileURL == "" {
		writeError(w, apperr.InvalidRequest("name and file_url required", nil))
		return
	}
	uid := userIDFrom(r.Context())
	m := membershipFrom(r.Context())
	if !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err := s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO library_files (project_id, folder_id, name, file_url, content_type, size_bytes, created_by)
		VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id::text`,
		projectID, body.FolderID, body.Name, body.FileURL, body.ContentType, body.SizeBytes, uid.String()).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "name": body.Name, "file_url": body.FileURL})
}

func (s *Server) handlePatchLibraryFile(w http.ResponseWriter, r *http.Request) {
	fileID := chi.URLParam(r, "id")
	var body struct {
		Name           *string `json:"name"`
		AssignedUserID *string `json:"assigned_user_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	m := membershipFrom(r.Context())
	if !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	if body.Name != nil {
		_, err := s.db.Pool.Exec(r.Context(), `
			UPDATE library_files SET name = $1, updated_at = now() WHERE id = $2`, *body.Name, fileID)
		if err != nil {
			writeError(w, apperr.Internal("update failed"))
			return
		}
	}
	if body.AssignedUserID != nil {
		if *body.AssignedUserID == "" {
			_, err := s.db.Pool.Exec(r.Context(), `
				UPDATE library_files SET assigned_user_id = NULL, updated_at = now() WHERE id = $1`, fileID)
			if err != nil {
				writeError(w, apperr.Internal("update failed"))
				return
			}
		} else {
			_, err := s.db.Pool.Exec(r.Context(), `
				UPDATE library_files SET assigned_user_id = $1, updated_at = now() WHERE id = $2`, *body.AssignedUserID, fileID)
			if err != nil {
				writeError(w, apperr.Internal("update failed"))
				return
			}
		}
	}
	writeJSON(w, http.StatusOK, map[string]string{"id": fileID, "status": "updated"})
}

func (s *Server) handleListLibraryFileComments(w http.ResponseWriter, r *http.Request) {
	fileID := chi.URLParam(r, "id")
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT c.id::text, c.user_id::text, c.author_name, c.body, c.created_at,
		       u.display_name, u.email
		FROM library_file_comments c
		LEFT JOIN users u ON u.id = c.user_id
		WHERE c.file_id = $1
		ORDER BY c.created_at ASC`, fileID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, body string
		var userID, authorName, displayName, email *string
		var created time.Time
		if err := rows.Scan(&id, &userID, &authorName, &body, &created, &displayName, &email); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		author := ""
		if displayName != nil && *displayName != "" {
			author = *displayName
		} else if email != nil {
			author = *email
		} else if authorName != nil {
			author = *authorName
		}
		data = append(data, map[string]any{
			"id": id, "user_id": userID, "author_name": author, "body": body, "created_at": created,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": data})
}

func (s *Server) handleCreateLibraryFileComment(w http.ResponseWriter, r *http.Request) {
	fileID := chi.URLParam(r, "id")
	var body struct {
		Body string `json:"body"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if strings.TrimSpace(body.Body) == "" {
		writeError(w, apperr.InvalidRequest("body required", nil))
		return
	}
	uid := userIDFrom(r.Context())
	m := membershipFrom(r.Context())
	if !permissions.Has(permissions.Role(m.Role), permissions.PermViewProduct) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	var id string
	err := s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO library_file_comments (file_id, user_id, body)
		VALUES ($1,$2,$3) RETURNING id::text`, fileID, uid.String(), body.Body).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "body": body.Body})
}

func (s *Server) handleCreateLibraryShare(w http.ResponseWriter, r *http.Request) {
	var body struct {
		BrandID        string  `json:"brand_id"`
		ProjectID      *string `json:"project_id"`
		FolderID       *string `json:"folder_id"`
		FileID         *string `json:"file_id"`
		Label          *string `json:"label"`
		AllowComments  *bool   `json:"allow_comments"`
		ExpiresAt      *string `json:"expires_at"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), body.BrandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermEditStructuredData) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	allowComments := true
	if body.AllowComments != nil {
		allowComments = *body.AllowComments
	}
	var expiresAt *time.Time
	if body.ExpiresAt != nil && *body.ExpiresAt != "" {
		t, err := time.Parse(time.RFC3339, *body.ExpiresAt)
		if err != nil {
			writeError(w, apperr.InvalidRequest("invalid expires_at", nil))
			return
		}
		expiresAt = &t
	}
	var id, token string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO library_shares (brand_id, project_id, folder_id, file_id, label, allow_comments, expires_at, created_by)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
		RETURNING id::text, token`,
		body.BrandID, body.ProjectID, body.FolderID, body.FileID, body.Label, allowComments, expiresAt, uid.String()).
		Scan(&id, &token)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{
		"id": id, "token": token, "url_path": "/share/" + token,
	})
}

func (s *Server) handleListLibraryShares(w http.ResponseWriter, r *http.Request) {
	projectID := r.URL.Query().Get("project_id")
	if projectID == "" {
		writeError(w, apperr.InvalidRequest("project_id required", nil))
		return
	}
	var brandID string
	_ = s.db.Pool.QueryRow(r.Context(), `SELECT brand_id::text FROM library_projects WHERE id = $1`, projectID).Scan(&brandID)
	uid := userIDFrom(r.Context())
	m, err := s.db.GetMembership(r.Context(), uid.String(), brandID)
	if err != nil || !permissions.Has(permissions.Role(m.Role), permissions.PermViewProduct) {
		writeError(w, apperr.Forbidden("insufficient permissions"))
		return
	}
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT id::text, token, label, allow_comments, expires_at, created_at,
		       project_id::text, folder_id::text, file_id::text
		FROM library_shares
		WHERE project_id = $1 OR folder_id IN (SELECT id FROM library_folders WHERE project_id = $1)
		ORDER BY created_at DESC`, projectID)
	if err != nil {
		writeError(w, apperr.Internal("query failed"))
		return
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, token string
		var label, projectIDOut, folderID, fileID *string
		var allowComments bool
		var expiresAt *time.Time
		var created time.Time
		if err := rows.Scan(&id, &token, &label, &allowComments, &expiresAt, &created, &projectIDOut, &folderID, &fileID); err != nil {
			writeError(w, apperr.Internal("scan failed"))
			return
		}
		data = append(data, map[string]any{
			"id": id, "token": token, "label": label, "allow_comments": allowComments,
			"expires_at": expiresAt, "created_at": created,
			"project_id": projectIDOut, "folder_id": folderID, "file_id": fileID,
			"url_path": "/share/" + token,
		})
	}
	writeJSON(w, http.StatusOK, map[string]any{"data": data})
}

func (s *Server) handleGetPublicShare(w http.ResponseWriter, r *http.Request) {
	token := chi.URLParam(r, "token")
	folderID := r.URL.Query().Get("folder_id")
	share, err := s.loadShareByToken(r, token)
	if err != nil {
		writeError(w, err)
		return
	}

	if share.FileID != nil {
		file, err := s.loadLibraryFileByID(r, *share.FileID)
		if err != nil {
			writeError(w, err)
			return
		}
		comments, _ := s.loadPublicComments(r, *share.FileID)
		writeJSON(w, http.StatusOK, map[string]any{
			"scope":           "file",
			"label":           share.Label,
			"allow_comments":  share.AllowComments,
			"file":            file,
			"comments":        comments,
		})
		return
	}

	projectID := share.ProjectID
	if share.FolderID != nil && folderID == "" {
		folderID = *share.FolderID
	}
	if projectID == nil {
		writeError(w, apperr.NotFound("share not found"))
		return
	}

	contents, err := s.loadShareContents(r, *projectID, folderID)
	if err != nil {
		writeError(w, err)
		return
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"scope":          "folder",
		"label":          share.Label,
		"allow_comments": share.AllowComments,
		"project_id":     *projectID,
		"folder_id":      nullIfEmpty(folderID),
		"contents":       contents,
	})
}

func (s *Server) handleCreatePublicShareComment(w http.ResponseWriter, r *http.Request) {
	token := chi.URLParam(r, "token")
	share, err := s.loadShareByToken(r, token)
	if err != nil {
		writeError(w, err)
		return
	}
	if !share.AllowComments {
		writeError(w, apperr.Forbidden("comments disabled"))
		return
	}
	var body struct {
		Body       string `json:"body"`
		AuthorName string `json:"author_name"`
		FileID     string `json:"file_id"`
	}
	if err := decodeJSON(r, &body); err != nil {
		writeError(w, err)
		return
	}
	if strings.TrimSpace(body.Body) == "" || body.FileID == "" {
		writeError(w, apperr.InvalidRequest("body and file_id required", nil))
		return
	}
	if !s.shareAllowsFile(r, share, body.FileID) {
		writeError(w, apperr.Forbidden("file not in share scope"))
		return
	}
	authorName := strings.TrimSpace(body.AuthorName)
	if authorName == "" {
		authorName = "Guest"
	}
	var id string
	err = s.db.Pool.QueryRow(r.Context(), `
		INSERT INTO library_file_comments (file_id, author_name, body)
		VALUES ($1,$2,$3) RETURNING id::text`, body.FileID, authorName, body.Body).Scan(&id)
	if err != nil {
		writeError(w, apperr.Internal("create failed"))
		return
	}
	writeJSON(w, http.StatusCreated, map[string]any{"id": id, "body": body.Body, "author_name": authorName})
}

type libraryShare struct {
	ID             string
	BrandID        string
	ProjectID      *string
	FolderID       *string
	FileID         *string
	Label          *string
	AllowComments  bool
	ExpiresAt      *time.Time
}

func (s *Server) loadShareByToken(r *http.Request, token string) (*libraryShare, error) {
	var share libraryShare
	var projectID, folderID, fileID, label *string
	err := s.db.Pool.QueryRow(r.Context(), `
		SELECT id::text, brand_id::text, project_id::text, folder_id::text, file_id::text,
		       label, allow_comments, expires_at
		FROM library_shares WHERE token = $1`, token).
		Scan(&share.ID, &share.BrandID, &projectID, &folderID, &fileID, &label, &share.AllowComments, &share.ExpiresAt)
	if err != nil {
		return nil, apperr.NotFound("share not found")
	}
	if share.ExpiresAt != nil && share.ExpiresAt.Before(time.Now()) {
		return nil, apperr.Forbidden("share expired")
	}
	share.ProjectID = projectID
	share.FolderID = folderID
	share.FileID = fileID
	share.Label = label
	return &share, nil
}

func (s *Server) shareAllowsFile(r *http.Request, share *libraryShare, fileID string) bool {
	if share.FileID != nil {
		return *share.FileID == fileID
	}
	var projectID string
	err := s.db.Pool.QueryRow(r.Context(), `SELECT project_id::text FROM library_files WHERE id = $1`, fileID).Scan(&projectID)
	if err != nil {
		return false
	}
	if share.ProjectID != nil && *share.ProjectID != projectID {
		return false
	}
	if share.FolderID != nil {
		var folderID *string
		_ = s.db.Pool.QueryRow(r.Context(), `SELECT folder_id::text FROM library_files WHERE id = $1`, fileID).Scan(&folderID)
		if folderID == nil || *folderID != *share.FolderID {
			return false
		}
	}
	return true
}

func (s *Server) loadLibraryFileByID(r *http.Request, fileID string) (map[string]any, error) {
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT f.id::text, f.name, f.file_url, f.content_type, f.size_bytes,
		       f.assigned_user_id::text, u.display_name, u.email, f.created_at
		FROM library_files f
		LEFT JOIN users u ON u.id = f.assigned_user_id
		WHERE f.id = $1`, fileID)
	if err != nil {
		return nil, apperr.Internal("query failed")
	}
	defer rows.Close()
	if !rows.Next() {
		return nil, apperr.NotFound("file not found")
	}
	return scanLibraryFileRow(rows.Scan)
}

func (s *Server) loadPublicComments(r *http.Request, fileID string) ([]map[string]any, error) {
	rows, err := s.db.Pool.Query(r.Context(), `
		SELECT c.id::text, c.author_name, c.body, c.created_at, u.display_name, u.email
		FROM library_file_comments c
		LEFT JOIN users u ON u.id = c.user_id
		WHERE c.file_id = $1 ORDER BY c.created_at ASC`, fileID)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	data := make([]map[string]any, 0)
	for rows.Next() {
		var id, body string
		var authorName, displayName, email *string
		var created time.Time
		if err := rows.Scan(&id, &authorName, &body, &created, &displayName, &email); err != nil {
			return nil, err
		}
		author := "Guest"
		if displayName != nil && *displayName != "" {
			author = *displayName
		} else if email != nil && *email != "" {
			author = *email
		} else if authorName != nil && *authorName != "" {
			author = *authorName
		}
		data = append(data, map[string]any{
			"id": id, "author_name": author, "body": body, "created_at": created,
		})
	}
	return data, nil
}

func (s *Server) loadShareContents(r *http.Request, projectID, folderID string) (map[string]any, error) {
	breadcrumbs := []map[string]any{{"id": nil, "name": "root"}}
	if folderID != "" {
		var currentID *string = &folderID
		path := make([]map[string]any, 0)
		for currentID != nil {
			var id, name string
			var parentID *string
			err := s.db.Pool.QueryRow(r.Context(), `
				SELECT id::text, name, parent_folder_id::text
				FROM library_folders WHERE id = $1 AND project_id = $2`, *currentID, projectID).
				Scan(&id, &name, &parentID)
			if err != nil {
				return nil, apperr.NotFound("folder not found")
			}
			path = append([]map[string]any{{"id": id, "name": name}}, path...)
			currentID = parentID
		}
		breadcrumbs = append(breadcrumbs, path...)
	}

	var folderRows interface {
		Close()
		Next() bool
		Scan(dest ...any) error
	}
	var err error
	if folderID == "" {
		folderRows, err = s.db.Pool.Query(r.Context(), `
			SELECT id::text, name, parent_folder_id::text, created_at
			FROM library_folders WHERE project_id = $1 AND parent_folder_id IS NULL ORDER BY name`, projectID)
	} else {
		folderRows, err = s.db.Pool.Query(r.Context(), `
			SELECT id::text, name, parent_folder_id::text, created_at
			FROM library_folders WHERE project_id = $1 AND parent_folder_id = $2 ORDER BY name`, projectID, folderID)
	}
	if err != nil {
		return nil, apperr.Internal("folder query failed")
	}
	defer folderRows.Close()
	folders := make([]map[string]any, 0)
	for folderRows.Next() {
		var id, name string
		var parentID *string
		var created time.Time
		if err := folderRows.Scan(&id, &name, &parentID, &created); err != nil {
			return nil, apperr.Internal("scan failed")
		}
		folders = append(folders, map[string]any{"id": id, "name": name, "parent_folder_id": parentID})
	}

	var fileRows interface {
		Close()
		Next() bool
		Scan(dest ...any) error
	}
	if folderID == "" {
		fileRows, err = s.db.Pool.Query(r.Context(), `
			SELECT f.id::text, f.name, f.file_url, f.content_type, f.size_bytes,
			       NULL::text, NULL::text, NULL::text, f.created_at
			FROM library_files f
			WHERE f.project_id = $1 AND f.folder_id IS NULL ORDER BY f.name`, projectID)
	} else {
		fileRows, err = s.db.Pool.Query(r.Context(), `
			SELECT f.id::text, f.name, f.file_url, f.content_type, f.size_bytes,
			       NULL::text, NULL::text, NULL::text, f.created_at
			FROM library_files f
			WHERE f.project_id = $1 AND f.folder_id = $2 ORDER BY f.name`, projectID, folderID)
	}
	if err != nil {
		return nil, apperr.Internal("file query failed")
	}
	defer fileRows.Close()
	files := make([]map[string]any, 0)
	for fileRows.Next() {
		item, err := scanLibraryFileRow(fileRows.Scan)
		if err != nil {
			return nil, apperr.Internal("scan failed")
		}
		files = append(files, item)
	}

	var projectName string
	_ = s.db.Pool.QueryRow(r.Context(), `SELECT name FROM library_projects WHERE id = $1`, projectID).Scan(&projectName)

	return map[string]any{
		"project_name": projectName,
		"breadcrumbs":  breadcrumbs,
		"folders":      folders,
		"files":        files,
	}, nil
}

func scanLibraryProject(scan func(dest ...any) error) (map[string]any, error) {
	var id, brandID, name string
	var description, collectionID, createdBy *string
	var created, updated time.Time
	if err := scan(&id, &brandID, &name, &description, &collectionID, &createdBy, &created, &updated); err != nil {
		return nil, err
	}
	return map[string]any{
		"id": id, "brand_id": brandID, "name": name, "description": description,
		"collection_id": collectionID, "created_by": createdBy,
		"created_at": created, "updated_at": updated,
	}, nil
}

func scanLibraryFileRow(scan func(dest ...any) error) (map[string]any, error) {
	var id, name, fileURL string
	var contentType, assignedUserID, displayName, email *string
	var sizeBytes *int64
	var created time.Time
	if err := scan(&id, &name, &fileURL, &contentType, &sizeBytes, &assignedUserID, &displayName, &email, &created); err != nil {
		return nil, err
	}
	assignee := ""
	if displayName != nil && *displayName != "" {
		assignee = *displayName
	} else if email != nil && *email != "" {
		assignee = *email
	}
	return map[string]any{
		"id": id, "name": name, "file_url": fileURL, "content_type": contentType,
		"size_bytes": sizeBytes, "assigned_user_id": assignedUserID,
		"assignee_name": nullIfEmpty(assignee), "created_at": created,
	}, nil
}

func nullIfEmpty(s string) any {
	if s == "" {
		return nil
	}
	return s
}
