import sys
import os
import argparse
import subprocess
from pathlib import Path
from mutagen.flac import FLAC

def parse_cue_time(time_str):
    parts = time_str.strip().split(':')
    if len(parts) != 3:
        return 0.0
    minutes = int(parts[0])
    seconds = int(parts[1])
    frames = int(parts[2])
    return minutes * 60.0 + seconds + (frames / 75.0)

def strip_quotes(val):
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        return val[1:-1]
    return val

def sanitize_filename(name):
    for ch in r'/\:*?"<>|':
        name = name.replace(ch, '_')
    return name

def read_cue_file(path):
    for enc in ("utf-8-sig", "utf-8", "cp1252", "gbk", "shift_jis", "latin1"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError:
            continue
    with open(path, "r", encoding="latin1") as f:
        return f.read()

def parse_cue(content):
    global_album = ""
    global_performer = ""
    global_date = ""
    global_genre = ""
    global_comment = ""

    tracks = []
    current_track = None

    for line in content.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split(maxsplit=1)
        cmd = parts[0].upper()
        arg = parts[1] if len(parts) > 1 else ""

        if cmd == "REM":
            rem_parts = arg.split(maxsplit=1)
            if len(rem_parts) == 2:
                rem_cmd = rem_parts[0].upper()
                rem_val = strip_quotes(rem_parts[1])
                if rem_cmd in ("DATE", "YEAR"):
                    global_date = rem_val
                elif rem_cmd == "GENRE":
                    global_genre = rem_val
                elif rem_cmd == "COMMENT":
                    global_comment = rem_val
        elif cmd == "PERFORMER":
            val = strip_quotes(arg)
            if current_track is None:
                global_performer = val
            else:
                current_track["artist"] = val
        elif cmd == "TITLE":
            val = strip_quotes(arg)
            if current_track is None:
                global_album = val
            else:
                current_track["title"] = val
        elif cmd == "TRACK":
            track_parts = arg.split()
            num = int(track_parts[0])
            current_track = {
                "number": num,
                "title": f"Track {num:02d}",
                "artist": None,
                "index_00": None,
                "index_01": None,
            }
            tracks.append(current_track)
        elif cmd == "INDEX" and current_track is not None:
            idx_parts = arg.split()
            if len(idx_parts) == 2:
                idx_num = idx_parts[0]
                idx_time = parse_cue_time(idx_parts[1])
                if idx_num == "00":
                    current_track["index_00"] = idx_time
                elif idx_num == "01":
                    current_track["index_01"] = idx_time

    return {
        "album": global_album,
        "performer": global_performer,
        "date": global_date,
        "genre": global_genre,
        "comment": global_comment,
        "tracks": tracks,
    }

def main():
    parser = argparse.ArgumentParser(description="Split audio image into FLAC tracks using CUE sheet")
    parser.add_argument("-i", "--image", help="Path to input audio file (.flac, .ape, or .wv)")
    parser.add_argument("-c", "--cue", help="Path to CUE sheet file (.cue)")
    args = parser.parse_args()

    pwd = Path.cwd()

    if not args.image:
        audio_files = [f for f in pwd.iterdir() if f.is_file() and f.suffix.lower() in ('.flac', '.ape', '.wv')]
        if len(audio_files) == 1:
            image_path = audio_files[0]
        elif len(audio_files) == 0:
            print("Error: No .flac, .ape, or .wv file found in current directory. Please specify one with -i or --image.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Error: Multiple audio files found ({len(audio_files)}). Please specify one with -i or --image.", file=sys.stderr)
            sys.exit(1)
    else:
        image_path = Path(args.image)
        if not image_path.is_file():
            print(f"Error: Image file '{image_path}' does not exist.", file=sys.stderr)
            sys.exit(1)

    if not args.cue:
        cue_files = [f for f in pwd.iterdir() if f.is_file() and f.suffix.lower() == '.cue']
        if len(cue_files) == 1:
            cue_path = cue_files[0]
        elif len(cue_files) == 0:
            print("Error: No .cue file found in current directory. Please specify one with -c or --cue.", file=sys.stderr)
            sys.exit(1)
        else:
            print(f"Error: Multiple .cue files found ({len(cue_files)}). Please specify one with -c or --cue.", file=sys.stderr)
            sys.exit(1)
    else:
        cue_path = Path(args.cue)
        if not cue_path.is_file():
            print(f"Error: Cue file '{cue_path}' does not exist.", file=sys.stderr)
            sys.exit(1)

    cue_content = read_cue_file(cue_path)
    cue_data = parse_cue(cue_content)

    tracks = cue_data["tracks"]
    if not tracks:
        print("Error: No audio tracks found in CUE sheet.", file=sys.stderr)
        sys.exit(1)

    print(f"Splitting {image_path.name} using {cue_path.name}...")

    pregap_created = False
    if tracks[0]["index_00"] is not None and tracks[0]["index_01"] is not None:
        if tracks[0]["index_00"] < tracks[0]["index_01"]:
            start_sec = tracks[0]["index_00"]
            end_sec = tracks[0]["index_01"]
            out_file = pwd / "00 - pregap.flac"
            cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(image_path), "-ss", f"{start_sec:.6f}", "-to", f"{end_sec:.6f}", "-c:a", "flac", str(out_file)]
            subprocess.run(cmd, check=True)
            pregap_created = True

    total_tracks = len(tracks)
    for i, track in enumerate(tracks):
        start_sec = track["index_01"]
        if start_sec is None:
            continue

        if i + 1 < total_tracks:
            end_sec = tracks[i + 1]["index_01"]
        else:
            end_sec = None

        track_num = track["number"]
        track_title = track["title"]
        track_artist = track["artist"] or cue_data["performer"]

        out_name = f"{track_num:02d} - {sanitize_filename(track_title)}.flac"
        out_file = pwd / out_name

        cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(image_path), "-ss", f"{start_sec:.6f}"]
        if end_sec is not None:
            cmd.extend(["-to", f"{end_sec:.6f}"])
        cmd.extend(["-c:a", "flac", str(out_file)])

        subprocess.run(cmd, check=True)

        audio = FLAC(str(out_file))
        if cue_data["performer"]:
            audio["ALBUMARTIST"] = cue_data["performer"]
        if cue_data["album"]:
            audio["ALBUM"] = cue_data["album"]
        if track_artist:
            audio["ARTIST"] = track_artist
        if track_title:
            audio["TITLE"] = track_title
        audio["TRACKNUMBER"] = str(track_num)
        audio["TRACKTOTAL"] = str(total_tracks)
        if cue_data["date"]:
            audio["DATE"] = cue_data["date"]
        if cue_data["genre"]:
            audio["GENRE"] = cue_data["genre"]
        if cue_data["comment"]:
            audio["COMMENT"] = cue_data["comment"]
        audio.save()

    if pregap_created:
        print("\nNOTE: '00 - pregap.flac' was created because the CUE defines an offset for Track 1.")
        print("To ensure 'discid' (TOC hash) matches perfectly, move '00 - pregap.flac' out")
        print("of this folder before running the ID tool.")

    print("Split complete.")

if __name__ == "__main__":
    main()
