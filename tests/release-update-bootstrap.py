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
from release import build as contract  # noqa: E402

spec = importlib.util.spec_from_file_location("phase5_fixtures", PROJECT / "tests/release-update-driver.py")
assert spec and spec.loader
phase5 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = phase5
spec.loader.exec_module(phase5)


def listing(tag: str, *, immutable=True, draft=False, assets=True,
            duplicate=None, prerelease=None, size=123) -> dict:
    name = contract.artifact_name(tag)
    files = [
        {"name": "release.json", "size": 100, "state": "uploaded",
         "browser_download_url": f"{boot.RELEASES}/download/{tag}/release.json"},
        {"name": name, "size": size, "state": "uploaded",
         "browser_download_url": f"{boot.RELEASES}/download/{tag}/{name}"},
    ] if assets else []
    if duplicate:
        files.append(copy.deepcopy(next(item for item in files if item["name"] == duplicate)))
    return {"tag_name": tag, "draft": draft, "immutable": immutable,
            "prerelease": ("-rc" in tag if prerelease is None else prerelease),
            "assets": files}


class FakeTransport:
    def __init__(self, rows=None, files=None):
        self.rows = rows or []
        self.files = files or {}
        self.calls = []

    def fetch(self, url, limit, destination=None):
        self.calls.append(url)
        data = (json.dumps(self.rows).encode() if url.startswith(boot.API + "?")
                else self.files[url])
        if len(data) > limit:
            raise boot.BootstrapError("bounded fixture download")
        if destination is None:
            return data
        destination.write_bytes(data)
        return None


class Fixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.release_temp = tempfile.TemporaryDirectory()
        cls.source, cls.metadata_path, cls.artifact_path, cls.target = phase5.BundleFixture.build(
            Path(cls.release_temp.name))

    @classmethod
    def tearDownClass(cls):
        cls.release_temp.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "root"
        (self.root / "run").mkdir(parents=True)
        identity = self.root / "usr/share/vanhyprarch/release.json"
        identity.parent.mkdir(parents=True)
        identity.write_bytes(contract.metadata_bytes(self.source))
        identity.chmod(0o644)
        self.identity_path = identity
        self.user = TargetUser("fixture", os.getuid(), os.getgid(), Path("/home/fixture"),
                               (os.getgid(),))
        row = listing(self.target["version"], size=self.target["artifact"]["size"])
        row["assets"][0]["size"] = self.metadata_path.stat().st_size
        self.transport = FakeTransport([row], {
            row["assets"][0]["browser_download_url"]: self.metadata_path.read_bytes(),
            row["assets"][1]["browser_download_url"]: self.artifact_path.read_bytes(),
        })
        self.updater = boot.Bootstrap(self.user, transport=self.transport,
                                     root=self.root, uid=os.getuid(), gid=os.getgid())


class SelectionTests(Fixture):
    def test_highest_semantic_release_can_be_on_later_page(self):
        source = copy.deepcopy(self.source)
        source["version"], source["channel"] = "v1.0.0", "stable"
        pages = {1: [listing(f"v1.0.{number}") for number in range(1, 101)],
                 2: [listing("v2.0.0"), listing("v1.1.0")]}

        class PagedTransport(FakeTransport):
            def fetch(self, url, limit, destination=None):
                self.calls.append(url)
                return json.dumps(pages[int(url.rsplit("page=", 1)[1])]).encode()

        self.updater.transport = PagedTransport()
        self.assertEqual(self.updater.discover(source).tag, "v2.0.0")
        self.assertEqual(self.updater.transport.calls,
                         [f"{boot.API}?per_page=100&page=1",
                          f"{boot.API}?per_page=100&page=2"])

    def test_stable_uses_semantic_order_and_ignores_candidates(self):
        source = copy.deepcopy(self.source)
        source["version"], source["channel"] = "v1.0.0", "stable"
        self.transport.rows = [listing("v1.0.9"), listing("v1.0.10"),
                               listing("v1.1.0-rc1"), listing("v1.0.0")]
        self.assertEqual(self.updater.discover(source).tag, "v1.0.10")

    def test_candidate_rc_order_then_stable_same_base(self):
        self.transport.rows = [listing("v1.0.0-rc9"), listing("v1.0.0-rc10"),
                               listing("v1.1.0-rc1")]
        self.assertEqual(self.updater.discover(self.source).tag, "v1.0.0-rc10")
        self.transport.rows.append(listing("v1.0.0"))
        self.assertEqual(self.updater.discover(self.source).tag, "v1.0.0")
        source = copy.deepcopy(self.source)
        source["version"] = "v1.0.0-rc2"
        self.assertEqual(self.updater.discover(source).tag, "v1.0.0")

    def test_no_newer_and_draft_or_malformed_tag_ignored(self):
        self.transport.rows = [listing("v1.0.0-rc1"), listing("v1.0.0-rc2", draft=True),
                               {"tag_name": "nonsense"}]
        self.assertIsNone(self.updater.discover(self.source))

    def test_publication_and_asset_failures_are_errors(self):
        for changes in ({"immutable": False}, {"assets": False},
                        {"duplicate": "release.json"},
                        {"duplicate": contract.artifact_name("v1.0.0-rc2")},
                        {"prerelease": False}):
            with self.subTest(changes=changes):
                self.transport.rows = [listing("v1.0.0-rc2", **changes)]
                with self.assertRaises(boot.BootstrapError):
                    self.updater.discover(self.source)
        for value in (None, "true", 1):
            with self.subTest(immutable=value):
                row = listing("v1.0.0-rc2")
                if value is None:
                    row.pop("immutable")
                else:
                    row["immutable"] = value
                self.transport.rows = [row]
                with self.assertRaisesRegex(boot.BootstrapError, "immutable"):
                    self.updater.discover(self.source)

    def test_duplicate_listing_key_and_unsupported_api_shape_fail(self):
        with self.assertRaises(boot.BootstrapError):
            boot._json(b'{"tag_name":"v1.0.0","tag_name":"v2.0.0"}')
        self.transport.rows = {"message": "rate limited"}
        with self.assertRaises(boot.BootstrapError):
            self.updater.discover(self.source)


