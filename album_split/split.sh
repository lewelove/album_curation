#!/usr/bin/env bash
set -e

IMAGE_FILE=""
CUE_FILE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        -i|--image)
            IMAGE_FILE="$2"
            shift 2
            ;;
        -c|--cue)
            CUE_FILE="$2"
            shift 2
            ;;
        *)
            echo "Error: Unknown argument '$1'"
            exit 1
            ;;
    esac
done

if [ -z "$IMAGE_FILE" ]; then
    shopt -s nullglob nocaseglob
    AUDIO_FILES=(*.flac *.ape)
    shopt -u nullglob nocaseglob
    if [ ${#AUDIO_FILES[@]} -eq 1 ]; then
        IMAGE_FILE="${AUDIO_FILES[0]}"
    elif [ ${#AUDIO_FILES[@]} -eq 0 ]; then
        echo "Error: No .flac or .ape file found in current directory. Please specify one using -i or --image."
        exit 1
    else
        echo "Error: Multiple audio files found (${#AUDIO_FILES[@]}). Please specify one using -i or --image."
        exit 1
    fi
fi

if [ ! -f "$IMAGE_FILE" ]; then
    echo "Error: Image file '$IMAGE_FILE' does not exist."
    exit 1
fi

if [ -z "$CUE_FILE" ]; then
    shopt -s nullglob nocaseglob
    CUE_FILES=(*.cue)
    shopt -u nullglob nocaseglob
    if [ ${#CUE_FILES[@]} -eq 1 ]; then
        CUE_FILE="${CUE_FILES[0]}"
    elif [ ${#CUE_FILES[@]} -eq 0 ]; then
        echo "Error: No .cue file found in current directory. Please specify one using -c or --cue."
        exit 1
    else
        echo "Error: Multiple .cue files found (${#CUE_FILES[@]}). Please specify one using -c or --cue."
        exit 1
    fi
fi

if [ ! -f "$CUE_FILE" ]; then
    echo "Error: Cue file '$CUE_FILE' does not exist."
    exit 1
fi

echo "Splitting $IMAGE_FILE using $CUE_FILE..."

shnsplit -f "$CUE_FILE" -o flac -t "%n - %t" "$IMAGE_FILE"

echo "Applying tags from CUE sheet..."

cuetag.sh "$CUE_FILE" 0[1-9]*.flac [1-9][0-9]*.flac

if [ -f "00 - pregap.flac" ]; then
    echo ""
    echo "NOTE: '00 - pregap.flac' was created because the CUE defines an offset for Track 1."
    echo "To ensure 'discid' (TOC hash) matches perfectly, move '00 - pregap.flac' out"
    echo "of this folder before running the ID tool."
fi

echo "Split complete."
