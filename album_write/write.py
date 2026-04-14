#!/usr/bin/env python
import os
import sys
import json
import base64
import mimetypes
import xxhash
from mutagen.flac import FLAC, Picture

def fmt(val):
    return val if val else "(empty)"

def get_hash(data):
    h = xxhash.xxh64(data).digest()
    return base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    target_dir = sys.argv[1]
    lock_file = os.path.join(target_dir, "metadata.lock.json")

    if not os.path.isfile(lock_file):
        sys.exit(1)

    with open(lock_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    album_data = data.get("album", {})
    album_info = album_data.get("info", {})
    album_tags = album_data.get("tags", {})
    tracks_data = data.get("tracks", [])

    if not tracks_data:
        sys.exit(0)

    total_discs = album_info.get("total_discs", 1)
    json_cover_hash = album_info.get("cover_hash")
    cover_filename = album_info.get("cover_path", "cover.png")
    cover_path = os.path.join(target_dir, cover_filename)

    disk_cover_data = None
    disk_cover_hash = None
    if os.path.exists(cover_path):
        with open(cover_path, "rb") as cf:
            disk_cover_data = cf.read()
        disk_cover_hash = get_hash(disk_cover_data)

    first_track_path = os.path.join(target_dir, tracks_data[0]["info"]["track_path"])
    first_audio = FLAC(first_track_path)
    embedded_cover_hash = None
    if first_audio.pictures:
        for pic in first_audio.pictures:
            if pic.type == 3:
                embedded_cover_hash = get_hash(pic.data)
                break

    update_cover = (disk_cover_hash is not None) and (embedded_cover_hash != disk_cover_hash)

    target_tags_per_track = []
    for t in tracks_data:
        tags = {}
        tags["ALBUM"] = str(album_data.get("ALBUM", ""))
        tags["ALBUMARTIST"] = str(album_data.get("ALBUMARTIST", ""))
        tags["DATE"] = str(album_data.get("DATE", ""))
        tags["COMMENT"] = str(album_data.get("COMMENT", ""))
        tags["GENRE"] = "; ".join(album_data.get("GENRE", []))
        
        if "DISCOGS_URL" in album_tags:
            tags["DISCOGS_URL"] = str(album_tags["DISCOGS_URL"])
        if "MUSICBRAINZ_URL" in album_tags:
            tags["MUSICBRAINZ_URL"] = str(album_tags["MUSICBRAINZ_URL"])
            
        tags["ARTIST"] = str(t.get("ARTIST", ""))
        tags["TITLE"] = str(t.get("TITLE", ""))
        tags["TRACKNUMBER"] = str(t.get("TRACKNUMBER", ""))
        
        if total_discs > 1:
            tags["DISCNUMBER"] = str(t.get("DISCNUMBER", "1"))
        else:
            tags["DISCNUMBER"] = None

        target_tags_per_track.append((t["info"]["track_path"], tags))

    all_diffs = []
    diff_counts = {}

    for rel_path, target_tags in target_tags_per_track:
        track_file = os.path.join(target_dir, rel_path)
        audio = FLAC(track_file)
        track_changes = []

        target_keys = {k for k, v in target_tags.items() if v is not None}

        for old_tag in audio.keys():
            if old_tag.upper() not in target_keys:
                old_val = audio[old_tag][0] if audio[old_tag] else ""
                track_changes.append((old_tag.upper(), old_val, "(delete)"))

        for tag, new_val in target_tags.items():
            if new_val is not None:
                old_val_list = audio.get(tag, [])
                old_val = old_val_list[0] if old_val_list else ""
                if old_val != new_val:
                    track_changes.append((tag, old_val, new_val))
        
        all_diffs.append({"path": rel_path, "changes": track_changes})
        for change in track_changes:
            diff_counts[change] = diff_counts.get(change, 0) + 1

    album_diffs = []
    for change, count in diff_counts.items():
        if count == len(tracks_data):
            album_diffs.append(change)

    track_diffs_output = []
    for track_diff in all_diffs:
        unique_changes = [c for c in track_diff["changes"] if c not in album_diffs]
        if unique_changes:
            track_diffs_output.append({"path": track_diff["path"], "changes": unique_changes})

    has_changes = update_cover or album_diffs or track_diffs_output

    if update_cover:
        print("COVER MISMATCH")
        print(f"Embedded: {fmt(embedded_cover_hash)} -> Folder: {fmt(disk_cover_hash)}")
        print(f"Action: Syncing {cover_filename} to all tracks\n")

    if album_diffs:
        print("ALBUM DIFF")
        for tag, old, new in album_diffs:
            print(f"{tag}: {fmt(old)} -> {fmt(new)}")
        print()

    if track_diffs_output:
        print("TRACK DIFF")
        for td in track_diffs_output:
            print(td["path"])
            for tag, old, new in td["changes"]:
                print(f"{tag}: {fmt(old)} -> {fmt(new)}")
            print()

    if not has_changes:
        print("No changes needed.")
        return

    ans = input("Proceed? y/n: ").strip().lower()
    if ans not in ('y', 'yes'):
        sys.exit(0)

    new_pic = None
    if update_cover:
        new_pic = Picture()
        new_pic.data = disk_cover_data
        new_pic.type = 3
        new_pic.mime = mimetypes.guess_type(cover_path)[0] or "image/jpeg"
        new_pic.desc = "Front Cover"

    for rel_path, target_tags in target_tags_per_track:
        track_file = os.path.join(target_dir, rel_path)
        audio = FLAC(track_file)
        
        target_keys = {k for k, v in target_tags.items() if v is not None}
        for old_tag in list(audio.keys()):
            if old_tag.upper() not in target_keys:
                del audio[old_tag]
        
        for tag, new_val in target_tags.items():
            if new_val is not None:
                audio[tag] = [new_val]
        
        if update_cover:
            audio.clear_pictures()
            audio.add_picture(new_pic)
            
        audio.save()

if __name__ == "__main__":
    main()
