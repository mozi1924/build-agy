#!/usr/bin/env python3
"""
Publishes a GitHub Release with built .deb and .rpm assets and changelogs.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
METADATA_FILE = BASE_DIR / "metadata.json"
VERSIONS_FILE = BASE_DIR / "versions.json"

def main():
    if not METADATA_FILE.exists():
        print("metadata.json not found.")
        sys.exit(0)

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    # Collect all deb and rpm files
    deb_files = list((DIST_DIR / "deb").glob("*.deb"))
    rpm_files = list((DIST_DIR / "rpm").glob("*.rpm"))
    all_packages = deb_files + rpm_files

    if not all_packages:
        print("No packages found to release.")
        sys.exit(0)

    # Generate release tag: e.g. v2026.09.30 or based on IDE version
    ide_ver = meta.get("ide", {}).get("version", "latest")
    date_tag = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
    tag_name = f"v{ide_ver}-{date_tag}"
    title = f"Antigravity Release (IDE v{meta['ide']['version']} / Hub v{meta['hub']['version']} / CLI v{meta['cli']['version']})"

    notes_lines = [
        f"## Antigravity Linux Packages Release",
        f"",
        f"- **Antigravity IDE**: `v{meta['ide']['version']}`",
        f"- **Antigravity 2.0 (Hub)**: `v{meta['hub']['version']}`",
        f"- **Antigravity CLI**: `v{meta['cli']['version']}`",
        f"",
        f"### 📋 Official Changelogs",
    ]

    for comp, name in [("ide", "Antigravity IDE"), ("hub", "Antigravity Hub"), ("cli", "Antigravity CLI")]:
        ch = meta.get(comp, {}).get("changelog", {})
        if ch and ch.get("items"):
            notes_lines.append(f"#### {name} (v{meta[comp]['version']}): {ch.get('title', '')}")
            for item in ch["items"][:5]:
                notes_lines.append(f"- {item}")
            notes_lines.append("")

    notes_lines.append("### 📦 Repository Usage")
    notes_lines.append("Visit the [Repository Portal](https://mozi1924.github.io/build-agy) for one-click setup on Debian, Ubuntu, Fedora, RHEL, and openSUSE.")
    
    notes_body = "\n".join(notes_lines)

    notes_file = BASE_DIR / "release_notes.md"
    notes_file.write_text(notes_body, encoding="utf-8")

    file_args = " ".join([f"'{f}'" for f in all_packages])
    cmd = f"gh release create '{tag_name}' {file_args} --title '{title}' --notes-file '{notes_file}'"
    print(f"Creating GitHub release: {tag_name}...")
    res = subprocess.run(cmd, shell=True, text=True)
    if res.returncode == 0:
        print(f"[✓] Successfully published GitHub release: {tag_name}")
    else:
        print(f"[-] Release creation skipped or failed: returncode {res.returncode}")

    # Update versions.json
    new_versions = {
        "cli": {"version": meta["cli"]["version"]},
        "hub": {"version": meta["hub"]["version"]},
        "ide": {"version": meta["ide"]["version"]},
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    VERSIONS_FILE.write_text(json.dumps(new_versions, indent=2), encoding="utf-8")
    print(f"[✓] Updated {VERSIONS_FILE}")

if __name__ == "__main__":
    main()
