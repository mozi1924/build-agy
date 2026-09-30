#!/usr/bin/env python3
"""
Antigravity Package Builder
Builds .deb and .rpm packages for Antigravity components:
- cli (antigravity-cli, agy)
- hub (antigravity, antigravity-hub)
- ide (antigravity-ide, agy-ide)
"""

import argparse
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = BASE_DIR / "scripts"
TEMPLATES_DIR = BASE_DIR / "templates"
CACHE_DIR = BASE_DIR / "cache"
DIST_DIR = BASE_DIR / "dist"
DEB_OUT_DIR = DIST_DIR / "deb"
RPM_OUT_DIR = DIST_DIR / "rpm"

sys.path.insert(0, str(SCRIPTS_DIR))
from extract_icons import extract_hub_icon, extract_ide_icon

# Architecture mapping
ARCH_MAP_DEB = {
    "x86_64": "amd64",
    "amd64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
}

ARCH_MAP_RPM = {
    "x86_64": "x86_64",
    "amd64": "x86_64",
    "aarch64": "aarch64",
    "arm64": "aarch64",
}

def log(msg: str):
    print(f"[build_packages] {msg}")

def download_file(url: str, dest_path: Path, expected_sha512: str = None) -> bool:
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    if dest_path.exists():
        if expected_sha512:
            calc_hash = hashlib.sha512(dest_path.read_bytes()).hexdigest()
            if calc_hash == expected_sha512:
                log(f"Cached archive matches expected SHA512: {dest_path.name}")
                return True
            log(f"Cached file hash mismatch, re-downloading {dest_path.name}")
        else:
            log(f"Using cached file: {dest_path.name}")
            return True

    log(f"Downloading {url} -> {dest_path}...")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out:
        shutil.copyfileobj(resp, out)

    if expected_sha512:
        calc_hash = hashlib.sha512(dest_path.read_bytes()).hexdigest()
        if calc_hash != expected_sha512:
            log(f"Error: Downloaded checksum mismatch for {dest_path.name}!")
            return False

    return True

