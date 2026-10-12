#!/usr/bin/env bash
# Deploy _user_profiles stack using AWS profile from .env (default concrete).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -f .env ]]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

export AWS_PROFILE="${AWS_PROFILE:-concrete}"
REGION="${AWS_REGION:-us-east-1}"
PREFIX="${_USER_PROFILES_PREFIX:-_user_profiles}"
STACK_NAME="${_USER_PROFILES_STACK_NAME:-user-profiles-stack}"
ARTIFACT_BUCKET="${_USER_PROFILES_ARTIFACT_BUCKET:-}"

if [[ -z "$ARTIFACT_BUCKET" ]]; then
  echo "Set _USER_PROFILES_ARTIFACT_BUCKET in .env (S3 bucket for Lambda zip)."
  exit 1
fi

bash "$ROOT/scripts/_user_profiles_build_lambda.sh"
ZIP="$ROOT/.build/_user_profiles_worker.zip"
S3_KEY="${PREFIX}_worker.zip"

aws s3 cp "$ZIP" "s3://${ARTIFACT_BUCKET}/${S3_KEY}" --region "$REGION"

aws cloudformation deploy \
  --stack-name "$STACK_NAME" \
  --template-file "$ROOT/infra/_user_profiles_stack.yaml" \
  --parameter-overrides \
    ProjectPrefix="$PREFIX" \
    AwsRegion="$REGION" \
    LambdaS3Bucket="$ARTIFACT_BUCKET" \
    LambdaS3Key="$S3_KEY" \
  --capabilities CAPABILITY_NAMED_IAM \
  --region "$REGION"

QUEUE_URL="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserProfilesJobsQueueUrl'].OutputValue" \
  --output text)"

FUNCTION_NAME="$(aws cloudformation describe-stacks \
  --stack-name "$STACK_NAME" \
  --region "$REGION" \
  --query "Stacks[0].Outputs[?OutputKey=='UserProfilesWorkerFunctionName'].OutputValue" \
  --output text)"

echo "Updating Lambda environment from .env ..."

ENV_JSON="$(ROOT="$ROOT" python3 "$ROOT/scripts/_user_profiles_lambda_env.py")"

aws lambda update-function-configuration \
  --function-name "$FUNCTION_NAME" \
  --region "$REGION" \
  --environment "$ENV_JSON" \
  >/dev/null

echo ""
echo "Deploy complete."
echo "Add/update in .env:"
echo "_USER_PROFILES_OFFLOAD=true"
echo "_USER_PROFILES_JOBS_QUEUE_URL=$QUEUE_URL"
echo "_USER_PROFILES_WORKER_FUNCTION_NAME=$FUNCTION_NAME"
echo "STORAGE_BACKEND=dynamodb"
echo "DYNAMODB_ENDPOINT="
echo "DYNAMODB_USERS_TABLE=${PREFIX}_users"
echo "DYNAMODB_AGENCIES_TABLE=${PREFIX}_agencies"
