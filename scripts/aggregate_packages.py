#!/usr/bin/env python3
"""
Aggregate built packages from GitHub Actions artifacts into dist/
while preserving existing packages of unchanged components.
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

def get_component_type(filename: str) -> str:
    """Identify which component (cli, hub, ide) a package belongs to."""
    name = Path(filename).name
    if name.startswith("antigravity-cli_") or name.startswith("antigravity-cli-"):
        return "cli"
    elif name.startswith("antigravity-ide_") or name.startswith("antigravity-ide-"):
        return "ide"
    elif name.startswith("antigravity_") or (name.startswith("antigravity-") and not name.startswith("antigravity-cli") and not name.startswith("antigravity-ide")):
        return "hub"
    return "unknown"

def aggregate(artifacts_dir: Path, dist_dir: Path):
    deb_dist = dist_dir / "deb"
    rpm_dist = dist_dir / "rpm"
    deb_dist.mkdir(parents=True, exist_ok=True)
    rpm_dist.mkdir(parents=True, exist_ok=True)

    # Find newly built packages in artifacts directory
    new_debs = list(artifacts_dir.rglob("*.deb")) if artifacts_dir.exists() else []
    new_rpms = list(artifacts_dir.rglob("*.rpm")) if artifacts_dir.exists() else []

    if not new_debs and not new_rpms:
        print("[aggregate_packages] No new packages found in artifacts directory.")
        return

    # Determine which components were rebuilt
    rebuilt_components = set()
    for pkg in new_debs + new_rpms:
        ctype = get_component_type(pkg.name)
        if ctype != "unknown":
            rebuilt_components.add(ctype)

    print(f"[aggregate_packages] Rebuilt components detected: {', '.join(sorted(rebuilt_components))}")

    # Remove older packages of the rebuilt components from dist/
    for existing_deb in list(deb_dist.glob("*.deb")):
        if get_component_type(existing_deb.name) in rebuilt_components:
            print(f"[aggregate_packages] Removing obsolete deb: {existing_deb.name}")
            existing_deb.unlink()

    for existing_rpm in list(rpm_dist.glob("*.rpm")):
        if get_component_type(existing_rpm.name) in rebuilt_components:
            print(f"[aggregate_packages] Removing obsolete rpm: {existing_rpm.name}")
            existing_rpm.unlink()

    # Copy new packages into dist/
    for deb in new_debs:
        dest = deb_dist / deb.name
        shutil.copy2(deb, dest)
        print(f"[aggregate_packages] Installed new deb: {dest.name}")

    for rpm in new_rpms:
        dest = rpm_dist / rpm.name
        shutil.copy2(rpm, dest)
        print(f"[aggregate_packages] Installed new rpm: {dest.name}")

    print("\n[aggregate_packages] Current package summary in dist/:")
    print("  DEB packages:")
    for d in sorted(deb_dist.glob("*.deb")):
        print(f"    - {d.name}")
    print("  RPM packages:")
    for r in sorted(rpm_dist.glob("*.rpm")):
        print(f"    - {r.name}")

def main():
    parser = argparse.ArgumentParser(description="Aggregate new packages into dist/ preserving unchanged ones.")
    parser.add_argument("--artifacts-dir", default="artifacts", help="Directory where downloaded build artifacts reside")
    parser.add_argument("--dist-dir", default="dist", help="Target distribution directory containing deb/ and rpm/")
    args = parser.parse_args()

    artifacts_path = Path(args.artifacts_dir).resolve()
    dist_path = Path(args.dist_dir).resolve()

    aggregate(artifacts_path, dist_path)

if __name__ == "__main__":
    main()
