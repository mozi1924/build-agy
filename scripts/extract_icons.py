#!/usr/bin/env python3
"""
Icon extraction utility for Antigravity packages.
- Antigravity Hub: Pure Python extraction of icon.png from resources/app.asar
- Antigravity IDE: Extraction of resources/app/resources/linux/code.png
"""

import json
import os
import struct
import tarfile
from pathlib import Path

def extract_asar_file(asar_path: Path, internal_filename: str, out_path: Path) -> bool:
    """
    Extract a single file from an Electron ASAR archive using pure Python.
    Format:
    - 4 bytes: [unknown/magic]
    - 4 bytes: header_size (uint32 LE)
    - 4 bytes: header_size - 4 (uint32 LE)
    - 4 bytes: json_size (uint32 LE)
    - json_size bytes: JSON header mapping filenames to metadata
    - binary payload starts at: 8 + header_size
    """
    try:
        with asar_path.open("rb") as f:
            f.read(4)
            header_size = struct.unpack("<I", f.read(4))[0]
            f.read(4)
            json_size = struct.unpack("<I", f.read(4))[0]
            header = json.loads(f.read(json_size).decode("utf-8"))
            
            files = header.get("files", {})
            file_meta = files.get(internal_filename)
            if not file_meta:
                # Some asars nest files inside directories
                for k, v in files.items():
                    if isinstance(v, dict) and "files" in v:
                        if internal_filename in v["files"]:
                            file_meta = v["files"][internal_filename]
                            break
            
            if not file_meta or "offset" not in file_meta or "size" not in file_meta:
                return False
                
            offset = int(file_meta["offset"])
            size = int(file_meta["size"])
            f.seek(8 + header_size + offset)
            payload = f.read(size)
            
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(payload)
            return True
    except Exception as e:
        print(f"[-] Error extracting from ASAR {asar_path}: {e}")
        return False

def extract_hub_icon(extracted_hub_dir: Path, out_icon_path: Path) -> bool:
    """Finds app.asar in Antigravity Hub directory and extracts icon.png."""
    asar_candidates = list(extracted_hub_dir.glob("**/resources/app.asar"))
    if not asar_candidates:
        print(f"[-] No app.asar found in {extracted_hub_dir}")
        return False
    
    asar = asar_candidates[0]
    return extract_asar_file(asar, "icon.png", out_icon_path)

def extract_ide_icon(extracted_ide_dir: Path, out_icon_path: Path) -> bool:
    """Finds code.png in Antigravity IDE directory and copies it."""
    code_png_candidates = list(extracted_ide_dir.glob("**/resources/app/resources/linux/code.png"))
    if not code_png_candidates:
        # Fallback to any code.png or icon.png
        code_png_candidates = list(extracted_ide_dir.glob("**/code.png"))
        
    if code_png_candidates:
        src = code_png_candidates[0]
        out_icon_path.parent.mkdir(parents=True, exist_ok=True)
        out_icon_path.write_bytes(src.read_bytes())
        return True
    return False

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 4:
        print("Usage: extract_icons.py [hub|ide] <extracted_dir> <output_icon.png>")
        sys.exit(1)
        
    kind = sys.argv[1]
    src_dir = Path(sys.argv[2])
    out_icon = Path(sys.argv[3])
    
    if kind == "hub":
        ok = extract_hub_icon(src_dir, out_icon)
    else:
        ok = extract_ide_icon(src_dir, out_icon)
        
    if ok:
        print(f"[✓] Successfully extracted icon to {out_icon}")
    else:
        print("[-] Icon extraction failed")
        sys.exit(1)
