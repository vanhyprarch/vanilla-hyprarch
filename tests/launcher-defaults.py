#!/usr/bin/python
"""Exercise launcher seeding with an isolated, offscreen Quickshell instance."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
COMPONENTS = REPOSITORY / "home/.config/quickshell/vanhyprarch/components"
EXPECTED = ["firefox", "foot", "thunar", "io.github.kolunmi.Bazaar"]


def wait_for(predicate, process: subprocess.Popen, log: Path, description: str) -> None:
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if predicate():
            return
        if process.poll() is not None:
            raise AssertionError(f"Quickshell exited before {description}:\n{log.read_text()}")
        time.sleep(0.05)
    raise AssertionError(f"timed out waiting for {description}:\n{log.read_text()}")


def add_desktop_entry(directory: Path, desktop_id: str, name: str) -> None:
    (directory / f"{desktop_id}.desktop").write_text(
        f"[Desktop Entry]\nType=Application\nName={name}\nExec=/usr/bin/true\n",
        encoding="utf-8",
    )


def start_shell(config: Path, environment: dict[str, str], log: Path) -> tuple[subprocess.Popen, object]:
    stream = log.open("wb")
    process = subprocess.Popen(
        ["qs", "--no-color", "-p", str(config)],
        env=environment,
        stdout=stream,
        stderr=subprocess.STDOUT,
    )
    return process, stream


def stop_shell(process: subprocess.Popen, stream: object) -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)
    stream.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="vanhyprarch-launcher-defaults-") as temporary:
        root = Path(temporary)
        config_home = root / "config"
        config = config_home / "quickshell/launcher-defaults-test"
        config.mkdir(parents=True)
        (config / "components").symlink_to(COMPONENTS, target_is_directory=True)
        (config / "shell.qml").write_text(
            """import QtQuick
import Quickshell
import "components"

ShellRoot {
    LauncherStore {
        id: launcherStore
        onReadyChanged: {
            if (ready)
                console.log("LAUNCHER_READY:" + JSON.stringify(launchers.map(item => item.desktopId)))
        }
    }

    Timer {
        interval: 100
        running: true
        repeat: true
        onTriggered: console.log("LAUNCHER_INDEX:"
            + DesktopEntries.applications.values.map(item => item.id).join(","))
    }
}
""",
            encoding="utf-8",
        )

        applications = root / "data-home/applications"
        applications.mkdir(parents=True)
        data_dirs = root / "data-dirs"
        data_dirs.mkdir()
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        state_home = root / "state"
        state_home.mkdir()
        home = root / "home"
        home.mkdir()
        environment = dict(os.environ)
        environment.update({
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(config_home),
            "XDG_STATE_HOME": str(state_home),
            "XDG_DATA_HOME": str(applications.parent),
            "XDG_DATA_DIRS": str(data_dirs),
            "XDG_RUNTIME_DIR": str(runtime),
            "QT_QPA_PLATFORM": "offscreen",
            "QS_NO_RELOAD_POPUP": "1",
        })
        environment.pop("WAYLAND_DISPLAY", None)
        environment.pop("DISPLAY", None)

        for desktop_id, name in zip(EXPECTED[:3], ["Firefox", "Foot", "Thunar File Manager"]):
            add_desktop_entry(applications, desktop_id, name)
        add_desktop_entry(applications, "org.gnome.TextEditor", "Text Editor")

        log = root / "fresh.log"
        process, stream = start_shell(config, environment, log)
        try:
            wait_for(
                lambda: "LAUNCHER_INDEX:" in log.read_text()
                and all(name in log.read_text() for name in EXPECTED[:3]),
                process, log, "the initial three application entries",
            )
            time.sleep(0.3)
            assert not list(state_home.glob("quickshell/by-shell/*/launchers.json")), (
                "a partial fresh launcher seed was persisted"
            )

            add_desktop_entry(applications, EXPECTED[3], "Bazaar")
            wait_for(
                lambda: bool(list(state_home.glob("quickshell/by-shell/*/launchers.json"))),
                process, log, "the complete fresh launcher seed",
            )
            paths = list(state_home.glob("quickshell/by-shell/*/launchers.json"))
            assert len(paths) == 1, paths
            state_file = paths[0]
            saved = json.loads(state_file.read_text(encoding="utf-8"))
            assert [item["desktopId"] for item in saved["launchers"]] == EXPECTED, saved
            assert "org.gnome.TextEditor" not in [item["desktopId"] for item in saved["launchers"]]
        finally:
            stop_shell(process, stream)

        for label, content, expected_ids in (
            (
                "custom",
                b'{ "launchers": [{"desktopId":"thunar","customIcon":"user-icon"},'
                b'{"desktopId":"firefox","customIcon":""}] }\n',
                ["thunar", "firefox"],
            ),
            ("empty", b'{ "launchers": [] }\n', []),
        ):
            state_file.write_bytes(content)
            log = root / f"{label}.log"
            process, stream = start_shell(config, environment, log)
            try:
                marker = "LAUNCHER_READY:" + json.dumps(expected_ids, separators=(",", ":"))
                wait_for(lambda: marker in log.read_text(), process, log, f"{label} state load")
                time.sleep(0.3)
                assert state_file.read_bytes() == content, f"{label} launcher state changed"
            finally:
                stop_shell(process, stream)
            assert state_file.read_bytes() == content, f"{label} launcher state changed on exit"

    print("Launcher defaults and user-state preservation: PASS")


if __name__ == "__main__":
    main()
