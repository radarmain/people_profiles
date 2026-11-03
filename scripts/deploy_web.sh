#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

: "${AWS_PROFILE:=concrete}"
: "${AWS_REGION:=us-east-1}"
: "${ECR_REPOSITORY:=generated-profiles}"
: "${WEB_STACK_NAME:=generated-profiles-web}"
: "${WEB_SECRET_ARN:?Set WEB_SECRET_ARN to the Secrets Manager JSON secret}"
: "${WEB_CERTIFICATE_ARN:?Set WEB_CERTIFICATE_ARN to an issued ACM certificate for people.intelligence-platform.ai}"
: "${WEB_VPC_ID:?Set WEB_VPC_ID to the target VPC}"
: "${WEB_PUBLIC_SUBNETS:?Set WEB_PUBLIC_SUBNETS to comma-separated public subnet IDs}"
: "${ALLOWED_EMAILS:?Set ALLOWED_EMAILS to comma-separated permitted Google emails}"

ACCOUNT_ID="$(aws sts get-caller-identity --query Account --output text --profile "$AWS_PROFILE")"
REGISTRY="$ACCOUNT_ID.dkr.ecr.$AWS_REGION.amazonaws.com"
IMAGE_URI="$REGISTRY/$ECR_REPOSITORY:$(git rev-parse --short HEAD)"

aws ecr describe-repositories --repository-names "$ECR_REPOSITORY" \
  --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null 2>&1 || \
  aws ecr create-repository --repository-name "$ECR_REPOSITORY" \
    --image-scanning-configuration scanOnPush \
    --profile "$AWS_PROFILE" --region "$AWS_REGION" >/dev/null

aws ecr get-login-password --profile "$AWS_PROFILE" --region "$AWS_REGION" |
  docker login --username AWS --password-stdin "$REGISTRY"
docker build -t "$IMAGE_URI" .
docker push "$IMAGE_URI"

QUEUE_URL="$(aws cloudformation describe-stacks \
  --stack-name user-profiles-stack --query "Stacks[0].Outputs[?OutputKey=='UserProfilesJobsQueueUrl'].OutputValue" \
  --output text --profile "$AWS_PROFILE" --region "$AWS_REGION")"

aws cloudformation deploy \
  --stack-name "$WEB_STACK_NAME" \
  --template-file infra/_user_profiles_web_stack.yaml \
  --parameter-overrides \
    ImageUri="$IMAGE_URI" \
    CertificateArn="$WEB_CERTIFICATE_ARN" \
    SecretArn="$WEB_SECRET_ARN" \
    VpcId="$WEB_VPC_ID" \
    PublicSubnets="$WEB_PUBLIC_SUBNETS" \
    JobsQueueUrl="$QUEUE_URL" \
    AllowedEmails="$ALLOWED_EMAILS" \
  --capabilities CAPABILITY_NAMED_IAM \
  --profile "$AWS_PROFILE" --region "$AWS_REGION"

aws cloudformation describe-stacks --stack-name "$WEB_STACK_NAME" \
  --query "Stacks[0].Outputs" --output table \
  --profile "$AWS_PROFILE" --region "$AWS_REGION"
