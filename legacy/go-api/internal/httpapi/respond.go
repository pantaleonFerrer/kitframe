package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/gathered/kitframe/apps/api/internal/apperr"
	"github.com/gathered/kitframe/apps/api/internal/db"
)

type errorEnvelope struct {
	Error *apperr.Error `json:"error"`
}

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, err error) {
	if ae, ok := err.(*apperr.Error); ok {
		if ae.Details == nil {
			ae.Details = map[string]any{}
		}
		writeJSON(w, ae.HTTPStatus, errorEnvelope{Error: ae})
		return
	}
	writeJSON(w, http.StatusInternalServerError, errorEnvelope{
		Error: apperr.Internal("internal error"),
	})
}

func writePage(w http.ResponseWriter, data any, total, page int) {
	writeJSON(w, http.StatusOK, map[string]any{
		"data":  data,
		"total": total,
		"page":  page,
	})
}

func decodeJSON(r *http.Request, dst any) error {
	raw, err := decodeJSONRaw(r)
	if err != nil {
		return err
	}
	if err := json.Unmarshal(raw, dst); err != nil {
		return apperr.InvalidRequest("invalid JSON body", map[string]any{"reason": err.Error()})
	}
	return nil
}

func decodeJSONRaw(r *http.Request) ([]byte, error) {
	dec := json.NewDecoder(r.Body)
	var raw json.RawMessage
	if err := dec.Decode(&raw); err != nil {
		return nil, apperr.InvalidRequest("invalid JSON body", map[string]any{"reason": err.Error()})
	}
	return raw, nil
}

func paginationFrom(r *http.Request) db.Pagination {
	page := queryInt(r, "page", 1)
	pageSize := queryInt(r, "page_size", 25)
	return db.ParsePagination(page, pageSize)
}

func queryInt(r *http.Request, key string, def int) int {
	v := r.URL.Query().Get(key)
	if v == "" {
		return def
	}
	var n int
	for _, c := range v {
		if c < '0' || c > '9' {
			return def
		}
		n = n*10 + int(c-'0')
	}
	return n
}
