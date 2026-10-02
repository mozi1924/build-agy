#!/usr/bin/env python3
"""
Publishes a GitHub Release with built .deb and .rpm assets, changelogs,
and APT flat repository index files (Packages, Packages.gz, Release).
"""

import argparse
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
    parser = argparse.ArgumentParser(description="Publish or update GitHub release with packages and indices.")
    parser.add_argument("--tag", dest="tag", help="Explicit GitHub Release tag to create or update")
    parser.add_argument("--upload-indices-only", dest="indices_only", action="store_true", help="Only upload/update repository indices (Packages, Release) to existing release")
    args = parser.parse_args()

    if not METADATA_FILE.exists():
        print("metadata.json not found.")
        sys.exit(0)

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    flat_indices = [
        DIST_DIR / "deb" / "Packages",
        DIST_DIR / "deb" / "Packages.gz",
        DIST_DIR / "deb" / "Release",
    ]
    existing_indices = [f for f in flat_indices if f.exists()]

    if args.indices_only:
        all_assets = existing_indices
        if not all_assets:
            print("No flat repository index files found to upload.")
            sys.exit(0)
    else:
        deb_files = list((DIST_DIR / "deb").glob("*.deb"))
        rpm_files = list((DIST_DIR / "rpm").glob("*.rpm"))
        all_assets = deb_files + rpm_files + existing_indices
        if not all_assets:
            print("No packages or index files found to release.")
            sys.exit(0)

    # Determine release tag
    if args.tag:
        tag_name = args.tag
    elif "RELEASE_TAG" in os.environ and os.environ["RELEASE_TAG"]:
        tag_name = os.environ["RELEASE_TAG"]
    elif args.indices_only:
        # If updating indices only and no tag passed, get latest release tag
        res = subprocess.run("gh release list -L 1 --json tagName -q '.[0].tagName'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            tag_name = res.stdout.strip()
        else:
            tag_name = f"v{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    else:
        tag_name = f"v{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"

    file_args = " ".join([f"'{f}'" for f in all_assets])

    # Check if release already exists
    res_chk = subprocess.run(f"gh release view '{tag_name}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res_chk.returncode == 0:
        print(f"Release {tag_name} already exists. Uploading/updating assets with --clobber...")
        cmd = f"gh release upload '{tag_name}' {file_args} --clobber"
        res = subprocess.run(cmd, shell=True, text=True)
        if res.returncode == 0:
            print(f"[✓] Successfully uploaded assets to existing release: {tag_name}")
        else:
            print(f"[-] Asset upload failed: returncode {res.returncode}")
    else:
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

        cmd = f"gh release create '{tag_name}' {file_args} --title '{title}' --notes-file '{notes_file}'"
        print(f"Creating GitHub release: {tag_name}...")
        res = subprocess.run(cmd, shell=True, text=True)
        if res.returncode == 0:
            print(f"[✓] Successfully published GitHub release: {tag_name}")
        else:
            print(f"[-] Release creation skipped or failed: returncode {res.returncode}")

    # Update versions.json
    new_versions = {
        "cli": {
            "version": meta["cli"]["version"]
        },
        "hub": {
            "version": meta["hub"]["version"],
            "build": meta["hub"].get("build")
        },
        "ide": {
            "version": meta["ide"]["version"],
            "build": meta["ide"].get("build")
        },
        "last_updated": datetime.now(timezone.utc).isoformat()
    }
    VERSIONS_FILE.write_text(json.dumps(new_versions, indent=2), encoding="utf-8")
    print(f"[✓] Updated {VERSIONS_FILE}")

if __name__ == "__main__":
    main()
