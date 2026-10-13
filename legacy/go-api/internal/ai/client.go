package ai

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"time"
)

type Client struct {
	baseURL    string
	httpClient *http.Client
}

func NewClient(baseURL string) *Client {
	return &Client{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 90 * time.Second,
		},
	}
}

func (c *Client) post(ctx context.Context, path string, body any, out any) error {
	raw, err := json.Marshal(body)
	if err != nil {
		return err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, c.baseURL+path, bytes.NewReader(raw))
	if err != nil {
		return err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := c.httpClient.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return err
	}
	if resp.StatusCode >= 300 {
		return fmt.Errorf("ai service %s: status %d: %s", path, resp.StatusCode, string(data))
	}
	if out == nil {
		return nil
	}
	return json.Unmarshal(data, out)
}

func (c *Client) Extract(ctx context.Context, sourceDocumentURL string, taxonomySchema any) (map[string]any, error) {
	var out map[string]any
	err := c.post(ctx, "/extract", map[string]any{
		"source_document_url": sourceDocumentURL,
		"taxonomy_schema":     taxonomySchema,
	}, &out)
	return out, err
}

func (c *Client) GenerateCopy(ctx context.Context, product any, locales []string, glossary any) (map[string]any, error) {
	var out map[string]any
	err := c.post(ctx, "/generate-copy", map[string]any{
		"product":  product,
		"locales":  locales,
		"glossary": glossary,
	}, &out)
	return out, err
}

func (c *Client) ProcessImage(ctx context.Context, assetURL, operation string) (map[string]any, error) {
	var out map[string]any
	err := c.post(ctx, "/process-image", map[string]any{
		"asset_url": assetURL,
		"operation": operation,
	}, &out)
	return out, err
}

func (c *Client) QCScore(ctx context.Context, assetURL, goldenSetImageID string) (map[string]any, error) {
	var out map[string]any
	err := c.post(ctx, "/qc-score", map[string]any{
		"asset_url":           assetURL,
		"golden_set_image_id": goldenSetImageID,
	}, &out)
	return out, err
}

func (c *Client) TrainAvatarIdentity(ctx context.Context, referenceAssetURLs []string) (map[string]any, error) {
	var out map[string]any
	err := c.post(ctx, "/train-avatar-identity", map[string]any{
		"reference_asset_urls": referenceAssetURLs,
	}, &out)
	return out, err
}

func (c *Client) GenerateImage(ctx context.Context, body map[string]any) (map[string]any, error) {
	var out map[string]any
	err := c.post(ctx, "/generate-image", body, &out)
	return out, err
}
