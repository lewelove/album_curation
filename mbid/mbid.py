import sys
import re
import os
import time
import json
import requests
import musicbrainzngs
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.secrets/discogs.env"))
DISCOGS_TOKEN = os.getenv("DISCOGS_API_TOKEN")

def sanitize_keys(data):
    if isinstance(data, dict):
        return {k.replace('-', '_'): sanitize_keys(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [sanitize_keys(i) for i in data]
    else:
        return data

def get_discogs_raw(mb_release):
    if not DISCOGS_TOKEN:
        return {"error": "DISCOGS_API_TOKEN environment variable is missing"}
    
    discogs_url = ""
    for rel in mb_release.get("url-relation-list", []):
        if "discogs.com/release/" in rel["target"]:
            discogs_url = rel["target"]
            break
            
    if not discogs_url:
        return {"error": "No Discogs release relation found in MusicBrainz metadata"}

    match = re.search(r"release/(\d+)", discogs_url)
    if not match:
        return {"error": f"Could not extract Discogs ID from URL: {discogs_url}"}
        
    release_id = match.group(1)
    headers = {
        "User-Agent": "AlbumCurationTool/0.1",
        "Authorization": f"Discogs token={DISCOGS_TOKEN}"
    }

    try:
        r_resp = requests.get(f"https://api.discogs.com/releases/{release_id}", headers=headers)
        r_resp.raise_for_status()
        rel_data = r_resp.json()
        
        result = {"release": rel_data}
        master_id = rel_data.get("master_id")
        
        if master_id:
            time.sleep(1)
            m_resp = requests.get(f"https://api.discogs.com/masters/{master_id}", headers=headers)
            if m_resp.status_code == 200:
                result["master"] = m_resp.json()

        return result
    except Exception as e:
        return {"error": f"Discogs API request failed: {str(e)}"}

def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Error: A MusicBrainz Release URL must be provided as the first argument\n")
        sys.exit(1)

    url = sys.argv[1]
    match = re.search(r"release/([a-f0-9\-]+)", url)
    if not match:
        sys.stderr.write("Error: The provided string is not a valid MusicBrainz release URL\n")
        sys.exit(1)
    
    release_id = match.group(1)
    musicbrainzngs.set_useragent("album_curation_tool", "0.1")
    
    try:
        release = musicbrainzngs.get_release_by_id(
            release_id, 
            includes=["labels", "release-groups", "url-rels", "recordings", "artist-credits", "isrcs"]
        )["release"]
        
        rg_id = release["release-group"]["id"]
        release_group = musicbrainzngs.get_release_group_by_id(
            rg_id, 
            includes=["tags", "ratings", "url-rels", "artist-credits"]
        )["release-group"]
        
        discogs_data = get_discogs_raw(release)
        
        output = {
            "musicbrainz": {
                "release": release,
                "release_group": release_group
            },
            "discogs": discogs_data
        }
        
        sanitized = sanitize_keys(output)
        print(json.dumps(sanitized, indent=2, sort_keys=True))
            
    except musicbrainzngs.MusicBrainzError as e:
        sys.stderr.write(f"MusicBrainz API Error: {str(e)}\n")
        sys.exit(1)
    except Exception as e:
        sys.stderr.write(f"Unexpected System Error: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
