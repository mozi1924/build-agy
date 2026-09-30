#!/usr/bin/env python3
"""
Antigravity Repository Generator
Generates:
1. APT Flat repository (Debian/Ubuntu) in dist/deb/ for publishing to GitHub Release
2. RPM repository (Fedora/RHEL/CentOS/openSUSE) in public/rpm/ using location-prefix
   pointing to GitHub Releases (zero RPM files stored on GitHub Pages)
"""

import argparse
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
PUBLIC_DIR = BASE_DIR / "public"
DEBIAN_DIR = PUBLIC_DIR / "debian"
RPM_DIR = PUBLIC_DIR / "rpm"
METADATA_FILE = BASE_DIR / "metadata.json"

def log(msg: str):
    print(f"[update_repo] {msg}")

def calc_hash(path: Path, algo: str) -> str:
    h = getattr(hashlib, algo)()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

def get_repo_info():
    default_user = "mozi1924"
    default_repo = "build-agy"
    try:
        res = subprocess.run("git remote get-url origin", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            url = res.stdout.strip()
            m = re.search(r"github\.com[:/]([^/]+)/([^/\.]+)", url)
            if m:
                return m.group(1), m.group(2)
    except Exception:
        pass
    return default_user, default_repo

def get_release_tag(explicit_tag: str = None) -> str:
    if explicit_tag:
        return explicit_tag
    if "RELEASE_TAG" in os.environ and os.environ["RELEASE_TAG"]:
        return os.environ["RELEASE_TAG"]
    try:
        res = subprocess.run("gh release list -L 1 --json tagName -q '.[0].tagName'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip()
    except Exception:
        pass
    if METADATA_FILE.exists():
        import json
        with open(METADATA_FILE, "r", encoding="utf-8") as f:
            meta = json.load(f)
            ide_ver = meta.get("ide", {}).get("version", "latest")
            return f"v{ide_ver}"
    return "latest"

def extract_deb_control(deb_path: Path) -> dict:
    """Extracts control fields from a .deb archive."""
    cmd = f"dpkg-deb -I '{deb_path}'"
    res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"Failed to inspect {deb_path}: {res.stderr}")
    
    fields = {}
    current_key = None
    for line in res.stdout.splitlines():
        if line.startswith(" Package:"):
            current_key = "Package"
            fields[current_key] = line.split(":", 1)[1].strip()
        elif line.startswith(" ") and ":" in line and not line.startswith("   "):
            parts = line.strip().split(":", 1)
            current_key = parts[0].strip()
            fields[current_key] = parts[1].strip()
        elif line.startswith("  ") and current_key:
            fields[current_key] += "\n" + line

    # In flat repo, Filename is relative to flat repo root (the release asset filename)
    fields["Filename"] = deb_path.name
    fields["Size"] = str(deb_path.stat().st_size)
    fields["MD5sum"] = calc_hash(deb_path, "md5")
    fields["SHA1"] = calc_hash(deb_path, "sha1")
    fields["SHA256"] = calc_hash(deb_path, "sha256")
    return fields

def generate_apt_flat_repo():
    log("=== Generating APT Flat Repository for Releases ===")
    deb_dir = DIST_DIR / "deb"
    deb_files = sorted(list(deb_dir.glob("*.deb")))
    if not deb_files:
        log("[-] No .deb files found in dist/deb/")
        return

    package_entries = []
    architectures = set()

    for deb in deb_files:
        ctrl = extract_deb_control(deb)
        architectures.add(ctrl.get("Architecture", "all"))
        entry_lines = []
        for k in ["Package", "Version", "Architecture", "Maintainer", "Installed-Size", "Depends", "Provides", "Replaces", "Section", "Priority", "Filename", "Size", "SHA256", "SHA1", "MD5sum", "Description"]:
            if k in ctrl:
                entry_lines.append(f"{k}: {ctrl[k]}")
        package_entries.append("\n".join(entry_lines))

    packages_content = "\n\n".join(package_entries) + ("\n" if package_entries else "")
    
    packages_file = deb_dir / "Packages"
    packages_gz_file = deb_dir / "Packages.gz"
    
    packages_file.write_text(packages_content, encoding="utf-8")
    with open(packages_file, "rb") as f_in, gzip.open(packages_gz_file, "wb", compresslevel=9) as f_out:
        shutil.copyfileobj(f_in, f_out)

    # Generate Release file
    date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S UTC")
    arch_str = " ".join(sorted(architectures)) if architectures else "amd64 arm64"
    release_lines = [
        "Origin: Antigravity Community",
        "Label: Antigravity",
        "Suite: stable",
        "Codename: stable",
        f"Date: {date_str}",
        f"Architectures: {arch_str}",
        "Description: Google Antigravity (CLI, Hub, IDE) Community Flat Repository for Linux",
        "MD5Sum:",
    ]
    
    release_files = {
        "Packages": packages_file,
        "Packages.gz": packages_gz_file,
    }
    
    for name, p_file in release_files.items():
        release_lines.append(f" {calc_hash(p_file, 'md5')} {p_file.stat().st_size:>8} {name}")
    release_lines.append("SHA1:")
    for name, p_file in release_files.items():
        release_lines.append(f" {calc_hash(p_file, 'sha1')} {p_file.stat().st_size:>8} {name}")
    release_lines.append("SHA256:")
    for name, p_file in release_files.items():
        release_lines.append(f" {calc_hash(p_file, 'sha256')} {p_file.stat().st_size:>8} {name}")

    release_file = deb_dir / "Release"
    release_file.write_text("\n".join(release_lines) + "\n", encoding="utf-8")
    log(f"[✓] Created APT Flat indices in dist/deb/: Packages, Packages.gz, Release")

    # Clean any legacy public/debian folder so Pages has 0 deb files
    if DEBIAN_DIR.exists():
        log(f"Cleaning legacy {DEBIAN_DIR} to save GitHub Pages storage and bandwidth...")
        shutil.rmtree(DEBIAN_DIR, ignore_errors=True)

def generate_rpm_repo(release_tag: str):
    log("=== Generating RPM Repository ===")
    user, repo = get_repo_info()
    prefix = f"https://github.com/{user}/{repo}/releases/download/{release_tag}/"
    log(f"Using location-prefix: {prefix}")
    
    arches = ["x86_64", "aarch64"]
    rpm_dir = DIST_DIR / "rpm"
    rpm_files = list(rpm_dir.glob("*.rpm"))
    if not rpm_files:
        log("[-] No .rpm files found in dist/rpm/")
        return

    for arch in arches:
        arch_dir = RPM_DIR / arch
        arch_dir.mkdir(parents=True, exist_ok=True)

        matching = [r for r in rpm_files if f".{arch}.rpm" in r.name or ".noarch.rpm" in r.name]
        if not matching:
            log(f"[-] No matching RPM packages for {arch}")
            continue

        with tempfile.TemporaryDirectory() as td:
            staging_dir = Path(td) / arch
            staging_dir.mkdir()
            for r in matching:
                dest = staging_dir / r.name
                os.symlink(r.resolve(), dest)

            log(f"Running createrepo_c for {arch} ({len(matching)} packages)...")
            cmd = f"createrepo_c --general-compress-type=gz --location-prefix '{prefix}' --outputdir '{arch_dir}' '{staging_dir}'"
            res = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                log(f"createrepo_c failed: {res.stderr}")
                raise RuntimeError("createrepo_c failed")

        # Ensure no .rpm files exist in arch_dir
        for orphan_rpm in arch_dir.glob("*.rpm"):
            orphan_rpm.unlink()

        log(f"[✓] Created RPM repodata for {arch} (0 RPM files stored in public/rpm/{arch})")

def main():
    parser = argparse.ArgumentParser(description="Generate APT flat repo indices and RPM repo with release redirects.")
    parser.add_argument("--tag", dest="tag", help="Explicit GitHub Release tag to point packages to")
    args = parser.parse_args()

    tag = get_release_tag(args.tag)
    log(f"Active release tag: {tag}")

    generate_apt_flat_repo()
    generate_rpm_repo(tag)
    log("[✓] All repository indices successfully updated (zero heavy packages in public/)")

if __name__ == "__main__":
    main()
