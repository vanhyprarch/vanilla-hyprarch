#!/usr/bin/python
"""Isolated provider conflict tests: no live bus, password, or keyring reads."""
from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("secret_service", str(ROOT / "install/secret_service_preflight.py"))
spec = importlib.util.spec_from_loader(loader.name, loader)
MODULE = importlib.util.module_from_spec(spec)
loader.exec_module(MODULE)

REGISTRATION = "[D-BUS Service]\nName=org.freedesktop.secrets\nExec=/usr/bin/gnome-keyring-daemon --start --foreground --components=secrets\n"


class ProviderTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="vha-secrets-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.env = {"HOME": "/home/tester", "XDG_RUNTIME_DIR": "/run/user/1000"}
        self.log = []
        self.owner = False
        self.activatable = []
        self.executable_owner = "gnome-keyring"
        self.login_locked = False
        self.daemon = "/usr/bin/gnome-keyring-daemon"
        self.audit = MODULE.ProviderAudit(environment=self.env, root=self.root,
                                         uid=os.getuid(), runner=self.fake_run)

    def write(self, path, text):
        target = self.root / path.lstrip("/")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
        return target

    def bus_socket(self):
        target = self.root / "run/user/1000/bus"
        target.parent.mkdir(parents=True, exist_ok=True)
        sock = socket.socket(socket.AF_UNIX)
        self.addCleanup(sock.close)
        sock.bind(str(target))

    def process(self, executable=None):
        target = self.write(self.daemon, "fixture executable")
        self.write("/proc/123/stat", "123 (gnome-keyring) " + " ".join(["0"] * 19 + ["42", "0"]))
        (self.root / "proc/123/exe").symlink_to(target if executable is None else executable)

    def fake_run(self, argv):
        self.log.append(list(argv))
        if argv[0] == "/usr/bin/pacman":
            return self.executable_owner
        if "get-property" in argv:
            self.assertEqual(argv[-1], "Locked")
            return json.dumps({"data": self.login_locked})
        method = argv[argv.index("call") + 4]
        values = {"NameHasOwner": [self.owner], "ListActivatableNames": [self.activatable],
                  "GetNameOwner": [":1.22"], "GetConnectionUnixProcessID": [123],
                  "GetConnectionUnixUser": [os.getuid()]}
        self.assertIn("--auto-start=no", argv)
        if method == "ReadAlias":
            self.assertIn(argv[-1], ("login", "default"))
            return json.dumps({"data": ["/org/freedesktop/secrets/collection/login"]})
        if method == "SearchItems":
            self.assertEqual(argv[-4:], ["a{ss}", "1", "server", "Nextcloud"])
            return json.dumps({"data": [["/org/freedesktop/secrets/collection/login/1"], []]})
        return json.dumps({"data": values[method]})

    def test_absent_provider_and_installed_keepassxc_disabled(self):
        self.assertEqual(self.audit.preflight(), {"provider": "none", "current_owner": "no-session",
                                                 "configured_provider": "none"})
        self.write("/home/tester/.config/keepassxc/keepassxc.ini", "[FdoSecrets]\nEnabled=false\n")
        self.assertEqual(self.audit.preflight()["provider"], "none")
        self.assertFalse(self.log)  # No package Provides query or daemon activation.

    def test_configured_keepassxc_blocks_and_remains_untouched(self):
        target = self.write("/home/tester/.config/keepassxc/keepassxc.ini", "[FdoSecrets]\nEnabled=true\n")
        before = target.read_bytes(), target.stat().st_ino
        with self.assertRaisesRegex(MODULE.ProviderError, "configured KeePassXC"):
            self.audit.preflight()
        self.assertEqual((target.read_bytes(), target.stat().st_ino), before)
        self.assertFalse(self.log)

    def test_existing_gnome_registration_and_current_owner_are_supported(self):
        self.write("/usr/share/dbus-1/services/org.freedesktop.secrets.service", REGISTRATION)
        self.assertEqual(self.audit.preflight()["provider"], "gnome-keyring")
        self.bus_socket()
        self.process()
        self.owner = True
        self.assertEqual(self.audit.preflight()["current_owner"], "gnome-keyring")

    def test_competing_registration_even_when_shadowed_blocks(self):
        self.write("/home/tester/.local/share/dbus-1/services/org.freedesktop.secrets.service", REGISTRATION)
        target = self.write("/usr/share/dbus-1/services/other-name.service",
                            REGISTRATION.replace(MODULE.DAEMON, "/usr/bin/keepassxc"))
        before = target.read_bytes(), target.stat().st_ino
        with self.assertRaisesRegex(MODULE.ProviderError, "competing Secret Service registration"):
            self.audit.preflight()
        self.assertEqual((target.read_bytes(), target.stat().st_ino), before)

    def test_custom_service_directory_and_xdg_paths_are_inspected(self):
        self.write("/usr/share/dbus-1/session.conf", '<busconfig><include>/etc/dbus-1/session-local.conf</include></busconfig>')
        self.write("/etc/dbus-1/session-local.conf", '<busconfig><servicedir>/opt/providers</servicedir></busconfig>')
        self.write("/opt/providers/custom.service", REGISTRATION.replace(MODULE.DAEMON, "/usr/bin/other-provider"))
        with self.assertRaises(MODULE.ProviderError):
            self.audit.preflight()
        self.env["XDG_CONFIG_HOME"] = "/custom/config"
        self.write("/custom/config/keepassxc/keepassxc.ini", "[FdoSecrets]\nEnabled=true\n")
        with self.assertRaisesRegex(MODULE.ProviderError, "configured KeePassXC"):
            MODULE.ProviderAudit(environment=self.env, root=self.root).preflight()

    def test_competing_current_owner_blocks_without_daemon_start(self):
        self.bus_socket()
        alternate = self.write("/usr/bin/keepassxc", "fixture alternate")
        self.process(executable=alternate)
        self.owner = True
        with self.assertRaisesRegex(MODULE.ProviderError, "competing current"):
            self.audit.preflight()
        self.assertFalse(any(argv[0] == MODULE.DAEMON for argv in self.log))

    def test_ambiguous_activatable_provider_and_nonstandard_bus_block(self):
        self.bus_socket()
        self.activatable = [MODULE.NAME]
        with self.assertRaisesRegex(MODULE.ProviderError, "activatable"):
            self.audit.preflight()
        self.env["DBUS_SESSION_BUS_ADDRESS"] = "unix:path=/custom/bus"
        with self.assertRaisesRegex(MODULE.ProviderError, "nonstandard user bus"):
            self.audit.preflight()

    def test_malformed_settings_registration_and_xml_fail_closed(self):
        for path, text in (("/home/tester/.config/keepassxc/keepassxc.ini", "[FdoSecrets]\nEnabled=unknown\n"),
                           ("/usr/share/dbus-1/services/org.freedesktop.secrets.service", "invalid"),
                           ("/usr/share/dbus-1/session.conf", "<malformed")):
            with self.subTest(path=path):
                target = self.write(path, text)
                with self.assertRaises((ValueError, MODULE.configparser.Error, MODULE.ET.ParseError)):
                    self.audit.preflight()
                target.unlink()

    def test_unrelated_package_registration_symlink_is_supported(self):
        target = self.write("/other/systemd.service", "[D-BUS Service]\nName=org.freedesktop.systemd1\nExec=/bin/false\n")
        link = self.root / "usr/share/dbus-1/services/org.freedesktop.systemd1.service"
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        self.assertEqual(self.audit.preflight()["provider"], "none")

    def test_command_errors_do_not_expose_output_and_do_not_use_password_stdin(self):
        completed = mock.Mock(returncode=1, stdout="sensitive-fixture-value", stderr="sensitive-fixture-value")
        with mock.patch.object(MODULE.subprocess, "run", return_value=completed) as call:
            with self.assertRaises(MODULE.ProviderError) as error:
                MODULE.run([MODULE.DAEMON, "--start", "--components=secrets"])
        self.assertNotIn("sensitive-fixture-value", str(error.exception))
        self.assertEqual(call.call_args.kwargs["stdin"], MODULE.subprocess.DEVNULL)
        self.assertNotIn("shell", call.call_args.kwargs)

    def test_no_user_bus_and_keyrings_remain_untouched(self):
        keyring = self.write("/home/tester/.local/share/keyrings/login.keyring", "opaque fixture; never read by audit")
        before = keyring.stat().st_ino, keyring.stat().st_mtime_ns
        self.assertEqual(self.audit.preflight()["current_owner"], "no-session")
        self.assertEqual((keyring.stat().st_ino, keyring.stat().st_mtime_ns), before)
        self.assertFalse(self.log)

    def test_kpxc_config_override_is_inspected(self):
        self.env["KPXC_CONFIG"] = "/custom/keepass.ini"
        self.write("/custom/keepass.ini", "[FdoSecrets]\nEnabled=true\n")
        with self.assertRaisesRegex(MODULE.ProviderError, "configured KeePassXC"):
            self.audit.preflight()

    def test_provider_symlink_requires_review_without_altering_it(self):
        target = self.write("/custom/registration", REGISTRATION)
        link = self.root / "usr/share/dbus-1/services/org.freedesktop.secrets.service"
        link.parent.mkdir(parents=True)
        link.symlink_to(target)
        with self.assertRaisesRegex(MODULE.ProviderError, "symlinked"):
            self.audit.preflight()
        self.assertTrue(link.is_symlink())

    def test_ambiguous_executable_package_blocks(self):
        self.bus_socket()
        self.process()
        self.owner = True
        self.executable_owner = "other-provider"
        with self.assertRaisesRegex(MODULE.ProviderError, "executable ownership"):
            self.audit.preflight()

    def test_standard_and_custom_context_are_captured_before_sudo(self):
        home = Path("/home/tester")
        standard = MODULE.capture_context({}, 1000, home)
        self.assertEqual(standard["environment"]["XDG_CONFIG_HOME"], str(home / ".config"))
        custom = MODULE.capture_context({"XDG_CONFIG_HOME": "/custom/config", "XDG_DATA_HOME": "/custom/data",
                                         "XDG_DATA_DIRS": "/opt/data:/usr/share", "PASSWORD": "never-capture"}, 1000, home)
        self.assertEqual(MODULE.context_environment(custom, 1000, home)["XDG_CONFIG_HOME"], "/custom/config")
        self.assertNotIn("PASSWORD", custom["environment"])
        self.write("/custom/config/keepassxc/keepassxc.ini", "[FdoSecrets]\nEnabled=true\n")
        env = MODULE.context_environment(custom, 1000, home)
        with self.assertRaisesRegex(MODULE.ProviderError, "configured KeePassXC"):
            MODULE.ProviderAudit(environment=env, root=self.root).preflight()

    def test_context_unknown_identity_missing_paths_and_relative_values_block(self):
        home = Path("/home/tester")
        for context in (None, {}, {"uid": 123, "environment": {}},
                        {"uid": 1000, "environment": {"HOME": str(home)}}):
            with self.subTest(context=context), self.assertRaises(MODULE.ProviderError):
                MODULE.context_environment(context, 1000, home)
        for values in ({"XDG_CONFIG_HOME": "relative"}, {"XDG_DATA_DIRS": "/usr/share:relative"}):
            with self.assertRaises(MODULE.ProviderError):
                MODULE.capture_context(values, 1000, home)

    def test_private_bus_or_unverifiable_runtime_context_blocks_capture(self):
        for values in ({"DBUS_SESSION_BUS_ADDRESS": "unix:path=/custom/bus"},
                       {"XDG_RUNTIME_DIR": "/custom/runtime"}):
            with self.assertRaisesRegex(MODULE.ProviderError, "nonstandard"):
                MODULE.capture_context(values, 1000, Path("/home/tester"))

    def test_malformed_unrelated_registration_does_not_become_provider(self):
        self.write("/usr/share/dbus-1/services/org.example.Unrelated.service", "malformed unrelated contents")
        self.assertEqual(self.audit.preflight()["provider"], "none")

    def test_acceptance_probe_reads_only_metadata_and_counts(self):
        loader = importlib.machinery.SourceFileLoader("secret_service_live", str(ROOT / "tests/secret-service-live.py"))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        probe = importlib.util.module_from_spec(spec)
        loader.exec_module(probe)
        self.assertEqual(probe.inspect(self.audit), {"gnome_keyring_owner": False})
        self.bus_socket()
        self.process()
        self.owner = True
        keyring = self.write("/home/tester/.local/share/keyrings/login.keyring", "opaque fixture")
        keyring.chmod(0o600)
        before = keyring.stat().st_ino, keyring.stat().st_mtime_ns
        result = probe.inspect(self.audit)
        self.assertTrue(all(result[k] for k in ("gnome_keyring_owner", "default_is_login", "login_unlocked", "persistent_login_file")))
        self.assertEqual(result["gnome_keyring_processes"], 1)
        self.assertEqual(result["nextcloud_login_items_unlocked"], 1)
        self.assertEqual((keyring.stat().st_ino, keyring.stat().st_mtime_ns), before)
        self.assertFalse(any("GetSecret" in str(args) or "Attributes" in args for args in self.log))
        self.login_locked = True
        self.assertFalse(probe.inspect(self.audit)["login_unlocked"])


if __name__ == "__main__":
    unittest.main()
