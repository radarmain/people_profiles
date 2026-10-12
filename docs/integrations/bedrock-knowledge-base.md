# Bedrock Knowledge Base

## Purpose

Retrieve internal document chunks about a **user** or **agency** to enrich profiles and LLM summaries.

Code: `app/services/bedrock_knowledge_base.py`

## API

- Client: `bedrock-agent-runtime`
- Operation: **`Retrieve`**
- Region: **`AWS_KB_REGION`** (not necessarily `AWS_REGION`)

## Search modes

| `BEDROCK_KB_SEARCH_MODE` | Retrieval config |
|--------------------------|------------------|
| `managed` | `managedSearchConfiguration` (Bedrock **Managed** KB) |
| `vector` | `vectorSearchConfiguration` (classic vector store KB) |
| `auto` | Try managed, then vector on incompatible configuration |

Managed KBs **reject** `vectorSearchConfiguration` with `ValidationException`.

## User queries

Built from profile signals, e.g.:

- Email address  
- Display name  
- Name + domain  
- Slack / HiBob title hints  
- `agency client {domain}`  

Multiple queries run; chunks are deduplicated by content hash and ranked by score.

## Agency queries

Run during agency summary preparation:

- Domain  
- `agency client {domain}`  
- Company display name variants  

Results stored on `AgencyProfile.knowledge_base`.

## Stored shape (user)

```json
{
  "status": "ok",
  "queries": [ ... ],
  "normalized": { "top_chunks": [ { "score", "text", "source_uri", "metadata" } ] },
  "errors": [ ... ],
  "search_mode": "managed",
  "region": "..."
}
```

## IAM

`bedrock:Retrieve` on the knowledge base ARN.

## Related

- [Configuration](../configuration.md)
- [LLM summaries](../llm-summaries.md)
- [AWS & production notes](../aws-and-production-notes.md)
