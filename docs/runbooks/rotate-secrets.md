# Rotate secrets

1. Generate new `JWT_SECRET` and `APP_ENCRYPTION_KEY`
2. Deploy new key id alongside Shopify token encryption (AES-GCM blob prefix)
3. Increment forces logout via `token_version` only when rotating JWT after compromise
4. Revoke refresh token families if JWT leaked
