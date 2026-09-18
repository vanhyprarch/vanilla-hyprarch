#!/usr/bin/python

import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import types
import unittest
from unittest import mock
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
MANAGER = REPOSITORY / "install/zig-screensaver/manager.py"


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
