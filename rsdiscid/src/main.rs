mod format;
mod local;
mod remote;
mod utils;

use clap::Parser;
use std::fs;
use std::path::PathBuf;

#[derive(Parser)]
#[command(name = "rsdiscid", version = "0.1", about = "Audio utilities for FLAC disc ID calculation and metadata fetching")]
struct Cli {
    #[arg(long)]
    metadata: bool,

    #[arg(long)]
    mbid: bool,

    target: Option<String>,
}

fn main() {
    let cli = Cli::parse();
    let mut target = cli.target.clone();

    if target.is_none() && (cli.metadata || cli.mbid) {
        if let Ok(content) = fs::read_to_string("metadata.toml") {
            match toml::from_str::<toml::Value>(&content) {
                Ok(meta) => {
                    if let Some(url) = meta.get("album")
                        .and_then(|a| a.get("MUSICBRAINZ_URL"))
                        .and_then(|u| u.as_str()) 
                    {
                        target = Some(url.to_string());
                    }
                }
                Err(e) => {
                    eprintln!("Error: Found metadata.toml but failed to parse it: {}", e);
                    std::process::exit(1);
                }
            }
        }
    }

    if let Some(target_val) = target {
        if target_val.starts_with("http") {
            let data = remote::fetch_remote_metadata(&target_val).expect("Failed to fetch remote metadata");
            let mut final_lines = Vec::new();

            if cli.mbid {
                final_lines.extend(format::get_mbid_lines(&data));
            }
            if cli.metadata {
                if !final_lines.is_empty() {
                    final_lines.push(String::new());
                }
                final_lines.extend(format::get_metadata_lines(&data));
            }

            if !cli.mbid && !cli.metadata {
                println!("{}", serde_json::to_string_pretty(&data).unwrap());
            } else {
                println!("{}", final_lines.join("\n").trim_end());
            }
        } else {
            local::calculate_local_ids(&PathBuf::from(target_val));
        }
    } else {
        if cli.metadata || cli.mbid {
            eprintln!("Error: No URL provided and MUSICBRAINZ_URL not found in metadata.toml");
            std::process::exit(1);
        } else {
            local::calculate_local_ids(&PathBuf::from("."));
        }
    }
}
