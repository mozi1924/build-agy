#!/usr/bin/env python3
"""
Fetch latest Antigravity metadata (CLI, Hub, IDE) and changelogs.
"""

import gzip
import json
import os
import re
import sys
import urllib.request
from bs4 import BeautifulSoup

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"

def fetch_url(url: str) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept-Encoding": "gzip, deflate",
    })
    with urllib.request.urlopen(req, timeout=15) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        return raw.decode("utf-8", errors="replace")

def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_cli_metadata() -> dict:
    base = "https://antigravity-cli-auto-updater-974169037036.us-central1.run.app/manifests"
    amd64_info = fetch_json(f"{base}/linux_amd64.json")
    arm64_info = fetch_json(f"{base}/linux_arm64.json")
    
    version = amd64_info.get("version", "unknown")
    return {
        "version": version,
        "x86_64": {
            "url": amd64_info.get("url"),
            "sha512": amd64_info.get("sha512"),
        },
        "aarch64": {
            "url": arm64_info.get("url"),
            "sha512": arm64_info.get("sha512"),
        }
    }

def fetch_download_page_metadata() -> dict:
    html = fetch_url("https://antigravity.google/download")
    
    def find_first(pattern):
        matches = re.findall(pattern, html)
        return matches[0] if matches else None

    # Hub downloads
    hub_x64 = find_first(r'https://storage\.googleapis\.com/antigravity-public/antigravity-hub/[^/]+/linux-x64/Antigravity\.tar\.gz')
    hub_arm = find_first(r'https://storage\.googleapis\.com/antigravity-public/antigravity-hub/[^/]+/linux-arm/Antigravity\.tar\.gz')
    
    # IDE downloads
    ide_x64 = find_first(r'https://edgedl\.me\.gvt1\.com/edgedl/release2/j0qc3/antigravity/stable/[^/]+/linux-x64/Antigravity(?:%20|\+)IDE\.tar\.gz')
    ide_arm = find_first(r'https://edgedl\.me\.gvt1\.com/edgedl/release2/j0qc3/antigravity/stable/[^/]+/linux-arm/Antigravity(?:%20|\+)IDE\.tar\.gz')

    def parse_version_info(url):
        if not url:
            return "unknown", "unknown"
        m = re.search(r'/(\d+\.\d+\.\d+(?:-\d+)?)/', url)
        if m:
            build = m.group(1)
            ver = build.split('-')[0]
            return ver, build
        return "unknown", "unknown"

    hub_ver, hub_build = parse_version_info(hub_x64)
    ide_ver, ide_build = parse_version_info(ide_x64)

    return {
        "hub": {
            "version": hub_ver,
            "build": hub_build,
            "x86_64": {"url": hub_x64},
            "aarch64": {"url": hub_arm},
        },
        "ide": {
            "version": ide_ver,
            "build": ide_build,
            "x86_64": {"url": ide_x64},
            "aarch64": {"url": ide_arm},
        }
    }

def fetch_changelogs() -> dict:
    html = fetch_url("https://antigravity.google/docs/changelog")
    soup = BeautifulSoup(html, "html.parser")
    main = soup.find("main")
    if not main:
        return {}

    changelogs = {}
    current_section = None
    current_version = None

    for el in main.find_all(["h2", "h3", "ul", "p"]):
        if el.name == "h2":
            sec_name = el.text.strip()
            # Normalize section name
            if "CLI" in sec_name:
                current_section = "cli"
            elif "IDE" in sec_name:
                current_section = "ide"
            elif "2.0" in sec_name or "Hub" in sec_name or "Desktop" in sec_name:
                current_section = "hub"
            else:
                current_section = sec_name.lower().replace(" ", "_")
            if current_section not in changelogs:
                changelogs[current_section] = {}
            current_version = None
        elif el.name == "h3" and current_section:
            text = el.text.strip()
            if re.match(r"^v\d+\.\d+", text):
                current_version = text.lstrip("v")
                changelogs[current_section][current_version] = {
                    "raw_version": text,
                    "title": "",
                    "items": []
                }
            elif current_version:
                changelogs[current_section][current_version]["title"] = text
        elif el.name in ["ul", "p"] and current_section and current_version:
            target = changelogs[current_section][current_version]
            if el.name == "ul":
                items = [li.text.strip() for li in el.find_all("li") if li.text.strip()]
                target["items"].extend(items)
            else:
                p_text = el.text.strip()
                if p_text and not p_text.startswith("Track updates"):
                    target["items"].append(p_text)

    return changelogs

def collect_all_metadata() -> dict:
    print("[*] Querying Antigravity CLI updater API...")
    cli_meta = fetch_cli_metadata()
    
    print("[*] Scraping Antigravity official download page...")
    download_meta = fetch_download_page_metadata()
    
    print("[*] Scraping Antigravity official changelogs...")
    changelogs = fetch_changelogs()

    def get_comp_changelog(comp_name, version):
        sec = changelogs.get(comp_name, {})
        if version in sec:
            return sec[version]
        # Try matching major.minor if patch doesn't match
        for k in sec:
            if k.startswith('.'.join(version.split('.')[:2])):
                return sec[k]
        # Or return latest entry if available
        if sec:
            latest_k = list(sec.keys())[0]
            entry = dict(sec[latest_k])
            entry["note"] = f"Showing latest documented changes ({latest_k})"
            return entry
        return {}

    result = {
        "cli": {
            **cli_meta,
            "changelog": get_comp_changelog("cli", cli_meta["version"])
        },
        "hub": {
            **download_meta["hub"],
            "changelog": get_comp_changelog("hub", download_meta["hub"]["version"])
        },
        "ide": {
            **download_meta["ide"],
            "changelog": get_comp_changelog("ide", download_meta["ide"]["version"])
        },
        "all_changelogs": changelogs
    }
    return result

def main():
    metadata = collect_all_metadata()
    out_file = "metadata.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)
    print(f"[✓] Metadata successfully written to {out_file}")
    
    print("\n[Summary of Latest Releases]")
    print(f"  • CLI Version: {metadata['cli']['version']}")
    print(f"  • Hub Version: {metadata['hub']['version']} ({metadata['hub']['build']})")
    print(f"  • IDE Version: {metadata['ide']['version']} ({metadata['ide']['build']})")

    # Check differences against versions.json if it exists
    versions_file = "versions.json"
    to_build = []
    if os.path.exists(versions_file):
        with open(versions_file, "r", encoding="utf-8") as f:
            old_versions = json.load(f)
        for comp in ["cli", "hub", "ide"]:
            old_ver = old_versions.get(comp, {}).get("version")
            new_ver = metadata[comp]["version"]
            if old_ver != new_ver:
                to_build.append(comp)
                print(f"  -> Update detected for {comp}: {old_ver} -> {new_ver}")
            else:
                print(f"  -> {comp} is up-to-date ({new_ver})")
    else:
        to_build = ["cli", "hub", "ide"]
        print("  -> No existing versions.json found. All components scheduled for build.")

    if "--check-new" in sys.argv:
        print("TO_BUILD=" + ",".join(to_build))

if __name__ == "__main__":
    main()
