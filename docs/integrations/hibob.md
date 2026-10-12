# HiBob integration

## Purpose

Match the signed-in user to an employee record in Bob (HiBob) using work email.

## Authentication

Server-side **service user** (Basic auth: `ID:token`).

Docs:

- [API Service users](https://apidocs.hibob.com/docs/api-service-users.md)
- [Read employee data](https://apidocs.hibob.com/docs/how-to-read-employee-data.md)

## Configuration

```env
HIBOB_SERVICE_USER_ID=...
HIBOB_SERVICE_USER_TOKEN=...
HIBOB_API_BASE=https://api.hibob.com/v1
```

If either credential is empty, enrichment sets `hibob.status = not_configured` and continues.

## API call

Code: `app/services/hibob.py`

- `POST /v1/people/search`
- Filter: `root.email` equals user email
- Fields: name, email, title, department, site, start date, reports-to

Response is normalized to `hibob.normalized` for rollups and LLM context.

## Permissions

The service user needs People search permissions on categories such as **root**, **about**, **employment**, and **work**. Missing field permissions silently omit fields (HTTP 200 with partial data).

## Agency rollups

HiBob department/title fields feed `agency.inferred.top_departments` and `top_titles` when members have HiBob data.

## Related

- [Configuration](../configuration.md)
- [Data model](../data-model-and-storage.md)
