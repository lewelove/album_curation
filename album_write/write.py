#!/usr/bin/env python
import os
import sys
import json
import base64
import mimetypes
import xxhash
from mutagen.flac import FLAC, Picture

SYNC_TAGS = [
    "ALBUM", "ALBUMARTIST", "DATE", "GENRE", "COMMENT",
    "TITLE", "ARTIST", "DISCOGS_URL", "MUSICBRAINZ_URL",
    "REPLAYGAIN_TRACK_GAIN", "REPLAYGAIN_ALBUM_GAIN"
]

def fmt(val):
    return str(val) if val else ""

def get_hash(data):
    h = xxhash.xxh64(data).digest()
    return base64.urlsafe_b64encode(h).decode("ascii").rstrip("=")

def process_album(target_dir):
    lock_file = os.path.join(target_dir, "album.lock.json")
    if not os.path.isfile(lock_file):
        return

    with open(lock_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    album_obj = data.get("album", {})
    tracks_data = data.get("tracks", [])
    if not tracks_data:
        return

    exclude_keys = {"info", "tags", "keys", "covers", "manifests", "file", "id"}
    album_pool = {k.upper(): v for k, v in album_obj.items() if k not in exclude_keys and not isinstance(v, dict)}
    for pool_key in ["tags", "keys"]:
        if pool_key in album_obj:
            album_pool.update({k.upper(): v for k, v in album_obj[pool_key].items()})

    total_discs = album_obj.get("total_discs", 1)
    
    cover_filename = album_obj.get("covers", {}).get("main", {}).get("file", {}).get("path", "cover.png")
    cover_path = os.path.join(target_dir, cover_filename)
    
    disk_cover_data = None
    disk_cover_hash = None
    if os.path.exists(cover_path):
        with open(cover_path, "rb") as cf:
            disk_cover_data = cf.read()
        disk_cover_hash = get_hash(disk_cover_data)

    first_track_path = os.path.join(target_dir, tracks_data[0].get("file", {}).get("path", ""))
    first_audio = FLAC(first_track_path)
    embedded_cover_hash = None
    if first_audio.pictures:
        for pic in first_audio.pictures:
            if pic.type == 3:
                embedded_cover_hash = get_hash(pic.data)
                break

    update_cover = (disk_cover_hash is not None) and (embedded_cover_hash != disk_cover_hash)

    tasks = []
    for t in tracks_data:
        t_info = t.get("info", {})
        t_file = t.get("file", {})
        rel_path = t_file.get("path")
        if not rel_path:
            continue

        needs_tags = not t_info.get("embedded_keys_subset_match", False)
        
        target_tags = {}
        if needs_tags:
            track_pool = {k.upper(): v for k, v in t.items() if k not in exclude_keys and not isinstance(v, dict)}
            for pool_key in ["tags", "keys"]:
                if pool_key in t:
                    track_pool.update({k.upper(): v for k, v in t[pool_key].items()})

            for tag_name in SYNC_TAGS:
                val = track_pool.get(tag_name, album_pool.get(tag_name))
                if val is not None:
                    target_tags[tag_name] = "; ".join(val) if isinstance(val, list) else str(val)

            target_tags["ARTIST"] = str(track_pool.get("ARTIST", ""))
            target_tags["TITLE"] = str(track_pool.get("TITLE", ""))
            target_tags["TRACKNUMBER"] = str(track_pool.get("TRACKNUMBER", "0"))
            
            if total_discs > 1:
                target_tags["DISCNUMBER"] = str(track_pool.get("DISCNUMBER", "1"))
        
        tasks.append({
            "path": rel_path,
            "needs_tags": needs_tags,
            "target_tags": target_tags,
            "diffs": []
        })

    for task in tasks:
        if not task["needs_tags"]:
            continue

        track_file = os.path.join(target_dir, task["path"])
        audio = FLAC(track_file)
        target_keys = set(task["target_tags"].keys())
        diffs = []
        
        for old_tag in list(audio.keys()):
            u_old = old_tag.upper()
            if u_old not in target_keys:
                old_vals = audio.get(old_tag, [])
                old_val = "; ".join(old_vals) if isinstance(old_vals, list) else str(old_vals)
                diffs.append(f"\033[31m- {u_old}: \033[90m{old_val}\033[0m")

        for tag, new_val in task["target_tags"].items():
            old_vals = audio.get(tag, audio.get(tag.lower(), []))
            old_val = old_vals[0] if old_vals else ""
            if str(old_val) != str(new_val):
                if not old_val:
                    diffs.append(f"\033[32m+ {tag}: \033[90m{new_val}\033[0m")
                else:
                    diffs.append(f"\033[34m~ {tag}: \033[90m{old_val} -> {new_val}\033[0m")

        task["diffs"] = diffs

    active_tasks = [t for t in tasks if t["needs_tags"]]
    common_diffs = []
    if len(active_tasks) > 1:
        first_diffs = active_tasks[0]["diffs"]
        for d in first_diffs:
            if all(d in t["diffs"] for t in active_tasks):
                common_diffs.append(d)
                
        for t in active_tasks:
            t["diffs"] = [d for d in t["diffs"] if d not in common_diffs]

    has_actual_changes = update_cover or bool(common_diffs) or any(t["diffs"] for t in active_tasks)
    if not has_actual_changes:
        return

    if target_dir != ".":
        print(f"\n\033[1;36m{target_dir}\033[0m")
    else:
        print()

    if update_cover:
        print("\033[33m🖼️  Cover update required\033[0m")

    if common_diffs:
        print("\033[1;34m💿 Album Diff\033[0m")
        for d in common_diffs:
            print(f"   {d}")

    for task in tasks:
        if task["diffs"]:
            print(f"\033[1m🎵 {task['path']}\033[0m")
            for d in task["diffs"]:
                print(f"   {d}")

    try:
        ans = input(f"\n\033[1;35mApply changes? [y/N]: \033[0m").strip().lower()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
        
    if ans not in ('y', 'yes'):
        return

    new_pic = None
    if update_cover:
        new_pic = Picture()
        new_pic.data = disk_cover_data
        new_pic.type = 3
        new_pic.mime = mimetypes.guess_type(cover_path)[0] or "image/jpeg"
        new_pic.desc = "Front Cover"

    for task in tasks:
        rel_path = task["path"]
        audio = FLAC(os.path.join(target_dir, rel_path))
        
        if task["needs_tags"]:
            target_tags = task["target_tags"]
            for old_tag in list(audio.keys()):
                if old_tag.upper() not in target_tags:
                    del audio[old_tag]
            for tag, val in target_tags.items():
                audio[tag] = [val]
        
        if update_cover:
            audio.clear_pictures()
            audio.add_picture(new_pic)
            
        audio.save()
        
    print("\033[32m✔ Done.\033[0m")

def main():
    if len(sys.argv) > 1:
        base_dir = sys.argv[1]
        for root, dirs, files in os.walk(base_dir):
            if "album.lock.json" in files:
                process_album(root)
    else:
        process_album(".")

if __name__ == "__main__":
    main()
