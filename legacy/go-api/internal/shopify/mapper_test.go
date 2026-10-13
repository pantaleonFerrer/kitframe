package shopify

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"testing"
)

func TestMapProductToShopifyPayload(t *testing.T) {
	cat := "jersey"
	color := "blaugrana"
	size := "M"
	in := ProductInput{
		InternalReference: "HOME-26-001",
		Category:          &cat,
		StructuredData: map[string]any{
			"composition": "100% polyester",
			"category":    "jersey",
		},
		SEO: map[string]any{
			"title":            "Home Kit Jersey",
			"meta_description": "Official home kit",
		},
		Translations: map[string]any{
			"es": map[string]any{"title": "Camiseta local"},
		},
		Variants: []VariantInput{
			{SKU: "HOME-26-001-M", Color: &color, Size: &size},
		},
	}
	p := MapProductToShopifyPayload(in)
	if p.Title != "Home Kit Jersey" {
		t.Fatalf("title=%s", p.Title)
	}
	if p.ProductType != "jersey" {
		t.Fatalf("type=%s", p.ProductType)
	}
	if len(p.Variants) != 1 || p.Variants[0].SKU != "HOME-26-001-M" {
		t.Fatalf("variants=%v", p.Variants)
	}
	if len(p.Metafields) < 1 {
		t.Fatal("expected metafields")
	}
}

func TestVerifyWebhookHMAC(t *testing.T) {
	secret := "test-secret"
	body := []byte(`{"id":1}`)
	if VerifyWebhookHMAC(secret, body, "bad") {
		t.Fatal("tampered should fail")
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(body)
	header := base64.StdEncoding.EncodeToString(mac.Sum(nil))
	if !VerifyWebhookHMAC(secret, body, header) {
		t.Fatal("valid hmac should pass")
	}
	if VerifyWebhookHMAC("", body, "x") {
		t.Fatal("empty secret should fail")
	}
}
