# Email Provider Integration — Gmail OAuth Design

## Purpose

Enable real email ingestion from Gmail so that inbound messages are processed
automatically rather than requiring manual simulation.

## Architecture

```
Gmail Account
    │
    OAuth2 consent flow
    │
    v
Refresh Token (stored securely)
    │
    Gmail API (google-auth + google-api-python-client)
    │
    Watch / Poll
    │
    v
New Email Event
    │
    Company Resolver (email domain → company)
    │
    v
InboundAgent → ResearchAgent → QualificationAgent → PipelineAgent
```

## Database Changes

Add to `app/db/models.py`:

### ConnectedEmailAccount

| Field | Type | Description |
|-------|------|-------------|
| id | UUID PK | |
| email_address | String(320) | The Gmail address connected |
| provider | String(50) | Always "gmail" |
| refresh_token | Text (encrypted) | OAuth2 refresh token |
| scopes | JSONB | Granted scopes |
| is_active | Boolean | Whether this account is being polled |
| last_sync_at | DateTime | Last successful sync |
| created_at | DateTime | |
| updated_at | DateTime | |

### EmailFilter

| Field | Type | Description |
|-------|------|-------------|
| id | UUID PK | |
| account_id | FK → ConnectedEmailAccount | |
| filter_type | String(20) | "include" or "exclude" |
| pattern | String(500) | Filter pattern (from, subject, etc.) |
| created_at | DateTime | |

## Environment Variables

```
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
GOOGLE_REDIRECT_URI=http://localhost:8000/api/v1/email/auth/callback
```

## API Endpoints

```
GET  /api/v1/email/auth          → Redirect to Google OAuth consent
GET  /api/v1/email/auth/callback  → OAuth2 callback, stores refresh token
POST /api/v1/email/sync          → Trigger manual sync for connected accounts
GET  /api/v1/email/filters       → List email filters
POST /api/v1/email/filters       → Create/update filter
```

## OAuth2 Flow

1. BDR clicks "Connect Gmail" → redirected to `GET /api/v1/email/auth`
2. App redirects to Google OAuth consent screen with scopes:
   - `https://www.googleapis.com/auth/gmail.readonly`
   - `https://www.googleapis.com/auth/gmail.metadata`
3. User consents → Google redirects to callback URL with auth code
4. Server exchanges auth code for refresh + access tokens
5. Refresh token is encrypted and stored in `ConnectedEmailAccount`
6. Initial sync is triggered automatically

## Prevention

- **Do NOT** store Gmail password anywhere
- **Encrypt** refresh_token at rest (Fernet or similar)
- **Scope limited** to read-only + metadata (cannot send or delete)
- **Filter** before processing to avoid spam/newsletters

## Filtering Strategy

The `EmailFilter` table stores rules. On sync:

1. Fetch recent email headers (from, subject, date)
2. Apply include/exclude filters
3. Skip emails matching exclude patterns:
   - `from: *@newsletter.*`
   - `subject: "unsubscribe"`
   - `from: *@marketing.*`
4. Only pass matching emails to InboundAgent for processing

## How to Implement

### Phase 1 — Auth

```python
# app/services/gmail_auth.py
from google_auth_oauthlib.flow import Flow

flow = Flow.from_client_secrets_file(
    "client_secret.json",
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
    redirect_uri=settings.google_redirect_uri,
)

# Generate auth URL
auth_url, state = flow.authorization_url(
    access_type="offline",
    include_granted_scopes="true",
    prompt="consent",
)
```

Store `state` in session to validate callback.

### Phase 2 — Sync

```python
# app/services/gmail_sync.py
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

creds = Credentials(
    token=None,
    refresh_token=account.refresh_token,
    token_uri="https://oauth2.googleapis.com/token",
    client_id=settings.google_client_id,
    client_secret=settings.google_client_secret,
)

service = build("gmail", "v1", credentials=creds)
results = service.users().messages().list(
    userId="me",
    maxResults=10,
).execute()
```

### Phase 3 — Processing

Pass `from_email`, `subject`, and `body` as `InboundRequest`:

```python
from app.api.router import process_inbound_message

result = await process_inbound_message(
    InboundRequest(
        from_email=msg["from"],
        from_name=msg["from_name"],
        subject=msg["subject"],
        body=msg["body"],
        channel="email",
    ),
    db,
)
```

## Security Considerations

- Refresh tokens should be encrypted with `cryptography.fernet`
- Never log raw email content
- Never log refresh tokens
- Rate-limit sync to avoid API quota issues
- Consider webhook-based push (Pub/Sub) instead of polling for production
