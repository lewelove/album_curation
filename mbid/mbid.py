#!/usr/bin/env python
import sys
import re
import musicbrainzngs

def format_date(date_str):
    if not date_str:
        return ""
    parts = date_str.split('-')
    if len(parts) >= 2:
        return f"{parts[0]}-{parts[1]}"
    return parts[0]

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
        release = musicbrainzngs.get_release_by_id(release_id, includes=["labels", "release-groups"])["release"]
        
        rg_id = release["release-group"]["id"]
        release_group = musicbrainzngs.get_release_group_by_id(rg_id)["release-group"]
        
        original_date = release_group.get("first-release-date", "")
        specific_date = release.get("date", "")
        country = release.get("country", "")
        
        label_info = release.get("label-info-list", [{}])[0]
        label = label_info.get("label", {}).get("name", "")
        catno = label_info.get("catalog-number", "")
        
        print(f'ORIGINAL_YYYY_MM = "{format_date(original_date)}"')
        print(f'COUNTRY = "{country}"')
        print(f'LABEL = "{label}"')
        print(f'CATALOGNUMBER = "{catno}"')
        print(f'RELEASE_YYYY_MM = "{format_date(specific_date)}"')
        
    except Exception as e:
        sys.stderr.write(f"Error: {str(e)}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
