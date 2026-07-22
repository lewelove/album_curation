import sys
import os
import re
import requests
import musicbrainzngs
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/.secrets/discogs.env"))
DISCOGS_TOKEN = os.getenv("DISCOGS_API_TOKEN")

def join_artists(artist_credit):
    parts = []
    if not artist_credit:
        return ""
    for credit in artist_credit:
        if isinstance(credit, str):
            parts.append(credit)
        elif isinstance(credit, dict):
            if "artist" in credit and "name" in credit["artist"]:
                parts.append(credit["artist"]["name"])
            elif "name" in credit:
                parts.append(credit["name"])
            if "joinphrase" in credit:
                parts.append(credit["joinphrase"])
    return "".join(parts)

def get_artist_id(artist_credit):
    if not artist_credit or not isinstance(artist_credit, list):
        return ""
    first = artist_credit[0]
    if isinstance(first, dict) and "artist" in first and "id" in first["artist"]:
        return first["artist"]["id"]
    return ""

def fmt_date(date_str):
    if not date_str:
        return ""
    if len(date_str) >= 7:
        return date_str[:7]
    return date_str

def toml_val(val):
    if isinstance(val, bool):
        return str(val).lower()
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, list):
        items = [toml_val(x) for x in val]
        return f"[{', '.join(items)}]"
    escaped = str(val).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'

def fetch_discogs_data(mb_release):
    token = DISCOGS_TOKEN or os.getenv("DISCOGS_TOKEN")
    if not token:
        return {}
    discogs_url = ""
    relations = mb_release.get("url-relation-list", []) or mb_release.get("relations", [])
    for rel in relations:
        target = rel.get("target") or rel.get("url", {}).get("resource", "")
        if "discogs.com/release/" in target or "discogs.com/master/" in target:
            discogs_url = target
            break
    if not discogs_url:
        return {}
    headers = {
        "User-Agent": "AlbumCuration/0.1",
        "Authorization": f"Discogs token={token}"
    }
    m_rel = re.search(r"release/(\d+)", discogs_url)
    m_mas = re.search(r"master/(\d+)", discogs_url)
    result = {}
    try:
        if m_rel:
            rel_id = m_rel.group(1)
            resp = requests.get(f"https://api.discogs.com/releases/{rel_id}", headers=headers)
            if resp.status_code == 200:
                rel_data = resp.json()
                result["release"] = rel_data
                master_id = rel_data.get("master_id")
                if master_id:
                    m_resp = requests.get(f"https://api.discogs.com/masters/{master_id}", headers=headers)
                    if m_resp.status_code == 200:
                        result["master"] = m_resp.json()
        elif m_mas:
            mas_id = m_mas.group(1)
            m_resp = requests.get(f"https://api.discogs.com/masters/{mas_id}", headers=headers)
            if m_resp.status_code == 200:
                result["master"] = m_resp.json()
    except Exception:
        pass
    return result

def parse_release_id(url):
    match = re.search(r"release/([a-f0-9\-]+)", url)
    if match:
        return match.group(1)
    return None

