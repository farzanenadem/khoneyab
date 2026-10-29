#!/bin/bash
set -euo pipefail

IMAGE_NAME="jobyab-api"
VERSION=$(awk -F'"' '/^version[[:space:]]*/{print $2}' pyproject.toml)

echo "Building ${IMAGE_NAME}:${VERSION}"

docker build -t "${IMAGE_NAME}:${VERSION}" -t "${IMAGE_NAME}:latest" -f Dockerfile .
docker build -t "jobyab-web:${VERSION}" -t "jobyab-web:latest" ui/web