def run_cmd(cmd, cwd=None):
    res = subprocess.run(cmd, shell=True, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0:
        log(f"Command failed: {cmd}\nOutput: {res.stdout}\nError: {res.stderr}")
        raise RuntimeError(f"Command failed: {cmd}")
    return res.stdout

def create_deb_package(pkg_name: str, version: str, deb_arch: str, staging_dir: Path, description: str, provides: list, depends: list, postinst_lines: list = None) -> Path:
    deb_dir = staging_dir / "DEBIAN"
    deb_dir.mkdir(parents=True, exist_ok=True)
    
    # Calculate installed size in KB
    total_size = sum(f.stat().st_size for f in staging_dir.rglob('*') if f.is_file())
    installed_size = max(1, total_size // 1024)

    control_content = f"""Package: {pkg_name}
Version: {version}-1
Section: devel
Priority: optional
Architecture: {deb_arch}
Maintainer: Antigravity Community Maintainers <https://github.com/mozi1924/build-agy>
Installed-Size: {installed_size}
Depends: {', '.join(depends)}
Provides: {', '.join(provides)}
Replaces: {', '.join(provides)}
Description: {description}
 Repackaged from official Google Antigravity Linux binaries.
"""
    (deb_dir / "control").write_text(control_content.strip() + "\n", encoding="utf-8")
    os.chmod(deb_dir / "control", 0o644)

    # Postinst
    postinst_script = ["#!/bin/sh", "set -e"]
    if postinst_lines:
        postinst_script.extend(postinst_lines)
    postinst_script.append("exit 0\n")
    (deb_dir / "postinst").write_text("\n".join(postinst_script), encoding="utf-8")
    os.chmod(deb_dir / "postinst", 0o755)

    # Postrm
    postrm_script = """#!/bin/sh
set -e
if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database /usr/share/applications >/dev/null 2>&1 || true
fi
if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache -q /usr/share/icons/hicolor >/dev/null 2>&1 || true
fi
exit 0
"""
    (deb_dir / "postrm").write_text(postrm_script, encoding="utf-8")
    os.chmod(deb_dir / "postrm", 0o755)

    DEB_OUT_DIR.mkdir(parents=True, exist_ok=True)
    deb_filename = f"{pkg_name}_{version}-1_{deb_arch}.deb"
    deb_path = DEB_OUT_DIR / deb_filename
    
    log(f"Building DEB: {deb_filename}...")
    run_cmd(f"dpkg-deb --build --root-owner-group '{staging_dir}' '{deb_path}'")
    log(f"[✓] Created DEB: {deb_path}")
    return deb_path

def create_rpm_package(pkg_name: str, version: str, rpm_arch: str, staging_dir: Path, description: str, provides: list, changelog_entry: str = None) -> Path:
    rpmbuild_root = staging_dir.parent / "rpmbuild"
    shutil.rmtree(rpmbuild_root, ignore_errors=True)
    for sub in ["BUILD", "RPMS", "SOURCES", "SPECS", "SRPMS"]:
        (rpmbuild_root / sub).mkdir(parents=True, exist_ok=True)

    provides_directives = "\n".join([f"Provides: {p} = {version}-1" for p in provides])
    
    # Format changelog
    if not changelog_entry:
        changelog_entry = "- Update to official release version"
    
    spec_content = f"""%global debug_package %{{nil}}
%global __os_install_post %{{nil}}
%global __strip /bin/true
%undefine __brp_check_rpaths
%undefine __brp_strip
%undefine __brp_strip_comment_note
%undefine __brp_strip_static_archive
%global __provides_exclude_from ^/opt/.*\\.so.*$
%global __requires_exclude_from ^/opt/.*\\.so.*$
%global __requires_exclude ^(libffmpeg\\.so|libmsalruntime\\.so|/usr/bin/node|/usr/bin/perl|/usr/bin/python3)

Name:           {pkg_name}
Version:        {version}
Release:        1%{{?dist}}
Summary:        {description}
License:        Proprietary (Google Terms of Service)
URL:            https://antigravity.google
{provides_directives}

%description
{description}. Repackaged from official Google Linux binaries.

%install
cp -a {staging_dir}/* %{{buildroot}}/
rm -rf %{{buildroot}}/DEBIAN

%post
if [ -x /usr/bin/update-desktop-database ]; then
    /usr/bin/update-desktop-database %{{_datadir}}/applications &> /dev/null || :
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    /usr/bin/gtk-update-icon-cache %{{_datadir}}/icons/hicolor &> /dev/null || :
fi

%postun
if [ -x /usr/bin/update-desktop-database ]; then
    /usr/bin/update-desktop-database %{{_datadir}}/applications &> /dev/null || :
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    /usr/bin/gtk-update-icon-cache %{{_datadir}}/icons/hicolor &> /dev/null || :
fi

%files
/*

%changelog
* Wed Sep 30 2026 Antigravity Maintainers <https://github.com/mozi1924/build-agy> - {version}-1
{changelog_entry}
"""
    spec_file = rpmbuild_root / "SPECS" / f"{pkg_name}.spec"
    spec_file.write_text(spec_content, encoding="utf-8")

    RPM_OUT_DIR.mkdir(parents=True, exist_ok=True)
    log(f"Building RPM for {pkg_name} {version} ({rpm_arch})...")
    run_cmd(f"rpmbuild --target '{rpm_arch}' --define '_topdir {rpmbuild_root}' -bb '{spec_file}'")

    generated_rpms = list((rpmbuild_root / "RPMS" / rpm_arch).glob("*.rpm"))
    if not generated_rpms:
        raise RuntimeError(f"No RPM generated in {rpmbuild_root / 'RPMS' / rpm_arch}")
    
    target_rpm = RPM_OUT_DIR / generated_rpms[0].name
    shutil.copy2(generated_rpms[0], target_rpm)
    log(f"[✓] Created RPM: {target_rpm}")
    return target_rpm

def build_cli(meta: dict, arch_key: str):
    version = meta["version"]
    arch_info = meta[arch_key]
    url = arch_info["url"]
    sha512 = arch_info.get("sha512")
    deb_arch = ARCH_MAP_DEB[arch_key]
    rpm_arch = ARCH_MAP_RPM[arch_key]

    log(f"=== Building CLI ({version}, {arch_key}) ===")
    archive_name = f"cli_{version}_{arch_key}.tar.gz"
    archive_path = CACHE_DIR / archive_name
    if not download_file(url, archive_path, sha512):
        return False

    staging_dir = CACHE_DIR / f"staging_cli_{version}_{arch_key}"
    shutil.rmtree(staging_dir, ignore_errors=True)
    bin_dir = staging_dir / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)

    # Extract binary
    with tarfile.open(archive_path, "r:*") as tar:
        for member in tar.getmembers():
            if member.name.endswith("antigravity") or member.name.endswith("agy"):
                f = tar.extractfile(member)
                dest_bin = bin_dir / "agy"
                dest_bin.write_bytes(f.read())
                os.chmod(dest_bin, 0o755)
                break
    
    if not (bin_dir / "agy").exists():
        raise RuntimeError("Failed to extract CLI binary 'agy'/'antigravity'")

    # Symlink /usr/bin/antigravity-cli -> agy
    (bin_dir / "antigravity-cli").symlink_to("agy")

    desc = "Google Antigravity CLI (agy)"
    provides = ["antigravity-cli", "agy"]
    depends = ["libc6"]
    
    changelog_items = meta.get("changelog", {}).get("items", [])
    changelog_str = "\n".join([f"- {item}" for item in changelog_items[:5]]) if changelog_items else "- CLI release update"

    create_deb_package("antigravity-cli", version, deb_arch, staging_dir, desc, provides, depends)
    create_rpm_package("antigravity-cli", version, rpm_arch, staging_dir, desc, provides, changelog_str)
    return True

def build_hub(meta: dict, arch_key: str):
    version = meta["version"]
    arch_info = meta[arch_key]
    url = arch_info["url"]
    deb_arch = ARCH_MAP_DEB[arch_key]
    rpm_arch = ARCH_MAP_RPM[arch_key]

    log(f"=== Building Hub ({version}, {arch_key}) ===")
    archive_name = f"hub_{version}_{arch_key}.tar.gz"
    archive_path = CACHE_DIR / archive_name
    if not download_file(url, archive_path):
        return False

    staging_dir = CACHE_DIR / f"staging_hub_{version}_{arch_key}"
    shutil.rmtree(staging_dir, ignore_errors=True)
    
    opt_dest = staging_dir / "opt" / "antigravity"
    opt_dest.mkdir(parents=True, exist_ok=True)

    log("Extracting Hub tarball with system tar...")
    run_cmd(f"tar -xzf '{archive_path}' -C '{extracted_root}'")
    top_dirs = [d for d in extracted_root.iterdir() if d.is_dir()]
    source_dir = top_dirs[0] if top_dirs else extracted_root

    # Move to /opt/antigravity
    for item in source_dir.iterdir():
        shutil.move(str(item), str(opt_dest / item.name))

    # Icon
    icon_dest = staging_dir / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "antigravity.png"
    extract_hub_icon(opt_dest, icon_dest)

    # Desktop file
    apps_dir = staging_dir / "usr" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATES_DIR / "antigravity.desktop", apps_dir / "antigravity.desktop")

    # Symlinks: /usr/bin/antigravity and /usr/bin/agy-hub
    bin_dir = staging_dir / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "antigravity").symlink_to("/opt/antigravity/antigravity")
    (bin_dir / "agy-hub").symlink_to("/opt/antigravity/antigravity")

    # Permissions
    if (opt_dest / "chrome-sandbox").exists():
        os.chmod(opt_dest / "chrome-sandbox", 0o4755)

    desc = "Google Antigravity 2.0 Agent Platform"
    provides = ["antigravity", "antigravity-hub", "antigravity2"]
    depends = ["ca-certificates", "libasound2 | libasound2t64", "libnss3", "libatk-bridge2.0-0", "libgtk-3-0", "xdg-utils"]
    postinst_lines = [
        "if [ -f /opt/antigravity/chrome-sandbox ]; then chmod 4755 /opt/antigravity/chrome-sandbox || true; fi",
        "update-desktop-database /usr/share/applications || true",
        "gtk-update-icon-cache /usr/share/icons/hicolor || true",
    ]
    
    changelog_items = meta.get("changelog", {}).get("items", [])
    changelog_str = "\n".join([f"- {item}" for item in changelog_items[:5]]) if changelog_items else "- Antigravity 2.0 Hub update"

    create_deb_package("antigravity", version, deb_arch, staging_dir, desc, provides, depends, postinst_lines)
    create_rpm_package("antigravity", version, rpm_arch, staging_dir, desc, provides, changelog_str)
    return True

