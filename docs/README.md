# MTPI User Profiles — Documentation

Proof-of-concept application that signs users in with Google, enriches individual and agency profiles from multiple sources, and generates LLM summaries on AWS Bedrock.

## Start here

| Document | Description |
|----------|-------------|
| [Overview](./overview.md) | Goals, user journey, and scope |
| [Architecture](./architecture.md) | Components, data flow, and key modules |
| [Getting started](./getting-started.md) | Local install, run, and first login |
| [Configuration reference](./configuration.md) | All environment variables |

## Features

| Document | Description |
|----------|-------------|
| [Authentication & sessions](./authentication.md) | Google, Slack, tokens, re-link flows |
| [Data model & storage](./data-model-and-storage.md) | Users, agencies, local JSON vs DynamoDB |
| [Enrichment pipeline](./enrichment-pipeline.md) | What runs on refresh vs summary |
| [Work profile](./work-profile.md) | Role/function inference and workflow routing |
| [LLM summaries](./llm-summaries.md) | User and agency Bedrock prompts |

## Integrations

| Document | Description |
|----------|-------------|
| [Google (OAuth + People API)](./integrations/google.md) | Identity and extended profile |
| [Google Calendar](./integrations/google-calendar.md) | Meeting co-attendance (user OAuth) |
| [Slack](./integrations/slack.md) | User token, workspace, public channels |
| [HiBob](./integrations/hibob.md) | Service user and People search |
| [Bedrock Knowledge Base](./integrations/bedrock-knowledge-base.md) | Retrieve API, managed vs vector KB |
| [LinkedIn lookup](./integrations/linkedin-lookup.md) | Web search + LLM disambiguation |
| [Internal tools (stub)](./integrations/internal-tools.md) | Placeholder for your APIs |

## Operations

| Document | Description |
|----------|-------------|
| [HTTP routes & API](./api-routes.md) | Pages, auth callbacks, `/api/me` |
| [AWS & production notes](./aws-and-production-notes.md) | Profile `concrete`, regions, hardening |
| [Lambda offload](./aws-lambda-offload.md) | SQS + `_user_profiles_worker`, deploy script |

## Code map

```
app/
  main.py                 FastAPI app, session middleware, static files
  config.py               Settings from .env
  routers/                auth, pages, api
  models/domain.py        UserProfile, AgencyProfile
  services/               enrichment, LLM, integrations
  storage/                local JSON or DynamoDB
```

When changing behavior, update the relevant doc in this folder so the PoC stays explainable to the team.
