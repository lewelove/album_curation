#!/usr/bin/env python
import sys
import os
import glob
import base64
import hashlib
import re
import json
import time
import requests
import musicbrainzngs
import discid
import tomllib
from pathlib import Path
from mutagen.flac import FLAC
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.secrets/discogs.env"))
DISCOGS_TOKEN = os.getenv("DISCOGS_API_TOKEN")

def natural_keys(text):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'(\d+)', text)]

def get_sort_key(filepath):
    try:
        audio = FLAC(filepath)
        tr = audio.get('tracknumber', [None])[0]
        if tr:
            return (0, int(tr.split('/')[0]))
    except Exception:
        pass
    return (1, natural_keys(os.path.basename(filepath)))

def get_total_samples(filepath):
    audio = FLAC(filepath)
    return audio.info.total_samples

def get_ctdb_id(folder_path):
    pattern = os.path.join(folder_path, '*.flac')
    files = glob.glob(pattern)
    if not files:
        return None
    files = sorted(files, key=get_sort_key)
    offsets = []
    current_offset = 150
    for f in files:
        samples = get_total_samples(f)
        sectors = samples // 588
        offsets.append(current_offset)
        current_offset += sectors
    leadout = current_offset
    pregap = offsets[0]
    x = ""
    for offset in offsets[1:]:
        x += f"{offset - pregap:08X}"
    x += f"{leadout - pregap:08X}"
    sha1 = hashlib.sha1(x.ljust(800, '0').encode('ascii')).digest()
    ctdb = base64.b64encode(sha1).decode('ascii').replace('+', '.').replace('/', '_').replace('=', '-')
    return ctdb

def calculate_local_ids(folder_path):
    pattern = os.path.join(folder_path, '*.flac')
    files = glob.glob(pattern)
    if not files:
        sys.exit(1)
    files = sorted(files, key=get_sort_key)
    offsets = []
    current_offset = 150
    for f in files:
        samples = get_total_samples(f)
        sectors = samples // 588
        offsets.append(current_offset)
        current_offset += sectors
    leadout = current_offset
    try:
        disc = discid.put(1, len(files), leadout, offsets)
        mbid = disc.id
        freedb = disc.freedb_id.upper()
    except Exception:
        mbid = "Error"
        freedb = "Error"
    id1 = 0
    id2 = 0
    for i, offset in enumerate(offsets):
        track_num = i + 1
        id1 += offset
        id2 += offset * track_num
    track_num = len(offsets) + 1
    id1 += leadout
    id2 += leadout * track_num
    id1 &= 0xFFFFFFFF
    id2 &= 0xFFFFFFFF
    accuraterip = f"{id1:08x}-{id2:08x}-{freedb.lower()}" if freedb != "Error" else "Error"
    ctdb = get_ctdb_id(folder_path)
    lines = [
        f"MUSICBRAINZ DISCID  : {mbid}",
        f"FREEDB DISCID       : {freedb}",
        f"ACCURATERIP ID      : {accuraterip}",
        f"CTDB TOCID          : {ctdb}",
        "-" * 50,
        f'CTDBID_URL = "http://db.cuetools.net/?tocid={ctdb}"'
    ]
    sys.stdout.write("\n".join(lines))

def join_artists(artist_credit):
    parts = []
    for credit in artist_credit:
        if isinstance(credit, str):
            parts.append(credit)
        else:
            parts.append(credit.get('artist', {}).get('name', ''))
            if 'joinphrase' in credit:
                parts.append(credit['joinphrase'])
    return "".join(parts)

def fmt_yyyy_mm(date_str):
    if not date_str:
        return ""
    if len(date_str) >= 7:
        return date_str[:7]
    if len(date_str) == 4:
        return f"{date_str}-00"
    return date_str

def toml_val(v):
    if isinstance(v, (list, dict)):
        return json.dumps(v)
    if isinstance(v, bool):
        return str(v).lower()
    if isinstance(v, (int, float)):
        return str(v)
    return f'"{v}"'

def get_discogs_data(mb_obj, is_rg=False):
    if not DISCOGS_TOKEN:
        return {"error": "Missing token"}
    discogs_url = ""
    for rel in mb_obj.get("url-relation-list", []):
        if "discogs.com/release/" in rel["target"] or "discogs.com/master/" in rel["target"]:
            discogs_url = rel["target"]
            break
    if not discogs_url:
        return {"error": "No relation"}
    m_rel = re.search(r"release/(\d+)", discogs_url)
    m_mas = re.search(r"master/(\d+)", discogs_url)
    headers = {"User-Agent": "AlbumCuration/0.1", "Authorization": f"Discogs token={DISCOGS_TOKEN}"}
    result = {}
    try:
        if m_rel:
            r_resp = requests.get(f"https://api.discogs.com/releases/{m_rel.group(1)}", headers=headers)
            r_resp.raise_for_status()
            rel_data = r_resp.json()
            result["release"] = rel_data
            master_id = rel_data.get("master_id")
            if master_id:
                time.sleep(1)
                m_resp = requests.get(f"https://api.discogs.com/masters/{master_id}", headers=headers)
                if m_resp.status_code == 200:
                    result["master"] = m_resp.json()
        elif m_mas:
            m_resp = requests.get(f"https://api.discogs.com/masters/{m_mas.group(1)}", headers=headers)
            m_resp.raise_for_status()
            result["master"] = m_resp.json()
        return result
    except Exception as e:
        return {"error": str(e)}

