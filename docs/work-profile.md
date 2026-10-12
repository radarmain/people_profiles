# Work profile (role & workflow routing)

## North star

Users signing in are expected to be from the **Meet The People** network of agencies. The product goal is not a generic CRM blurb — it is a **deep, evidence-backed picture of what someone does in their job** so downstream MTP platforms can offer the right **workflows** (creative brief review, reporting, trafficking, leadership tools, etc.).

The machine-readable artifact is `user.work_profile` (JSON). The markdown `user.llm_summary` is a human-readable **role & work brief** aligned with the same inference.

## Structured fields

| Field | Purpose |
|-------|---------|
| `primary_role_label` | Best title in plain language (e.g. Creative Director) |
| `function` | `creative`, `data_analytics`, `technology_engineering`, `account_client`, … |
| `seniority` | `director`, `manager`, `senior_ic`, … |
| `agency_orientation` | Creative vs analytics vs full-service shop (when inferable) |
| `work_focus_phrases` | Short phrases for day-to-day work |
| `suggested_workflows` | Stable IDs for routing (see `work_profile_taxonomy.py`) |
| `confidence` / `evidence_gaps` | Honest limits for product UX |

Taxonomy constants live in `app/services/work_profile_taxonomy.py`. Extend `SuggestedWorkflow` as real platform workflow IDs are defined.

## Signals (priority)

1. **Slack** — profile title, public channels and topics (operating footprint)
2. **HiBob** — HR title and department (when configured)
3. **Google People** — organizations / current role
4. **LinkedIn lookup** — matched title and snippet summary
5. **Bedrock Knowledge Base** — internal docs mentioning the person or agency
6. **Calendar network** — who they meet most (closeness scores; same-domain provisional discovery)
7. **Agency domain** — shop type hints (e.g. analytics vs creative)

See [Google Calendar](./integrations/google-calendar.md) for association and provisional lifecycle.

## When it runs

On **Analyze role & generate summaries** (`POST /profile/summary`):

1. Refresh enrichment (same as before)
2. **`persist_work_profile()`** — Bedrock JSON (heuristic fallback if Bedrock fails)
3. User LLM brief (prompt includes `work_profile`)
4. Agency enrichment + agency summary

Lambda worker uses the same `job_runner.run_summarize_job` path.

### Admin: any user (including provisional)

On admin user detail, **Generate work profile** (`POST /admin/users/{id}/work-profile`) runs
`run_work_profile_job` **inline**:

1. Refresh available signals (provisionals: LinkedIn / HiBob / KB only — no Google/Slack)
2. Infer `work_profile` using titles + LinkedIn + **meeting-network peer closeness**
3. Write role brief (`llm_summary`)

Sparse / provisional profiles are expected to have **lower confidence**; that is intentional.

## API

`GET /api/me` returns `work_profile` on the user object (OAuth tokens still redacted).

## Next steps (product)

- Map `suggested_workflows` to real entitlements in each MTP product
- Add optional user confirmation (“Is this your role?”) to boost confidence
- Enrich with MTP-internal tools (CRM, project systems) under `user.internal`
- Agency-level rollups: % creative vs data vs leadership for account planning
