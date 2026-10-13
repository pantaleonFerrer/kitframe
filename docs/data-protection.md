# Data protection (Kitframe)

Personal data processed:

- Users: email, name, password hash, locale, last login
- Rights records: subject names/aliases, clearance status, notes
- Model reference photos of real people (highest sensitivity)

Purpose: operate the merchandising content workflow for the brand tenant.

Legal basis: to be confirmed by the client (decision D8) before any `real_person` model set is used in production.

Retention: user accounts kept while membership is active; deactivated users retain audit history without login. Deleting a real-person model set deletes its photos from object storage; generation metadata is retained without the photos.

Processors (to be finalized with D1–D3, D6): hosting, object storage, image provider, LLM provider, transactional email.
