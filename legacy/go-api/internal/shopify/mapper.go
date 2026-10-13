package shopify

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
)

type ProductInput struct {
	InternalReference string
	Category          *string
	StructuredData    map[string]any
	SEO               map[string]any
	Translations      map[string]any
	Variants          []VariantInput
	ShopifyProductID  *string
}

type VariantInput struct {
	SKU             string
	Color           *string
	Size            *string
	ColorNormalized *string
}

type Payload struct {
	Title       string           `json:"title"`
	BodyHTML    string           `json:"body_html"`
	Vendor      string           `json:"vendor"`
	ProductType string           `json:"product_type"`
	Status      string           `json:"status"`
	Tags        []string         `json:"tags"`
	Variants    []PayloadVariant `json:"variants"`
	Metafields  []Metafield      `json:"metafields"`
	Handle      string           `json:"handle,omitempty"`
	ID          string           `json:"id,omitempty"`
}

type PayloadVariant struct {
	SKU     string `json:"sku"`
	Option1 string `json:"option1,omitempty"`
	Option2 string `json:"option2,omitempty"`
}

type Metafield struct {
	Namespace string `json:"namespace"`
	Key       string `json:"key"`
	Value     string `json:"value"`
	Type      string `json:"type"`
}

func mapProductToShopifyPayload(in ProductInput) Payload {
	title := in.InternalReference
	if seoTitle, ok := in.SEO["title"].(string); ok && seoTitle != "" {
		title = seoTitle
	}
	body := ""
	if desc, ok := in.SEO["meta_description"].(string); ok {
		body = desc
	}
	productType := ""
	if in.Category != nil {
		productType = *in.Category
	}
	if cat, ok := in.StructuredData["category"].(string); ok && productType == "" {
		productType = cat
	}
	variants := make([]PayloadVariant, 0, len(in.Variants))
	for _, v := range in.Variants {
		pv := PayloadVariant{SKU: v.SKU}
		if v.Color != nil {
			pv.Option1 = *v.Color
		}
		if v.Size != nil {
			pv.Option2 = *v.Size
		}
		variants = append(variants, pv)
	}
	metafields := []Metafield{}
	if raw, err := json.Marshal(in.StructuredData); err == nil {
		metafields = append(metafields, Metafield{
			Namespace: "kitframe",
			Key:       "structured_data",
			Value:     string(raw),
			Type:      "json",
		})
	}
	if raw, err := json.Marshal(in.Translations); err == nil && string(raw) != "null" {
		metafields = append(metafields, Metafield{
			Namespace: "kitframe",
			Key:       "translations",
			Value:     string(raw),
			Type:      "json",
		})
	}
	p := Payload{
		Title:       title,
		BodyHTML:    body,
		Vendor:      "Kitframe",
		ProductType: productType,
		Status:      "active",
		Tags:        []string{"kitframe"},
		Variants:    variants,
		Metafields:  metafields,
	}
	if in.ShopifyProductID != nil {
		p.ID = *in.ShopifyProductID
	}
	return p
}

func MapProductToShopifyPayload(in ProductInput) Payload {
	return mapProductToShopifyPayload(in)
}

func VerifyWebhookHMAC(secret string, body []byte, header string) bool {
	if secret == "" || header == "" {
		return false
	}
	mac := hmac.New(sha256.New, []byte(secret))
	_, _ = mac.Write(body)
	expected := base64.StdEncoding.EncodeToString(mac.Sum(nil))
	return hmac.Equal([]byte(expected), []byte(header))
}
