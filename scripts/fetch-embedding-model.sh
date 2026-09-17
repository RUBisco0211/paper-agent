#!/usr/bin/env bash
# 直接从 hf-mirror 下载 bge-m3 的 dense 权重（不拉 onnx / colbert / sparse）。
# 关键：绕过宿主机代理——curl 会继承 https_proxy，而该代理对大文件不稳定。
set -euo pipefail

BASE="https://hf-mirror.com/BAAI/bge-m3/resolve/main"
OUT="models/bge-m3"
export NO_PROXY="hf-mirror.com"
export no_proxy="hf-mirror.com"

FILES=(
  config.json
  config_sentence_transformers.json
  modules.json
  sentence_bert_config.json
  1_Pooling/config.json
  tokenizer.json
  tokenizer_config.json
  special_tokens_map.json
  sentencepiece.bpe.model
  pytorch_model.bin
)

for f in "${FILES[@]}"; do
  mkdir -p "$OUT/$(dirname "$f")"
  if [[ "$f" != "pytorch_model.bin" && -s "$OUT/$f" ]]; then
    echo "--- $f (已存在，跳过)"
    continue
  fi
  echo "--- $f"
  curl -fL --noproxy '*' --retry 5 --retry-delay 3 -C - \
    -o "$OUT/$f" "$BASE/$f" -s \
    -w "    %{size_download} 字节 @ %{speed_download} B/s\n"
done

echo "=== 完成 ==="
du -sh "$OUT"
ls -la "$OUT"
