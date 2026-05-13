<p align="center">
  <h1 align="center">⌨️ CodeMaker</h1>
  <p align="center">
    <strong>System-level input interceptor & AI code spoofing tool</strong>
  </p>
  <p align="center">
    A background service that monitors your keyboard for a trigger sequence,<br>
    screenshots the screen, sends it to Google Gemini, then <em>ghost-types</em> the<br>
    AI-generated code — one character per keystroke — by intercepting your real input.
  </p>
  <p align="center">
    <img src="https://img.shields.io/badge/python-3.11+-blue?logo=python&logoColor=white" alt="Python 3.11+">
    <img src="https://img.shields.io/badge/platform-Linux%20%7C%20Windows-green" alt="Linux | Windows">
    <img src="https://img.shields.io/badge/wayland-all%20compositors-purple" alt="Wayland">
    <img src="https://img.shields.io/badge/license-MIT-yellow" alt="MIT License">
  </p>
</p>

---

## Table of Contents

- [How It Works](#how-it-works)
- [Installation](#installation)
  - [Arch Linux](#-arch-linux)
  - [Debian / Ubuntu](#-debian--ubuntu)
  - [Fedora / RHEL](#-fedora--rhel)
  - [Windows](#-windows)
- [Configuration](#configuration)
- [Usage](#usage)
- [Troubleshooting](#troubleshooting)
- [Architecture](#architecture)
- [Running Tests](#running-tests)

---

## How It Works

```
┌──────────────┐      ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
│   OBSERVER   │─────►│   CAPTURE    │─────►│  PROCESSING  │─────►│   PLAYBACK   │
│              │      │              │      │              │      │              │
│  Monitors    │      │  Screenshot  │      │  Gemini API  │      │  Ghost-types │
│  trigger     │      │  taken       │      │  returns     │      │  code from   │
│  sequence    │      │  silently    │      │  code        │      │  buffer      │
└──────────────┘      └──────────────┘      └──────────────┘      └──────┬───────┘
       ▲                                                                  │
       └─────────────────── buffer exhausted ─────────────────────────────┘
```

1. **OBSERVER** — The service silently monitors your keyboard for the trigger sequence (default: `Tab Tab Tab Backspace Backspace Backspace`)
2. **CAPTURE** — On trigger, it silently screenshots your screen and sends it to the Gemini API
3. **PROCESSING** — Gemini analyzes the screenshot and generates code based on the system prompt
4. **PLAYBACK** — Every key you press now outputs the next character from the AI-generated code instead of the real character. Backspace moves backward through the code buffer.

### The Ghost Typing Mechanism

During playback, your physical keyboard is intercepted at the kernel level (Linux) or via low-level hooks (Windows). The real character is suppressed and replaced with the next character from the AI's code buffer.

**Backspace Pointer-Sync:**

| Scenario | What Happens |
|----------|-------------|
| Normal typing | Next character from AI code is injected |
| Backspace (buffer has content) | Moves cursor back in code buffer, deletes injected char |
| Backspace (at position 0) | Blocked — tracks how far "past the start" you went |
| Typing after over-backspacing | Keystrokes are silently consumed until you "catch up" to position 0 |

---

## Installation

### Prerequisites (All Platforms)

- **Python 3.11** or newer
- A **Google Gemini API key** — get one free at [aistudio.google.com](https://aistudio.google.com/apikey)

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

#### 4. Configure

```bash
cp .env.example .env

# Edit .env and set your Gemini API key
# Use your preferred editor:
nano .env    # or: vim .env / code .env
```

Set `GEMINI_API_KEY=your_actual_key_here` at minimum.

#### 5. Run

```bash
# Option A: Using sudo with the venv Python (recommended)
sudo .venv/bin/python -m codemaker

# Option B: If your user is in the 'input' group and uinput rules are set
source .venv/bin/activate
python -m codemaker
```

</details>

---

### 🐧 Debian / Ubuntu

<details>
<summary><strong>Click to expand</strong></summary>

#### 1. Install system dependencies

```bash
# Update package lists
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
```

#### 2. Set up input permissions

```bash
# Add your user to the input group
sudo usermod -aG input $USER

# Create udev rule for /dev/uinput access
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
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 4. Configure

```bash
cp .env.example .env
nano .env
# Set: GEMINI_API_KEY=your_actual_key_here
```

#### 5. Run

```bash
# Option A: Using sudo with the venv Python (recommended)
sudo .venv/bin/python3 -m codemaker

# Option B: If your user is in the 'input' group and uinput rules are set
source .venv/bin/activate
python3 -m codemaker
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
# For Hyprland / Sway / wlroots-based compositors:
sudo dnf install grim

# For KDE Plasma:
sudo dnf install spectacle

# For GNOME (usually pre-installed on Fedora Workstation):
sudo dnf install gnome-screenshot

# Ensure uinput module is loaded
sudo modprobe uinput
```

#### 2. Set up input permissions

```bash
# Add your user to the input group
sudo usermod -aG input $USER

# Create udev rule for /dev/uinput access
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
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

#### 4. Configure

```bash
cp .env.example .env
nano .env
# Set: GEMINI_API_KEY=your_actual_key_here
```

#### 5. Run

```bash
# Option A: Using sudo with the venv Python (recommended)
sudo .venv/bin/python3 -m codemaker

# Option B: If your user is in the 'input' group and uinput rules are set
source .venv/bin/activate
python3 -m codemaker
```

</details>

---

### 🪟 Windows

<details>
<summary><strong>Click to expand</strong></summary>

#### 1. Install Python

Download and install Python 3.11+ from [python.org](https://www.python.org/downloads/).

> **Important:** During installation, check **"Add Python to PATH"** and **"Install for all users"**.

Verify the installation:

```powershell
python --version
# Should show Python 3.11.x or newer
```

#### 2. Install Git (optional, for cloning)

Download from [git-scm.com](https://git-scm.com/download/win) or use winget:

```powershell
winget install Git.Git
```

#### 3. Clone and set up the project

Open **PowerShell** (or Command Prompt):

```powershell
git clone <your-repo-url> CodeMaker
cd CodeMaker

# Create virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1

# If you get an execution policy error, run this first:
# Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Install dependencies
pip install -r requirements.txt
```

#### 4. Configure

```powershell
copy .env.example .env

# Edit .env with Notepad or your editor
notepad .env
# Set: GEMINI_API_KEY=your_actual_key_here
```

#### 5. Run

**Right-click PowerShell → "Run as Administrator"**, then:

```powershell
cd C:\path\to\CodeMaker
.\.venv\Scripts\Activate.ps1
python -m codemaker
```

> **Note:** Running as Administrator is recommended for reliable low-level keyboard hook operation. The tool will work without admin, but some applications with elevated privileges may not respond to injected keystrokes.

</details>

---

## Configuration

All settings live in the `.env` file. Copy `.env.example` to `.env` and edit:

| Variable | Default | Description |
|:---------|:--------|:------------|
| `GEMINI_API_KEY` | *(required)* | Your Google Gemini API key |
| `SYSTEM_PROMPT` | `Solve this in c and have no comments at all.` | The instruction sent to Gemini alongside the screenshot |
| `TRIGGER_SEQUENCE` | `tab,tab,tab,backspace,backspace,backspace` | Comma-separated key names that activate capture |
| `GEMINI_MODEL` | `gemini-2.0-flash` | Gemini model (`gemini-2.0-flash`, `gemini-2.5-pro`, etc.) |
| `SCREENSHOT_TOOL` | `auto` | `grim`, `gnome-screenshot`, `spectacle`, `pillow`, or `auto` |
| `KILL_COMBO` | `ctrl+shift+escape` | Emergency kill combo to exit instantly |
| `KEYBOARD_DEVICE` | *(auto-detect)* | Linux only: explicit device path like `/dev/input/event3` |

### Available Key Names for `TRIGGER_SEQUENCE`

Letters: `a` through `z` · Digits: `0` through `9` · Modifiers: `shift`, `ctrl`, `alt`, `meta`  
Special: `tab`, `backspace`, `enter`, `space`, `escape`, `delete`, `capslock`  
Navigation: `up`, `down`, `left`, `right`, `home`, `end`, `pageup`, `pagedown`  
Function keys: `f1` through `f12`

---

## Usage

### Starting the Service

```bash
# Linux
sudo .venv/bin/python -m codemaker

# Windows (Admin PowerShell)
python -m codemaker
```

You'll see a startup banner:

```
╔══════════════════════════════════════════╗
║         CodeMaker v0.1.0 Active          ║
║                                          ║
║  Trigger: tab,tab,tab,backspace,...      ║
║  Model:   gemini-2.0-flash              ║
║  Kill:    ctrl+escape+shift              ║
║                                          ║
║  Waiting for trigger sequence...          ║
╚══════════════════════════════════════════╝
```

### Workflow

1. Open any text editor, IDE, or code input field
2. Type the trigger sequence: **Tab Tab Tab Backspace Backspace Backspace**
3. Wait 2–5 seconds for the screenshot to be captured and processed by Gemini
4. Start typing anything — every key you press will output the next character of the AI-generated code
5. Use **Backspace** to move backward in the code buffer
6. When the entire code buffer has been typed out, normal keyboard operation resumes automatically

### Emergency Exit

Press **Ctrl+Shift+Escape** (or your configured `KILL_COMBO`) at any time to instantly kill the service and restore normal keyboard operation.

> **If your keyboard becomes unresponsive** (e.g., the process was killed with `kill -9`), unplug and replug your keyboard, or switch to a TTY (`Ctrl+Alt+F2`) and kill the process.

---

## Troubleshooting

### Linux

<details>
<summary><strong>Permission denied: /dev/input/event*</strong></summary>

Your user is not in the `input` group, or the group change hasn't taken effect.

```bash
# Check your groups
groups

# If 'input' is not listed:
sudo usermod -aG input $USER
# Then LOG OUT and back in (or reboot)

# Quick fix (does not persist):
sudo python -m codemaker
```

</details>

<details>
<summary><strong>Permission denied: /dev/uinput</strong></summary>

The udev rule for uinput hasn't been created or applied.

```bash
# Create the rule
echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' | \
  sudo tee /etc/udev/rules.d/99-uinput.rules

# Reload
sudo udevadm control --reload-rules
sudo udevadm trigger

# Verify
ls -la /dev/uinput
# Should show: crw-rw---- 1 root input ...
```

</details>

<details>
<summary><strong>No keyboard device found</strong></summary>

The auto-detection couldn't find your keyboard. List available devices:

```bash
sudo .venv/bin/python -c "
import evdev
for path in evdev.list_devices():
    dev = evdev.InputDevice(path)
    print(f'{dev.path}: {dev.name}')
"
```

Find your keyboard in the output and set `KEYBOARD_DEVICE` in `.env`:

```
KEYBOARD_DEVICE=/dev/input/event3
```

</details>

<details>
<summary><strong>Screenshot fails: "All screenshot methods failed"</strong></summary>

Install a screenshot tool compatible with your compositor:

```bash
# Hyprland / Sway / wlroots:
sudo pacman -S grim          # Arch
sudo apt install grim         # Debian/Ubuntu
sudo dnf install grim         # Fedora

# KDE Plasma:
sudo pacman -S spectacle     # Arch
sudo apt install kde-spectacle # Debian/Ubuntu
sudo dnf install spectacle    # Fedora

# GNOME:
sudo pacman -S gnome-screenshot  # Arch
sudo apt install gnome-screenshot # Debian/Ubuntu (usually pre-installed)
```

Or force a specific tool in `.env`:

```
SCREENSHOT_TOOL=grim
```

</details>

<details>
<summary><strong>evdev build fails: "Python.h not found"</strong></summary>

Install the Python development headers:

```bash
sudo apt install python3-dev    # Debian/Ubuntu
sudo dnf install python3-devel  # Fedora
sudo pacman -S python           # Arch (headers included by default)
```

Then reinstall:

```bash
pip install --force-reinstall evdev
```

</details>

### Windows

<details>
<summary><strong>Keyboard hook not working in elevated apps</strong></summary>

Some apps running as Administrator won't receive injected keystrokes unless CodeMaker is also running as Administrator. Always run from an elevated PowerShell:

1. Right-click PowerShell → **Run as Administrator**
2. Navigate to the project and run as usual

</details>

<details>
<summary><strong>PowerShell: "cannot be loaded because running scripts is disabled"</strong></summary>

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

</details>

---

## Architecture

```
CodeMaker/
├── .env.example              # Configuration template
├── .env                      # Your config (gitignored)
├── requirements.txt          # Python dependencies
├── README.md                 # This file
├── codemaker/
│   ├── __init__.py           # Package metadata
│   ├── __main__.py           # python -m codemaker entry
│   ├── main.py               # Orchestrator — wires everything
│   ├── config.py             # .env → frozen Config dataclass
│   ├── state.py              # OBSERVER/CAPTURE/PLAYBACK state machine
│   ├── trigger.py            # Sliding-window trigger detector
│   ├── playback.py           # Code buffer + backspace pointer-sync
│   ├── capture.py            # Universal screenshot capture
│   ├── gemini.py             # Gemini Vision API integration
│   ├── utils.py              # Logging, code fence stripping
│   └── platform/
│       ├── __init__.py
│       ├── base.py           # Abstract PlatformHook interface
│       ├── linux.py          # evdev grab + uinput virtual keyboard
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
| Compositor support | All (Hyprland, Sway, GNOME, KDE, river, dwl) | All WMs | N/A |
| Required privileges | `input` group or root | `input` group or root | Administrator (recommended) |

---

## Running Tests

```bash
# Activate the virtual environment
source .venv/bin/activate    # Linux
.\.venv\Scripts\Activate.ps1 # Windows

# Run all tests
python -m pytest tests/ -v

# Run specific test files
python -m pytest tests/test_playback.py -v
python -m pytest tests/test_trigger.py -v
python -m pytest tests/test_state.py -v
```

Expected output:

```
========================= 36 passed in 0.03s =========================
```

---

## License

MIT
