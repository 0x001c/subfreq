# SpotFram — Spotify Automation & Streaming Framework

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-Async-green.svg)](https://playwright.dev/)
[![PySide6](https://img.shields.io/badge/PySide6-Qt6-informational.svg)](https://pypi.org/project/PySide6/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An asynchronous automation framework and desktop GUI for multi-account Spotify playback, session management, and proxy routing. Built on top of **Playwright Async** and **PySide6 (Qt6)** with humanized interaction patterns and Widevine CDM DRM preservation.

---

## ⚡ Key Features

- **Widevine CDM & DRM Preservation**: Carefully tuned Chromium launch arguments and default-arg overrides that prevent Playwright from disabling Widevine CDM, enabling native DRM web playback.
- **Humanized Interaction Engine**:
  - Cubic/Quadratic Bezier curve mouse movement simulation with jitter and natural curve points.
  - Randomized playback durations (30s+ minimum tracking threshold up to full track length).
  - Variable human typing speeds and natural scrolling behaviors.
  - Realistic volume adjustments and navigation paths.
- **Dual Operating Modes**:
  - **Modern PySide6 GUI**: Dark-themed desktop dashboard with real-time stream counters, account status cards, live logs, multi-account runner, and built-in proxy checker.
  - **Asynchronous CLI Runner**: Lightweight batch processing via `main.py` utilizing `asyncio.Semaphore` concurrency controls.
- **Session & Cookie Persistence**:
  - Independent Chrome user data profiles for each account (`chrome_profiles/profile_<username>`).
  - Automatic session cookie export and restoration (`cookies/<username>.json`) to bypass repetitive logins and CAPTCHAs.
- **Sticky Proxy Routing**:
  - MD5 hash-based deterministic proxy assignment so accounts consistently route through identical exit nodes.
  - Full support for `HOST:PORT:USER:PASS` and `http://` authenticated proxies.
- **Smart Playback Diversification**:
  - Target track interleaving with randomized high-profile filler tracks to emulate authentic listening habits.

---

## 📁 Project Structure

```text
spotfram/
├── core/
│   ├── actions.py         # SpotifyBot logic (login, human clicks, playback, cookie handling)
│   ├── browser.py         # Playwright Chromium launcher with DRM configuration
│   └── proxy_manager.py   # Sticky proxy hashing and parser
├── accounts.example.txt   # Example structure for credentials and proxy associations
├── proxies.example.txt    # Example list for standalone proxy rotation
├── config.py              # Central configuration (tracks, concurrency, timeouts)
├── gui_app.py             # PySide6 desktop application interface
├── main.py                # Asynchronous CLI entry point
├── requirements.txt       # Dependencies
└── README.md
```

---

## 🛠️ Prerequisites

1. **Python 3.10+**
2. **Google Chrome** installed (required for Widevine CDM DRM support on Windows):
   - `C:\Program Files\Google\Chrome\Application\chrome.exe`
   - `C:\Program Files (x86)\Google\Chrome\Application\chrome.exe`
   - `%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe`

---

## 🚀 Installation

1. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/spotfram.git
   cd spotfram
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux / macOS:
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Install Playwright drivers**:
   ```bash
   playwright install
   ```

---

## ⚙️ Configuration

### 1. Accounts Configuration (`accounts.txt`)
Create an `accounts.txt` file in the root directory following `accounts.example.txt`:
```text
email:password:proxy_ip:proxy_port:proxy_username:proxy_password
```
*Note: If no proxy is needed per-account, proxy manager will assign from `proxies.txt`.*

### 2. Standalone Proxies (`proxies.txt`)
Optional standalone list following `proxies.example.txt`:
```text
ip:port:username:password
ip:port
```

### 3. General Settings (`config.py`)
Modify `config.py` to customize behavior:
```python
# Concurrency limit
MAX_CONCURRENT_SESSIONS = 4

# Target song(s) you wish to play
TARGET_SONGS = [
    "https://open.spotify.com/track/YOUR_TRACK_ID",
]

# Filler songs for randomized listening diversity
FILLER_TRACKS = [
    "https://open.spotify.com/track/...",
]
```

---

## 🖥️ Usage

### Desktop GUI App
To launch the graphical control interface:
```bash
python gui_app.py
```
From the GUI you can:
- View live stream counts and session status.
- Start/stop individual or bulk account sessions.
- Edit `accounts.txt` and `proxies.txt` directly.
- Test proxy latency and connectivity.
- Monitor real-time logs and debug output.

### Headless / CLI Runner
To run batch operations via terminal:
```bash
python main.py
```

---

## 🛡️ Operational Notes

- **Git & Privacy**: Sensitive files (`accounts.txt`, `proxies.txt`, `cookies/`, `chrome_profiles/`) are excluded via `.gitignore`. Never commit active account credentials.
- **DRM Playback**: Do not enable `--disable-component-update` or pass headless flags that disable CDM modules, as Spotify Web Player will throw a DRM playback error (`Spotify is unable to play this right now`).

---

## 📄 License

Distributed under the [MIT License](LICENSE).
