<p align="center">
  <h1 align="center">⌨️ CodeMaker</h1>
  <p align="center">
    <strong>System-level input interceptor & AI code spoofing tool</strong>
  </p>
  <p align="center">
    A background service that monitors your keyboard for a trigger sequence,<br>
    screenshots the screen, sends it to an AI model, then <em>ghost-types</em> the<br>
    generated code — one character per keystroke — by intercepting your real input.
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python 3.11+">
    <img src="https://img.shields.io/badge/platform-Linux%20%7C%20Windows-green" alt="Linux | Windows">
    <img src="https://img.shields.io/badge/wayland-all%20compositors-purple" alt="Wayland">
    <img src="https://img.shields.io/badge/providers-7%20APIs%20+%20local-orange" alt="Multi-Provider">
    <img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT License">
  </p>
</p>

---

## Table of Contents

- [How It Works](#how-it-works)
- [Supported AI Providers](#supported-ai-providers)
- [Installation](#installation)
  - [Arch Linux](#-arch-linux)
  - [Debian / Ubuntu](#-debian--ubuntu)
  - [Fedora / RHEL](#-fedora--rhel)
  - [Windows](#-windows)
- [Finding Your Keyboard Device (Linux)](#finding-your-keyboard-device-linux)
- [Configuration](#configuration)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Autostart / Run on Boot](#autostart--run-on-boot)
- [Running Tests](#running-tests)

---

## How It Works

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   OBSERVER   │─────►│   CAPTURE    │─────►│  PROCESSING  │─────►│   PLAYBACK   │
│              │      │              │      │              │      │              │
│  Monitors    │      │  Screenshot  │      │  AI provider │      │  Ghost-types │
│  trigger     │      │  taken       │      │  returns     │      │  code from   │
│  sequence    │      │  silently    │      │  code        │      │  buffer      │
└──────────────┘      └──────────────┘      └──────────────┘      └──────┬───────┘
       ▲                                                                  │
       └─────────────────── buffer exhausted ─────────────────────────────┘
```

1. **OBSERVER** — The service silently monitors your keyboard for the trigger sequence (default: `Tab Tab Tab Backspace Backspace Backspace`)
2. **CAPTURE** — On trigger, it silently screenshots your screen
3. **PROCESSING** — The screenshot is sent to the configured AI provider (with automatic fallback to the next provider on failure)
4. **PLAYBACK** — Every key you press now outputs the next character from the AI-generated code. Indentation is stripped so your editor's auto-indent handles formatting. Backspace moves backward through the code buffer.

### Backspace Behavior

| Scenario | What Happens |
|----------|-------------|
| Normal typing | Next character from AI code is injected |
| Backspace (buffer has content) | Moves cursor back in code buffer, deletes injected char |
| Backspace (at position 0) | Blocked — stays at start |
| Any key after backspacing to 0 | Resumes typing from the beginning of the buffer |

---

## Supported AI Providers

CodeMaker supports **up to 5 API providers + 1 local model**, tried in configurable priority order. If one fails (rate limit, error), it automatically falls back to the next.

| Provider | Free Tier | Vision | Get API Key |
|----------|-----------|--------|-------------|
| **Google Gemini** | 1,500 req/day (Flash) | ✅ | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| **Groq** | 14,400 req/day | ✅ | [console.groq.com](https://console.groq.com) |
| **OpenRouter** | $1 free credit | ✅ | [openrouter.ai](https://openrouter.ai) |
| **Mistral** | Free tier | ✅ | [console.mistral.ai](https://console.mistral.ai) |
| **Together AI** | $1 free credit | ✅ | [together.ai](https://www.together.ai) |
| **GitHub Models** | Free with GitHub | ✅ | [github.com/marketplace/models](https://github.com/marketplace/models) |
| **Any OpenAI-compatible** | varies | ✅ | Custom `BASE_URL` |
| **Ollama (local)** | ∞ unlimited | ✅ | [ollama.com](https://ollama.com) — auto-downloads models |

### Recommended Setup

Set Gemini as primary (smartest), OpenRouter as free fallback, Groq as last-resort, and optionally a local two-stage pipeline for offline use:

```env
PROVIDER_PRIORITY=2,3,1,local

# Provider 1: Groq (fast but less capable)
PROVIDER_1_TYPE=groq
PROVIDER_1_KEY=your_groq_key
PROVIDER_1_MODEL=meta-llama/llama-4-scout-17b-16e-instruct

# Provider 2: Gemini (best code quality — tried first)
PROVIDER_2_TYPE=gemini
PROVIDER_2_KEY=your_gemini_key
PROVIDER_2_MODEL=gemini-2.5-flash

# Provider 3: OpenRouter (free vision fallback)
PROVIDER_3_TYPE=openrouter
PROVIDER_3_KEY=your_openrouter_key
PROVIDER_3_MODEL=google/gemma-4-31b-it:free

# Local: two-stage pipeline (vision extracts question, code model solves it)
LOCAL_VISION_MODEL=minicpm-v
LOCAL_CODE_MODEL=qwen2.5-coder:7b
# LOCAL_CODE_MODEL_QUALITY=qwen2.5-coder:14b  # Uncomment for slower, higher quality code
```

---

## Installation

### Prerequisites (All Platforms)

- **Python 3.11** or newer
- At least one AI provider API key (see [Supported AI Providers](#supported-ai-providers))

---

### 🐧 Arch Linux

<details open>
<summary><strong>Click to expand</strong></summary>

#### 1. Install system dependencies

```bash
# Python & build tools
sudo pacman -S python python-pip git

# Screenshot tool (install at least one)
# For Hyprland / Sway / wlroots-based compositors:
sudo pacman -S grim

# For KDE Plasma:
sudo pacman -S spectacle

# For GNOME:
sudo pacman -S gnome-screenshot

# For uinput kernel module (usually already loaded)
sudo modprobe uinput

# Optional: for local AI model support
sudo pacman -S ollama
```

#### 2. Set up input permissions

```bash
# Add your user to the input group (required for keyboard access)
sudo usermod -aG input $USER

# Ensure /dev/uinput is accessible
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | \
  sudo tee /etc/udev/rules.d/99-uinput.rules

# Reload udev rules
sudo udevadm control --reload-rules
sudo udevadm trigger

# ⚠️ LOG OUT AND BACK IN for group changes to take effect
```

#### 3. Clone and set up the project

```bash
git clone <your-repo-url> CodeMaker
cd CodeMaker

# Create virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 4. Find your keyboard device

Many laptops split keyboard input across multiple `/dev/input/event*` devices. Run the diagnostic tool to find the correct one:

```bash
sudo .venv/bin/python diagnose_keyboard.py
```

Press a few keys and the tool will tell you which device to use. Set it in your `.env`:

```env
KEYBOARD_DEVICE=/dev/input/event10   # Use the path from the diagnostic
```

#### 5. Configure

```bash
cp .env.example .env
nano .env
```

Set at minimum:
- `PROVIDER_1_KEY` — your Gemini API key (or whichever provider you're using)
- `KEYBOARD_DEVICE` — from the diagnostic above

#### 6. Run

```bash
# Using sudo with the venv Python
sudo .venv/bin/python -m codemaker
```

</details>

---

### 🐧 Debian / Ubuntu

<details>
<summary><strong>Click to expand</strong></summary>

#### 1. Install system dependencies

```bash
sudo apt update

# Python & build tools (python3-venv is separate on Debian/Ubuntu)
sudo apt install python3 python3-pip python3-venv git

# Build dependencies for python-evdev
sudo apt install python3-dev gcc

# Screenshot tool (install at least one)
# For Hyprland / Sway / wlroots-based compositors:
sudo apt install grim

# For KDE Plasma:
sudo apt install kde-spectacle

# For GNOME (usually pre-installed):
sudo apt install gnome-screenshot

# Ensure uinput module is loaded
sudo modprobe uinput

# Optional: for local AI model support
curl -fsSL https://ollama.com/install.sh | sh
```

#### 2. Set up input permissions

```bash
sudo usermod -aG input $USER

echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | \
  sudo tee /etc/udev/rules.d/99-uinput.rules

sudo udevadm control --reload-rules
sudo udevadm trigger

# ⚠️ LOG OUT AND BACK IN for group changes to take effect
```

#### 3. Clone and set up the project

```bash
git clone <your-repo-url> CodeMaker
cd CodeMaker

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 4. Find your keyboard device

```bash
sudo .venv/bin/python3 diagnose_keyboard.py
# Press some keys, then Ctrl+C. Set the suggested path in .env.
```

#### 5. Configure

```bash
cp .env.example .env
nano .env
# Set PROVIDER_1_KEY and KEYBOARD_DEVICE
```

#### 6. Run

```bash
sudo .venv/bin/python3 -m codemaker
```

</details>

---

### 🐧 Fedora / RHEL

<details>
<summary><strong>Click to expand</strong></summary>

#### 1. Install system dependencies

```bash
# Python & build tools
sudo dnf install python3 python3-pip python3-devel gcc git

# Screenshot tool (install at least one)
sudo dnf install grim          # wlroots compositors
sudo dnf install spectacle     # KDE Plasma
sudo dnf install gnome-screenshot  # GNOME

# Ensure uinput module is loaded
sudo modprobe uinput

# Optional: for local AI model support
curl -fsSL https://ollama.com/install.sh | sh
```

#### 2. Set up input permissions

```bash
sudo usermod -aG input $USER

echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | \
  sudo tee /etc/udev/rules.d/99-uinput.rules

sudo udevadm control --reload-rules
sudo udevadm trigger

# ⚠️ LOG OUT AND BACK IN for group changes to take effect
```

#### 3. Clone and set up the project

```bash
git clone <your-repo-url> CodeMaker
cd CodeMaker

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

#### 4. Find your keyboard device

```bash
sudo .venv/bin/python3 diagnose_keyboard.py
# Press some keys, then Ctrl+C. Set the suggested path in .env.
```

#### 5. Configure

```bash
cp .env.example .env
nano .env
# Set PROVIDER_1_KEY and KEYBOARD_DEVICE
```

#### 6. Run

```bash
sudo .venv/bin/python3 -m codemaker
```

</details>

---

### 🪟 Windows

<details>
<summary><strong>Click to expand</strong></summary>

#### 1. Install Python

Download and install Python 3.11+ from [python.org](https://www.python.org/downloads/).

> **Important:** Check **"Add Python to PATH"** and **"Install for all users"** during installation.

#### 2. Install Git (optional)

```powershell
winget install Git.Git
```

#### 3. Clone and set up the project

```powershell
git clone <your-repo-url> CodeMaker
cd CodeMaker

python -m venv .venv
.\.venv\Scripts\Activate.ps1

# If execution policy error:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

pip install -r requirements.txt
```

#### 4. Configure

```powershell
copy .env.example .env
notepad .env
# Set PROVIDER_1_KEY
```

> No `KEYBOARD_DEVICE` needed on Windows — keyboard hooking is automatic.

#### 5. Run

**Right-click PowerShell → "Run as Administrator"**, then:

```powershell
cd C:\path\to\CodeMaker
.\.venv\Scripts\Activate.ps1
python -m codemaker
```

</details>

---

## Finding Your Keyboard Device (Linux)

Many laptops (especially Lenovo, ASUS, Dell) split keyboard input across multiple `/dev/input/event*` devices. The auto-detection may pick the wrong one. Use the included diagnostic tool:

```bash
sudo .venv/bin/python diagnose_keyboard.py
```

**Output:**

```
══════════════════════════════════════════════════════════════════
  CodeMaker Keyboard Diagnostic
  Press keys on your keyboard. Watch which device receives them.
  Press Ctrl+C to stop.
══════════════════════════════════════════════════════════════════

  Monitoring: /dev/input/event3       AT Translated Set 2 keyboard
  Monitoring: /dev/input/event7       ITE Tech. Inc. ITE Device(8295)
  Monitoring: /dev/input/event10      ITE Tech. Inc. ITE Device(8176)
──────────────────────────────────────────────────────────────────
  ⌨️  /dev/input/event10      │ ITE Tech. Inc. ITE Device(8176)      │ KEY_A
  ⌨️  /dev/input/event10      │ ITE Tech. Inc. ITE Device(8176)      │ KEY_B
──────────────────────────────────────────────────────────────────
  ✅ Set this in your .env:
     KEYBOARD_DEVICE=/dev/input/event10
```

> **Common patterns:**
> - **Lenovo IdeaPad/ThinkPad:** Usually `ITE Tech` device, not `AT Translated Set 2`
> - **External USB keyboards:** Named after the brand (e.g., `Logitech`, `Corsair`)
> - **Key remappers (keyd, kmonad):** Use the virtual device they create
> - **Gaming mice with macros:** Will show as a separate keyboard — ignore these

---

## Configuration

All settings live in the `.env` file. Copy `.env.example` to `.env` and edit:

### Core Settings

| Variable | Default | Description |
|:---------|:--------|:------------|
| `SYSTEM_PROMPT` | `Solve this in c and have no comments at all.` | Instruction sent to the AI with the screenshot |
| `TRIGGER_SEQUENCE` | `tab,tab,tab,backspace,backspace,backspace` | Comma-separated key names that activate capture |
| `SCREENSHOT_TOOL` | `auto` | `grim`, `gnome-screenshot`, `spectacle`, `pillow`, or `auto` |
| `KILL_COMBO` | `ctrl+shift+escape` | Emergency kill combo to exit instantly |
| `RESET_COMBO` | `ctrl+shift+r` | Jump back to observer mode (cancels playback) |
| `KEYBOARD_DEVICE` | *(auto-detect)* | Linux only: explicit device path like `/dev/input/event10` |

### AI Provider Settings

| Variable | Description |
|:---------|:------------|
| `PROVIDER_PRIORITY` | Comma-separated priority order: `1,2,3,4,5,local` |
| `PROVIDER_N_TYPE` | Provider type: `gemini`, `groq`, `openrouter`, `mistral`, `together`, `github`, `openai` |
| `PROVIDER_N_KEY` | API key for the provider |
| `PROVIDER_N_MODEL` | Model name/ID |
| `PROVIDER_N_BASE_URL` | Custom base URL (for `openai` type or overrides) |
| `LOCAL_MODEL` | Single Ollama model for vision+code (simple mode) |
| `LOCAL_VISION_MODEL` | Vision model for question extraction (pipeline mode, e.g., `qwen2.5vl:7b`) |
| `LOCAL_CODE_MODEL` | Code model for solution generation (pipeline mode, e.g., `qwen2.5-coder:7b`) |
| `LOCAL_VISION_PROMPT` | Custom prompt for the vision extraction step |
| `OLLAMA_URL` | Ollama server URL (default: `http://localhost:11434`) |

### Local Model Recommendations

The two-stage pipeline loads models **sequentially** so each gets your full VRAM. You can also enable **Quality Mode** (`LOCAL_CODE_MODEL_QUALITY`) to split a larger code model across your GPU VRAM and system RAM.

| Setup | Vision Model (Extract) | Code Model (Generate) | Quality | Speed |
|:-----|:-------------|:-----------|:--------|:------|
| **4 GB VRAM** | `minicpm-v` (~1 GB) | `qwen2.5-coder:3b` (~2.5 GB) | ⭐⭐⭐ Good | ⚡ Fast |
| **6 GB VRAM** | `minicpm-v` (~1 GB) | `qwen2.5-coder:7b` (~5 GB) | ⭐⭐⭐⭐ Very Good | ⚡ Fast |
| **6 GB VRAM + 8 GB RAM** | `minicpm-v` (~1 GB) | **Quality Mode:** `qwen2.5-coder:14b` (~9 GB) | ⭐⭐⭐⭐⭐ Excellent | 🐢 Slower (~5-10 tok/s) |
| **6 GB VRAM + 12 GB RAM** | `minicpm-v` (~1 GB) | **Quality Mode:** `qwen2.5-coder:32b` (~20 GB) | ⭐⭐⭐⭐⭐⭐ Frontier | 🐌 Slow (~2-5 tok/s) |

### Available Key Names

Letters: `a`–`z` · Digits: `0`–`9` · Modifiers: `shift`, `ctrl`, `alt`, `meta`  
Special: `tab`, `backspace`, `enter`, `space`, `escape`, `delete`, `capslock`  
Navigation: `up`, `down`, `left`, `right`, `home`, `end`, `pageup`, `pagedown`  
Function keys: `f1`–`f12`

---

## Usage

### Starting the Service

```bash
# Linux
sudo .venv/bin/python -m codemaker

# Windows (Admin PowerShell)
python -m codemaker
```

You'll see a startup banner showing the active provider chain:

```
╔══════════════════════════════════════════╗
║         CodeMaker v0.1.0 Active          ║
║                                          ║
║  Trigger: tab,tab,tab,backspace,...      ║
║  Kill:    ctrl+escape+shift              ║
║                                          ║
║  Waiting for trigger sequence...          ║
╚══════════════════════════════════════════╝
  Providers: provider_1(gemini:gemini-2.0-fla) → provider_2(groq:llama-4-scout-1)
```

### Workflow

1. Open any text editor, IDE, or code input field
2. Type the trigger sequence: **Tab Tab Tab Backspace Backspace Backspace**
3. Wait 2–5 seconds for the screenshot to be captured and processed
4. Start typing anything — every key you press outputs the next character of the AI-generated code
5. Use **Backspace** to move backward in the code buffer
6. When the entire code buffer has been typed out, normal keyboard operation resumes automatically

> **Note:** Indentation is automatically stripped from the AI output so your editor's auto-indent handles formatting correctly.

### Emergency Exit

Press **Ctrl+Shift+Escape** (or your configured `KILL_COMBO`) at any time to instantly kill the service and restore normal keyboard operation.

> **If your keyboard becomes unresponsive** (e.g., the process crashed hard), unplug and replug your keyboard, or switch to a TTY (`Ctrl+Alt+F2`) and kill the process.

---

## Troubleshooting

### Linux

<details>
<summary><strong>Permission denied: /dev/input/event*</strong></summary>

Your user is not in the `input` group, or the group change hasn't taken effect.

```bash
groups  # Check if 'input' is listed
sudo usermod -aG input $USER
# LOG OUT and back in, or reboot
```

Quick fix: `sudo .venv/bin/python -m codemaker`

</details>

<details>
<summary><strong>Permission denied: /dev/uinput</strong></summary>

```bash
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | \
  sudo tee /etc/udev/rules.d/99-uinput.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

</details>

<details>
<summary><strong>Wrong keyboard detected / no keys received</strong></summary>

The auto-detection picked the wrong device. Run the diagnostic:

```bash
sudo .venv/bin/python diagnose_keyboard.py
```

Press keys and see which device receives them. Set it in `.env`:

```env
KEYBOARD_DEVICE=/dev/input/event10
```

**Common causes:**
- Laptop keyboards often use `ITE Tech` devices, not `AT Translated Set 2`
- Key remappers (keyd, kmonad) grab the physical device — use their virtual output device instead
- Gaming mice with macro keys show up as keyboards

</details>

<details>
<summary><strong>Device busy (EBUSY) — "already grabbed by another program"</strong></summary>

Another program (like `keyd`, `kmonad`, or a previous CodeMaker instance) has an exclusive grab on the keyboard.

```bash
# If using keyd, either stop it:
sudo systemctl stop keyd

# Or use keyd's virtual output device:
KEYBOARD_DEVICE=/dev/input/event26   # keyd virtual keyboard
```

</details>

<details>
<summary><strong>Screenshot fails: "All screenshot methods failed"</strong></summary>

When running as `sudo`, Wayland environment variables are stripped. CodeMaker auto-recovers them, but if it still fails:

```bash
# Install a screenshot tool for your compositor:
sudo pacman -S grim          # Arch + wlroots
sudo apt install grim         # Debian + wlroots
sudo dnf install grim         # Fedora + wlroots

# Or force a specific tool:
SCREENSHOT_TOOL=grim
```

</details>

<details>
<summary><strong>evdev build fails: "Python.h not found"</strong></summary>

```bash
sudo apt install python3-dev    # Debian/Ubuntu
sudo dnf install python3-devel  # Fedora
sudo pacman -S python           # Arch (headers included)
```

</details>

### API Issues

<details>
<summary><strong>429 RESOURCE_EXHAUSTED — quota exceeded</strong></summary>

Your API provider's free tier is exhausted. Solutions:

1. **Wait** for daily reset (midnight Pacific Time for Gemini)
2. **Add more providers** as fallbacks in `.env` (e.g., Groq, OpenRouter)
3. **Create a new API key** from a different Google Cloud project
4. **Use a local model** via Ollama (unlimited, no API needed)

</details>

<details>
<summary><strong>Model not found (404)</strong></summary>

Check the exact model ID for your provider. Common mistakes:

```env
# ❌ Wrong (missing org prefix for Groq)
PROVIDER_2_MODEL=llama-4-scout-17b-16e-instruct

# ✅ Correct
PROVIDER_2_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

</details>

### Windows

<details>
<summary><strong>Keyboard hook not working in elevated apps</strong></summary>

Run CodeMaker as Administrator: Right-click PowerShell → **Run as Administrator**.

</details>

<details>
<summary><strong>PowerShell execution policy error</strong></summary>

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

</details>

---

## Architecture

```
CodeMaker/
├── .env.example              # Configuration template (all providers)
├── .env                      # Your config (gitignored)
├── requirements.txt          # Python dependencies
├── diagnose_keyboard.py      # Keyboard device finder tool
├── README.md                 # This file
├── codemaker/
│   ├── __init__.py           # Package metadata
│   ├── __main__.py           # python -m codemaker entry
│   ├── main.py               # Orchestrator — wires everything
│   ├── config.py             # .env → Config dataclass + provider parsing
│   ├── state.py              # OBSERVER/CAPTURE/PLAYBACK state machine
│   ├── trigger.py            # Sliding-window trigger detector
│   ├── playback.py           # Code buffer + backspace logic
│   ├── capture.py            # Universal screenshot (auto env recovery)
│   ├── providers.py          # Multi-provider AI backend + fallback chain
│   ├── gemini.py             # Legacy Gemini-only module (deprecated)
│   ├── utils.py              # Logging, code fence & indentation stripping
│   └── platform/
│       ├── __init__.py
│       ├── base.py           # Abstract PlatformHook interface
│       ├── linux.py          # evdev grab + uinput (all compositors)
│       └── windows.py        # WH_KEYBOARD_LL + SendInput
└── tests/
    ├── test_trigger.py       # Trigger detector tests
    ├── test_playback.py      # Playback buffer tests
    ├── test_state.py         # State machine tests
    └── test_utils.py         # Utility function tests
```

### Platform Support Matrix

| Feature | Linux (Wayland) | Linux (X11) | Windows 10/11 |
|:--------|:---------------|:------------|:--------------|
| Keyboard interception | evdev grab | evdev grab | WH_KEYBOARD_LL |
| Key injection | uinput virtual keyboard | uinput virtual keyboard | SendInput (Unicode) |
| Screenshot | grim / spectacle / gnome-screenshot | Pillow ImageGrab | Pillow ImageGrab |
| Compositor support | All (Hyprland, Sway, GNOME, KDE, etc.) | All WMs | N/A |
| Required privileges | `input` group or root | `input` group or root | Administrator (recommended) |

### Provider Fallback Flow

```
Trigger → Screenshot → Provider 1 ──fail──► Provider 2 ──fail──► ... ──fail──► Local Ollama
                            │                    │                                  │
                            ▼                    ▼                                  ▼
                        ✅ Code              ✅ Code                           ✅ Code
                            │                    │                                  │
                            └────────────────────┴──────────────────────────────────┘
                                                 │
                                          Strip indentation
                                                 │
                                          Ghost-type buffer
```

---

## Running Tests

```bash
source .venv/bin/activate    # Linux
# .\.venv\Scripts\Activate.ps1  # Windows

python -m pytest tests/ -v
```

Expected output:

```
========================= 34 passed in 0.03s =========================
```

---

## Autostart / Run on Boot

### 🐧 Linux (systemd — all distros)

<details>
<summary><strong>Click to expand</strong></summary>

#### 1. Create the service file

```bash
sudo nano /etc/systemd/system/codemaker.service
```

Paste the following (adjust paths to match your setup):

```ini
[Unit]
Description=CodeMaker — AI code ghost-typing service
After=graphical-session.target
Wants=graphical-session.target

[Service]
Type=simple
# ─── CHANGE THESE to match your setup ───
User=root
Environment=SUDO_USER=tarun
Environment=SUDO_UID=1000
WorkingDirectory=/home/tarun/CodeMaker
ExecStart=/home/tarun/CodeMaker/.venv/bin/python -m codemaker
# ─────────────────────────────────────────
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=graphical-session.target
```

> **Important:** The `SUDO_USER` and `SUDO_UID` environment variables are needed so CodeMaker can recover your Wayland session for screenshots. Replace `tarun` and `1000` with your username and UID (`id -u`).

#### 2. Enable and start

```bash
# Reload systemd to pick up the new service
sudo systemctl daemon-reload

# Start immediately
sudo systemctl start codemaker

# Enable on boot
sudo systemctl enable codemaker

# Check status
sudo systemctl status codemaker

# View logs
journalctl -u codemaker -f
```

#### 3. Manage

```bash
sudo systemctl stop codemaker      # Stop
sudo systemctl restart codemaker   # Restart
sudo systemctl disable codemaker   # Disable autostart
```

</details>

### 🐧 Arch Linux (systemd user service — no sudo needed)

<details>
<summary><strong>Click to expand</strong></summary>

If your user has `input` group access and uinput rules set up, you can run as a user service instead of root:

#### 1. Create the user service

```bash
mkdir -p ~/.config/systemd/user
nano ~/.config/systemd/user/codemaker.service
```

```ini
[Unit]
Description=CodeMaker — AI code ghost-typing service
After=graphical-session.target

[Service]
Type=simple
WorkingDirectory=/home/tarun/CodeMaker
ExecStart=/home/tarun/CodeMaker/.venv/bin/python -m codemaker
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
```

#### 2. Enable and start

```bash
systemctl --user daemon-reload
systemctl --user start codemaker
systemctl --user enable codemaker

# View logs
journalctl --user -u codemaker -f
```

> **Note:** User services only run while you're logged in. If you need it running before login, use the root systemd service above.

</details>

### 🪟 Windows (Task Scheduler)

<details>
<summary><strong>Click to expand</strong></summary>

#### Option A: Task Scheduler (simplest)

1. Press **Win+R**, type `taskschd.msc`, press Enter
2. Click **Create Task** (not "Basic Task")
3. **General tab:**
   - Name: `CodeMaker`
   - Check **"Run with highest privileges"**
   - Configure for: Windows 10/11
4. **Triggers tab → New:**
   - Begin the task: **At log on**
   - Delay task for: `10 seconds`
5. **Actions tab → New:**
   - Action: Start a program
   - Program: `C:\path\to\CodeMaker\.venv\Scripts\python.exe`
   - Arguments: `-m codemaker`
   - Start in: `C:\path\to\CodeMaker`
6. **Conditions tab:**
   - Uncheck "Start only if on AC power"
7. Click **OK**

#### Option B: Startup folder (quick & dirty)

1. Press **Win+R**, type `shell:startup`, press Enter
2. Create a file `codemaker.bat` with:

```batch
@echo off
cd /d C:\path\to\CodeMaker
.venv\Scripts\python.exe -m codemaker
```

> **Note:** The startup folder method doesn't run as Administrator. Some elevated apps may not respond to injected keystrokes.

#### Option C: Windows Service (NSSM — most robust)

```powershell
# Install NSSM (Non-Sucking Service Manager)
winget install NSSM

# Create the service
nssm install CodeMaker "C:\path\to\CodeMaker\.venv\Scripts\python.exe" "-m codemaker"
nssm set CodeMaker AppDirectory "C:\path\to\CodeMaker"
nssm set CodeMaker Start SERVICE_AUTO_START

# Start it
nssm start CodeMaker

# Manage
nssm stop CodeMaker
nssm remove CodeMaker confirm
```

</details>

---

## License

MIT
