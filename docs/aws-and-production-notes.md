# AWS & production notes

## AWS profile `concrete`

Local development expects:

```bash
export AWS_PROFILE=concrete
```

Used for:

- Bedrock **Converse** (summaries, LinkedIn disambiguation) — `AWS_REGION`
- Bedrock **Knowledge Base Retrieve** — `AWS_KB_REGION` (can differ from `AWS_REGION`)
- DynamoDB (when not using local JSON)

## IAM (minimum PoC)

| Capability | Actions |
|------------|---------|
| Summaries | `bedrock:InvokeModel` on chosen foundation model |
| Knowledge Base | `bedrock:Retrieve` on the KB resource |
| DynamoDB | `GetItem`, `PutItem`, `Query` on profile tables |

Scope policies to resource ARNs, not `*`.

## Regions

- **`AWS_REGION`**: Bedrock runtime for Converse, DynamoDB default region  
- **`AWS_KB_REGION`**: Must match the region where the knowledge base was created  

List KBs:

```bash
AWS_PROFILE=concrete aws bedrock-agent list-knowledge-bases --region "$AWS_KB_REGION"
```

## Production hardening checklist

- [ ] Store OAuth tokens in **Secrets Manager** (or similar), not profile documents  
- [ ] HTTPS-only cookies (`https_only=True` on session middleware)  
- [ ] Hosted OAuth redirect URLs for production domain  
- [ ] Encrypt DynamoDB at rest; least-privilege IAM roles on compute  
- [ ] Rate-limit enrichment and summary endpoints  
- [ ] Audit logging for PII access  
- [ ] Replace DuckDuckGo with a contracted search API (Tavily, etc.)  

## Deployment

The web deployment is defined in [`infra/_user_profiles_web_stack.yaml`](../infra/_user_profiles_web_stack.yaml)
and can be run with [`scripts/deploy_web.sh`](../scripts/deploy_web.sh). It uses ECS Fargate
behind an HTTPS Application Load Balancer. Before running it, create:

- An issued ACM certificate for `people.intelligence-platform.ai`
- A JSON Secrets Manager secret containing the application credentials listed in the web stack
- Public subnets in the target VPC
- `ALLOWED_EMAILS` containing every permitted Google login address

After deployment, create a DNS `CNAME` for `people.intelligence-platform.ai` pointing to the
stack's `LoadBalancerDnsName` output. Google and Slack OAuth redirect URLs must use the production
base URL.

## Other deployment options

- **ECS/Fargate** or **App Runner** for the FastAPI container  
- **ALB** + TLS termination  
- **DynamoDB** tables in target account/region  
- Optional: **Cognito** federated with Google instead of direct Google OAuth  

## Related

- [Configuration](./configuration.md)
- [Bedrock Knowledge Base](./integrations/bedrock-knowledge-base.md)