def generate_manifests(release_id):
    musicbrainzngs.set_useragent("album_curation", "0.1")
    release = musicbrainzngs.get_release_by_id(
        release_id,
        includes=["labels", "release-groups", "url-rels", "recordings", "artist-credits", "media"]
    )["release"]

    rg_id = release["release-group"]["id"]
    release_group = musicbrainzngs.get_release_group_by_id(
        rg_id,
        includes=["tags", "url-rels", "artist-credits"]
    )["release-group"]

    discogs_data = fetch_discogs_data(release)

    album_artist = join_artists(release_group.get("artist-credit")) or join_artists(release.get("artist-credit"))
    album_title = release_group.get("title") or release.get("title", "")
    orig_date = fmt_date(release_group.get("first-release-date", ""))
    issue_date = release.get("date", "")

    genres = []
    styles = []
    if "master" in discogs_data:
        genres = discogs_data["master"].get("genres", [])
        styles = discogs_data["master"].get("styles", [])
    elif "release" in discogs_data:
        genres = discogs_data["release"].get("genres", [])
        styles = discogs_data["release"].get("styles", [])

    primary_genre = genres[0] if genres else ""

    country = release.get("country", "")
    label = ""
    catalognumber = ""
    label_info_list = release.get("label-info-list", [])
    if label_info_list:
        first_label = label_info_list[0]
        if "label" in first_label and "name" in first_label["label"]:
            label = first_label["label"]["name"]
        if "catalog-number" in first_label and first_label["catalog-number"]:
            catalognumber = first_label["catalog-number"]

    medium_list = release.get("medium-list", [])
    total_discs = len(medium_list)

    metadata_lines = ["[album]", ""]
    metadata_lines.append(f"albumartist = {toml_val(album_artist)}")
    metadata_lines.append(f"album = {toml_val(album_title)}")
    metadata_lines.append(f"date = {toml_val(orig_date)}")
    metadata_lines.append("")
    metadata_lines.append(f"genre = {toml_val(primary_genre)}")
    metadata_lines.append(f"genres = {toml_val(genres)}")
    metadata_lines.append(f"styles = {toml_val(styles)}")
    metadata_lines.append("")
    metadata_lines.append(f"country = {toml_val(country)}")
    metadata_lines.append(f"label = {toml_val(label)}")
    metadata_lines.append(f"catalognumber = {toml_val(catalognumber)}")
    metadata_lines.append(f"release_date = {toml_val(issue_date)}")
    metadata_lines.append("")

    for medium in medium_list:
        disc_num = int(medium.get("position", 1))
        track_list = medium.get("track-list", [])
        for track in track_list:
            track_num = int(track.get("number", track.get("position", 1)))
            track_title = track.get("recording", {}).get("title") or track.get("title", "")
            track_artist = join_artists(track.get("artist-credit")) or join_artists(track.get("recording", {}).get("artist-credit"))

            metadata_lines.append("[[tracks]]")
            if total_discs > 1:
                metadata_lines.append(f"discnumber = {disc_num}")
            metadata_lines.append(f"tracknumber = {track_num}")
            metadata_lines.append(f"title = {toml_val(track_title)}")
            if track_artist and track_artist != album_artist:
                metadata_lines.append(f"artist = {toml_val(track_artist)}")
            metadata_lines.append("")

    albumartist_id = get_artist_id(release_group.get("artist-credit")) or get_artist_id(release.get("artist-credit"))
    discogs_rel_id = str(discogs_data.get("release", {}).get("id", "")) if "release" in discogs_data else ""
    discogs_mas_id = str(discogs_data.get("master", {}).get("id", "")) if "master" in discogs_data else ""

    id_lines = ["[album]", ""]
    id_lines.append(f"musicbrainz_albumartistid = {toml_val(albumartist_id)}")
    id_lines.append(f"musicbrainz_releasegroupid = {toml_val(rg_id)}")
    id_lines.append("")
    id_lines.append(f"musicbrainz_albumid = {toml_val(release_id)}")
    id_lines.append("")
    id_lines.append(f"discogs_releaseid = {toml_val(discogs_rel_id)}")
    id_lines.append(f"discogs_masterid = {toml_val(discogs_mas_id)}")
    id_lines.append("")

    for medium in medium_list:
        disc_num = int(medium.get("position", 1))
        track_list = medium.get("track-list", [])
        for track in track_list:
            track_num = int(track.get("number", track.get("position", 1)))
            release_track_id = track.get("id", "")
            track_artist_id = get_artist_id(track.get("artist-credit")) or get_artist_id(track.get("recording", {}).get("artist-credit")) or albumartist_id

            id_lines.append("[[tracks]]")
            if total_discs > 1:
                id_lines.append(f"discnumber = {disc_num}")
            id_lines.append(f"tracknumber = {track_num}")
            id_lines.append(f"musicbrainz_releasetrackid = {toml_val(release_track_id)}")
            id_lines.append(f"musicbrainz_artistid = {toml_val(track_artist_id)}")
            id_lines.append("")

    return "\n".join(metadata_lines).rstrip(), "\n".join(id_lines).rstrip()

def main():
    args = sys.argv[1:]
    to_stdout = "--stdout" in args
    url_arg = next((a for a in args if not a.startswith("--")), None)

    if not url_arg:
        sys.stderr.write("Error: MusicBrainz release URL required\n")
        sys.exit(1)

    release_id = parse_release_id(url_arg)
    if not release_id:
        sys.stderr.write("Error: Invalid MusicBrainz release URL\n")
        sys.exit(1)

    meta_content, id_content = generate_manifests(release_id)

    if to_stdout:
        sys.stdout.write(f"--- metadata.toml ---\n{meta_content}\n\n--- id.toml ---\n{id_content}\n")
    else:
        Path("metadata.toml").write_text(meta_content + "\n", encoding="utf-8")
        Path("id.toml").write_text(id_content + "\n", encoding="utf-8")
        sys.stdout.write("Generated metadata.toml and id.toml\n")

if __name__ == "__main__":
    main()
