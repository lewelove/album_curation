use crate::local;
use crate::utils;
use serde_json::{json, Value};
use std::fs;
use std::path::PathBuf;

pub fn get_mbid_lines(data: &Value) -> Vec<String> {
    let is_rg = data.get("_is_rg").and_then(|v| v.as_bool()).unwrap_or(false);
    let mb = data.get("musicbrainz").unwrap();
    let rg = mb.get("release_group").unwrap();
    let rel = mb.get("release");
    let dg_fallback = json!({});
    let dg = data.get("discogs").unwrap_or(&dg_fallback);

    let album_artist = utils::join_artists(rg.get("artist-credit"));
    let mut lines = vec!["[album]".to_string(), "".to_string()];

    lines.push(format!("ALBUMARTIST = \"{}\"", album_artist));
    if let Some(title) = rg.get("title").and_then(|t| t.as_str()) {
        lines.push(format!("ALBUM = \"{}\"", title));
    }
    lines.push("".to_string());

    if !is_rg {
        if let Some(id) = rel.and_then(|r| r.get("id")).and_then(|i| i.as_str()) {
            lines.push(format!("MUSICBRAINZ_RELEASE_URL = \"https://musicbrainz.org/release/{}\"", id));
        }
    }
    if let Some(id) = rg.get("id").and_then(|i| i.as_str()) {
        lines.push(format!("MUSICBRAINZ_RELEASEGROUP_URL = \"https://musicbrainz.org/release-group/{}\"", id));
    }
    lines.push("".to_string());

    if !is_rg {
        if let Some(id) = rel.and_then(|r| r.get("id")).and_then(|i| i.as_str()) {
            lines.push(format!("MUSICBRAINZ_ALBUMID = \"{}\"", id));
        }
    }
    if let Some(id) = rg.get("artist-credit").and_then(|a| a.as_array()).and_then(|a| a.first()).and_then(|c| c.get("artist")).and_then(|a| a.get("id")).and_then(|i| i.as_str()) {
        lines.push(format!("MUSICBRAINZ_ALBUMARTISTID = \"{}\"", id));
    }
    if let Some(id) = rg.get("id").and_then(|i| i.as_str()) {
        lines.push(format!("MUSICBRAINZ_RELEASEGROUPID = \"{}\"", id));
    }
    lines.push("".to_string());

    append_tracks(&mut lines, is_rg, rel, dg, &album_artist, true);
    lines
}

pub fn get_metadata_lines(data: &Value) -> Vec<String> {
    let is_rg = data.get("_is_rg").and_then(|v| v.as_bool()).unwrap_or(false);
    let mb = data.get("musicbrainz").unwrap();
    let rg = mb.get("release_group").unwrap();
    let rel = mb.get("release");
    let dg_fallback = json!({});
    let dg = data.get("discogs").unwrap_or(&dg_fallback);

    let album_artist = utils::join_artists(rg.get("artist-credit"));
    let ctdb = if !is_rg { local::get_ctdb_id(&PathBuf::from(".")) } else { None };

    let mut gen_keys = Vec::new();
    gen_keys.push(Some(("ALBUMARTIST".to_string(), json!(album_artist))));
    if let Some(title) = rg.get("title").and_then(|t| t.as_str()) {
        gen_keys.push(Some(("ALBUM".to_string(), json!(title))));
    }
    
    let date_str = rg.get("first-release-date").and_then(|d| d.as_str()).unwrap_or("");
    gen_keys.push(Some(("DATE".to_string(), json!(if date_str.len() >= 4 { &date_str[..4] } else { "" }))));
    gen_keys.push(None);

    if let Some(master) = dg.get("master") {
        if let Some(g) = master.get("genres") { gen_keys.push(Some(("GENRE".to_string(), g.clone()))); }
        if let Some(s) = master.get("styles") { gen_keys.push(Some(("STYLES".to_string(), s.clone()))); }
        gen_keys.push(None);
    }

    gen_keys.push(Some(("ORIGINAL_YYYY_MM".to_string(), json!(utils::fmt_yyyy_mm(date_str)))));
    gen_keys.push(None);

    if !is_rg {
        if let Some(release) = rel {
            if let Some(c) = release.get("country").and_then(|c| c.as_str()) { gen_keys.push(Some(("COUNTRY".to_string(), json!(c)))); }
            if let Some(label_list) = release.get("label-info").and_then(|l| l.as_array()) {
                if let Some(node) = label_list.first() {
                    if let Some(n) = node.get("label").and_then(|l| l.get("name")).and_then(|n| n.as_str()) { gen_keys.push(Some(("LABEL".to_string(), json!(n)))); }
                    if let Some(c) = node.get("catalog-number").and_then(|c| c.as_str()) { gen_keys.push(Some(("CATALOGNUMBER".to_string(), json!(c)))); }
                }
            }
            let rel_date = release.get("date").and_then(|d| d.as_str()).unwrap_or("");
            gen_keys.push(Some(("RELEASE_YYYY_MM".to_string(), json!(utils::fmt_yyyy_mm(rel_date)))));
            gen_keys.push(None);
        }
    }

    if is_rg {
        if let Some(id) = dg.get("master").and_then(|m| m.get("id")) { gen_keys.push(Some(("DISCOGS_URL".to_string(), json!(format!("https://discogs.com/master/{}", id))))); }
        if let Some(id) = rg.get("id").and_then(|i| i.as_str()) { gen_keys.push(Some(("MUSICBRAINZ_URL".to_string(), json!(format!("https://musicbrainz.org/release-group/{}", id))))); }
    } else {
        if let Some(id) = dg.get("release").and_then(|r| r.get("id")) { gen_keys.push(Some(("DISCOGS_URL".to_string(), json!(format!("https://discogs.com/release/{}", id))))); }
        if let Some(id) = rel.and_then(|r| r.get("id")).and_then(|i| i.as_str()) { gen_keys.push(Some(("MUSICBRAINZ_URL".to_string(), json!(format!("https://musicbrainz.org/release/{}", id))))); }
    }

    if let Some(ctdb_id) = ctdb { gen_keys.push(Some(("CTDBID_URL".to_string(), json!(format!("http://db.cuetools.net/?tocid={}", ctdb_id))))); }

    let mut lines = vec!["[album]".to_string(), "".to_string()];
    let mut keys_processed: Vec<String> = Vec::new();

    for entry in gen_keys {
        if let Some((k, v)) = entry {
            keys_processed.push(k.clone());
            lines.push(format!("{} = {}", k, utils::toml_val(&v)));
        } else { lines.push("".to_string()); }
    }

    if let Ok(content) = fs::read_to_string("metadata.toml") {
        if let Ok(meta) = toml::from_str::<toml::Value>(&content) {
            if let Some(album) = meta.get("album").and_then(|a| a.as_table()) {
                let mut added_extra = false;
                for (k, v) in album {
                    if !keys_processed.contains(k) {
                        if !added_extra { lines.push("".to_string()); added_extra = true; }
                        lines.push(format!("{} = {}", k, v));
                    }
                }
            }
        }
    }

    lines.push("".to_string());
    append_tracks(&mut lines, is_rg, rel, dg, &album_artist, false);
    lines
}

