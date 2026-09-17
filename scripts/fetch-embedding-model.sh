#!/usr/bin/env bash
#
# 预下载 Embedding 权重到 ./models，供 docker compose 以只读方式挂载。
#
#   ./scripts/fetch-embedding-model.sh                     # 默认 BAAI/bge-m3（dense 权重）
#   SOURCE=hf-mirror ./scripts/fetch-embedding-model.sh    # 换源
#   MODEL=BAAI/bge-large-en-v1.5 ./scripts/fetch-embedding-model.sh
#
# 为什么需要它：容器内下载需要能直连 HuggingFace；网络受限时（例如国内直连不通、
# 或镜像源缺少 etag 头导致 TEI 下载失败）只能在宿主机预下载再挂载。
#
# 实测结论（2026-09）：
#   * ModelScope 支持 Range 分片，10 连接并行可达 4~5MB/s —— 首选
#   * hf-mirror 的大文件走 Xet 重建，不支持 Range，单连接约 0.1~1.3MB/s —— 兜底
#   * 宿主机若配置了 HTTP 代理，必须绕过：代理在 GB 级传输上会中途卡死（--noproxy）
set -euo pipefail

MODEL="${MODEL:-BAAI/bge-m3}"
SOURCE="${SOURCE:-modelscope}"      # modelscope | hf-mirror
OUT="${OUT:-models/$(basename "$MODEL")}"
PARTS="${PARTS:-10}"
PARALLEL_THRESHOLD=$((100 * 1024 * 1024))

# dense 推理需要的文件（不含 onnx / colbert_linear.pt / sparse_linear.pt，省约 2GB）
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

case "$SOURCE" in
  modelscope) BASE="https://modelscope.cn/api/v1/models/${MODEL}/repo?Revision=master&FilePath=" ;;
  hf-mirror)  BASE="https://hf-mirror.com/${MODEL}/resolve/main/" ;;
  *) echo "未知 SOURCE：$SOURCE（可选 modelscope / hf-mirror）" >&2; exit 1 ;;
esac
HOST="$(echo "$BASE" | awk -F/ '{print $3}')"
export NO_PROXY="$HOST" no_proxy="$HOST"

file_url() {
  if [[ "$SOURCE" == "modelscope" ]]; then printf '%s%s' "$BASE" "$1"; else printf '%s%s' "$BASE" "$1"; fi
}

remote_size() {
  curl -sL --noproxy '*' -r 0-0 -D - -o /dev/null "$(file_url "$1")" \
    | awk 'BEGIN{IGNORECASE=1} /^content-range:/{n=split($0,a,"/"); gsub(/\r/,"",a[n]); print a[n]}' \
    | tail -1
}

download_parallel() {
  local rel="$1" size="$2" start total step from to i pids=() fail=0
  start=$( [[ -f "$OUT/$rel" ]] && stat -f%z "$OUT/$rel" || echo 0 )
  (( size <= start )) && { echo "    已完整（$start 字节）"; return 0; }

  total=$((size - start))
  step=$(( (total + PARTS - 1) / PARTS ))
  echo "    续传 $start → $size（$PARTS 个分片）"
  for i in $(seq 0 $((PARTS - 1))); do
    from=$((start + i * step)); to=$((from + step - 1))
    (( to >= size )) && to=$((size - 1))
    (( from > to )) && continue
    curl -fL --noproxy '*' --retry 8 --retry-delay 3 -r "$from-$to" \
      -o "$OUT/$rel.part$i" "$(file_url "$rel")" -s &
    pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p" || fail=1; done
  (( fail == 0 )) || { echo "    分片失败，可重跑续传" >&2; return 1; }

  # 拼接前逐片校验，避免服务端忽略 Range 造成错位
  for i in $(seq 0 $((PARTS - 1))); do
    from=$((start + i * step)); to=$((from + step - 1)); (( to >= size )) && to=$((size - 1))
    (( from > to )) && continue
    expect=$((to - from + 1)); actual=$(stat -f%z "$OUT/$rel.part$i")
    (( actual == expect )) || { echo "    分片 $i 大小不符（$actual != $expect），中止" >&2; return 1; }
  done
  for i in $(seq 0 $((PARTS - 1))); do
    [[ -f "$OUT/$rel.part$i" ]] || continue
    cat "$OUT/$rel.part$i" >> "$OUT/$rel"
    rm -f "$OUT/$rel.part$i"
  done
}

mkdir -p "$OUT"
echo "模型 $MODEL ← $SOURCE，输出 $OUT"
for rel in "${FILES[@]}"; do
  mkdir -p "$OUT/$(dirname "$rel")"
  if [[ "$rel" != "pytorch_model.bin" && -s "$OUT/$rel" ]]; then
    echo "--- $rel（已存在，跳过）"
    continue
  fi
  echo "--- $rel"
  size=$(remote_size "$rel")
  [[ "$size" =~ ^[0-9]+$ ]] || { echo "    拿不到大小，跳过" >&2; continue; }
  if (( size > PARALLEL_THRESHOLD )); then
    download_parallel "$rel" "$size"
  else
    curl -fL --noproxy '*' --retry 5 --retry-delay 3 -C - \
      -o "$OUT/$rel" "$(file_url "$rel")" -s \
      -w "    %{size_download} 字节 @ %{speed_download} B/s\n"
  fi
done

echo "=== 完成 ==="
du -sh "$OUT"
ls -la "$OUT"
