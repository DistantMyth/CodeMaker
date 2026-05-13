#!/usr/bin/env python3
"""Diagnostic: monitor ALL keyboard devices to find which one receives your keypresses.

Usage: sudo .venv/bin/python diagnose_keyboard.py

Press any keys and see which device lights up. Press Ctrl+C to stop.
"""

import selectors
import sys

import evdev
from evdev import ecodes as e, InputDevice, categorize


def main():
    devices = []
    sel = selectors.DefaultSelector()

    print("=" * 70)
    print("  CodeMaker Keyboard Diagnostic")
    print("  Press keys on your keyboard. Watch which device receives them.")
    print("  Press Ctrl+C to stop.")
    print("=" * 70)
    print()

    for path in evdev.list_devices():
        dev = InputDevice(path)
        caps = dev.capabilities(verbose=False).get(e.EV_KEY, [])

        # Only include devices that have key capabilities
        has_letters = sum(
            1 for c in range(ord('a'), ord('z') + 1)
            if getattr(e, f"KEY_{chr(c).upper()}") in caps
        )

        if has_letters == 0 and e.KEY_TAB not in caps:
            continue

        devices.append(dev)
        sel.register(dev, selectors.EVENT_READ)
        letter_count = has_letters
        tab = "✓" if e.KEY_TAB in caps else "✗"
        bs = "✓" if e.KEY_BACKSPACE in caps else "✗"
        print(
            f"  Monitoring: {dev.path:<25} {dev.name}"
        )
        print(
            f"              letters={letter_count}/26  tab={tab}  backspace={bs}"
        )

    print()
    if not devices:
        print("ERROR: No keyboard-like devices found!")
        sys.exit(1)

    print("─" * 70)
    print("  Waiting for key events... (press some keys now)")
    print("─" * 70)
    print()

    event_counts: dict[str, int] = {}

    try:
        while True:
            for key, mask in sel.select():
                dev = key.fileobj
                for event in dev.read():
                    if event.type == e.EV_KEY and event.value == 1:  # KEY_DOWN only
                        key_event = categorize(event)
                        key_name = key_event.keycode
                        if isinstance(key_name, list):
                            key_name = key_name[0]

                        path = dev.path
                        event_counts[path] = event_counts.get(path, 0) + 1

                        print(
                            f"  ⌨️  {path:<25} "
                            f"│ {dev.name:<45} "
                            f"│ {key_name}"
                        )
    except KeyboardInterrupt:
        print()
        print("─" * 70)
        print("  Summary — events received per device:")
        print("─" * 70)
        for dev in devices:
            count = event_counts.get(dev.path, 0)
            marker = " ◄── USE THIS ONE" if count > 0 else ""
            star = "★" if count > 0 else " "
            print(
                f"  {star} {dev.path:<25} "
                f"{dev.name:<40} "
                f"events={count}{marker}"
            )

        winners = [
            dev for dev in devices if event_counts.get(dev.path, 0) > 0
        ]
        if winners:
            best = max(winners, key=lambda d: event_counts.get(d.path, 0))
            print()
            print(f"  ✅ Set this in your .env:")
            print(f"     KEYBOARD_DEVICE={best.path}")
        print()
    finally:
        sel.close()


if __name__ == "__main__":
    main()
