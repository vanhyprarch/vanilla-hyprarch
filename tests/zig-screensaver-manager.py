#!/usr/bin/python

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import types
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
MANAGER = REPOSITORY / "install/zig-screensaver/manager.py"
SERVERPLAN_URL = (
    "https://vanhyprarch.it/dist/v1/vanhyprarch-zig-player/releases/v0.1.1/assets/"
    "vanhyprarch-zig-player-v0.1.1-linux-x86_64.tar.gz"
)


def load_manager():
    module = types.ModuleType("zig_manager_under_test")
    module.__file__ = str(MANAGER)
    exec(compile(MANAGER.read_text(encoding="utf-8"), str(MANAGER), "exec"),
        module.__dict__)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ZigScreensaverManagerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="zig-manager-test.")
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.data = self.root / "data"
        self.runtime = self.root / "runtime"
        self.resources = self.root / "resources"
        self.source = self.root / "source"
        for path in (self.home, self.data, self.runtime, self.resources, self.source):
            path.mkdir(mode=0o700)
        shutil.copy2("/usr/bin/true", self.source / "vanhyprarch-zig-player")
        (self.source / "LICENSE").write_text("test license\n", encoding="utf-8")
        (self.source / "THIRD_PARTY_NOTICES.md").write_text("test notices\n", encoding="utf-8")
        (self.source / "README.md").write_text("test readme\n", encoding="utf-8")
        self.original_readme_hash = digest(self.source / "README.md")
        self.archive = self.root / "fixture.tar.gz"
        self.write_archive()
        self.metadata = self.resources / "vanhyprarch-zig-player.conf"
        self.write_metadata()
        self.controller = self.root / "controller"
        self.idle = self.root / "idle"
        self.log = self.root / "operations.log"
        self.controller.write_text("#!/bin/sh\nprintf 'controller:%s\\n' \"$*\" >> \"$MOCK_LOG\"\n", encoding="utf-8")
        self.idle.write_text(
            "#!/bin/sh\n"
            "printf 'idle:%s\\n' \"$*\" >> \"$MOCK_LOG\"\n"
            "if [ \"${1-}\" = reconcile-screensaver ] && [ \"${2-}\" = installed ] "
            "&& [ ! -e \"$MOCK_MARKER\" ]; then exit 3; fi\n"
            "if [ \"${1-}\" = reconcile-screensaver ] && [ \"${2-}\" = installed ] "
            "&& [ -e \"$MOCK_FAIL_INSTALLED\" ]; then rm -f \"$MOCK_FAIL_INSTALLED\"; exit 1; fi\n"
            "if [ \"${1-}\" = reconcile-screensaver ] && [ \"${2-}\" = absent ] "
            "&& [ -e \"$MOCK_FAIL_ABSENT\" ]; then "
            "if [ \"$(cat \"$MOCK_FAIL_ABSENT\")\" = defer ]; then printf 'now\\n' > \"$MOCK_FAIL_ABSENT\"; "
            "else rm -f \"$MOCK_FAIL_ABSENT\"; exit 1; fi; fi\n"
            "if [ \"${1-}\" = remove-screensaver ] && [ -e \"$MOCK_FAIL_REMOVE\" ]; "
            "then rm -f \"$MOCK_FAIL_REMOVE\"; exit 1; fi\n"
            "if [ \"${1-}\" = screensaver-uninstall-plan ]; then "
            "printf 'stored_lock=screensaver\\nresulting_lock=display\\npreference_sha256='; "
            "cat \"$MOCK_PREFERENCE_HASH\"; fi\n",
            encoding="utf-8")
        self.controller.chmod(0o755)
        self.idle.chmod(0o755)
        self.preference_hash = self.root / "preference-hash"
        self.preference_hash.write_text("a" * 64 + "\n", encoding="utf-8")
        self.environment = os.environ.copy()
        self.environment.update({
            "HOME": str(self.home),
            "XDG_DATA_HOME": str(self.data),
            "XDG_RUNTIME_DIR": str(self.runtime),
            "VANHYPRARCH_ALLOW_TEST_OVERRIDES": "1",
            "VANHYPRARCH_ZIG_SCREENSAVER_RESOURCE_DIR": str(self.resources),
            "VANHYPRARCH_TEST_ARCHIVE": str(self.archive),
            "VANHYPRARCH_TARGET_ARCHITECTURE": "x86_64",
            "VANHYPRARCH_SCREENSAVER_EXECUTABLE": str(self.controller),
            "VANHYPRARCH_IDLE_EXECUTABLE": str(self.idle),
            "MOCK_LOG": str(self.log),
            "MOCK_FAIL_INSTALLED": str(self.root / "fail-installed"),
            "MOCK_FAIL_REMOVE": str(self.root / "fail-remove"),
            "MOCK_FAIL_ABSENT": str(self.root / "fail-absent"),
            "MOCK_MARKER": str(self.data / "vanhyprarch/components/zig-screensaver"),
            "MOCK_PREFERENCE_HASH": str(self.preference_hash),
        })

    def tearDown(self):
        self.temporary.cleanup()

    def write_archive(self, extra=False):
        root = "vanhyprarch-zig-player-test-linux-x86_64"
        with tarfile.open(self.archive, "w:gz") as package:
            directory = tarfile.TarInfo(root + "/")
            directory.type = tarfile.DIRTYPE
            directory.mode = 0o755
            package.addfile(directory)
            for name in ("LICENSE", "README.md", "THIRD_PARTY_NOTICES.md", "vanhyprarch-zig-player"):
                package.add(self.source / name, arcname=f"{root}/{name}", recursive=False)
            if extra:
                package.add(self.source / "README.md", arcname=f"{root}/unexpected", recursive=False)

    def write_metadata(self, archive_hash=None):
        values = {
            "VERSION": "v0.1.1", "ARCHITECTURE": "x86_64",
            "ASSET": "vanhyprarch-zig-player-test-linux-x86_64.tar.gz",
            "SHA256": archive_hash or digest(self.archive),
            "BINARY_SHA256": digest(self.source / "vanhyprarch-zig-player"),
            "LICENSE_SHA256": digest(self.source / "LICENSE"),
            "NOTICES_SHA256": digest(self.source / "THIRD_PARTY_NOTICES.md"),
            "README_SHA256": digest(self.source / "README.md"),
            "REPOSITORY_URL": "https://example.invalid/repository",
            "RELEASE_URL": "https://example.invalid/release",
            "DOWNLOAD_URL": "https://example.invalid/download",
            "SOURCE_TAG_URL": "https://example.invalid/tag",
            "SOURCE_ARCHIVE_URL": "https://example.invalid/source",
        }
        self.metadata.write_text("".join(
            f"VANHYPRARCH_ZIG_PLAYER_{key}={value}\n" for key, value in values.items()),
            encoding="utf-8")

    def run_manager(self, *arguments, success=True):
        result = subprocess.run([str(MANAGER), *arguments], env=self.environment,
            text=True, capture_output=True, check=False)
        if success and result.returncode != 0:
            self.fail(f"manager failed: {result.stderr}")
        if not success and result.returncode == 0:
            self.fail("manager unexpectedly succeeded")
        return result

    def status(self):
        return json.loads(self.run_manager("component-status", "--json").stdout)

    def run_transport(self, responses, operation="install", success=True):
        module = load_manager()
        environment = self.environment.copy()
        environment.pop("VANHYPRARCH_TEST_ARCHIVE")
        requests = []
        work_directories = []
        real_run = module.run
        real_temporary_directory = tempfile.TemporaryDirectory
        stdout, stderr = io.StringIO(), io.StringIO()

        def staging_directory(**kwargs):
            temporary = real_temporary_directory(dir=self.root, **kwargs)
            work = Path(temporary.name)
            self.assertEqual(work.stat().st_mode & 0o777, 0o700)
            work_directories.append(work)
            return temporary

        def transport_run(argv, *, check=True):
            if argv[0] != "/usr/bin/curl":
                return real_run(argv, check=check)
            self.assertFalse(check)
            self.assertLess(len(requests), len(responses), "unexpected transport retry")
            code, payload, message = responses[len(requests)]
            requests.append(argv[-1])
            archive = Path(argv[argv.index("--output") + 1])
            self.assertEqual(archive.parent, work_directories[-1])
            self.assertFalse(archive.exists(), "partial download was not discarded")
            self.assertEqual(argv[1], "--disable")
            for option, expected in (("--proto", "=https"), ("--proto-redir", "=https"),
                    ("--connect-timeout", "10"), ("--max-time", "120")):
                self.assertEqual(argv[argv.index(option) + 1], expected)
            self.assertIn("--fail", argv)
            if isinstance(payload, OSError):
                raise payload
            if payload is not None:
                archive.write_bytes(payload)
            return subprocess.CompletedProcess(argv, code, stdout="", stderr=message)

        with mock.patch.dict(os.environ, environment, clear=True), \
                mock.patch.object(module, "run", side_effect=transport_run), \
                mock.patch.object(module.tempfile, "TemporaryDirectory", side_effect=staging_directory), \
                redirect_stdout(stdout), redirect_stderr(stderr):
            github_url = module.parse_metadata(self.metadata)["VANHYPRARCH_ZIG_PLAYER_DOWNLOAD_URL"]
            code = module.main([str(MANAGER), operation])
        self.assertEqual(code, 0 if success else 1, stderr.getvalue())
        self.assertEqual(len(requests), len(responses))
        self.assertTrue(work_directories)
        for work in work_directories:
            self.assertFalse(work.exists(), "temporary acquisition files survived")
        expected_urls = [github_url]
        if len(responses) == 2:
            expected_urls.append(SERVERPLAN_URL)
        self.assertEqual(requests, expected_urls)
        return stderr.getvalue()

    def installed_snapshot(self):
        files = [self.home / ".local/bin/vanhyprarch-zig-player",
            self.data / "vanhyprarch/components/zig-screensaver"]
        for directory in (self.data / "licenses/vanhyprarch-zig-player",
                self.data / "doc/vanhyprarch-zig-player"):
            files.extend(directory.iterdir())
        return {path: (path.read_bytes(), path.stat().st_mode & 0o777) for path in files}

    def test_github_transport_success_publishes_valid_payload(self):
        self.run_transport([(0, self.archive.read_bytes(), "")])
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        self.assertEqual(binary.read_bytes(), (self.source / "vanhyprarch-zig-player").read_bytes())
        self.assertEqual(binary.stat().st_mode & 0o777, 0o755)
        release = self.data / "doc/vanhyprarch-zig-player/vanhyprarch-zig-player.conf"
        self.assertEqual(release.read_bytes(), self.metadata.read_bytes())
        self.assertEqual(release.stat().st_mode & 0o777, 0o644)
        marker = self.data / "vanhyprarch/components/zig-screensaver"
        self.assertEqual(marker.read_bytes(), b"vanhyprarch-zig-screensaver-v1\n")
        self.assertEqual(marker.stat().st_mode & 0o777, 0o644)
        self.assertEqual(self.status()["state"], "installed")

    def test_http_404_and_network_failures_fall_back(self):
        archive_bytes = self.archive.read_bytes()
        self.run_manager("install")
        for code, message in ((22, "HTTP 404"), (6, "host resolution failed"),
                (7, "connection failed"), (28, "timeout"), (18, "partial transfer"),
                (56, "connection interrupted")):
            with self.subTest(code=code):
                diagnostic = self.run_transport([(code, b"partial GitHub bytes", message),
                    (0, archive_bytes, "")], operation="reinstall")
                self.assertIn("trying ServerPlan", diagnostic)
                self.assertEqual(self.status()["state"], "installed")

    def test_http_404_fallback_installs_from_clean_state(self):
        self.run_transport([(22, b"partial", "HTTP 404"), (0, self.archive.read_bytes(), "")])
        self.assertEqual(self.status()["state"], "installed")
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        self.assertEqual(digest(binary), digest(self.source / "vanhyprarch-zig-player"))

    def test_checksum_failure_never_retries_another_source(self):
        for responses in ([(0, b"wrong GitHub archive", "")],
                [(22, None, "HTTP 404"), (0, b"wrong ServerPlan archive", "")],
                [(0, self.archive.read_bytes()[:100], "")]):
            with self.subTest(sources=len(responses)):
                diagnostic = self.run_transport(responses, success=False)
                self.assertIn("archive checksum verification failed", diagnostic)
                self.assertEqual(self.status()["state"], "not-installed")

    def test_completed_invalid_payload_never_falls_back(self):
        for failure in ("member", "layout", "ELF", "runtime library"):
            with self.subTest(failure=failure):
                if failure == "ELF":
                    player = self.source / "vanhyprarch-zig-player"
                    contents = bytearray(player.read_bytes())
                    contents[18:20] = (183).to_bytes(2, "little")
                    player.write_bytes(contents)
                self.write_archive(extra=failure == "layout")
                self.write_metadata()
                if failure == "member":
                    contents = self.metadata.read_text()
                    self.metadata.write_text(contents.replace(self.original_readme_hash, "0" * 64))
                if failure == "runtime library":
                    shutil.copy2("/usr/bin/true", self.source / "vanhyprarch-zig-player")
                    self.write_archive()
                    self.write_metadata()
                    self.environment["VANHYPRARCH_TEST_MISSING_LIBRARY"] = "1"
                diagnostic = self.run_transport([(0, self.archive.read_bytes(), "")], success=False)
                expected = {"member": "member checksum", "layout": "unexpected path",
                    "ELF": "not an x86_64 ELF", "runtime library": "required runtime library"}
                self.assertIn(expected[failure], diagnostic)
                self.assertEqual(self.status()["state"], "not-installed")

    def test_failed_transport_reinstall_preserves_complete_installation(self):
        self.run_manager("install")
        before = self.installed_snapshot()
        before_log = self.log.read_bytes()
        failures = (
            [(22, b"partial", "HTTP 404"), (28, b"partial fallback", "timeout")],
            [(0, b"wrong GitHub archive", "")],
            [(22, None, "HTTP 404"), (0, b"wrong ServerPlan archive", "")],
        )
        for responses in failures:
            with self.subTest(sources=len(responses)):
                diagnostic = self.run_transport(responses, operation="reinstall", success=False)
                if responses[-1][0] != 0:
                    self.assertIn("GitHub download failed", diagnostic)
                    self.assertIn("ServerPlan download failed", diagnostic)
                self.assertEqual(self.installed_snapshot(), before)
                self.assertEqual(self.log.read_bytes(), before_log)
                self.assertEqual(self.status()["state"], "installed")

    def test_local_and_security_curl_errors_do_not_fall_back(self):
        for code in (2, 3, 23, 26, 27, 47, 48, 58, 60, 63, 77, -15):
            with self.subTest(code=code):
                diagnostic = self.run_transport([(code, b"partial", "local or security error")],
                    success=False)
                self.assertNotIn("trying ServerPlan", diagnostic)
                self.assertEqual(self.status()["state"], "not-installed")

    def test_staging_and_partial_cleanup_errors_do_not_fall_back(self):
        self.run_transport([(0, PermissionError("staging denied"), "")], success=False)
        module = load_manager()
        archive = self.root / "partial.tar.gz"
        archive.write_bytes(b"partial")
        result = subprocess.CompletedProcess([], 22, stdout="", stderr="HTTP 404")
        with mock.patch.object(module, "run", return_value=result) as runner, \
                mock.patch.object(module.Path, "unlink", side_effect=PermissionError("cleanup denied")):
            with self.assertRaises(PermissionError):
                module.download_archive(archive, "https://example.invalid/download")
        self.assertEqual(runner.call_count, 1)

    def test_canonical_metadata_remains_valid_without_fallback_field(self):
        module = load_manager()
        canonical = REPOSITORY / "install/vanhyprarch-zig-player.conf"
        with mock.patch.dict(os.environ, {}, clear=True):
            values = module.parse_metadata(canonical)
        self.assertEqual(values["VANHYPRARCH_ZIG_PLAYER_SHA256"],
            "9bd759283aa823aba124c94d64b9696df670551a1d6418ca1a32194ea0b1a887")
        self.assertEqual(values["VANHYPRARCH_ZIG_PLAYER_BINARY_SHA256"],
            "e5669983b2c9af6f121096c77796116df52b85bdf014c3bb30ced18a7353e9cf")
        self.run_manager("install")
        before = self.installed_snapshot()
        self.run_transport([(0, self.archive.read_bytes(), "")], operation="reinstall")
        self.assertEqual(self.installed_snapshot(), before)
        self.assertEqual(self.status()["state"], "installed")

    def test_install_damage_repair_and_uninstall(self):
        self.assertEqual(self.status()["state"], "not-installed")
        self.run_manager("install")
        installed = self.status()
        self.assertEqual(installed["state"], "installed")
        marker = self.data / "vanhyprarch/components/zig-screensaver"
        self.assertEqual(marker.read_bytes(), b"vanhyprarch-zig-screensaver-v1\n")
        self.assertEqual(marker.stat().st_mode & 0o777, 0o644)
        self.assertFalse((self.runtime / "vanhyprarch/zig-screensaver-install.receipt").exists())
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        binary.write_bytes(binary.read_bytes() + b"damage")
        self.assertEqual(self.status()["state"], "incomplete")
        self.run_manager("repair")
        self.assertEqual(self.status()["state"], "installed")
        plan = json.loads(self.run_manager("uninstall-plan", "--json").stdout)
        self.assertEqual(plan["resulting_lock"], "display")
        self.run_manager("uninstall", "--plan-token", plan["plan_token"])
        self.assertEqual(self.status()["state"], "not-installed")
        self.assertFalse(binary.exists())
        self.run_manager("uninstall", "--plan-token", plan["plan_token"])
        self.assertIn("idle:remove-screensaver", self.log.read_text(encoding="utf-8"))

    def test_adopt_does_not_replace_valid_payload(self):
        self.run_manager("install")
        marker = self.data / "vanhyprarch/components/zig-screensaver"
        marker.unlink()
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        inode = binary.stat().st_ino
        release = self.data / "doc/vanhyprarch-zig-player/vanhyprarch-zig-player.conf"
        release.write_text("legacy reviewed release record\n", encoding="utf-8")
        self.run_manager("adopt")
        self.assertEqual(binary.stat().st_ino, inode)
        self.assertEqual(release.read_bytes(), self.metadata.read_bytes())
        self.assertEqual(self.status()["state"], "installed")

    def test_invalid_inputs_never_publish_marker(self):
        marker = self.data / "vanhyprarch/components/zig-screensaver"
        self.write_metadata("0" * 64)
        self.run_manager("install", success=False)
        self.assertFalse(marker.exists())
        (self.source / "README.md").write_text("corrupt member\n", encoding="utf-8")
        self.write_archive()
        self.write_metadata()
        metadata_text = self.metadata.read_text(encoding="utf-8")
        current_readme_hash = digest(self.source / "README.md")
        self.metadata.write_text(metadata_text.replace(current_readme_hash,
            self.original_readme_hash), encoding="utf-8")
        self.run_manager("install", success=False)
        self.assertFalse(marker.exists())
        wrong_architecture = bytearray((self.source / "vanhyprarch-zig-player").read_bytes())
        wrong_architecture[18:20] = (183).to_bytes(2, "little")
        (self.source / "vanhyprarch-zig-player").write_bytes(wrong_architecture)
        (self.source / "vanhyprarch-zig-player").chmod(0o755)
        self.write_archive()
        self.write_metadata()
        self.run_manager("install", success=False)
        self.assertFalse(marker.exists())
        self.write_metadata()
        self.environment["VANHYPRARCH_TARGET_ARCHITECTURE"] = "aarch64"
        self.run_manager("install", success=False)
        self.assertFalse(marker.exists())
        self.environment["VANHYPRARCH_TARGET_ARCHITECTURE"] = "x86_64"
        self.write_archive(extra=True)
        self.write_metadata()
        self.run_manager("install", success=False)
        self.assertFalse(marker.exists())

    def test_failed_reinstall_and_uninstall_keep_valid_component(self):
        self.run_manager("install")
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        original_bytes = binary.read_bytes()
        archive_bytes = self.archive.read_bytes()
        self.archive.write_bytes(b"not an archive\n")
        self.run_manager("reinstall", success=False)
        self.archive.write_bytes(archive_bytes)
        self.assertEqual(binary.read_bytes(), original_bytes)
        self.assertEqual(self.status()["state"], "installed")
        (self.root / "fail-absent").write_text("now\n", encoding="utf-8")
        self.run_manager("reinstall", success=False)
        self.assertEqual(binary.read_bytes(), original_bytes)
        self.assertEqual(self.status()["state"], "installed")
        for publication_boundary in range(1, 6):
            self.environment["VANHYPRARCH_TEST_FAIL_AFTER_PUBLISH"] = \
                str(publication_boundary)
            self.run_manager("reinstall", success=False)
            self.assertEqual(binary.read_bytes(), original_bytes)
            self.assertEqual(self.status()["state"], "installed")
        self.environment.pop("VANHYPRARCH_TEST_FAIL_AFTER_PUBLISH")
        (self.root / "fail-installed").touch()
        self.run_manager("reinstall", success=False)
        self.assertEqual(self.status()["state"], "installed")
        (self.root / "fail-remove").touch()
        plan = json.loads(self.run_manager("uninstall-plan", "--json").stdout)
        self.run_manager("uninstall", "--plan-token", plan["plan_token"], success=False)
        self.assertEqual(self.status()["state"], "installed")

    def test_invalid_marker_payload_combinations_are_not_installed(self):
        marker = self.data / "vanhyprarch/components/zig-screensaver"
        marker.parent.mkdir(parents=True)
        marker.write_bytes(b"vanhyprarch-zig-screensaver-v1\n")
        marker.chmod(0o644)
        self.assertEqual(self.status()["state"], "incomplete")
        marker.write_bytes(b"wrong\n")
        self.assertEqual(self.status()["capability"], "incomplete")
        marker.write_bytes(b"vanhyprarch-zig-screensaver-v1\n")
        marker.chmod(0o600)
        self.assertEqual(self.status()["marker"], "invalid")

    def test_xdg_data_home_empty_falls_back_and_relative_is_rejected(self):
        self.environment["XDG_DATA_HOME"] = ""
        fallback_status = self.status()
        self.assertEqual(fallback_status["state"], "not-installed")
        self.environment["XDG_DATA_HOME"] = "relative-data"
        result = self.run_manager("component-status", "--json", success=False)
        self.assertIn("XDG_DATA_HOME must be absolute", result.stderr)

    def test_unsafe_objects_are_error_and_not_cleanable(self):
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        binary.parent.mkdir(parents=True)
        binary.symlink_to("/usr/bin/true")
        status = self.status()
        self.assertEqual(status["state"], "error")
        self.assertFalse(status["cleanup_safe"])
        self.run_manager("clean-up", success=False)
        self.run_manager("repair", success=False)
        self.assertTrue(binary.is_symlink())

    def test_component_operation_lock_rejects_symlink(self):
        runtime_root = self.runtime / "vanhyprarch"
        runtime_root.mkdir(mode=0o700)
        operation_lock = runtime_root / "zig-screensaver-component.lock"
        operation_lock.symlink_to(self.root / "unrelated-lock-target")
        self.run_manager("install", success=False)
        self.assertTrue(operation_lock.is_symlink())
        self.assertFalse((self.root / "unrelated-lock-target").exists())

    def test_wrong_owner_material_is_not_cleanable(self):
        self.run_manager("install")
        module = types.ModuleType("zig_manager_under_test")
        module.__file__ = str(MANAGER)
        exec(compile(MANAGER.read_text(encoding="utf-8"), str(MANAGER), "exec"),
            module.__dict__)
        with mock.patch.dict(os.environ, self.environment, clear=True):
            path_map = module.paths()
            real_lstat = module.lstat_optional

            def wrong_binary_owner(path):
                info = real_lstat(path)
                if path == path_map["binary"] and info is not None:
                    fields = list(info)
                    fields[4] = os.getuid() + 1
                    return os.stat_result(fields)
                return info

            with mock.patch.object(module, "lstat_optional", side_effect=wrong_binary_owner):
                self.assertFalse(module.cleanup_is_safe(path_map, self.metadata))

    def test_arbitrary_regular_material_is_not_cleanable(self):
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        binary.parent.mkdir(parents=True)
        shutil.copy2("/usr/bin/false", binary)
        binary.chmod(0o755)
        status = self.status()
        self.assertIn(status["state"], ("incomplete", "error"))
        self.assertFalse(status["cleanup_safe"])
        self.run_manager("clean-up", success=False)
        self.assertTrue(binary.exists())

        binary.unlink()
        license_dir = self.data / "licenses/vanhyprarch-zig-player"
        doc_dir = self.data / "doc/vanhyprarch-zig-player"
        license_dir.mkdir(parents=True)
        doc_dir.mkdir(parents=True)
        for path in (license_dir / "LICENSE", license_dir / "THIRD_PARTY_NOTICES.md",
                doc_dir / "README.md", doc_dir / "vanhyprarch-zig-player.conf"):
            path.write_text("unrelated user material\n", encoding="utf-8")
            path.chmod(0o644)
        self.assertFalse(self.status()["cleanup_safe"])
        self.run_manager("clean-up", success=False)
        self.assertEqual((doc_dir / "README.md").read_text(), "unrelated user material\n")

    def test_runtime_receipt_proves_only_canonical_interrupted_payload(self):
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        binary.parent.mkdir(parents=True)
        shutil.copy2(self.source / "vanhyprarch-zig-player", binary)
        binary.chmod(0o755)
        receipt = self.runtime / "vanhyprarch/zig-screensaver-install.receipt"
        receipt.parent.mkdir(mode=0o700)
        receipt.write_bytes(b"vanhyprarch-zig-screensaver-install-v1\n")
        receipt.chmod(0o600)
        self.assertTrue(self.status()["cleanup_safe"])
        self.run_manager("clean-up")
        self.assertFalse(binary.exists())
        self.assertFalse(receipt.exists())

    def test_extra_entry_rejects_installed_and_uninstall_preflight(self):
        self.run_manager("install")
        marker = self.data / "vanhyprarch/components/zig-screensaver"
        extra = self.data / "doc/vanhyprarch-zig-player/unrelated.txt"
        extra.write_text("keep me\n", encoding="utf-8")
        status = self.status()
        self.assertEqual(status["state"], "incomplete")
        self.assertFalse(status["cleanup_safe"])
        before_log = self.log.read_text(encoding="utf-8")
        self.run_manager("uninstall-plan", "--json", success=False)
        after_log = self.log.read_text(encoding="utf-8")
        self.assertEqual(after_log.count("controller:stop"), before_log.count("controller:stop"))
        self.assertEqual(after_log.count("idle:remove-screensaver"),
            before_log.count("idle:remove-screensaver"))
        self.assertTrue(marker.exists())
        self.assertEqual(extra.read_text(), "keep me\n")

    def test_stale_uninstall_plan_refuses_before_mutation(self):
        self.run_manager("install")
        plan = json.loads(self.run_manager("uninstall-plan", "--json").stdout)
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        os.utime(binary, ns=(binary.stat().st_atime_ns, binary.stat().st_mtime_ns + 1))
        self.preference_hash.write_text("b" * 64 + "\n", encoding="utf-8")
        before_log = self.log.read_text(encoding="utf-8")
        self.run_manager("uninstall", "--plan-token", plan["plan_token"], success=False)
        after_log = self.log.read_text(encoding="utf-8")
        self.assertEqual(after_log.count("controller:stop"), before_log.count("controller:stop"))
        self.assertEqual(after_log.count("idle:remove-screensaver"),
            before_log.count("idle:remove-screensaver"))
        self.assertEqual(self.status()["state"], "installed")

    def test_wrong_mode_and_missing_runtime_library_fail_closed(self):
        self.run_manager("install")
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        binary.chmod(0o700)
        self.assertEqual(self.status()["state"], "incomplete")

        self.tearDown()
        self.setUp()
        self.environment["VANHYPRARCH_TEST_MISSING_LIBRARY"] = "1"
        self.run_manager("install", success=False)
        self.environment.pop("VANHYPRARCH_TEST_MISSING_LIBRARY")
        self.assertEqual(self.status()["state"], "not-installed")

    def test_custom_xdg_legacy_adoption_copies_without_replacing_player(self):
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        binary.parent.mkdir(parents=True)
        shutil.copy2(self.source / "vanhyprarch-zig-player", binary)
        binary.chmod(0o755)
        inode = binary.stat().st_ino
        legacy_license = self.home / ".local/share/licenses/vanhyprarch-zig-player"
        legacy_doc = self.home / ".local/share/doc/vanhyprarch-zig-player"
        legacy_license.mkdir(parents=True)
        legacy_doc.mkdir(parents=True)
        shutil.copy2(self.source / "LICENSE", legacy_license / "LICENSE")
        shutil.copy2(self.source / "THIRD_PARTY_NOTICES.md",
            legacy_license / "THIRD_PARTY_NOTICES.md")
        shutil.copy2(self.source / "README.md", legacy_doc / "README.md")
        shutil.copy2(self.metadata, legacy_doc / "vanhyprarch-zig-player.conf")
        self.run_manager("adopt")
        self.assertEqual(binary.stat().st_ino, inode)
        self.assertEqual(self.status()["state"], "installed")
        self.assertTrue((self.data / "licenses/vanhyprarch-zig-player/LICENSE").is_file())
        self.assertTrue((legacy_license / "LICENSE").is_file())

    def test_custom_xdg_legacy_adoption_refuses_ambiguity_and_conflicts(self):
        binary = self.home / ".local/bin/vanhyprarch-zig-player"
        binary.parent.mkdir(parents=True)
        shutil.copy2(self.source / "vanhyprarch-zig-player", binary)
        binary.chmod(0o755)
        legacy_license = self.home / ".local/share/licenses/vanhyprarch-zig-player"
        legacy_doc = self.home / ".local/share/doc/vanhyprarch-zig-player"
        legacy_license.mkdir(parents=True)
        legacy_doc.mkdir(parents=True)
        shutil.copy2(self.source / "LICENSE", legacy_license / "LICENSE")
        shutil.copy2(self.source / "THIRD_PARTY_NOTICES.md",
            legacy_license / "THIRD_PARTY_NOTICES.md")
        shutil.copy2(self.source / "README.md", legacy_doc / "README.md")
        shutil.copy2(self.metadata, legacy_doc / "vanhyprarch-zig-player.conf")
        ambiguous = legacy_doc / "unrelated.txt"
        ambiguous.write_text("unrelated\n", encoding="utf-8")
        self.run_manager("adopt", success=False)
        self.assertFalse((self.data / "vanhyprarch/components/zig-screensaver").exists())
        self.assertTrue(ambiguous.exists())

        ambiguous.unlink()
        conflict = self.data / "doc/vanhyprarch-zig-player/README.md"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("conflicting user data\n", encoding="utf-8")
        self.run_manager("adopt", success=False)
        self.assertEqual(conflict.read_text(encoding="utf-8"), "conflicting user data\n")
        self.assertFalse((self.data / "vanhyprarch/components/zig-screensaver").exists())

    def test_absent_rollback_failure_is_reported_without_marker(self):
        (self.root / "fail-installed").touch()
        (self.root / "fail-absent").write_text("defer\n", encoding="utf-8")
        self.run_manager("install", success=False)
        marker = self.data / "vanhyprarch/components/zig-screensaver"
        self.assertFalse(marker.exists())
        status = self.status()
        self.assertEqual(status["state"], "incomplete")
        self.assertTrue(status["cleanup_safe"])
        self.run_manager("clean-up")
        self.assertEqual(self.status()["state"], "not-installed")


if __name__ == "__main__":
    unittest.main()
