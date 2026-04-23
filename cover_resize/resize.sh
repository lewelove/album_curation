#!/usr/bin/env bash

set +H
set -f

if ! command -v magick &> /dev/null; then
    echo "Error: ImageMagick (magick) not found."
    exit 1
fi

MONOCHROME=false
FILTER="Mitchell"
INPUT_ARG=""

for arg in "$@"; do
    case $arg in
        --monochrome|--mono)
            MONOCHROME=true
            ;;
        --mitchell)
            FILTER="Mitchell"
            ;;
        --lanczos)
            FILTER="Lanczos"
            ;;
        --spline)
            FILTER="Spline"
            ;;
        --catrom)
            FILTER="Catrom"
            ;;
        --robidoux)
            FILTER="Robidoux"
            ;;
        --quadratic)
            FILTER="Quadratic"
            ;;
        *)
            INPUT_ARG="$arg"
            ;;
    esac
done

if [ -z "$INPUT_ARG" ]; then
    echo "Usage: $0 [--monochrome] [--mitchell|--lanczos|--spline|--catrom|--robidoux|--quadratic] <image_file>"
    exit 1
fi

if [[ "$INPUT_ARG" == *.psd ]]; then
    PSD_PNG="${INPUT_ARG}.png"
    echo "[>] PSD detected, extracting composite to $PSD_PNG..."
    magick "$INPUT_ARG[0]" "$PSD_PNG"
    INPUT_ARG="$PSD_PNG"
fi

INPUT_PATH=$(realpath -- "$INPUT_ARG")
if [ ! -f "$INPUT_PATH" ]; then
    echo "Error: File not found: $INPUT_PATH"
    exit 1
fi

DIR=$(dirname -- "$INPUT_PATH")
FILE_PATH=$(basename -- "$INPUT_PATH")
OUT_DIR="${DIR}"
mkdir -p "$OUT_DIR"

MONO_SUFFIX=""
[ "$MONOCHROME" = true ] && MONO_SUFFIX="+mono"

DIMENSIONS=$(magick identify -format "%w %h" "$INPUT_PATH" 2>/dev/null)
ORIG_W=$(echo "$DIMENSIONS" | cut -d' ' -f1)
ORIG_H=$(echo "$DIMENSIONS" | cut -d' ' -f2)

if [ "$ORIG_W" -ne "$ORIG_H" ]; then
    echo "[!] Image is not square ($ORIG_W x $ORIG_H), exiting..."
    exit 1
fi

PRE_MONO=()
POST_MONO=()
if [ "$MONOCHROME" = true ]; then
    PRE_MONO=(-colorspace Oklab -channel 1,2 -evaluate set 50% +channel)
    POST_MONO=(-colorspace Oklab -channel 1,2 -evaluate set 50% +channel)
fi

process_size() {
    local TARGET_SIZE="$1"
    local FILTER_LOWER
    FILTER_LOWER=$(echo "$FILTER" | tr '[:upper:]' '[:lower:]')

    if [ "$ORIG_W" -eq "$TARGET_SIZE" ]; then
        if [ "$MONOCHROME" = false ]; then
            local FILENAME="${FILE_PATH}+none+${TARGET_SIZE}.png"
            local OUT_PATH="${OUT_DIR}/${FILENAME}"
            cp "$INPUT_PATH" "$OUT_PATH"
            echo "[~] > [${TARGET_SIZE}] $FILENAME [Resampling Skipped]"
        else
            local FILENAME="${FILE_PATH}${MONO_SUFFIX}+none+${TARGET_SIZE}.png"
            local OUT_PATH="${OUT_DIR}/${FILENAME}"
            magick "$INPUT_PATH" "${PRE_MONO[@]}" -colorspace sRGB -strip "$OUT_PATH"
            echo "[*] > [${TARGET_SIZE}] $FILENAME [Resampling Skipped]"
        fi
        return
    fi

    local INTERNAL_CS="RGB"
    [ "$TARGET_SIZE" -gt "$ORIG_W" ] && INTERNAL_CS="Oklab"

    local FILENAME="${FILE_PATH}${MONO_SUFFIX}+${FILTER_LOWER}+${TARGET_SIZE}.png"
    local OUT_PATH="${OUT_DIR}/${FILENAME}"

    magick "$INPUT_PATH" \
        "${PRE_MONO[@]}" \
        -colorspace "$INTERNAL_CS" \
        -filter "$FILTER" \
        -distort Resize "${TARGET_SIZE}x${TARGET_SIZE}" \
        "${POST_MONO[@]}" \
        -colorspace sRGB \
        -strip \
        "$OUT_PATH"

    if [ "$TARGET_SIZE" -gt "$ORIG_W" ]; then
        echo "[+] > [${TARGET_SIZE}] $FILENAME [Upscaled]"
    else
        echo "[-] > [${TARGET_SIZE}] $FILENAME [Downscaled]"
    fi
}

MODE_STR="Color"
[ "$MONOCHROME" = true ] && MODE_STR="Monochrome"

echo "[>] Starting Resampling for: $INPUT_ARG [${ORIG_W}x${ORIG_H}px] [$MODE_STR] [Filter: $FILTER]"

process_size 1080
# process_size 1440
# process_size 2160
