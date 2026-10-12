#!/usr/bin/env bash
# Build deployment zip for _user_profiles_worker Lambda.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BUILD="$ROOT/.build/_user_profiles_lambda"
ZIP="$ROOT/.build/_user_profiles_worker.zip"

rm -rf "$BUILD" "$ZIP"
mkdir -p "$BUILD"

# Lambda runs Linux x86_64 — install manylinux wheels (not macOS binaries).
python3 -m pip install -q "$ROOT" --target "$BUILD" \
  --platform manylinux2014_x86_64 \
  --python-version 3.12 \
  --implementation cp \
  --only-binary=:all: \
  --upgrade

cp -R "$ROOT/app" "$BUILD/app"
cp "$ROOT/lambda/_user_profiles_worker/handler.py" "$BUILD/handler.py"

(cd "$BUILD" && zip -rq "$ZIP" .)
echo "Built $ZIP"
