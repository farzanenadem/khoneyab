#!/bin/bash
set -euo pipefail

IMAGE_NAME="naji/llm"
VERSION=$(awk -F'"' '/^version[[:space:]]*/{print $2}' pyproject.toml)

echo "Building ${IMAGE_NAME}:${VERSION}"

docker build --network=host -t "${IMAGE_NAME}:${VERSION}" -f Dockerfile .
