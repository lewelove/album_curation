import os
import shutil
import subprocess
import urllib.parse
import tomllib
from pathlib import Path

def setup_album():
    pwd = Path.cwd()
    image_exts = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".tiff", ".bmp", ".pdf"}
    keep_exts = {".toml", ".flac", ".opus", ".json"}
    
    covers_dir = pwd / "Digital Covers"
    info_dir = pwd / "Info"

    for item in pwd.iterdir():
        if not item.is_file() or item.name.startswith("."):
            continue
            
        ext = item.suffix.lower()
        
        if ext in image_exts:
            covers_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(covers_dir / item.name))
        elif ext not in keep_exts:
            info_dir.mkdir(exist_ok=True)
            shutil.move(str(item), str(info_dir / item.name))

if __name__ == "__main__":
    setup_album()
