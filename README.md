# Antigravity Linux Package Repository 🚀

> Automated packaging pipeline and community repository (APT & RPM) for Google Antigravity components on Linux: **Antigravity IDE**, **Antigravity 2.0 (Hub)**, and **Antigravity CLI**.

[![Build & Deploy](https://github.com/mozi1924/build-agy/actions/workflows/build-repo.yml/badge.svg)](https://github.com/mozi1924/build-agy/actions/workflows/build-repo.yml)

Since Google Antigravity 2.0, official distribution on Linux was reduced to standalone `.tar.gz` archives. This repository bridges that gap by continuously monitoring Google's official release endpoints, packaging native `.deb` and `.rpm` binaries, and serving them via GitHub Pages as an active APT & YUM/DNF repository.

---

## 🌟 Highlights & Fixes

* **Full Desktop & Browser URL Scheme Integration**:
  * Registers `x-scheme-handler/antigravity` and `x-scheme-handler/antigravity-ide` so Google OAuth authentication in browsers smoothly redirects and launches the app.
* **Terminal Detachment & Cleaner Shell UX**:
  * Provides `/usr/bin/antigravity-ide` and `/usr/bin/agy-ide` (matching macOS conventions) wired directly to Google's official CLI wrapper (`cli.js`).
  * Running `agy-ide .` from the terminal launches the GUI and immediately returns `0` to your shell without spewing Chromium debug logs.
* **Automatic Official Changelogs**:
  * Scrapes `https://antigravity.google/docs/changelog` on every release.
  * Injects release notes directly into RPM `%changelog`, DEB packages, GitHub Releases, and the web portal.
* **Dual-Architecture Support**:
  * Packages both `x86_64` (amd64) and `aarch64` (arm64).

---

## 📦 Quick Installation

### Ubuntu / Debian / Linux Mint / Pop!_OS (APT)

```bash
# 1. Add repository source list
echo "deb [trusted=yes] https://github.com/mozi1924/build-agy/releases/latest/download/ ./" | sudo tee /etc/apt/sources.list.d/antigravity.list

# 2. Update package list and install
sudo apt update
sudo apt install -y antigravity-ide antigravity antigravity-cli
```

### Fedora / RHEL / CentOS Stream / Rocky Linux (DNF)

```bash
# 1. Add repository configuration
sudo tee /etc/yum.repos.d/antigravity.repo << 'EOF'
[antigravity]
name=Antigravity RPM Repository
baseurl=https://mozi1924.github.io/build-agy/rpm/$basearch/
enabled=1
gpgcheck=0
EOF

# 2. Install packages
sudo dnf install -y antigravity-ide antigravity antigravity-cli
```

### openSUSE (Zypper)

```bash
sudo zypper addrepo --no-gpgcheck https://mozi1924.github.io/build-agy/rpm/\$basearch/ antigravity
sudo zypper refresh
sudo zypper install -y antigravity-ide antigravity antigravity-cli
```

---

## 🛠️ Repository Architecture & Workflow

```text
build-agy/
├── .github/
│   └── workflows/
│       └── build-repo.yml        # CI/CD: periodic checks, package builds, Pages deployment
├── scripts/
│   ├── fetch_metadata.py         # Scrapes CLI API, download page URLs, and changelog
│   ├── extract_icons.py          # Pure Python icon extraction from app.asar / code.png
│   ├── build_packages.py         # Builds DEB (dpkg-deb) and RPM (rpmbuild)
│   ├── update_repo.py            # Generates APT (Release/Packages) and RPM (createrepo_c)
│   ├── generate_web.py           # Generates GitHub Pages web portal (index.html)
│   └── publish_release.py        # Creates GitHub Release with changelogs and assets
├── templates/
│   ├── antigravity.desktop       # Desktop entry for Hub with URL scheme
│   ├── antigravity-ide.desktop   # Desktop entry for IDE
│   ├── antigravity-ide-url-handler.desktop # Hidden URL scheme handler for OAuth
│   └── index.html.jinja          # Web portal template
└── versions.json                 # State tracking for built versions
```

---

## 💻 Local Testing & Manual Build

```bash
# 1. Install dependencies (Fedora)
sudo dnf install -y createrepo_c rpm-build dpkg-dev python3-pip
pip install -r requirements.txt

# 2. Fetch metadata & check for updates
python3 scripts/fetch_metadata.py

# 3. Build a specific package or all
python3 scripts/build_packages.py -c cli -a x86_64

# 4. Generate local repository files in public/
python3 scripts/update_repo.py
python3 scripts/generate_web.py
```

---

## 📜 Disclaimer

This is an unofficial community project not affiliated with or endorsed by Google LLC. All trademarks and binary copyrights belong to their respective owners.
