#!/usr/bin/env python
import sys
import os
import glob
import base64
import hashlib
import re
import discid
from mutagen.flac import FLAC

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

def calculate_ids(folder_path):
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
    
    if freedb != "Error":
        accuraterip = f"{id1:08x}-{id2:08x}-{freedb.lower()}"
    else:
        accuraterip = "Error"

    pregap = offsets[0]
    x = ""
    for offset in offsets[1:]:
        x += f"{offset - pregap:08X}"
    x += f"{leadout - pregap:08X}"
    
    sha1 = hashlib.sha1(x.ljust(800, '0').encode('ascii')).digest()
    ctdb = base64.b64encode(sha1).decode('ascii').replace('+', '.').replace('/', '_').replace('=', '-')

    print(f"MUSICBRAINZ DISCID  : {mbid}")
    print(f"FREEDB DISCID       : {freedb}")
    print(f"ACCURATERIP ID      : {accuraterip}")
    print(f"CTDB TOCID          : {ctdb}")
    print("-" * 50)
    print(f'CTDBID_URL = "http://db.cuetools.net/?tocid={ctdb}"')

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    calculate_ids(target)
