#!/usr/bin/env bash
# CLIP ViT-B/32 text encoder (ONNX). Only needed to add new kinds of items to recognition.
set -euo pipefail
cd "$(dirname "$0")/.."
curl -fL -o models/clip_textual.onnx \
  https://clip-as-service.s3.us-east-2.amazonaws.com/models-436c69702d61732d53657276696365/onnx/ViT-B-32/textual.onnx
echo "done: models/clip_textual.onnx"
