use rayon::prelude::*;
use serde::{Deserialize, Serialize};
use std::fs;
use std::path::{Path, PathBuf};
use std::process::Command;
use walkdir::WalkDir;

#[derive(Deserialize)]
struct Config {
    source_dir: String,
    dest_root: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct LockFile {
    album: Album,
    tracks: Vec<Track>,
}

#[derive(Debug, Deserialize, Serialize)]
struct Album {
    ALBUM: String,
    ALBUMARTIST: String,
    DATE: String,
    GENRE: Vec<String>,
    info: AlbumInfo,
}

#[derive(Debug, Deserialize, Serialize)]
struct AlbumInfo {
    album_path: String,
}

#[derive(Debug, Deserialize, Serialize)]
struct Track {
    ARTIST: String,
    DISCNUMBER: u32,
    TITLE: String,
    TRACKNUMBER: u32,
    info: TrackInfo,
}

#[derive(Debug, Deserialize, Serialize)]
struct TrackInfo {
    track_path: String,
}

struct AlbumTask {
    lock_data: LockFile,
    source_dir: PathBuf,
}

fn main() {
    let config_content = fs::read_to_string("config.toml")
        .expect("Failed to read config.toml in root directory");
    let config: Config = toml::from_str(&config_content)
        .expect("Failed to parse config.toml");

    let tasks: Vec<AlbumTask> = WalkDir::new(&config.source_dir)
        .into_iter()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_name() == "metadata.lock.json")
        .filter_map(|e| {
            let content = fs::read_to_string(e.path()).ok()?;
            let lock_data: LockFile = serde_json::from_str(&content).ok()?;
            Some(AlbumTask {
                lock_data,
                source_dir: e.path().parent()?.to_path_buf(),
            })
        })
        .collect();

    tasks.into_par_iter().for_each(|task| {
        process_album(task, &config.dest_root);
    });
}

fn process_album(task: AlbumTask, dest_root: &str) {
    let dest_album_dir = Path::new(dest_root).join(&task.lock_data.album.info.album_path);

    if dest_album_dir.join("metadata.toml").exists() {
        return;
    }

    if fs::create_dir_all(&dest_album_dir).is_err() {
        return;
    }

    if let Ok(entries) = fs::read_dir(&task.source_dir) {
        for entry in entries.filter_map(|e| e.ok()) {
            let path = entry.path();
            if path.is_file() {
                if let Some(ext) = path.extension() {
                    if ext.to_string_lossy().to_lowercase() == "flac" {
                        continue;
                    }
                }
                let dest_file = dest_album_dir.join(entry.file_name());
                let _ = fs::copy(&path, &dest_file);
            }
        }
    }

    let genre = task.lock_data.album.GENRE.first().cloned().unwrap_or_else(|| "Unknown".to_string());

    for track in &task.lock_data.tracks {
        let input_file = task.source_dir.join(&track.info.track_path);
        let output_file_name = format!("{}.opus", Path::new(&track.info.track_path).file_stem().unwrap_or_default().to_string_lossy());
        let output_file = dest_album_dir.join(output_file_name);

        let _ = Command::new("ffmpeg")
            .arg("-hide_banner")
            .arg("-loglevel")
            .arg("error")
            .arg("-n")
            .arg("-i")
            .arg(&input_file)
            .arg("-c:a")
            .arg("libopus")
            .arg("-b:a")
            .arg("128k")
            .arg("-metadata")
            .arg(format!("ALBUM={}", task.lock_data.album.ALBUM))
            .arg("-metadata")
            .arg(format!("ALBUMARTIST={}", task.lock_data.album.ALBUMARTIST))
            .arg("-metadata")
            .arg(format!("DATE={}", task.lock_data.album.DATE))
            .arg("-metadata")
            .arg(format!("GENRE={}", genre))
            .arg("-metadata")
            .arg(format!("ARTIST={}", track.ARTIST))
            .arg("-metadata")
            .arg(format!("TITLE={}", track.TITLE))
            .arg("-metadata")
            .arg(format!("DISCNUMBER={}", track.DISCNUMBER))
            .arg("-metadata")
            .arg(format!("TRACKNUMBER={}", track.TRACKNUMBER))
            .arg(&output_file)
            .status();
    }
}
