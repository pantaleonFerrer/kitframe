package sse

import (
	"encoding/json"
	"net/http"
	"sync"
)

type Hub struct {
	mu   sync.RWMutex
	subs map[string]map[chan []byte]struct{}
}

func NewHub() *Hub {
	return &Hub{subs: make(map[string]map[chan []byte]struct{})}
}

func (h *Hub) Subscribe(collectionID string) chan []byte {
	ch := make(chan []byte, 16)
	h.mu.Lock()
	defer h.mu.Unlock()
	if h.subs[collectionID] == nil {
		h.subs[collectionID] = make(map[chan []byte]struct{})
	}
	h.subs[collectionID][ch] = struct{}{}
	return ch
}

func (h *Hub) Unsubscribe(collectionID string, ch chan []byte) {
	h.mu.Lock()
	defer h.mu.Unlock()
	if m, ok := h.subs[collectionID]; ok {
		delete(m, ch)
		close(ch)
		if len(m) == 0 {
			delete(h.subs, collectionID)
		}
	}
}

func (h *Hub) Publish(collectionID string, event string, payload any) {
	raw, err := json.Marshal(map[string]any{
		"event":   event,
		"payload": payload,
	})
	if err != nil {
		return
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	for ch := range h.subs[collectionID] {
		select {
		case ch <- raw:
		default:
		}
	}
}

func WriteSSE(w http.ResponseWriter, flusher http.Flusher, data []byte) {
	_, _ = w.Write([]byte("data: "))
	_, _ = w.Write(data)
	_, _ = w.Write([]byte("\n\n"))
	flusher.Flush()
}
