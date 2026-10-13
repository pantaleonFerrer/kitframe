package httpapi

import (
	"io"
	"mime/multipart"
	"net/http"
	"path/filepath"
	"strings"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/go-chi/chi/v5"
)

func (s *Server) handleUpload(w http.ResponseWriter, r *http.Request) {
	if err := r.ParseMultipartForm(64 << 20); err != nil {
		writeError(w, apperr.InvalidRequest("invalid multipart form", map[string]any{"reason": err.Error()}))
		return
	}

	headers := collectUploadFileHeaders(r)
	if len(headers) == 0 {
		writeError(w, apperr.InvalidRequest("no files provided", nil))
		return
	}

	results := make([]map[string]any, 0, len(headers))
	for _, fh := range headers {
		f, err := fh.Open()
		if err != nil {
			writeError(w, apperr.InvalidRequest("could not read file", map[string]any{"filename": fh.Filename}))
			return
		}
		contentType := fh.Header.Get("Content-Type")
		put, err := s.store.Put(r.Context(), fh.Filename, contentType, f, fh.Size)
		_ = f.Close()
		if err != nil {
			writeError(w, apperr.Internal("upload failed"))
			return
		}
		urlStr := put.URL
		if put.Local {
			urlStr = s.store.AbsoluteLocalURL(r, put.Key)
		}
		results = append(results, map[string]any{
			"url":          urlStr,
			"filename":     put.Filename,
			"content_type": put.ContentType,
			"size":         put.Size,
			"key":          put.Key,
		})
	}

	writeJSON(w, http.StatusCreated, map[string]any{"data": results})
}

func (s *Server) handleGetUpload(w http.ResponseWriter, r *http.Request) {
	key := chi.URLParam(r, "*")
	if key == "" {
		key = chi.URLParam(r, "key")
	}
	key = strings.TrimPrefix(key, "/")
	if key == "" || strings.Contains(key, "..") {
		writeError(w, apperr.NotFound("file not found"))
		return
	}

	f, contentType, err := s.store.OpenLocal(key)
	if err != nil {
		writeError(w, apperr.NotFound("file not found"))
		return
	}
	defer f.Close()

	w.Header().Set("Content-Type", contentType)
	w.Header().Set("Cache-Control", "private, max-age=3600")
	w.Header().Set("Content-Disposition", "inline; filename=\""+filepath.Base(key)+"\"")
	w.WriteHeader(http.StatusOK)
	_, _ = io.Copy(w, f)
}

func collectUploadFileHeaders(r *http.Request) []*multipart.FileHeader {
	if r.MultipartForm == nil {
		return nil
	}
	var out []*multipart.FileHeader
	for _, key := range []string{"files", "file"} {
		out = append(out, r.MultipartForm.File[key]...)
	}
	return out
}
