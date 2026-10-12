# Google Calendar (user OAuth)

User-delegated **read-only** Calendar access — no Workspace admin required.

## Purpose

Build a **meeting co-attendance graph** (who someone meets often, internal vs external domains) to support:

- MTP **network associations** with **closeness scores (1–100)**
- Auto-discovery of **same-domain colleagues** as provisional users
- **Work profile** / segment hints (external creative agencies vs same-domain leadership time)

We do **not** store event titles, descriptions, or locations — only **aggregates** per attendee email.

## GCP setup

1. Enable **Google Calendar API** in the same project as your OAuth client.
2. OAuth scope (included in default `GOOGLE_OAUTH_SCOPES`):

   `https://www.googleapis.com/auth/calendar.readonly`

3. Users must **Re-link Google** after scope change (`/auth/google/relink`).

## Configuration

| Variable | Default | Meaning |
|----------|---------|---------|
| `GOOGLE_CALENDAR_ENABLED` | `true` | Toggle calendar enrichment |
| `GOOGLE_CALENDAR_LOOKBACK_DAYS` | `90` | Past window for events |
| `GOOGLE_CALENDAR_MAX_EVENTS` | `400` | Cap events scanned per refresh |
| `GOOGLE_CALENDAR_MAX_CALENDARS` | `5` | Calendars read from calendar list |
| `GOOGLE_CALENDAR_TOP_ATTENDEES` | `20` | Top partners shown on profile |
| `CALENDAR_NETWORK_ENABLED` | `true` | Resolve attendees → associations |
| `CALENDAR_NETWORK_CREATE_PROVISIONAL` | `true` | Create same-domain unknown attendees |
| `CALENDAR_NETWORK_MAX_ATTENDEES_FOR_NETWORK` | `500` | Cap attendees processed for network |
| `CALENDAR_NETWORK_MAX_NEW_PROVISIONALS_PER_SYNC` | `25` | Safety valve per refresh |

## Network sync rules

After calendar aggregates load, `sync_calendar_network()`:

| Attendee | In DB? | Action |
|----------|--------|--------|
| Any domain | Yes | Bidirectional edge + closeness score |
| Same domain as logged-in user | No | Create **provisional** user, edge, enqueue enrich |
| External domain | No | Skip (no create, no edge) |

**Closeness score:** `round(100 * meeting_count / max_count)` among linked attendees in the lookback window (clamped 1–100).

**Provisional users** use `user_id = prov_<sha256(email)[:24]>`, `account_kind=provisional`. When they later sign in with Google, the provisional record is **merged** into the Google `sub` and association refs are rewritten.

## Stored shape

Under `user.google.calendar`:

```json
{
  "status": "ok",
  "window": { "start": "...", "end": "...", "lookback_days": 90 },
  "normalized": {
    "top_attendees": [ { "email": "...", "meeting_count": 12, "mtp_user_id": "..." } ],
    "all_attendees": [ "..." ],
    "mtp_connection_edges": [],
    "top_attendee_domains": [["agency.com", 40]]
  }
}
```

Under `user.network_associations`:

```json
{
  "updated_at": "...",
  "window_days": 90,
  "edges": [
    {
      "other_user_id": "...",
      "email": "...",
      "closeness_score": 87,
      "meeting_count": 12,
      "other_account_kind": "member",
      "source": "calendar"
    }
  ]
}
```

## Code

- `app/services/google_calendar_enrichment.py` — fetch + aggregate
- `app/services/calendar_network_sync.py` — associations + provisional create
- `app/services/provisional_user.py` — create / merge on Google login

## Related

- [Google (OAuth + People API)](./google.md)
- [Work profile](../work-profile.md)
- [Data model](../data-model-and-storage.md)
