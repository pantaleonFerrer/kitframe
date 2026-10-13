package observability

import (
	"encoding/json"
	"io"
	"log/slog"
	"os"
	"time"
)

func NewJSONLogger(w io.Writer) *slog.Logger {
	if w == nil {
		w = os.Stdout
	}
	return slog.New(slog.NewJSONHandler(w, &slog.HandlerOptions{Level: slog.LevelInfo}))
}

type Fields map[string]any

func LogJSON(w io.Writer, level, msg string, fields Fields) error {
	if w == nil {
		w = os.Stdout
	}
	payload := map[string]any{
		"time":  time.Now().UTC().Format(time.RFC3339Nano),
		"level": level,
		"msg":   msg,
	}
	for k, v := range fields {
		payload[k] = v
	}
	enc := json.NewEncoder(w)
	return enc.Encode(payload)
}