class AcquisitionTests(Fixture):
    def _fake_driver(self, bundle, operation):
        self.calls.append((operation, bundle.stage, bundle.tree.stat().st_uid,
                           bundle.tree.stat().st_mode))
        if operation == "plan":
            return json.dumps({"source": self.source["version"],
                               "target": self.target["version"],
                               "target_sha256": self.target["artifact"]["sha256"],
                               "migrations": [], "authorities": {"system-integration": "plan"}})
        self.identity_path.write_bytes(self.metadata_path.read_bytes())
        return "complete"

    def test_no_update_and_unreleased_are_clean(self):
        self.transport.rows = []
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.updater.run_update(), 0)
        self.assertIn("up to date", out.getvalue())
        self.assertEqual(len(self.transport.calls), 1)
        self.identity_path.unlink()
        with self.assertRaisesRegex(boot.BootstrapError, "unreleased/development"):
            self.updater.run_update()

    def test_cancel_and_yes_use_verified_root_preview(self):
        self.calls = []
        self.updater._driver = self._fake_driver
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.updater.run_update(answer=lambda _: ""), 0)
        self.assertEqual([item[0] for item in self.calls], ["plan"])
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
        self.assertIn(self.target["summary"], out.getvalue())
        self.assertIn(f"{boot.RELEASES}/tag/{self.target['version']}", out.getvalue())
        self.assertFalse(list((self.root / "run").glob("vanhyprarch-preview-*")))
        self.calls = []
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.updater.run_update(answer=lambda _: "y"), 0)
        self.assertEqual([item[0] for item in self.calls], ["plan", "apply"])
        self.assertEqual(self.identity_path.read_bytes(), self.metadata_path.read_bytes())
        for _operation, stage, uid, mode in self.calls:
            self.assertEqual(stage.parent, self.root / "run")
            self.assertEqual(uid, os.getuid())
            self.assertFalse(mode & 0o022)

    def test_tampered_metadata_archive_and_plan_do_not_execute_apply(self):
        self.calls = []
        self.updater._driver = self._fake_driver
        row = self.transport.rows[0]
        metadata_url = row["assets"][0]["browser_download_url"]
        artifact_url = row["assets"][1]["browser_download_url"]
        for url, data in ((metadata_url, b"{}"),
                          (artifact_url, self.artifact_path.read_bytes() + b"bad")):
            with self.subTest(url=url):
                old = self.transport.files[url]
                self.transport.files[url] = data
                with self.assertRaises((boot.BootstrapError, contract.ReleaseError)):
                    self.updater.run_update(answer=lambda _: "y")
                self.transport.files[url] = old
        self.assertEqual(self.calls, [])

    def test_same_size_archive_corruption_and_tag_mismatch_never_execute(self):
        self.calls = []
        self.updater._driver = self._fake_driver
        row = self.transport.rows[0]
        artifact_url = row["assets"][1]["browser_download_url"]
        original = self.transport.files[artifact_url]
        self.transport.files[artifact_url] = bytes([original[0] ^ 1]) + original[1:]
        with self.assertRaises(contract.ReleaseError):
            self.updater.run_update(answer=lambda _: "y")
        self.transport.files[artifact_url] = original
        metadata_url = row["assets"][0]["browser_download_url"]
        original_metadata = self.transport.files[metadata_url]
        changed = copy.deepcopy(self.target)
        changed["version"] = "v1.0.0-rc3"
        changed["artifact"]["name"] = contract.artifact_name("v1.0.0-rc3")
        self.transport.files[metadata_url] = contract.metadata_bytes(changed)
        with self.assertRaisesRegex(boot.BootstrapError, "does not match"):
            self.updater.run_update(answer=lambda _: "y")
        self.transport.files[metadata_url] = original_metadata
        self.assertEqual(self.calls, [])

    def test_bounded_metadata_and_artifact_download_fail_before_handoff(self):
        self.calls = []
        self.updater._driver = self._fake_driver
        row = self.transport.rows[0]
        for url, data in ((row["assets"][0]["browser_download_url"],
                           b"x" * (contract.MAX_METADATA + 1)),
                          (row["assets"][1]["browser_download_url"], b"short")):
            with self.subTest(url=url):
                original = self.transport.files[url]
                self.transport.files[url] = data
                with self.assertRaises((boot.BootstrapError, contract.ReleaseError)):
                    self.updater.run_update(answer=lambda _: "y")
                self.transport.files[url] = original
        self.assertEqual(self.calls, [])

    def test_target_plan_failure_and_incomplete_apply_remain_nonzero(self):
        def fail_plan(_bundle, _operation):
            raise boot.BootstrapError("target plan failed")
        self.updater._driver = fail_plan
        with self.assertRaisesRegex(boot.BootstrapError, "plan failed"):
            self.updater.run_update(answer=lambda _: "y")
        self.assertEqual(self.identity_path.read_bytes(), contract.metadata_bytes(self.source))
        calls = []
        def incomplete(bundle, operation):
            calls.append(operation)
            if operation == "plan":
                return json.dumps({"source": self.source["version"],
                                   "target": self.target["version"],
                                   "target_sha256": self.target["artifact"]["sha256"],
                                   "migrations": [], "authorities": {}})
            raise boot.BootstrapError("update incomplete")
        self.updater._driver = incomplete
        with self.assertRaisesRegex(boot.BootstrapError, "update incomplete"):
            self.updater.run_update(answer=lambda _: "y")
        self.assertEqual(calls, ["plan", "apply"])

    def test_driver_handoff_is_preview_not_download_path(self):
        bundle = self.updater.store.prepare(self.metadata_path, self.artifact_path,
                                             permanent=False)
        try:
            completed = SimpleNamespace(returncode=0, stdout="{}", stderr="")
            self.updater.run = mock.Mock(return_value=completed)
            self.updater._driver(bundle, "plan")
            command = self.updater.run.call_args.args[0]
            self.assertEqual(command[1], str(bundle.tree / "install/release_update.py"))
            self.assertNotIn(str(self.metadata_path.parent), command[1])
            self.assertEqual(command[-2:], ["--release-artifact", str(bundle.artifact_path)])
        finally:
            self.updater.store.preview_cleanup(bundle)

    def test_active_journal_skips_discovery_and_resumes_exact_target(self):
        authority = phase5.FakeAuthorities(self.root)
        driver = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                               testing=True, authority=authority)
        authority.fail_before = "system-integration"
        with self.assertRaises(Exception):
            driver.apply(self.metadata_path, self.artifact_path)
        self.transport.rows = [listing("v1.0.0")]
        self.updater._driver = lambda _bundle, operation: driver.resume() if operation == "resume" else self.fail("wrong operation")
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(self.updater.run_update(), 0)
        self.assertEqual(self.transport.calls, [])
        self.assertIsNone(driver.journal.inspect())
        self.assertIn("complete", out.getvalue())

    def test_bad_journal_or_missing_retained_target_fails_without_discovery(self):
        with self.updater.journal.lock.acquire():
            self.updater.journal.begin(self.source, self.target)
        with self.assertRaises(Exception):
            self.updater.run_update()
        self.assertEqual(self.transport.calls, [])
        self.updater.journal.path.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(boot.JournalError):
            self.updater.run_update()
        self.assertEqual(self.transport.calls, [])

    def test_committed_identity_with_journal_uses_terminal_resume(self):
        authority = phase5.FakeAuthorities(self.root)
        driver = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                               testing=True, authority=authority)
        with mock.patch.object(driver.journal, "clear_after_commit", side_effect=OSError("interrupted")):
            with self.assertRaises(Exception):
                driver.apply(self.metadata_path, self.artifact_path)
        before = list(authority.calls)
        self.updater._driver = lambda _bundle, operation: driver.resume() if operation == "resume" else self.fail("wrong operation")
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(self.updater.run_update(), 0)
        self.assertEqual(authority.calls, before)
        self.assertEqual(self.transport.calls, [])

    def test_failed_resume_retains_journal_and_skips_network(self):
        authority = phase5.FakeAuthorities(self.root)
        driver = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                               testing=True, authority=authority)
        authority.fail_before = "system-integration"
        with self.assertRaises(Exception):
            driver.apply(self.metadata_path, self.artifact_path)
        self.updater._driver = lambda *_: (_ for _ in ()).throw(boot.BootstrapError("resume incomplete"))
        with self.assertRaisesRegex(boot.BootstrapError, "resume incomplete"):
            self.updater.run_update()
        self.assertIsNotNone(driver.journal.inspect())
        self.assertEqual(self.transport.calls, [])

    def test_active_journal_cannot_resume_as_another_target_user(self):
        authority = phase5.FakeAuthorities(self.root)
        driver = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                               testing=True, authority=authority)
        authority.fail_before = "system-integration"
        with self.assertRaises(Exception):
            driver.apply(self.metadata_path, self.artifact_path)
        other = TargetUser("other", self.user.uid, self.user.gid,
                           self.user.home, self.user.groups)
        updater = boot.Bootstrap(other, transport=self.transport, root=self.root,
                                 uid=os.getuid(), gid=os.getgid())
        updater._driver = lambda *_: self.fail("target code must not execute")
        with self.assertRaisesRegex(boot.BootstrapError, "different target user"):
            updater.run_update()
        self.assertEqual(self.transport.calls, [])


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
                with self.assertRaises(boot.BootstrapError):
                    boot.Transport().fetch(boot.API, limit)
        opener = SimpleNamespace(open=lambda *_args, **_kwargs: Response(b"abc", 3))
        with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
            with tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "archive"
                self.assertIsNone(boot.Transport().fetch(boot.API, 10, path))
                self.assertEqual(path.read_bytes(), b"abc")

    def test_http_rate_limit_and_network_error(self):
        for error, expected in ((urllib.error.HTTPError(boot.API, 403, "", {"X-RateLimit-Remaining": "0"}, None), "rate limit"),
                                (urllib.error.URLError("offline"), "network unavailable")):
            try:
                opener = SimpleNamespace(open=mock.Mock(side_effect=error))
                with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
                    with self.assertRaisesRegex(boot.BootstrapError, expected):
                        boot.Transport().fetch(boot.API, 10)
            finally:
                if isinstance(error, urllib.error.HTTPError):
                    error.close()

    def test_http_error_and_timeout(self):
        for error, expected in ((urllib.error.HTTPError(boot.API, 503, "", {}, None), "HTTP 503"),
                                (TimeoutError("timed out"), "network unavailable")):
            try:
                opener = SimpleNamespace(open=mock.Mock(side_effect=error))
                with mock.patch.object(boot.urllib.request, "build_opener", return_value=opener):
                    with self.assertRaisesRegex(boot.BootstrapError, expected):
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
        self.authority.state.write_text('{"schema":1,"schema":1}')
        with self.assertRaises(BootstrapIntegrationError):
            self.authority.plan(lifecycle="upgrade")
        self.authority.state.unlink()
        self.authority.state.parent.chmod(0o777)
        with self.assertRaises(BootstrapIntegrationError):
            self.authority.plan(lifecycle="fresh")

    def test_user_cli_crosses_sudo_once_with_resolved_account(self):
        with (mock.patch.object(boot.os, "geteuid", return_value=1000),
              mock.patch.object(boot.os, "getuid", return_value=1000),
              mock.patch.object(boot.pwd, "getpwuid",
                                return_value=SimpleNamespace(pw_name="fixture")),
              mock.patch.object(boot.subprocess, "call", return_value=0) as call):
            self.assertEqual(boot.main([]), 0)
        call.assert_called_once_with(["/usr/bin/sudo", "--",
                                      "/usr/local/bin/vanhyprarch-update",
                                      "--target-user", "fixture"])
        with mock.patch.object(boot.os, "geteuid", return_value=0):
            with self.assertRaises(SystemExit) as error:
                boot.main([])
        self.assertEqual(error.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
