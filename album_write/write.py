#!/usr/bin/env python
import os
import sys
import json
import base64
import mimetypes
import xxhash
from mutagen.flac import FLAC, Picture

SYNC_TAGS =[
    "ALBUM",
    "ALBUMARTIST",
    "DATE",
    "GENRE",
    "COMMENT",
    "TITLE",
    "ARTIST",
    "DISCOGS_URL",
    "MUSICBRAINZ_URL",
    "REPLAYGAIN_TRACK_GAIN",
    "REPLAYGAIN_ALBUM_GAIN",
]

def fmt(val):
    return val if val else "(empty)"

def get_hash(data):
    h = xxhash.xxh64(data).digest()
    return base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

def process_album(target_dir):
    lock_file = os.path.join(target_dir, "metadata.lock.json")

    if not os.path.isfile(lock_file):
        return

    with open(lock_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    album_obj = data.get("album", {})
    album_info = album_obj.get("info", {})

    if album_info.get("file_tag_subset_match", False):
        return

    tracks_data = data.get("tracks",[])
    if not tracks_data:
        return

    album_pool = {k.upper(): v for k, v in album_obj.items() if k not in ["info", "tags"]}
    if "tags" in album_obj:
        album_pool.update({k.upper(): v for k, v in album_obj["tags"].items()})

    total_discs = album_info.get("total_discs", 1)
    total_tracks = album_info.get("total_tracks", 0)
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

    target_tags_per_track =[]
    for t in tracks_data:
        target_tags = {}
        track_pool = {k.upper(): v for k, v in t.items() if k not in ["info", "tags"]}
        if "tags" in t:
            track_pool.update({k.upper(): v for k, v in t["tags"].items()})

        for tag_name in SYNC_TAGS:
            val = track_pool.get(tag_name)
            if val is None:
                val = album_pool.get(tag_name)
            
            if val is not None:
                if tag_name == "GENRE" and isinstance(val, list):
                    target_tags[tag_name] = "; ".join(val)
                else:
                    target_tags[tag_name] = str(val)

        target_tags["ARTIST"] = str(track_pool.get("ARTIST", ""))
        target_tags["TITLE"] = str(track_pool.get("TITLE", ""))
        target_tags["TRACKNUMBER"] = str(track_pool.get("TRACKNUMBER", "0"))
        
        if total_discs > 1:
            target_tags["DISCNUMBER"] = str(track_pool.get("DISCNUMBER", "1"))
        
        target_tags_per_track.append((t["info"]["track_path"], target_tags))

    all_diffs =[]
    diff_counts = {}

    for rel_path, target_tags in target_tags_per_track:
        track_file = os.path.join(target_dir, rel_path)
        audio = FLAC(track_file)
        track_changes =[]
        target_keys = set(target_tags.keys())

        for old_tag in list(audio.keys()):
            u_old = old_tag.upper()
            if u_old not in target_keys:
                old_val = audio[old_tag][0] if audio[old_tag] else ""
                track_changes.append((u_old, old_val, "(delete)"))

        for tag, new_val in target_tags.items():
            old_vals = audio.get(tag, audio.get(tag.lower(),[]))
            old_val = old_vals[0] if old_vals else ""
            if str(old_val) != str(new_val):
                track_changes.append((tag, old_val, new_val))
        
        all_diffs.append({"path": rel_path, "changes": track_changes})
        for change in track_changes:
            diff_counts[change] = diff_counts.get(change, 0) + 1

    album_diffs =[ch for ch, count in diff_counts.items() if count == len(tracks_data)]
    
    track_diffs_output =[]
    for td in all_diffs:
        uniques = [c for c in td["changes"] if c not in album_diffs]
        if uniques:
            track_diffs_output.append({"path": td["path"], "changes": uniques})

    if not (update_cover or album_diffs or track_diffs_output):
        print(f"No changes needed for {target_dir}")
        return

    print(f"\n--- Changes for {target_dir} ---")
    if update_cover:
        print(f"COVER MISMATCH: {fmt(embedded_cover_hash)} -> {fmt(disk_cover_hash)}")
    
    if album_diffs:
        print("ALBUM DIFF:")
        print()
        for tag, old, new in album_diffs:
            print(f"{tag}: {fmt(old)} -> {fmt(new)}")
        print()

    if track_diffs_output:
        print("TRACK DIFF:")
        print()
        for td in track_diffs_output:
            print(td["path"])
            for tag, old, new in td["changes"]:
                print(f"  {tag}: {fmt(old)} -> {fmt(new)}")

    ans = input(f"\nProceed with {target_dir}? y/n: ").strip().lower()
    if ans not in ('y', 'yes'):
        return

    new_pic = None
    if update_cover:
        new_pic = Picture()
        new_pic.data = disk_cover_data
        new_pic.type = 3
        new_pic.mime = mimetypes.guess_type(cover_path)[0] or "image/jpeg"
        new_pic.desc = "Front Cover"

    for rel_path, target_tags in target_tags_per_track:
        audio = FLAC(os.path.join(target_dir, rel_path))
        for old_tag in list(audio.keys()):
            if old_tag.upper() not in target_tags:
                del audio[old_tag]
        for tag, val in target_tags.items():
            audio[tag] = [val]
        if update_cover:
            audio.clear_pictures()
            audio.add_picture(new_pic)
        audio.save()

def main():
    if len(sys.argv) > 1:
        base_dir = sys.argv[1]
        for root, dirs, files in os.walk(base_dir):
            if "metadata.lock.json" in files:
                process_album(root)
    else:
        process_album(".")

if __name__ == "__main__":
    main()
