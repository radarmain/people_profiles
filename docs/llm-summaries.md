# LLM summaries

Implementation: `app/services/llm.py` (`SummaryService`).

## Models & AWS

- Uses **Bedrock Runtime Converse** via `bedrock_runtime_client()` → region **`AWS_REGION`**, profile **`AWS_PROFILE`**
- Model ID: `BEDROCK_MODEL_ID` (default `amazon.nova-lite-v1:0`)
- LinkedIn disambiguation can override with `LINKEDIN_LOOKUP_MODEL_ID` (empty = same as Bedrock model)

If Converse fails and `LLM_FALLBACK_WITHOUT_BEDROCK=true`, deterministic markdown templates are used instead.

## User summary

**Input:** `build_llm_context(user, agency)` — identity, Google, Slack, HiBob, KB, LinkedIn, agency snapshot (no OAuth secrets).

**Prompt sections requested:**

- Who they are  
- Role & seniority signals  
- Slack footprint  
- Google / identity signals  
- LinkedIn (automated match)  
- Internal knowledge base findings  
- Agency context  
- Gaps & recommended follow-ups  

**Output:** Stored in `user.llm_summary` with `llm_summary_generated_at`.

## Agency summary

**Input:** `build_agency_llm_context(store, agency)` — all members’ titles, Slack workspace, LinkedIn/KB snippets, user summary excerpts, agency KB, rollups.

**Prompt sections:**

- Company overview  
- Team composition  
- Slack & operating signals  
- Knowledge base intelligence  
- Relationship summary  
- Gaps & recommended account research  

**Output:** Stored in `agency.llm_summary`.

## Trigger

Profile UI: **Generate user & agency summaries** → `POST /profile/summary`.

Always runs a full user refresh first so summaries see fresh enrichment.

## Related

- [Enrichment pipeline](./enrichment-pipeline.md)
- [Bedrock Knowledge Base](./integrations/bedrock-knowledge-base.md)