def build_ide(meta: dict, arch_key: str):
    version = meta["version"]
    arch_info = meta[arch_key]
    url = arch_info["url"]
    deb_arch = ARCH_MAP_DEB[arch_key]
    rpm_arch = ARCH_MAP_RPM[arch_key]

    log(f"=== Building IDE ({version}, {arch_key}) ===")
    archive_name = f"ide_{version}_{arch_key}.tar.gz"
    archive_path = CACHE_DIR / archive_name
    if not download_file(url, archive_path):
        return False

    staging_dir = CACHE_DIR / f"staging_ide_{version}_{arch_key}"
    shutil.rmtree(staging_dir, ignore_errors=True)
    
    opt_dest = staging_dir / "opt" / "antigravity-ide"
    opt_dest.mkdir(parents=True, exist_ok=True)

    extracted_root = CACHE_DIR / f"extract_ide_{version}_{arch_key}"
    shutil.rmtree(extracted_root, ignore_errors=True)
    extracted_root.mkdir(parents=True, exist_ok=True)

    log("Extracting IDE tarball with system tar...")
    run_cmd(f"tar -xzf '{archive_path}' -C '{extracted_root}'")
    top_dirs = [d for d in extracted_root.iterdir() if d.is_dir()]
    source_dir = top_dirs[0] if top_dirs else extracted_root

    # Move to /opt/antigravity-ide
    for item in source_dir.iterdir():
        shutil.move(str(item), str(opt_dest / item.name))

    # Icon
    icon_dest = staging_dir / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps" / "antigravity-ide.png"
    extract_ide_icon(opt_dest, icon_dest)

    # Desktop files (both main and URL handler)
    apps_dir = staging_dir / "usr" / "share" / "applications"
    apps_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(TEMPLATES_DIR / "antigravity-ide.desktop", apps_dir / "antigravity-ide.desktop")
    shutil.copy2(TEMPLATES_DIR / "antigravity-ide-url-handler.desktop", apps_dir / "antigravity-ide-url-handler.desktop")

    # Symlinks: /usr/bin/antigravity-ide AND /usr/bin/agy-ide -> /opt/antigravity-ide/bin/antigravity-ide
    # This uses Google's built-in cli.js wrapper, releasing the terminal immediately without chromium log spam!
    bin_dir = staging_dir / "usr" / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    (bin_dir / "antigravity-ide").symlink_to("/opt/antigravity-ide/bin/antigravity-ide")
    (bin_dir / "agy-ide").symlink_to("/opt/antigravity-ide/bin/antigravity-ide")

    # Permissions
    if (opt_dest / "chrome-sandbox").exists():
        os.chmod(opt_dest / "chrome-sandbox", 0o4755)

    desc = "Google Antigravity IDE"
    provides = ["antigravity-ide", "agy-ide"]
    depends = ["ca-certificates", "libasound2 | libasound2t64", "libnss3", "libatk-bridge2.0-0", "libgtk-3-0", "xdg-utils"]
    postinst_lines = [
        "if [ -f /opt/antigravity-ide/chrome-sandbox ]; then chmod 4755 /opt/antigravity-ide/chrome-sandbox || true; fi",
        "update-desktop-database /usr/share/applications || true",
        "gtk-update-icon-cache /usr/share/icons/hicolor || true",
    ]
    
    changelog_items = meta.get("changelog", {}).get("items", [])
    changelog_str = "\n".join([f"- {item}" for item in changelog_items[:5]]) if changelog_items else "- Antigravity IDE update"

    create_deb_package("antigravity-ide", version, deb_arch, staging_dir, desc, provides, depends, postinst_lines)
    create_rpm_package("antigravity-ide", version, rpm_arch, staging_dir, desc, provides, changelog_str)
    return True

def main():
    parser = argparse.ArgumentParser(description="Antigravity Package Builder")
    parser.add_argument("-c", "--component", choices=["cli", "hub", "ide", "all"], default="all", help="Component to build")
    parser.add_argument("-a", "--arch", choices=["x86_64", "aarch64", "all"], default="x86_64", help="Architecture to build")
    args = parser.parse_args()

    meta_file = BASE_DIR / "metadata.json"
    if not meta_file.exists():
        log("metadata.json not found, running fetch_metadata.py...")
        run_cmd("python3 scripts/fetch_metadata.py", cwd=BASE_DIR)

    with open(meta_file, "r", encoding="utf-8") as f:
        meta = json.load(f)

    components = ["cli", "hub", "ide"] if args.component == "all" else [args.component]
    arches = ["x86_64", "aarch64"] if args.arch == "all" else [args.arch]

    for comp in components:
        for arch in arches:
            if comp == "cli":
                build_cli(meta["cli"], arch)
            elif comp == "hub":
                build_hub(meta["hub"], arch)
            elif comp == "ide":
                build_ide(meta["ide"], arch)

    log("[✓] All requested packages successfully built!")

if __name__ == "__main__":
    main()
