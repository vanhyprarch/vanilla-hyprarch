#!/usr/bin/python
"""Verify first Flatpak export discovery in one running offscreen Quickshell."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile
import time


DESKTOP_ID = "org.example.FirstFlatpak"


def wait_for(marker: str, process: subprocess.Popen, log: Path) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        output = log.read_text(encoding="utf-8", errors="replace")
        if marker in output:
            return
        if process.poll() is not None:
            raise AssertionError(f"Quickshell exited before {marker}:\n{output}")
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {marker}:\n{log.read_text()}")


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-flatpak-discovery-") as temporary:
        root = Path(temporary)
        config = root / "config/quickshell/flatpak-discovery-test"
        config.mkdir(parents=True)
        (config / "shell.qml").write_text(
            """import QtQuick
import Quickshell

ShellRoot {
    Connections {
        target: DesktopEntries.applications
        function onValuesChanged() {
            const entry = DesktopEntries.byId("org.example.FirstFlatpak")
            if (entry && DesktopEntries.applications.values.some(item => item === entry))
                console.log("FLATPAK_DISCOVERY_PASS:" + entry.id + ":" + entry.name)
            else
                console.log("FLATPAK_VALUES_CHANGED")
        }
    }
    Timer {
        interval: 150
        running: true
        repeat: false
        onTriggered: {
            if (DesktopEntries.applications.values.length === 0)
                console.log("FLATPAK_WATCHER_READY")
            else
                console.error("FLATPAK_DISCOVERY_FAILURE: fixture was not initially empty")
        }
    }
}
""",
            encoding="utf-8",
        )
        applications = root / "flatpak/exports/share/applications"
        applications.mkdir(parents=True)
        user_data = root / "user-data"
        user_data.mkdir()
        home = root / "home"
        home.mkdir()
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        environment = dict(os.environ)
        environment.update({
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(root / "config"),
            "XDG_DATA_HOME": str(user_data),
            "XDG_DATA_DIRS": str(applications.parent),
            "XDG_RUNTIME_DIR": str(runtime),
            "QT_QPA_PLATFORM": "offscreen",
            "QS_NO_RELOAD_POPUP": "1",
        })
        environment.pop("WAYLAND_DISPLAY", None)
        environment.pop("DISPLAY", None)
        log = root / "quickshell.log"
        with log.open("wb") as stream:
            process = subprocess.Popen(
                ["qs", "--no-color", "-p", str(config)],
                env=environment,
                stdout=stream,
                stderr=subprocess.STDOUT,
            )
            try:
                wait_for("FLATPAK_WATCHER_READY", process, log)
                (applications / f"{DESKTOP_ID}.desktop").write_text(
                    "[Desktop Entry]\nType=Application\nName=First Flatpak\n"
                    "Exec=/usr/bin/true\nIcon=application-x-executable\n",
                    encoding="utf-8",
                )
                wait_for(f"FLATPAK_DISCOVERY_PASS:{DESKTOP_ID}:First Flatpak", process, log)
                if process.poll() is not None:
                    raise AssertionError("Quickshell exited during live discovery")
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
        output = log.read_text(encoding="utf-8", errors="replace")
        if "FLATPAK_DISCOVERY_FAILURE" in output or "critical" in output.lower():
            raise AssertionError(f"Quickshell discovery error:\n{output}")
    print("Flatpak first export live DesktopEntries discovery: PASS")


if __name__ == "__main__":
    main()