fn append_tracks(lines: &mut Vec<String>, is_rg: bool, rel: Option<&Value>, dg: &Value, album_artist: &str, mbid_mode: bool) {
    if !is_rg {
        if let Some(release) = rel {
            if let Some(media) = release.get("media").and_then(|m| m.as_array()) {
                let multi_disc = media.len() > 1;
                for medium in media {
                    let disc_num = medium.get("position").and_then(|p| p.as_i64()).unwrap_or(1);
                    let track_list = medium.get("tracks").or_else(|| medium.get("track")).and_then(|t| t.as_array());
                    if let Some(tracks) = track_list {
                        for track in tracks {
                            lines.push("[[tracks]]".to_string());
                            if multi_disc { lines.push(format!("DISCNUMBER = {}", disc_num)); }
                            if let Some(n) = track.get("number").and_then(|n| n.as_str()) { lines.push(format!("TRACKNUMBER = {}", n)); }
                            let title = track.get("title").and_then(|t| t.as_str())
                                .or_else(|| track.get("recording").and_then(|r| r.get("title")).and_then(|t| t.as_str()));
                            if let Some(t) = title { lines.push(format!("TITLE = \"{}\"", t)); }
                            let t_artist = utils::join_artists(track.get("artist-credit").or_else(|| track.get("recording").and_then(|r| r.get("artist-credit"))));
                            if !t_artist.is_empty() && t_artist != album_artist { lines.push(format!("ARTIST = \"{}\"", t_artist)); }
                            if mbid_mode {
                                if let Some(id) = track.get("recording").and_then(|r| r.get("id")).and_then(|i| i.as_str()) { lines.push(format!("MUSICBRAINZ_TRACKID = \"{}\"", id)); }
                                if let Some(id) = track.get("id").and_then(|i| i.as_str()) { lines.push(format!("MUSICBRAINZ_RELEASETRACKID = \"{}\"", id)); }
                                let artist_id = track.get("artist-credit").or_else(|| track.get("recording").and_then(|r| r.get("artist-credit")))
                                    .and_then(|a| a.as_array()).and_then(|a| a.first()).and_then(|c| c.get("artist")).and_then(|a| a.get("id")).and_then(|i| i.as_str());
                                if let Some(id) = artist_id { lines.push(format!("MUSICBRAINZ_ARTISTID = \"{}\"", id)); }
                            }
                            lines.push("".to_string());
                        }
                    }
                }
            }
        }
    } else if let Some(master) = dg.get("master") {
        if let Some(tracklist) = master.get("tracklist").and_then(|t| t.as_array()) {
            let tracks: Vec<&Value> = tracklist.iter().filter(|t| t.get("type_").and_then(|ty| ty.as_str()) == Some("track")).collect();
            for (i, track) in tracks.iter().enumerate() {
                lines.push("[[tracks]]".to_string());
                lines.push(format!("TRACKNUMBER = {}", i + 1));
                if let Some(t) = track.get("title").and_then(|t| t.as_str()) { lines.push(format!("TITLE = \"{}\"", t)); }
                lines.push("".to_string());
            }
        }
    }
}
