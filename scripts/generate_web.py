#!/usr/bin/env python3
"""
Generates public/index.html for GitHub Pages software repository.
Direct downloads point to GitHub Releases CDN to protect GitHub Pages bandwidth.
"""

import argparse
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from jinja2 import Template

BASE_DIR = Path(__file__).resolve().parent.parent
DIST_DIR = BASE_DIR / "dist"
TEMPLATES_DIR = BASE_DIR / "templates"
PUBLIC_DIR = BASE_DIR / "public"
METADATA_FILE = BASE_DIR / "metadata.json"

def get_repo_info():
    default_user = "mozi1924"
    default_repo = "build-agy"
    try:
        res = subprocess.run("git remote get-url origin", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode == 0:
            url = res.stdout.strip()
            # e.g. git@github.com:user/repo.git or https://github.com/user/repo.git
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
    return "v" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")

def scan_available_packages(user: str, repo: str, release_tag: str):
    packages = []
    base_download_url = f"https://github.com/{user}/{repo}/releases/download/{release_tag}"

    deb_dir = DIST_DIR / "deb"
    if deb_dir.exists():
        for deb in sorted(deb_dir.glob("*.deb")):
            # e.g. antigravity-cli_1.2.14-1_amd64.deb
            m = re.match(r"^([^_]+)_([^_]+)_([^.]+)\.deb$", deb.name)
            if m:
                name, ver, arch = m.groups()
                packages.append({
                    "name": name,
                    "version": ver,
                    "arch": arch,
                    "format": "deb",
                    "filename": deb.name,
                    "url": f"{base_download_url}/{deb.name}"
                })

    rpm_dir = DIST_DIR / "rpm"
    if rpm_dir.exists():
        for rpm in sorted(rpm_dir.glob("*.rpm")):
            # e.g. antigravity-cli-1.2.14-1.fc44.x86_64.rpm or antigravity-cli-1.2.14-1.x86_64.rpm
            m = re.match(r"^(.+)-([0-9]+\.[0-9]+.*)-([^-]+)\.([^.]+)\.rpm$", rpm.name)
            if m:
                name, ver, rel, arch = m.groups()
                packages.append({
                    "name": name,
                    "version": f"{ver}-{rel}",
                    "arch": arch,
                    "format": "rpm",
                    "filename": rpm.name,
                    "url": f"{base_download_url}/{rpm.name}"
                })

    # Fallback to querying GitHub Release assets if dist/ has no packages
    if not packages:
        try:
            res = subprocess.run(f"gh release view '{release_tag}' --json assets", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if res.returncode == 0:
                data = json.loads(res.stdout)
                for asset in data.get("assets", []):
                    aname = asset.get("name", "")
                    if aname.endswith(".deb"):
                        m = re.match(r"^([^_]+)_([^_]+)_([^.]+)\.deb$", aname)
                        if m:
                            pname, ver, arch = m.groups()
                            packages.append({
                                "name": pname,
                                "version": ver,
                                "arch": arch,
                                "format": "deb",
                                "filename": aname,
                                "url": f"{base_download_url}/{aname}"
                            })
                    elif aname.endswith(".rpm"):
                        m = re.match(r"^(.+)-([0-9]+\.[0-9]+.*)-([^-]+)\.([^.]+)\.rpm$", aname)
                        if m:
                            pname, ver, rel, arch = m.groups()
                            packages.append({
                                "name": pname,
                                "version": f"{ver}-{rel}",
                                "arch": arch,
                                "format": "rpm",
                                "filename": aname,
                                "url": f"{base_download_url}/{aname}"
                            })
        except Exception:
            pass

    return packages

def main():
    parser = argparse.ArgumentParser(description="Generate web portal with release download links.")
    parser.add_argument("--tag", dest="tag", help="Explicit GitHub Release tag to point downloads to")
    args = parser.parse_args()

    if not METADATA_FILE.exists():
        print("metadata.json not found, running fetch_metadata.py...")
        subprocess.run("python3 scripts/fetch_metadata.py", shell=True, cwd=BASE_DIR, check=True)

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    user, repo = get_repo_info()
    repo_path = f"{user}/{repo}"
    domain = f"{user}.github.io/{repo}"
    release_tag = get_release_tag(args.tag)

    print(f"Generating web portal using release tag: {release_tag}")
    packages = scan_available_packages(user, repo, release_tag)

    template_file = TEMPLATES_DIR / "index.html.jinja"
    template = Template(template_file.read_text(encoding="utf-8"))

    html_content = template.render(
        meta=meta,
        domain=domain,
        repo_path=repo_path,
        release_tag=release_tag,
        packages=packages
    )

    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out_file = PUBLIC_DIR / "index.html"
    out_file.write_text(html_content, encoding="utf-8")
    print(f"[✓] Generated web portal: {out_file} ({len(packages)} packages linked to Releases)")

if __name__ == "__main__":
    main()
