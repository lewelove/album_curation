#!/usr/bin/env bash
set -e

TARGET_DIR="${1:-.}"
cd "$TARGET_DIR"

CUE_FILE=$(ls *.cue 2>/dev/null | head -n 1)
AUDIO_FILE=$(ls *.flac 2>/dev/null | head -n 1)

if [ -z "$CUE_FILE" ] || [ -z "$AUDIO_FILE" ]; then
    echo "Error: Could not find both a .cue and a .flac file in $TARGET_DIR"
    exit 1
fi

echo "Splitting $AUDIO_FILE using $CUE_FILE..."

shnsplit -f "$CUE_FILE" -o flac -t "%n - %t" "$AUDIO_FILE"

echo "Applying tags from CUE sheet..."

cuetag.sh "$CUE_FILE" 0[1-9]*.flac [1-9][0-9]*.flac

if [ -f "00 - pregap.flac" ]; then
    echo ""
    echo "NOTE: '00 - pregap.flac' was created because the CUE defines an offset for Track 1."
    echo "To ensure 'discid' (TOC hash) matches perfectly, move '00 - pregap.flac' out"
    echo "of this folder before running the ID tool."
fi

echo "Split complete."
