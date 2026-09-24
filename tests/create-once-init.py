#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import time
import tomllib
import unittest
from pathlib import Path
from unittest import mock


REPOSITORY = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPOSITORY / "install"))

from create_once import (  # noqa: E402
    ConflictError,
    CreateOnceInitializer,
    InitTarget,
)
from managed_deploy import ManagedDeployment, SafetyError, TargetContext  # noqa: E402


MPV_BYTES = (
    b"vo=gpu-next\n"
    b"target-colorspace-hint=auto\n"
    b"target-colorspace-hint-mode=source\n"
    b"fullscreen=yes\n"
)
MIME_BYTES = b"""[Default Applications]
audio/flac=mpv.desktop;
audio/mpeg=mpv.desktop;
audio/ogg=mpv.desktop;
audio/opus=mpv.desktop;
image/gif=imv.desktop;
image/jpeg=imv.desktop;
image/png=imv.desktop;
image/svg+xml=imv.desktop;
image/webp=imv.desktop;
inode/directory=thunar.desktop;
text/html=firefox.desktop;
text/plain=org.gnome.TextEditor.desktop;
video/mp4=mpv.desktop;
video/webm=mpv.desktop;
video/x-matroska=mpv.desktop;
x-scheme-handler/http=firefox.desktop;
x-scheme-handler/https=firefox.desktop;
"""
FOOT_BYTES_12 = b"font=monospace:size=12\n"
FOOT_BYTES_14 = b"font=monospace:size=14\n"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Fixture:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(mode=0o700)
        self.home = root / "home"
        self.config = root / "config"
        self.data = root / "data"
        self.state = root / "state"
        self.cache = root / "cache"
        self.runtime = root / "runtime"
        for path in (self.home, self.config, self.data, self.state, self.cache, self.runtime):
            path.mkdir(mode=0o700)
        self.target = InitTarget(
            TargetContext.build(
                home=self.home,
                config=self.config,
                data=self.data,
                state=self.state,
                cache=self.cache,
            ),
            self.runtime,
        )

    def cli(self, source: Path, command: str, environment: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        if environment:
            env.update(environment)
        return subprocess.run(
            [
                sys.executable,
                str(REPOSITORY / "install/create_once.py"),
                "--source-root",
                str(source),
                "--home",
                str(self.home),
                "--xdg-config-home",
                str(self.config),
                "--xdg-data-home",
                str(self.data),
                "--xdg-state-home",
                str(self.state),
                "--xdg-cache-home",
                str(self.cache),
                "--xdg-runtime-dir",
                str(self.runtime),
                command,
            ],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )


def write_minimal_release(root: Path) -> None:
    (root / "deployment").mkdir(parents=True)
    (root / "seeds").mkdir()
    (root / "seeds/example.conf").write_text("seed\n", encoding="utf-8")
    (root / "deployment/ownership-v2.toml").write_text(
        textwrap.dedent(
            """\
            schema_version = 2
            create_once_transaction_state = "transaction"

            [[artifact]]
            id = "example"
            source = "seeds/example.conf"
            target = "${XDG_CONFIG_HOME:-$HOME/.config}/example.conf"
            class = "CREATE_ONCE_USER"
            component = "test"
            kind = "file"
            mode = "0600"
            authority = "user"
            status = "implemented"
            user_editable = true
            machine_specific = false

            [[artifact]]
            id = "ignored-managed"
            source = "seeds/example.conf"
            target = "${XDG_CONFIG_HOME:-$HOME/.config}/ignored.conf"
            class = "VANILLA_MANAGED"
            component = "test"
            kind = "file"
            mode = "0644"
            authority = "vanilla-hyprarch"
            status = "implemented"
            user_editable = false
            machine_specific = false

            [[artifact]]
            id = "flatpak-user-application-exports"
            target = "${XDG_DATA_HOME:-$HOME/.local/share}/flatpak/exports/share/applications"
            class = "EXTERNAL_OWNED"
            component = "flatpak"
            kind = "tree"
            mode = "0755"
            authority = "flatpak"
            status = "implemented"
            user_editable = false
            machine_specific = false

            [[artifact]]
            id = "transaction"
            target = "${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/create-once-transaction-v1"
            class = "BACKEND_OWNED"
            component = "distribution"
            kind = "tree"
            mode = "0700"
            authority = "vanhyprarch-create-once"
            status = "implemented"
            user_editable = false
            machine_specific = false
            """
        ),
        encoding="utf-8",
    )


def install_fake_xdg_user_dirs(root: Path) -> Path:
    binary_dir = root / "fake-bin"
    binary_dir.mkdir()
    command = binary_dir / "xdg-user-dirs-update"
    command.write_text(
        """#!/bin/sh
set -eu
mkdir -p "$XDG_CONFIG_HOME" "$HOME/Desktop" "$HOME/Documents" "$HOME/Downloads" "$HOME/Music" "$HOME/Pictures" "$HOME/Public" "$HOME/Templates" "$HOME/Videos"
cat > "$XDG_CONFIG_HOME/user-dirs.dirs" <<EOF
XDG_DESKTOP_DIR="$HOME/Desktop"
XDG_DOWNLOAD_DIR="$HOME/Downloads"
XDG_TEMPLATES_DIR="$HOME/Templates"
XDG_PUBLICSHARE_DIR="$HOME/Public"
XDG_DOCUMENTS_DIR="$HOME/Documents"
XDG_MUSIC_DIR="$HOME/Music"
XDG_PICTURES_DIR="$HOME/Pictures"
XDG_VIDEOS_DIR="$HOME/Videos"
EOF
chmod 600 "$XDG_CONFIG_HOME/user-dirs.dirs"
locale_value=${LANG:-C}
printf '%s\n' "${locale_value%%.*}" > "$XDG_CONFIG_HOME/user-dirs.locale"
chmod 644 "$XDG_CONFIG_HOME/user-dirs.locale"
""",
        encoding="utf-8",
    )
    command.chmod(0o755)
    return binary_dir


class MinimalCreateOnceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.release = self.root / "release"
        write_minimal_release(self.release)
        self.fixture = Fixture(self.root / "target")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initializer(self) -> CreateOnceInitializer:
        return CreateOnceInitializer(source_root=self.release, target=self.fixture.target)

    def test_manifest_selects_only_create_once(self) -> None:
        initializer = self.initializer()
        self.assertEqual([item.identifier for item in initializer.seeds], ["example"])

    def test_plan_is_zero_write(self) -> None:
        before = sorted(str(path.relative_to(self.fixture.root)) for path in self.fixture.root.rglob("*"))
        plan = self.initializer().plan()
        after = sorted(str(path.relative_to(self.fixture.root)) for path in self.fixture.root.rglob("*"))
        self.assertEqual(before, after)
        self.assertEqual([item.action for item in plan], ["create", "create"])

    def test_create_exact_mode_and_idempotence(self) -> None:
        previous = os.umask(0o077)
        try:
            first = self.initializer().initialize()
            target = self.fixture.config / "example.conf"
            before = (target.stat().st_ino, target.stat().st_mtime_ns, digest(target))
            second = self.initializer().initialize()
            after = (target.stat().st_ino, target.stat().st_mtime_ns, digest(target))
        finally:
            os.umask(previous)
        self.assertEqual(first[-1].action, "seeded-by-vanilla")
        self.assertEqual(second[-1].action, "preserve-existing")
        self.assertEqual(before, after)
        self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
        self.assertEqual(target.read_bytes(), b"seed\n")
        self.assertFalse((self.fixture.config / "ignored.conf").exists())

    def test_existing_custom_file_is_preserved_byte_for_byte(self) -> None:
        target = self.fixture.config / "example.conf"
        target.write_bytes(b"custom\x00bytes")
        target.chmod(0o640)
        before = (target.stat().st_ino, target.stat().st_mtime_ns, target.read_bytes(), stat.S_IMODE(target.stat().st_mode))
        result = self.initializer().initialize()
        after = (target.stat().st_ino, target.stat().st_mtime_ns, target.read_bytes(), stat.S_IMODE(target.stat().st_mode))
        self.assertEqual(result[-1].action, "preserve-existing")
        self.assertEqual(before, after)

    def test_existing_symlink_and_wrong_type_fail_closed(self) -> None:
        target = self.fixture.config / "example.conf"
        target.symlink_to(self.fixture.home / "outside")
        with self.assertRaises(ConflictError):
            self.initializer().initialize()
        target.unlink()
        target.mkdir()
        with self.assertRaises(ConflictError):
            self.initializer().initialize()

    def test_symlinked_parent_fails_closed(self) -> None:
        self.fixture.config.rmdir()
        self.fixture.config.symlink_to(self.fixture.home)
        with self.assertRaises(SafetyError):
            self.initializer().plan()

    def test_source_symlink_fails_closed(self) -> None:
        source = self.release / "seeds/example.conf"
        source.unlink()
        source.symlink_to("/etc/passwd")
        with self.assertRaises(SafetyError):
            self.initializer().initialize()

    def test_abrupt_crash_windows_recover_idempotently(self) -> None:
        target = self.fixture.config / "example.conf"
        for checkpoint, published in (
            ("before-publish:example", False),
            ("after-publish:example", True),
            ("after-metadata-commit:example", True),
        ):
            if target.exists():
                target.unlink()
            transaction = self.fixture.state / "vanhyprarch/create-once-transaction-v1"
            if transaction.exists():
                shutil.rmtree(transaction)
            crashed = self.fixture.cli(
                self.release,
                "initialize",
                {
                    "VANHYPRARCH_CREATE_ONCE_TESTING": "1",
                    "VANHYPRARCH_CREATE_ONCE_TEST_FAULT_AT": checkpoint,
                },
            )
            self.assertEqual(crashed.returncode, 197, (checkpoint, crashed.stderr))
            self.assertEqual(target.exists(), published)
            planned = self.fixture.cli(self.release, "plan")
            self.assertEqual(planned.returncode, 2)
            self.assertIn("recovery-required", planned.stdout)
            recovered = self.fixture.cli(self.release, "initialize")
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertEqual(target.read_bytes(), b"seed\n")
            self.assertFalse(transaction.exists())
            second = self.fixture.cli(self.release, "initialize")
            self.assertEqual(second.returncode, 0, second.stderr)
            self.assertIn("preserve-existing", second.stdout)

    def test_malformed_transaction_fails_closed(self) -> None:
        transaction = self.fixture.state / "vanhyprarch/create-once-transaction-v1"
        transaction.mkdir(parents=True)
        (transaction / "intent.json").write_text("{", encoding="utf-8")
        (transaction / "intent.json").chmod(0o600)
        result = self.fixture.cli(self.release, "initialize")
        self.assertEqual(result.returncode, 2)
        self.assertIn("malformed", result.stderr)


class ActualManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.fixture = Fixture(self.root / "target")
        self.fake_bin = install_fake_xdg_user_dirs(self.root)
        self.path = f"{self.fake_bin}:{os.environ.get('PATH', '')}"
        deployment = ManagedDeployment(
            source_root=REPOSITORY,
            target=self.fixture.target.xdg,
            release_id="phase3-test",
        )
        deployment.apply("install")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def initializer(self) -> CreateOnceInitializer:
        return CreateOnceInitializer(source_root=REPOSITORY, target=self.fixture.target)

    def test_flatpak_user_export_scaffold_creation_preservation_and_validation(self) -> None:
        initializer = self.initializer()
        destination = self.fixture.data / "flatpak/exports/share/applications"
        with self.assertRaisesRegex(ConflictError, "Flatpak user export directory is missing"):
            initializer.validate()
        before = sorted((str(path.relative_to(self.fixture.root)), path.lstat().st_ino,
                         path.lstat().st_mtime_ns) for path in self.fixture.root.rglob("*"))
        self.assertEqual(initializer._flatpak_exports().action, "create")
        self.assertEqual(before, sorted((str(path.relative_to(self.fixture.root)), path.lstat().st_ino,
                                         path.lstat().st_mtime_ns) for path in self.fixture.root.rglob("*")))
        self.assertEqual(initializer._flatpak_exports(create=True).action, "preserve-existing")
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o755)
        self.assertEqual(destination.stat().st_uid, os.getuid())
        destination.chmod(0o700)
        exported = destination / "org.example.App.desktop"
        exported.write_bytes(b"example")
        link = destination / "org.example.Link.desktop"
        link.symlink_to(exported.name)
        saved = [(path.lstat().st_ino, path.lstat().st_mtime_ns, path.lstat().st_mode)
                 for path in (destination, exported, link)]
        self.assertEqual(initializer._flatpak_exports(create=True).action, "preserve-existing")
        self.assertEqual(saved, [(path.lstat().st_ino, path.lstat().st_mtime_ns,
                                  path.lstat().st_mode) for path in (destination, exported, link)])
        self.assertEqual(exported.read_bytes(), b"example")
        self.assertEqual(link.readlink(), Path(exported.name))
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o700)

    def test_flatpak_user_export_scaffold_rejects_unsafe_components(self) -> None:
        initializer = self.initializer()
        destination = self.fixture.data / "flatpak/exports/share/applications"
        destination.parent.mkdir(parents=True)
        destination.symlink_to(self.fixture.home)
        with self.assertRaises((SafetyError, ConflictError)):
            initializer._flatpak_exports(create=True)
        destination.unlink()
        destination.write_text("not a directory")
        with self.assertRaises((SafetyError, ConflictError)):
            initializer._flatpak_exports(create=True)
        destination.unlink()
        destination.parent.rmdir()
        destination.parent.write_text("not a directory")
        with self.assertRaises((SafetyError, ConflictError)):
            initializer._flatpak_exports(create=True)
        destination.parent.unlink()
        destination.parent.symlink_to(self.fixture.home)
        with self.assertRaises((SafetyError, ConflictError)):
            initializer._flatpak_exports(create=True)
        destination.parent.unlink()
        with mock.patch.object(os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises((SafetyError, ConflictError)):
                initializer._flatpak_exports(create=True)

    def test_flatpak_user_export_scaffold_respects_xdg_override(self) -> None:
        override = self.fixture.root / "other-data"
        override.mkdir(mode=0o700)
        with mock.patch.dict(os.environ, {"HOME": str(self.fixture.home),
                                      "XDG_DATA_HOME": str(override)}, clear=False):
            target = InitTarget.from_environment()
        initializer = CreateOnceInitializer(source_root=REPOSITORY, target=target)
        initializer._flatpak_exports(create=True)
        self.assertTrue((override / "flatpak/exports/share/applications").is_dir())
        self.assertFalse((self.fixture.home / ".local/share/flatpak").exists())

    def initialize(self) -> list:
        with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
            return self.initializer().initialize()

    def validate(self) -> list:
        with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
            return self.initializer().validate()

    def test_manifest_exact_create_once_inventory_and_seed_bytes(self) -> None:
        initializer = self.initializer()
        self.assertEqual(
            [item.identifier for item in initializer.seeds],
            ["foot-config", "machine-hyprland", "mimeapps-config", "mpv-config", "user-hyprland-override"],
        )
        self.assertEqual((REPOSITORY / "seeds/home/.config/mpv/mpv.conf").read_bytes(), MPV_BYTES)
        self.assertEqual((REPOSITORY / "seeds/home/.config/mimeapps.list").read_bytes(), MIME_BYTES)

    def test_actual_plan_is_zero_write(self) -> None:
        def snapshot() -> list[tuple[str, int, int, int]]:
            return sorted(
                (
                    str(path.relative_to(self.fixture.root)),
                    path.lstat().st_ino,
                    path.lstat().st_mtime_ns,
                    path.lstat().st_size,
                )
                for path in self.fixture.root.rglob("*")
            )

        before = snapshot()
        with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
            plan = self.initializer().plan()
        self.assertEqual(before, snapshot())
        self.assertIn("backend-initialize", {item.action for item in plan})

    def test_full_initialization_modes_backends_and_second_run(self) -> None:
        first = self.initialize()
        expected = {
            self.fixture.config / "vanhyprarch/machine/hyprland.lua": 0o600,
            self.fixture.config / "vanhyprarch/overrides/hyprland.lua": 0o600,
            self.fixture.config / "mpv/mpv.conf": 0o644,
            self.fixture.config / "foot/foot.ini": 0o644,
            self.fixture.config / "mimeapps.list": 0o644,
            self.fixture.config / "vanhyprarch/appearance.json": 0o600,
            self.fixture.config / "vanhyprarch/power-idle.conf": 0o600,
            self.fixture.config / "hypr/vanhyprarch-idle.conf": 0o600,
        }
        before: dict[Path, tuple[int, int, str]] = {}
        for path, mode in expected.items():
            self.assertTrue(path.is_file(), path)
            self.assertFalse(path.is_symlink())
            self.assertEqual(path.stat().st_uid, os.getuid())
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), mode)
            before[path] = (path.stat().st_ino, path.stat().st_mtime_ns, digest(path))
        self.assertEqual((self.fixture.config / "mpv/mpv.conf").read_bytes(), MPV_BYTES)
        self.assertEqual((self.fixture.config / "foot/foot.ini").read_bytes(), FOOT_BYTES_12)
        self.assertFalse((self.fixture.config / "vanhyprarch/text-size.conf").exists())
        self.assertEqual((self.fixture.config / "mimeapps.list").read_bytes(), MIME_BYTES)
        self.assertTrue((self.fixture.config / "user-dirs.dirs").is_file())
        self.assertTrue((self.fixture.config / "user-dirs.locale").is_file())
        second = self.initialize()
        for path in expected:
            self.assertEqual(before[path], (path.stat().st_ino, path.stat().st_mtime_ns, digest(path)))
        self.validate()
        self.assertTrue(any(item.action == "backend-initialized" for item in first))
        self.assertFalse(any(item.action == "seeded-by-vanilla" for item in second))

    def test_custom_create_once_files_are_never_changed(self) -> None:
        values = {
            self.fixture.config / "vanhyprarch/machine/hyprland.lua": b"-- machine custom\n",
            self.fixture.config / "vanhyprarch/overrides/hyprland.lua": b"-- override custom\n",
            self.fixture.config / "mpv/mpv.conf": b"fullscreen=no\n",
            self.fixture.config / "foot/foot.ini": b"font=Iosevka:size=15\npad=8x8\n",
            self.fixture.config / "mimeapps.list": b"[Default Applications]\ntext/plain=custom.desktop;\n",
        }
        before = {}
        for path, data in values.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            if path == self.fixture.config / "foot/foot.ini":
                path.chmod(0o640)
            before[path] = (path.stat().st_ino, path.stat().st_mtime_ns, stat.S_IMODE(path.stat().st_mode))
        self.initialize()
        self.initialize()
        for path, data in values.items():
            self.assertEqual(path.read_bytes(), data)
            self.assertEqual(
                (path.stat().st_ino, path.stat().st_mtime_ns, stat.S_IMODE(path.stat().st_mode)),
                before[path],
            )

    def test_foot_seed_uses_existing_explicit_text_size(self) -> None:
        preference = self.fixture.config / "vanhyprarch/text-size.conf"
        preference.parent.mkdir(parents=True, exist_ok=True)
        preference.write_bytes(b"version=1\nsize=14\n")
        preference.chmod(0o600)
        before = (preference.stat().st_ino, preference.stat().st_mtime_ns, preference.read_bytes())
        foot = self.fixture.config / "foot/foot.ini"
        self.assertFalse(foot.exists())
        self.initialize()
        self.assertEqual(foot.read_bytes(), FOOT_BYTES_14)
        self.assertEqual(stat.S_IMODE(foot.stat().st_mode), 0o644)
        self.assertEqual(
            (preference.stat().st_ino, preference.stat().st_mtime_ns, preference.read_bytes()),
            before,
        )
        created = (foot.stat().st_ino, foot.stat().st_mtime_ns, foot.read_bytes())
        self.initialize()
        self.assertEqual((foot.stat().st_ino, foot.stat().st_mtime_ns, foot.read_bytes()), created)
        self.validate()

    def test_invalid_text_size_refuses_missing_foot_seed(self) -> None:
        preference = self.fixture.config / "vanhyprarch/text-size.conf"
        preference.parent.mkdir(parents=True, exist_ok=True)
        preference.write_bytes(b"version=1\nsize=21\n")
        foot = self.fixture.config / "foot/foot.ini"
        with self.assertRaises(ConflictError):
            self.initializer().plan()
        with self.assertRaises(ConflictError):
            self.initialize()
        self.assertFalse(foot.exists())
        self.assertEqual(preference.read_bytes(), b"version=1\nsize=21\n")

    def test_existing_foot_is_preserved_even_with_invalid_text_size(self) -> None:
        foot = self.fixture.config / "foot/foot.ini"
        foot.parent.mkdir()
        foot.write_bytes(b"font=custom:size=13\n")
        preference = self.fixture.config / "vanhyprarch/text-size.conf"
        preference.parent.mkdir(parents=True, exist_ok=True)
        preference.write_bytes(b"invalid\n")
        before = (foot.stat().st_ino, foot.stat().st_mtime_ns, foot.read_bytes())
        self.initialize()
        self.assertEqual((foot.stat().st_ino, foot.stat().st_mtime_ns, foot.read_bytes()), before)

    def test_foot_unsafe_targets_fail_closed(self) -> None:
        foot = self.fixture.config / "foot/foot.ini"
        foot.parent.mkdir()
        foot.symlink_to(self.fixture.home / "outside")
        with self.assertRaises(ConflictError):
            self.initialize()
        foot.unlink()
        foot.mkdir()
        with self.assertRaises(ConflictError):
            self.initialize()
        foot.rmdir()
        foot.write_bytes(b"font=custom:size=13\n")
        artifact = next(item for item in self.initializer().seeds if item.identifier == "foot-config")
        with mock.patch("create_once.os.getuid", return_value=os.getuid() + 1):
            with self.assertRaises(ConflictError):
                self.initializer()._existing_result(artifact, foot)
        foot.unlink()
        foot.parent.rmdir()
        foot.parent.symlink_to(self.fixture.home)
        with self.assertRaises(SafetyError):
            self.initializer().plan()

    def test_installed_text_size_helper_updates_initialized_foot(self) -> None:
        self.initialize()
        foot = self.fixture.config / "foot/foot.ini"
        self.assertEqual(foot.read_bytes(), FOOT_BYTES_12)
        checked = subprocess.run(
            ["foot", "--check-config", f"--config={foot}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(checked.returncode, 0, checked.stderr)
        foot.write_bytes(FOOT_BYTES_12 + b"pad=8x8\n")

        fake_bin = self.root / "text-size-bin"
        fake_bin.mkdir()
        state = self.root / "gtk-factor"
        state.write_text("1.0\n", encoding="utf-8")
        gsettings = fake_bin / "gsettings"
        gsettings.write_text(
            "#!/bin/sh\n"
            "case $1:$2:$3 in\n"
            "get:org.gnome.desktop.interface:font-name) printf \"'Adwaita Sans 11'\\n\" ;;\n"
            "get:org.gnome.desktop.interface:text-scaling-factor) cat \"$MOCK_GSETTINGS_STATE\" ;;\n"
            "set:org.gnome.desktop.interface:text-scaling-factor) printf '%s\\n' \"$4\" > \"$MOCK_GSETTINGS_STATE\" ;;\n"
            "*) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        gsettings.chmod(0o755)
        environment = self.fixture.target.environment() | {
            "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
            "MOCK_GSETTINGS_STATE": str(state),
        }
        helper = self.fixture.config / "quickshell/vanhyprarch/helpers/vanhyprarch_text_size"
        result = subprocess.run(
            [str(helper), "set", "14"],
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("foot=updated\n", result.stdout)
        self.assertEqual(foot.read_bytes(), FOOT_BYTES_14 + b"pad=8x8\n")
        self.assertEqual(
            (self.fixture.config / "vanhyprarch/text-size.conf").read_bytes(),
            b"version=1\nsize=14\n",
        )

    def test_alternate_user_mime_configuration_prevents_seed(self) -> None:
        alternate = self.fixture.data / "applications/mimeapps.list"
        alternate.parent.mkdir(parents=True)
        alternate.write_text("[Default Applications]\ntext/plain=custom.desktop;\n", encoding="utf-8")
        results = self.initialize()
        self.assertFalse((self.fixture.config / "mimeapps.list").exists())
        mime = next(item for item in results if item.identifier == "mimeapps-config")
        self.assertEqual(mime.action, "preserve-existing")
        self.validate()

    def test_custom_pictures_path_is_authoritative(self) -> None:
        localized = self.fixture.home / "Immagini personalizzate"
        self.fixture.config.joinpath("user-dirs.dirs").write_text(
            f'XDG_PICTURES_DIR="{localized}"\n', encoding="utf-8"
        )
        self.fixture.config.joinpath("user-dirs.dirs").chmod(0o600)
        self.initialize()
        self.assertTrue((localized / "Wallpapers/Light/Wolkenstein_1_light.png").is_file())
        self.assertFalse((self.fixture.home / "Pictures/Wallpapers").exists())

    def test_wallpaper_deletion_modification_and_user_addition_survive(self) -> None:
        self.initialize()
        root = self.fixture.home / "Pictures/Wallpapers"
        deleted = root / "Light/Wolkenstein_2_light.png"
        modified = root / "Dark/Wolkenstein_2_dark.png"
        own = root / "Dark/my-wallpaper.png"
        deleted.unlink()
        modified.write_bytes(b"customized")
        own.write_bytes(b"mine")
        self.initialize()
        self.assertFalse(deleted.exists())
        self.assertEqual(modified.read_bytes(), b"customized")
        self.assertEqual(own.read_bytes(), b"mine")

    def test_custom_backend_preferences_and_malformed_state(self) -> None:
        self.initialize()
        appearance = self.fixture.config / "vanhyprarch/appearance.json"
        value = json.loads(appearance.read_text(encoding="utf-8"))
        value["mode"] = "dark"
        appearance.write_text(json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")
        power = self.fixture.config / "vanhyprarch/power-idle.conf"
        power.write_text("version=2\nscreensaver=never\ndisplay=300\nsuspend=never\nlock=display\neffect=colormix\n", encoding="utf-8")
        self.initialize()
        self.assertEqual(json.loads(appearance.read_text(encoding="utf-8"))["mode"], "dark")
        self.assertIn("display=300\n", power.read_text(encoding="utf-8"))
        appearance.write_text("{", encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.initialize()
        self.assertEqual(appearance.read_text(encoding="utf-8"), "{")

    def test_malformed_power_idle_preference_fails_closed(self) -> None:
        self.initialize()
        power = self.fixture.config / "vanhyprarch/power-idle.conf"
        power.write_text("invalid\n", encoding="utf-8")
        with self.assertRaises(ConflictError):
            self.initializer().plan()
        with self.assertRaises(ConflictError):
            self.initialize()
        self.assertEqual(power.read_text(encoding="utf-8"), "invalid\n")

    def test_power_idle_caffeine_projection_preserved_by_owner_hooks(self) -> None:
        self.initialize()
        command = self.fixture.home / ".local/bin/vanhyprarch-idle"
        preference = self.fixture.config / "vanhyprarch/power-idle.conf"
        fragment = self.fixture.config / "hypr/vanhyprarch-idle.conf"
        marker = self.fixture.runtime / "vanhyprarch/caffeine"
        preference_before = preference.read_bytes()
        with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
            self.assertTrue(any(item.identifier == "power-idle-defaults" for item in self.initializer().plan()))
        self.validate()

        capability = next(
            line.split("capability=", 1)[1]
            for line in fragment.read_text(encoding="utf-8").splitlines()
            if line.startswith("# Effective:")
        )
        rendered = subprocess.run(
            [command, "render", "never", "never", "never", "none", "on", "colormix", capability],
            env=self.fixture.target.environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(rendered.returncode, 0, rendered.stderr)
        fragment.write_text(rendered.stdout, encoding="utf-8")
        marker.write_text("on\n", encoding="utf-8")
        marker.chmod(0o600)
        fragment_before = (fragment.stat().st_ino, fragment.read_bytes())
        with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
            self.initializer().plan()
        self.assertEqual((fragment.stat().st_ino, fragment.read_bytes()), fragment_before)
        self.assertEqual(marker.read_text(encoding="utf-8"), "on\n")
        self.assertEqual(preference.read_bytes(), preference_before)
        self.validate()
        self.initialize()
        self.assertEqual(marker.read_text(encoding="utf-8"), "on\n")
        self.assertEqual((fragment.stat().st_ino, fragment.read_bytes()), fragment_before)
        self.assertEqual(preference.read_bytes(), preference_before)

        fragment.unlink()
        regenerated = subprocess.run(
            [command, "initialize-defaults"],
            env=self.fixture.target.environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertEqual(regenerated.returncode, 0, regenerated.stderr)
        self.assertEqual(fragment.read_bytes(), fragment_before[1])
        self.assertEqual(marker.read_text(encoding="utf-8"), "on\n")
        self.validate()

    def test_power_idle_initialize_status_waits_for_backend_lock(self) -> None:
        self.initialize()
        command = self.fixture.home / ".local/bin/vanhyprarch-idle"
        lock = self.fixture.runtime / "vanhyprarch/idle.lock"
        with lock.open("rb") as descriptor:
            fcntl.flock(descriptor, fcntl.LOCK_EX)
            process = subprocess.Popen(
                [command, "initialize-status"],
                env=self.fixture.target.environment(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            try:
                time.sleep(0.1)
                self.assertIsNone(process.poll())
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
            output, error = process.communicate(timeout=5)
        self.assertEqual(process.returncode, 0, error)
        self.assertIn("fragment=valid\n", output)

    def test_power_idle_owner_hooks_reject_drift_and_invalid_caffeine(self) -> None:
        self.initialize()
        command = self.fixture.home / ".local/bin/vanhyprarch-idle"
        preference = self.fixture.config / "vanhyprarch/power-idle.conf"
        fragment = self.fixture.config / "hypr/vanhyprarch-idle.conf"
        marker = self.fixture.runtime / "vanhyprarch/caffeine"
        preference_before = preference.read_bytes()
        for caffeine in ("off", "on"):
            if caffeine == "on":
                marker.write_text("on\n", encoding="utf-8")
                marker.chmod(0o600)
                fragment.write_text(
                    fragment.read_text(encoding="utf-8").replace(
                        "# Caffeine: off\n",
                        "# Caffeine: on\n# Automatic Power & Idle actions are disabled.\n",
                    ),
                    encoding="utf-8",
                )
            fragment_before = fragment.read_bytes()
            fragment.write_bytes(fragment_before + b"# drift\n")
            with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
                with self.assertRaisesRegex(ConflictError, "deployed hypridle configuration"):
                    self.initializer().plan()
            fragment.write_bytes(fragment_before)
            preference.write_text(
                "version=2\nscreensaver=never\ndisplay=300\nsuspend=never\nlock=display\neffect=colormix\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ConflictError, "deployed hypridle configuration"):
                self.validate()
            preference.write_bytes(preference_before)
            self.validate()

        marker.write_text("invalid\n", encoding="utf-8")
        with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
            with self.assertRaisesRegex(ConflictError, "invalid runtime state"):
                self.initializer().plan()
        marker.unlink()
        marker.symlink_to(preference)
        with self.assertRaisesRegex(ConflictError, "must not be a symbolic link"):
            self.validate()
        rejected = subprocess.run(
            [command, "initialize-defaults"],
            env=self.fixture.target.environment(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn("must not be a symbolic link", rejected.stderr)
        self.assertEqual(preference.read_bytes(), preference_before)
        self.assertEqual(fragment.read_bytes(), fragment_before)

    def test_appearance_abrupt_seed_crashes_recover(self) -> None:
        command = self.fixture.home / ".local/bin/vanhyprarch-appearance"
        environment = self.fixture.target.environment()
        for checkpoint in ("after-starter-publish", "after-starter-marker"):
            shutil.rmtree(self.fixture.home / "Pictures", ignore_errors=True)
            receipt = self.fixture.state / "vanhyprarch/appearance-assets.json"
            if receipt.exists():
                receipt.unlink()
            preference = self.fixture.config / "vanhyprarch/appearance.json"
            if preference.exists():
                preference.unlink()
            crashed_env = environment | {
                "VANHYPRARCH_APPEARANCE_TESTING": "1",
                "VANHYPRARCH_APPEARANCE_TEST_FAULT_AT": checkpoint,
            }
            crashed = subprocess.run(
                [command, "initialize-defaults"],
                env=crashed_env,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(crashed.returncode, 198)
            recovered = subprocess.run(
                [command, "initialize-defaults"],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(recovered.returncode, 0)
            self.assertTrue(receipt.is_file())
            self.assertTrue(preference.is_file())

    def test_power_idle_abrupt_initialization_recovers(self) -> None:
        command = self.fixture.home / ".local/bin/vanhyprarch-idle"
        environment = self.fixture.target.environment()
        for checkpoint in ("after-initial-preference", "after-initial-fragment"):
            preference = self.fixture.config / "vanhyprarch/power-idle.conf"
            fragment = self.fixture.config / "hypr/vanhyprarch-idle.conf"
            preference.unlink(missing_ok=True)
            fragment.unlink(missing_ok=True)
            crashed = subprocess.run(
                [command, "initialize-defaults"],
                env=environment
                | {
                    "VANHYPRARCH_IDLE_TESTING": "1",
                    "VANHYPRARCH_IDLE_TEST_FAULT_AT": checkpoint,
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(crashed.returncode, -9, (checkpoint, crashed.stderr))
            recovered = subprocess.run(
                [command, "initialize-defaults"],
                env=environment,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertEqual(recovered.returncode, 0, recovered.stderr)
            self.assertTrue(preference.is_file())
            self.assertTrue(fragment.is_file())

    def test_phase2_update_and_phase3_preserve_converge(self) -> None:
        self.initialize()
        machine = self.fixture.config / "vanhyprarch/machine/hyprland.lua"
        machine.write_text("-- changed machine\n", encoding="utf-8")
        wallpaper = self.fixture.home / "Pictures/Wallpapers/Light/Wolkenstein_4_light.png"
        wallpaper.unlink()
        deployment = ManagedDeployment(source_root=REPOSITORY, target=self.fixture.target.xdg, release_id="phase3-test")
        plan = deployment.apply("update")
        self.assertFalse(plan.changes)
        self.initialize()
        self.assertEqual(machine.read_text(encoding="utf-8"), "-- changed machine\n")
        self.assertFalse(wallpaper.exists())
        deployment.validate_installed(require_current_release=True)
        self.validate()

    def test_source_tree_removal_does_not_break_initialized_files(self) -> None:
        self.initialize()
        snapshots = {
            path: digest(path)
            for path in (
                self.fixture.config / "mpv/mpv.conf",
                self.fixture.config / "foot/foot.ini",
                self.fixture.config / "mimeapps.list",
                self.fixture.config / "vanhyprarch/machine/hyprland.lua",
            )
        }
        copied_source = self.root / "source-copy"
        shutil.copytree(REPOSITORY, copied_source, ignore=shutil.ignore_patterns(".git"))
        independent = Fixture(self.root / "independent-target")
        ManagedDeployment(source_root=copied_source, target=independent.target.xdg, release_id="copy").apply("install")
        with mock.patch.dict(os.environ, {"PATH": self.path}, clear=False):
            CreateOnceInitializer(source_root=copied_source, target=independent.target).initialize()
        shutil.rmtree(copied_source)
        self.assertEqual((independent.config / "mpv/mpv.conf").read_bytes(), MPV_BYTES)
        self.assertEqual((independent.config / "foot/foot.ini").read_bytes(), FOOT_BYTES_12)
        for path, expected in snapshots.items():
            self.assertEqual(digest(path), expected)


class ManifestContractTests(unittest.TestCase):
    def test_initializer_contract_and_mime_desktop_ids(self) -> None:
        with (REPOSITORY / "deployment/ownership-v2.toml").open("rb") as stream:
            manifest = tomllib.load(stream)
        hooks = {item["id"]: item for item in manifest["initializer"]}
        self.assertEqual(set(hooks), {"xdg-user-directories", "appearance-defaults", "power-idle-defaults"})
        text = (REPOSITORY / "seeds/home/.config/mimeapps.list").read_text(encoding="utf-8")
        self.assertEqual(text.count("[Default Applications]"), 1)
        self.assertNotIn("[Added Associations]", text)
        self.assertEqual(
            {value.rstrip(";") for line in text.splitlines() if "=" in line for value in [line.split("=", 1)[1]]},
            {"firefox.desktop", "thunar.desktop", "imv.desktop", "mpv.desktop",
             "org.gnome.TextEditor.desktop"},
        )


if __name__ == "__main__":
    unittest.main()
