#!/usr/bin/env python
import sys
import re
import os
import time
import requests
import musicbrainzngs
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.secrets/discogs.env"))
DISCOGS_TOKEN = os.getenv("DISCOGS_API_TOKEN")

def format_date(date_str):
    if not date_str:
        return ""
    parts = date_str.split('-')
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return parts[0]

def get_discogs_data(mb_release):
    if not DISCOGS_TOKEN:
        return None, ""
    
    discogs_url = ""
    for rel in mb_release.get("url-relation-list", []):
        if "discogs.com/release/" in rel["target"]:
            discogs_url = rel["target"]
            break
            
    if not discogs_url:
        return None, ""

    match = re.search(r"release/(\d+)", discogs_url)
    if not match:
        return None, discogs_url
        
    release_id = match.group(1)
    headers = {
        "User-Agent": "AlbumCurationTool/0.1",
        "Authorization": f"Discogs token={DISCOGS_TOKEN}"
    }

    try:
        r_resp = requests.get(f"https://api.discogs.com/releases/{release_id}", headers=headers)
        r_resp.raise_for_status()
        rel_data = r_resp.json()
        
        source_data = rel_data
        master_id = rel_data.get("master_id")
        
        if master_id:
            time.sleep(1)
            m_resp = requests.get(f"https://api.discogs.com/masters/{master_id}", headers=headers)
            if m_resp.status_code == 200:
                source_data = m_resp.json()

        return source_data.get("styles", []), discogs_url
    except Exception:
        return None, discogs_url

def main():
    if len(sys.argv) < 2:
        sys.exit(1)

    url = sys.argv[1]
    match = re.search(r"release/([a-f0-9\-]+)", url)
    if not match:
        sys.exit(1)
    
    release_id = match.group(1)
    musicbrainzngs.set_useragent("album_curation_tool", "0.1")
    
    try:
        release = musicbrainzngs.get_release_by_id(
            release_id, 
            includes=["labels", "release-groups", "url-rels", "recordings", "artist-credits"]
        )["release"]
        
        rg_id = release["release-group"]["id"]
        release_group = musicbrainzngs.get_release_group_by_id(rg_id)["release-group"]
        
        album_artist = release.get("artist-credit-phrase", "")
        album_title = release.get("title", "")
        release_date = release.get("date", "")
        original_date = release_group.get("first-release-date", "")
        country = release.get("country", "")
        
        label_info = release.get("label-info-list", [{}])[0]
        label = label_info.get("label", {}).get("name", "")
        catno = label_info.get("catalog-number", "")
        
        styles_list, d_url = get_discogs_data(release)
        styles_str = "; ".join(styles_list) if styles_list else ""
        
        tracks = []
        for medium in release.get("medium-list", []):
            for track in medium.get("track-list", []):
                tracks.append({
                    "number": int(track["number"]),
                    "title": track["recording"]["title"]
                })

        print("[album]")
        print()
        print(f'ALBUMARTIST = "{album_artist}"')
        print(f'ALBUM = "{album_title}"')
        print(f'DATE = "{release_date[:4] if release_date else ""}"')
        print()
        print(f'GENRE = "Alternative"')
        print(f'STYLES = "{styles_str}"')
        print()
        print(f'ORIGINAL_YYYY_MM = "{format_date(original_date)}"')
        print()
        print(f'COUNTRY = "{country}"')
        print(f'LABEL = "{label}"')
        print(f'CATALOGNUMBER = "{catno}"')
        print(f'RELEASE_YYYY_MM = "{format_date(release_date)}"')
        print()
        print(f'DISCOGS_URL = "{d_url}"')
        print(f'MUSICBRAINZ_URL = "https://musicbrainz.org/release/{release_id}"')
        print(f'CTDBID_URL = ""')
        print()
        print(f'UNIX_GENERATED = {int(time.time())}')
        print()
        
        if tracks:
            print("[[tracks]]")
            print(f'TRACKNUMBER = {tracks[0]["number"]}')
            print(f'TITLE = "{tracks[0]["title"]}"')
        
        for i in range(1, len(tracks)):
            print("[[tracks]]")
            print(f'TRACKNUMBER = {tracks[i]["number"]}')
            print(f'TITLE = "{tracks[i]["title"]}"')
            print()
            
    except Exception as e:
        sys.stderr.write(f"Error: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
