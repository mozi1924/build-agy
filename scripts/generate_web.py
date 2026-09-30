#!/usr/bin/env python3
"""
Generates public/index.html for GitHub Pages software repository.
"""

import json
import os
import re
import subprocess
from pathlib import Path
from jinja2 import Template

BASE_DIR = Path(__file__).resolve().parent.parent
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

def scan_available_packages():
    packages = []
    deb_dir = PUBLIC_DIR / "debian" / "pool" / "main"
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
                    "url": f"debian/pool/main/{deb.name}"
                })

    rpm_dir = PUBLIC_DIR / "rpm"
    if rpm_dir.exists():
        for rpm in sorted(rpm_dir.glob("*/*.rpm")):
            # e.g. antigravity-cli-1.2.14-1.fc44.x86_64.rpm
            m = re.match(r"^(.+)-([0-9]+\.[0-9]+.*)-([^-]+)\.([^.]+)\.rpm$", rpm.name)
            if m:
                name, ver, rel, arch = m.groups()
                packages.append({
                    "name": name,
                    "version": f"{ver}-{rel}",
                    "arch": arch,
                    "format": "rpm",
                    "filename": rpm.name,
                    "url": f"rpm/{rpm.parent.name}/{rpm.name}"
                })
    return packages

def main():
    if not METADATA_FILE.exists():
        print("metadata.json not found, running fetch_metadata.py...")
        subprocess.run("python3 scripts/fetch_metadata.py", shell=True, cwd=BASE_DIR, check=True)

    with open(METADATA_FILE, "r", encoding="utf-8") as f:
        meta = json.load(f)

    user, repo = get_repo_info()
    repo_path = f"{user}/{repo}"
    domain = f"{user}.github.io/{repo}"

    packages = scan_available_packages()

    template_file = TEMPLATES_DIR / "index.html.jinja"
    template = Template(template_file.read_text(encoding="utf-8"))

    html_content = template.render(
        meta=meta,
        domain=domain,
        repo_path=repo_path,
        packages=packages
    )

    out_file = PUBLIC_DIR / "index.html"
    out_file.write_text(html_content, encoding="utf-8")
    print(f"[✓] Generated web portal: {out_file}")

if __name__ == "__main__":
    main()
