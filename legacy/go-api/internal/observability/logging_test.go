package observability

import (
	"bytes"
	"encoding/json"
	"strings"
	"testing"
)

func TestLogJSON(t *testing.T) {
	var buf bytes.Buffer
	if err := LogJSON(&buf, "info", "hello", Fields{"request_id": "abc"}); err != nil {
		t.Fatal(err)
	}
	var payload map[string]any
	if err := json.Unmarshal(buf.Bytes(), &payload); err != nil {
		t.Fatal(err)
	}
	if payload["msg"] != "hello" {
		t.Fatalf("msg=%v", payload["msg"])
	}
	if payload["level"] != "info" {
		t.Fatalf("level=%v", payload["level"])
	}
	if payload["request_id"] != "abc" {
		t.Fatalf("request_id=%v", payload["request_id"])
	}
	if _, ok := payload["time"].(string); !ok {
		t.Fatal("missing time")
	}
}

func TestNewJSONLogger(t *testing.T) {
	var buf bytes.Buffer
	logger := NewJSONLogger(&buf)
	logger.Info("structured", "k", "v")
	out := buf.String()
	if !strings.Contains(out, "structured") {
		t.Fatalf("unexpected log output: %s", out)
	}
}
