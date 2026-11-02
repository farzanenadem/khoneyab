#!/bin/bash
set -euo pipefail

IMAGE_NAME="khoneyab-api"
VERSION=$(awk -F'"' '/^version[[:space:]]*/{print $2}' pyproject.toml)

echo "Building ${IMAGE_NAME}:${VERSION}"

docker build -t "${IMAGE_NAME}:${VERSION}" -t "${IMAGE_NAME}:latest" -f Dockerfile .
docker build -t "khoneyab-web:${VERSION}" -t "khoneyab-web:latest" ui/web
