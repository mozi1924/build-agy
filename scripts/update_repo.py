#!/usr/bin/env python3
"""
Antigravity Repository Generator
Generates:
1. APT repository (Debian/Ubuntu) in public/debian/
2. RPM repository (Fedora/RHEL/CentOS/openSUSE) in public/rpm/
"""

import gzip
import hashlib
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
PUBLIC_DIR = BASE_DIR / "public"
DEBIAN_DIR = PUBLIC_DIR / "debian"
RPM_DIR = PUBLIC_DIR / "rpm"

def log(msg: str):
    print(f"[update_repo] {msg}")

def calc_hash(path: Path, algo: str) -> str:
    h = getattr(hashlib, algo)()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

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

    fields["Filename"] = f"pool/main/{deb_path.name}"
    fields["Size"] = str(deb_path.stat().st_size)
    fields["MD5sum"] = calc_hash(deb_path, "md5")
    fields["SHA1"] = calc_hash(deb_path, "sha1")
    fields["SHA256"] = calc_hash(deb_path, "sha256")
    return fields

def generate_apt_repo():
    log("=== Generating APT Repository ===")
    pool_dir = DEBIAN_DIR / "pool" / "main"
    pool_dir.mkdir(parents=True, exist_ok=True)

    # Copy deb files to pool/main
    deb_files = list((DIST_DIR / "deb").glob("*.deb"))
    if not deb_files:
        log("[-] No .deb files found in dist/deb/")
        return

    for deb in deb_files:
        dest = pool_dir / deb.name
        shutil.copy2(deb, dest)

    dists_dir = DEBIAN_DIR / "dists" / "stable"
    architectures = ["amd64", "arm64"]

    release_file_entries = {}

    for arch in architectures:
        bin_dir = dists_dir / "main" / f"binary-{arch}"
        bin_dir.mkdir(parents=True, exist_ok=True)

        packages_file = bin_dir / "Packages"
        packages_gz_file = bin_dir / "Packages.gz"

        matching_debs = [p for p in pool_dir.glob("*.deb") if f"_{arch}.deb" in p.name or "_all.deb" in p.name]
        package_entries = []

        for deb in matching_debs:
            ctrl = extract_deb_control(deb)
            entry_lines = []
            for k in ["Package", "Version", "Architecture", "Maintainer", "Installed-Size", "Depends", "Provides", "Replaces", "Section", "Priority", "Filename", "Size", "SHA256", "SHA1", "MD5sum", "Description"]:
                if k in ctrl:
                    entry_lines.append(f"{k}: {ctrl[k]}")
            package_entries.append("\n".join(entry_lines))

        packages_content = "\n\n".join(package_entries) + ("\n" if package_entries else "")
        packages_file.write_text(packages_content, encoding="utf-8")

        # Compress to Packages.gz
        with open(packages_file, "rb") as f_in, gzip.open(packages_gz_file, "wb", compresslevel=9) as f_out:
            shutil.copyfileobj(f_in, f_out)

        for p_file in [packages_file, packages_gz_file]:
            rel_path = f"main/binary-{arch}/{p_file.name}"
            release_file_entries[rel_path] = {
                "size": p_file.stat().st_size,
                "md5": calc_hash(p_file, "md5"),
                "sha1": calc_hash(p_file, "sha1"),
                "sha256": calc_hash(p_file, "sha256"),
            }

    # Generate Release file
    date_str = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S UTC")
    release_lines = [
        "Origin: Antigravity Community",
        "Label: Antigravity",
        "Suite: stable",
        "Codename: stable",
        f"Date: {date_str}",
        f"Architectures: {' '.join(architectures)}",
        "Components: main",
        "Description: Google Antigravity (CLI, Hub, IDE) Community Repository for Linux",
        "MD5Sum:",
    ]
    for rel_path, info in release_file_entries.items():
        release_lines.append(f" {info['md5']} {info['size']:>8} {rel_path}")

    release_lines.append("SHA1:")
    for rel_path, info in release_file_entries.items():
        release_lines.append(f" {info['sha1']} {info['size']:>8} {rel_path}")

    release_lines.append("SHA256:")
    for rel_path, info in release_file_entries.items():
        release_lines.append(f" {info['sha256']} {info['size']:>8} {rel_path}")

    release_file = dists_dir / "Release"
    release_file.write_text("\n".join(release_lines) + "\n", encoding="utf-8")
    log(f"[✓] Created APT Release file: {release_file}")

def generate_rpm_repo():
    log("=== Generating RPM Repository ===")
    arches = ["x86_64", "aarch64"]
    rpm_files = list((DIST_DIR / "rpm").glob("*.rpm"))
    if not rpm_files:
        log("[-] No .rpm files found in dist/rpm/")
        return

    for arch in arches:
        arch_dir = RPM_DIR / arch
        arch_dir.mkdir(parents=True, exist_ok=True)

        matching = [r for r in rpm_files if f".{arch}.rpm" in r.name or ".noarch.rpm" in r.name]
        for rpm in matching:
            shutil.copy2(rpm, arch_dir / rpm.name)

        if matching:
            log(f"Running createrepo_c for {arch} ({len(matching)} packages)...")
            res = subprocess.run(f"createrepo_c --update '{arch_dir}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode != 0:
                log(f"createrepo_c failed: {res.stderr}")
                raise RuntimeError("createrepo_c failed")
            log(f"[✓] Created RPM repodata for {arch}")

def main():
    generate_apt_repo()
    generate_rpm_repo()
    log("[✓] All repository indices successfully updated in public/")

if __name__ == "__main__":
    main()
