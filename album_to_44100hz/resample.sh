#!/usr/bin/env bash
set -e

TARGET_DIR="${1:-.}"
cd "$TARGET_DIR"

if ! command -v ffmpeg &> /dev/null; then
    echo "Error: ffmpeg not found."
    exit 1
fi

FLAC_FILES=(*.flac)
if [ ! -e "${FLAC_FILES[0]}" ]; then
    echo "Error: No .flac files found in $TARGET_DIR"
    exit 1
fi

OUT_DIR="44100hz"
mkdir -p "$OUT_DIR"

echo "[>] Resampling FLACs to 44100Hz (Original Bit Depth) using SoX Resampler..."

for f in "${FLAC_FILES[@]}"; do
    echo "Processing: $f"
    ffmpeg -hide_banner -loglevel error -i "$f" -af "aresample=44100:resampler=soxr" "$OUT_DIR/$f"
done

echo "[+] Resampling complete. Files located in $OUT_DIR/"