def fetch_remote_metadata(url):
    is_rg = "release-group/" in url
    m = re.search(r"(release|release-group)/([a-f0-9\-]+)", url)
    if not m: return None
    mode, entity_id = m.groups()
    cache_dir = Path.home() / ".cache" / "discid"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / f"{'rg' if is_rg else 'rel'}-{entity_id}.json"
    if cache_file.exists():
        with open(cache_file, "r") as f:
            data = json.load(f)
            data["_is_rg"] = is_rg
            return data
    musicbrainzngs.set_useragent("album_curation", "0.1")
    data = {"_is_rg": is_rg}
    if is_rg:
        rg = musicbrainzngs.get_release_group_by_id(entity_id, includes=["tags", "url-rels", "artist-credits"])["release-group"]
        data["musicbrainz"] = {"release_group": rg}
        data["discogs"] = get_discogs_data(rg, is_rg=True)
    else:
        release = musicbrainzngs.get_release_by_id(entity_id, includes=["labels", "release-groups", "url-rels", "recordings", "artist-credits"])["release"]
        rg_id = release["release-group"]["id"]
        rg = musicbrainzngs.get_release_group_by_id(rg_id, includes=["tags", "url-rels", "artist-credits"])["release-group"]
        data["musicbrainz"] = {"release": release, "release_group": rg}
        data["discogs"] = get_discogs_data(release)
    with open(cache_file, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    return data

def get_mbid_lines(data):
    is_rg = data.get("_is_rg", False)
    mb = data["musicbrainz"]
    rg = mb["release_group"]
    rel = mb.get("release")
    dg = data.get("discogs", {})
    album_artist = join_artists(rg["artist-credit"])
    lines = ["[album]", ""]
    lines.append(f'ALBUMARTIST = "{album_artist}"')
    lines.append(f'ALBUM = "{rg["title"]}"')
    lines.append("")
    if not is_rg and rel:
        lines.append(f'MUSICBRAINZ_RELEASE_URL = "https://musicbrainz.org/release/{rel["id"]}"')
    lines.append(f'MUSICBRAINZ_RELEASEGROUP_URL = "https://musicbrainz.org/release-group/{rg["id"]}"')
    lines.append("")
    if not is_rg and rel:
        lines.append(f'MUSICBRAINZ_ALBUMID = "{rel["id"]}"')
    lines.append(f'MUSICBRAINZ_ALBUMARTISTID = "{rg["artist-credit"][0]["artist"]["id"]}"')
    lines.append(f'MUSICBRAINZ_RELEASEGROUPID = "{rg["id"]}"')
    lines.append("")
    if not is_rg and rel:
        multi_disc = int(rel.get("medium-count", 1)) > 1
        for medium in rel.get("medium-list", []):
            disc_num = int(medium["position"])
            for track in medium.get("track-list", []):
                t_artist = join_artists(track["artist-credit"])
                lines.append("[[tracks]]")
                if multi_disc: lines.append(f"DISCNUMBER = {disc_num}")
                lines.append(f"TRACKNUMBER = {int(track['number'])}")
                lines.append(f'TITLE = "{track["recording"]["title"]}"')
                if t_artist != album_artist: lines.append(f'ARTIST = "{t_artist}"')
                lines.append(f'MUSICBRAINZ_TRACKID = "{track["recording"]["id"]}"')
                lines.append(f'MUSICBRAINZ_RELEASETRACKID = "{track["id"]}"')
                lines.append(f'MUSICBRAINZ_ARTISTID = "{track["artist-credit"][0]["artist"]["id"]}"')
                lines.append("")
    elif is_rg and "master" in dg:
        tracks = [t for t in dg["master"].get("tracklist", []) if t.get("type_") == "track"]
        for i, track in enumerate(tracks, 1):
            lines.append("[[tracks]]")
            lines.append(f"TRACKNUMBER = {i}")
            lines.append(f'TITLE = "{track.get("title", "")}"')
            lines.append("")
    return lines

def get_metadata_lines(data):
    is_rg = data.get("_is_rg", False)
    mb = data["musicbrainz"]
    rg = mb["release_group"]
    rel = mb.get("release")
    dg = data.get("discogs", {})
    album_artist = join_artists(rg["artist-credit"])
    ctdb = get_ctdb_id(".") if not is_rg else None
    gen_keys = [
        ("ALBUMARTIST", album_artist),
        ("ALBUM", rg["title"]),
        ("DATE", rg.get("first-release-date", "")[:4]),
        None
    ]
    if "master" in dg:
        gen_keys.append(("GENRE", dg["master"].get("genres", [])))
        gen_keys.append(("STYLES", dg["master"].get("styles", [])))
        gen_keys.append(None)
    gen_keys.append(("ORIGINAL_YYYY_MM", fmt_yyyy_mm(rg.get("first-release-date", ""))))
    gen_keys.append(None)
    if not is_rg and rel:
        gen_keys.append(("COUNTRY", rel.get("country", "")))
        label_info = rel.get("label-info-list", [{}])[0]
        gen_keys.append(("LABEL", label_info.get("label", {}).get("name", "")))
        gen_keys.append(("CATALOGNUMBER", label_info.get("catalog-number", "")))
        gen_keys.append(("RELEASE_YYYY_MM", fmt_yyyy_mm(rel.get("date", ""))))
        gen_keys.append(None)
    if is_rg:
        if "master" in dg:
            gen_keys.append(("DISCOGS_URL", f"https://discogs.com/master/{dg['master'].get('id')}"))
        gen_keys.append(("MUSICBRAINZ_URL", f"https://musicbrainz.org/release-group/{rg['id']}"))
    else:
        if "release" in dg:
            gen_keys.append(("DISCOGS_URL", f"https://discogs.com/release/{dg['release'].get('id')}"))
        gen_keys.append(("MUSICBRAINZ_URL", f"https://musicbrainz.org/release/{rel['id']}"))
    if ctdb:
        gen_keys.append(("CTDBID_URL", f"http://db.cuetools.net/?tocid={ctdb}"))
    gen_map = {item[0]: item[1] for item in gen_keys if item is not None}
    extra_album = {}
    if os.path.exists("metadata.toml"):
        with open("metadata.toml", "rb") as f:
            existing_album = tomllib.load(f).get("album", {})
            for k, v in existing_album.items():
                if k not in gen_map: extra_album[k] = v
    lines = ["[album]", ""]
    for entry in gen_keys:
        if entry is None: lines.append("")
        else: lines.append(f'{entry[0]} = {toml_val(entry[1])}')
    if extra_album:
        lines.append("")
        for k, v in extra_album.items(): lines.append(f'{k} = {toml_val(v)}')
    lines.append("")
    if not is_rg and rel:
        multi_disc = int(rel.get("medium-count", 1)) > 1
        for medium in rel.get("medium-list", []):
            disc_num = int(medium["position"])
            for track in medium.get("track-list", []):
                t_artist = join_artists(track["artist-credit"])
                lines.append("[[tracks]]")
                if multi_disc: lines.append(f"DISCNUMBER = {disc_num}")
                lines.append(f"TRACKNUMBER = {int(track['number'])}")
                lines.append(f'TITLE = "{track["recording"]["title"]}"')
                if t_artist != album_artist: lines.append(f'ARTIST = "{t_artist}"')
                lines.append("")
    elif is_rg and "master" in dg:
        tracks = [t for t in dg["master"].get("tracklist", []) if t.get("type_") == "track"]
        for i, track in enumerate(tracks, 1):
            lines.append("[[tracks]]")
            lines.append(f"TRACKNUMBER = {i}")
            lines.append(f'TITLE = "{track.get("title", "")}"')
            lines.append("")
    return lines

def main():
    args = sys.argv[1:]
    flags = [a for a in args if a.startswith("--")]
    pos_args = [a for a in args if not a.startswith("--")]
    target = pos_args[0] if pos_args else None
    if not target and flags:
        if "--metadata" in flags or "--mbid" in flags:
            if os.path.exists("metadata.toml"):
                with open("metadata.toml", "rb") as f:
                    meta = tomllib.load(f)
                    target = meta.get("album", {}).get("MUSICBRAINZ_URL")
    if not target:
        if not flags:
            calculate_local_ids(".")
        else:
            sys.stderr.write("Error: No URL provided and MUSICBRAINZ_URL not found in metadata.toml\n")
            sys.exit(1)
        return
    if target.startswith("http"):
        data = fetch_remote_metadata(target)
        if not data: sys.exit(1)
        final_lines = []
        if "--mbid" in flags: final_lines.extend(get_mbid_lines(data))
        if "--metadata" in flags:
            if final_lines: final_lines.append("")
            final_lines.extend(get_metadata_lines(data))
        if not flags:
            sys.stdout.write(json.dumps(data, indent=2, sort_keys=True))
            return
        sys.stdout.write("\n".join(final_lines).rstrip())
    else:
        calculate_local_ids(target)

if __name__ == "__main__":
    main()
