#!/usr/bin/env python3
"""Offline installed updater discovery, acquisition, handoff and ownership tests."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
sys.path.insert(0, str(PROJECT / "install"))
from install import update_bootstrap as boot  # noqa: E402
from install.update_bootstrap_integration import (  # noqa: E402
    BootstrapIntegration, BootstrapIntegrationError, FILES,
)
from install.release_update import ReleaseUpdate, TargetUser  # noqa: E402
from install.release_migrations import MigrationContext, MigrationRegistry  # noqa: E402
from release import build as contract  # noqa: E402

spec = importlib.util.spec_from_file_location("phase5_fixtures", PROJECT / "tests/release-update-driver.py")
assert spec and spec.loader
phase5 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = phase5
spec.loader.exec_module(phase5)



class TransportTests(unittest.TestCase):
    def test_non_https_and_untrusted_host_rejected(self):
        for url in ("http://github.com/x", "https://evil.invalid/x",
                    "https://github.com.evil.invalid/x"):
            with self.assertRaises(boot.BootstrapError):
                boot.Transport().fetch(url, 10)

    def test_redirect_policy_and_limit(self):
        handler = boot._Redirects(asset=True)
        request = boot.urllib.request.Request(
            f"{boot.RELEASES}/download/v1.0.0/release.json",
            headers={"Authorization": "Bearer example", "Cookie": "session=example"})
        normal = "https://release-assets.githubusercontent.com/github-production-release-asset/file"
        redirected = handler.redirect_request(request, None, 302, "", {}, normal)
        self.assertEqual(redirected.full_url, normal)
        self.assertFalse(redirected.has_header("Authorization"))
        self.assertFalse(redirected.has_header("Cookie"))
        with self.assertRaises(boot.BootstrapError):
            handler.redirect_request(request, None, 302, "", {}, "http://evil.invalid/")
        with self.assertRaises(boot.BootstrapError):
            handler.redirect_request(request, None, 302, "", {}, "https://evil.invalid/file")
        with self.assertRaises(boot.BootstrapError):
            boot._Redirects(asset=False).redirect_request(
                boot.urllib.request.Request(boot.API), None, 302, "", {}, normal)
        handler = boot._Redirects(asset=True)
        for _ in range(3):
            handler.redirect_request(request, None, 302, "", {}, normal)
        with self.assertRaises(boot.BootstrapError):
            handler.redirect_request(request, None, 302, "", {}, normal)

    def test_transport_rejects_non_repository_api_and_direct_cdn(self):
        for url in ("https://api.github.com/repos/other/repo/releases",
                    "https://release-assets.githubusercontent.com/file",
                    f"{boot.API}?per_page=100&page=999"):
            with self.assertRaises(boot.BootstrapError):
                boot.Transport().fetch(url, 10)

    def test_stream_limit_and_truncation(self):
        class Response:
            status = 200
            url = boot.API
            def __init__(self, body, length):
                self.stream = io.BytesIO(body)
                self.headers = {"Content-Length": str(length)}
            def __enter__(self): return self
            def __exit__(self, *_): return None
            def read(self, size): return self.stream.read(size)
        for body, length, limit in ((b"abc", 5, 10), (b"abc", 3, 2)):
            opener = SimpleNamespace(open=lambda *_args, **_kwargs: Response(body, length))
            with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
                with self.assertRaises((boot.BootstrapError, boot.Unavailable)):
                    boot.Transport().fetch(boot.API, limit)
        opener = SimpleNamespace(open=lambda *_args, **_kwargs: Response(b"abc", 3))
        with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "archive"
                self.assertIsNone(boot.Transport().fetch(boot.API, 10, path))
                self.assertEqual(path.read_bytes(), b"abc")
        Response.status = 206
        with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
            with self.assertRaisesRegex(boot.BootstrapError, "unexpected"):
                boot.Transport().fetch(boot.API, 10)

    def test_http_rate_limit_and_network_error(self):
        for error, expected in ((urllib.error.HTTPError(boot.API, 403, "", {"X-RateLimit-Remaining": "0"}, None), "rate limit"),
                                (urllib.error.URLError("offline"), "network unavailable")):
            try:
                opener = SimpleNamespace(open=mock.Mock(side_effect=error))
                with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
                    with self.assertRaisesRegex(boot.Unavailable, expected):
                        boot.Transport().fetch(boot.API, 10)
            finally:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()

    def test_http_error_and_timeout(self):
        for error, expected in ((urllib.error.HTTPError(boot.API, 503, "", {}, None), "HTTP 503"),
                                (TimeoutError("timed out"), "network unavailable"),
                                (ConnectionResetError("interrupted"), "network unavailable")):
            try:
                opener = SimpleNamespace(open=mock.Mock(side_effect=error))
                with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
                    with self.assertRaisesRegex(boot.Unavailable, expected):
                        boot.Transport().fetch(boot.API, 10)
            finally:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()


class InstalledCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        self.root.mkdir()
        self.authority = BootstrapIntegration(PROJECT, self.root,
                                               uid=os.getuid(), gid=os.getgid())

    def test_fresh_publication_zipapp_and_upgraded_provenance(self):
        self.assertEqual(self.authority.plan(lifecycle="fresh"), "create")
        self.authority.apply(lifecycle="fresh")
        self.authority.validate()
        state = json.loads(self.authority.state.read_text())
        self.assertEqual(state["schema"], 3)
        self.assertEqual(state["update_protocol"], 1)
        self.assertEqual(set(state), {"schema", "sha256", "update_protocol",
                                     "distribution_initialized", "distribution_anchor_sha256"})
        self.assertEqual(stat.S_IMODE(self.authority.target.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.authority.state.stat().st_mode), 0o600)
        self.assertEqual(self.authority.plan(lifecycle="upgrade"), "preserve")
        result = subprocess.run(["python3", str(self.authority.target), "--help"],
                                capture_output=True, text=True, check=True)
        self.assertIn("--target-user", result.stdout)
        source = Path(self.temp.name) / "new-source"
        for name in FILES:
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / name, destination)
        (source / "install/update_bootstrap.py").write_bytes(
            (source / "install/update_bootstrap.py").read_bytes() + b"\n# next release\n")
        newer = BootstrapIntegration(source, self.root, uid=os.getuid(), gid=os.getgid())
        self.assertEqual(newer.plan(lifecycle="upgrade"), "replace")
        newer.apply(lifecycle="upgrade")
        newer.validate()

    def test_isolated_zipapp_contains_verifier_and_public_trust_resource(self):
        self.authority.apply(lifecycle="fresh")
        code = ("import sys,json; from pathlib import Path; sys.path.insert(0,sys.argv[1]); "
                "from importlib.resources import files; "
                "from install.signed_distribution import SecurityStore; "
                "from release.distribution import ROOT_YEARS,MAX_CATALOG_LIFETIME; "
                "data=files('release').joinpath('trust.json').read_bytes(); "
                "assert data==Path(sys.argv[2]).read_bytes(); "
                "value=json.loads(data); assert value['schema']==1; "
                "assert ROOT_YEARS==5 and MAX_CATALOG_LIFETIME==31536000; "
                "print('packaged verifier and exact source public trust: PASS')")
        result = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(self.authority.target),
                                 str(PROJECT / "release/trust.json")],
                                capture_output=True, text=True, check=True)
        self.assertIn("PASS", result.stdout)

    def test_stable_upgrade_plans_rc1_provenance_before_migration_0001(self):
        self.authority.apply(lifecycle="fresh")
        state = json.loads(self.authority.state.read_text())
        self.authority.state.write_text(
            json.dumps({"schema": 1, "sha256": state["sha256"]}, sort_keys=True) + "\n"
        )
        registry = MigrationRegistry(PROJECT)
        self.assertEqual(registry.declaration["version"], "v1.0.1")
        self.assertEqual(registry.declaration["channel"], "stable")
        # The published stable target remains a historical upgrade fixture.
        target = contract.parse_metadata(contract.metadata_bytes({
            **registry.declaration,
            "version": "v1.0.0", "channel": "stable",
            "summary": "First stable release of Vanilla HyprArch.",
            "commit": "2" * 40,
            "artifact": {"name": contract.artifact_name("v1.0.0"),
                         "size": 1, "sha256": "2" * 64},
        }))
        source = contract.parse_metadata(contract.metadata_bytes({
            **target,
            "version": "v1.0.0-rc1", "channel": "candidate",
            "commit": "1" * 40, "minimum_installed_version": None,
            "migration_level": 0,
            "artifact": {"name": contract.artifact_name("v1.0.0-rc1"),
                         "size": 1, "sha256": "1" * 64},
        }))
        self.assertEqual(registry.range_from(source["migration_level"]), [1])
        migration = registry._module(1)
        context = MigrationContext(self.root, PROJECT, source, target, 1,
                                   registry.entries[1]["scope"])
        self.assertIn("schema 1 to schema 2", migration.plan(context)[0])
        self.assertEqual(self.authority.plan(lifecycle="upgrade"), "preserve")
        with self.assertRaisesRegex(BootstrapIntegrationError, "requires migration"):
            self.authority.validate()
        migration.apply(context)
        self.assertTrue(migration.validate(context))
        self.assertEqual(json.loads(self.authority.state.read_text()), {
            "schema": 2, "sha256": state["sha256"], "update_protocol": 1,
        })
        self.authority.apply(lifecycle="upgrade")
        self.authority.validate()

    def test_publication_modes_do_not_depend_on_umask(self):
        old = os.umask(0o077)
        try:
            self.authority.apply(lifecycle="fresh")
        finally:
            os.umask(old)
        self.assertEqual(stat.S_IMODE(self.authority.target.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.authority.target.parent.stat().st_mode), 0o755)
        self.assertEqual(stat.S_IMODE(self.authority.state.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.authority.state.parent.stat().st_mode), 0o700)

    def test_missing_foreign_and_unsafe_installed_command_fail(self):
        self.authority.apply(lifecycle="fresh")
        self.authority.target.unlink()
        with self.assertRaisesRegex(BootstrapIntegrationError, "missing"):
            self.authority.plan(lifecycle="upgrade")
        self.authority.target.symlink_to(PROJECT / "install/update_bootstrap.py")
        with self.assertRaises(BootstrapIntegrationError):
            self.authority.plan(lifecycle="upgrade")

    def test_corrupt_provenance_and_unsafe_parent_fail_closed(self):
        self.authority.apply(lifecycle="fresh")
        self.authority.state.write_text('{"schema":2,"schema":2}')
        with self.assertRaises(BootstrapIntegrationError):
            self.authority.plan(lifecycle="upgrade")
        self.authority.state.unlink()
        self.authority.state.parent.chmod(0o777)
        with self.assertRaises(BootstrapIntegrationError):
            self.authority.plan(lifecycle="fresh")

    def test_invalid_user_context_reports_safely_before_sudo(self):
        for environment in ({"XDG_CONFIG_HOME": "relative-config"},
                            {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/private-session-bus"}):
            with (self.subTest(environment=environment),
                  mock.patch.dict(boot.os.environ, environment, clear=True),
                  mock.patch.object(boot.os, "geteuid", return_value=1000),
                  mock.patch.object(boot.os, "getuid", return_value=1000),
                  mock.patch.object(boot.pwd, "getpwuid",
                                    return_value=SimpleNamespace(pw_name="fixture", pw_dir="/home/fixture")),
                  mock.patch.object(boot.subprocess, "call") as call,
                  contextlib.redirect_stderr(io.StringIO()) as error):
                self.assertEqual(boot.main([]), 1)
                call.assert_not_called()
                self.assertEqual(error.getvalue(),
                                 "Vanilla HyprArch update unavailable: invalid target-user XDG context\n")

    def test_user_cli_crosses_sudo_once_with_resolved_account(self):
        with (mock.patch.dict(boot.os.environ, {}, clear=True),
              mock.patch.object(boot.os, "geteuid", return_value=1000),
              mock.patch.object(boot.os, "getuid", return_value=1000),
              mock.patch.object(boot.pwd, "getpwuid",
                                return_value=SimpleNamespace(pw_name="fixture", pw_dir="/home/fixture")),
              mock.patch.object(boot.subprocess, "call", return_value=0) as call):
            self.assertEqual(boot.main([]), 0)
        call.assert_called_once()
        argv = call.call_args.args[0]
        self.assertEqual(argv[:-1], ["/usr/bin/sudo", "--", "/usr/local/bin/vanhyprarch-update",
                                    "--target-user", "fixture", "--target-context-json"])
        self.assertEqual(json.loads(argv[-1])["uid"], 1000)
        self.assertEqual(json.loads(argv[-1])["environment"]["HOME"], "/home/fixture")
        with mock.patch.object(boot.os, "geteuid", return_value=0):
            with self.assertRaises(SystemExit) as error:
                boot.main([])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
