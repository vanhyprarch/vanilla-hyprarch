#!/usr/bin/env python3
"""Isolated one-time preparation tests. No host updater/package operations."""
import contextlib
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
spec = importlib.util.spec_from_file_location("preparation", PROJECT / "admin/prepare-updater.py")
prep = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prep)
FIXTURES = PROJECT / "tests/fixtures/updater-v1.0.0"
# Historical offline golden source, not approval for real preparation.
APPROVED = "76ba35807ae01197011017b119206316dff3796b"


def git(path, *args):
    return subprocess.check_output(["git", "-C", str(path), *args], stderr=subprocess.DEVNULL).decode().strip()


def snapshot(root):
    return {str(p.relative_to(root)): (p.lstat().st_mode, p.lstat().st_uid, p.lstat().st_gid,
            prep.digest(p.read_bytes()) if p.is_file() else None)
            for p in root.rglob("*")}


class Interrupted(Exception):
    pass


class PreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workspace = tempfile.TemporaryDirectory(prefix="vanhyprarch-preparation-test-")
        cls.base = Path(cls.workspace.name)
        cls.source = cls.base / "source"
        subprocess.run(["git", "clone", "--quiet", "--shared", "--no-checkout", str(PROJECT),
                        str(cls.source)], check=True)
        git(cls.source, "checkout", "--quiet", "--detach", APPROVED)
        git(cls.source, "remote", "set-url", "origin", "https://github.com/vanhyprarch/vanilla-hyprarch.git")
        cls.output = cls.base / "bundle"
        cls.output.mkdir()
        # All lifecycle tests are offline. Authentication is a separate operator
        # prerequisite; verify its exact Git invocation in a focused test below.
        with mock.patch.object(prep, "authenticate_source") as authenticate:
            cls.report = prep.build_bundle(cls.source, APPROVED, cls.output)
            authenticate.assert_called_once_with(cls.source, APPROVED)
        cls.metadata = cls.output / "release.json"
        cls.artifact = next(cls.output.glob("*.tar.gz"))
        cls.original = (FIXTURES / "vanhyprarch-update").read_bytes()
        cls.identity = (FIXTURES / "release.json").read_bytes()

    @classmethod
    def tearDownClass(cls):
        cls.workspace.cleanup()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=self.base)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o755)
        self.uid, self.gid = os.getuid(), os.getgid()
        for relative, data, mode in (
            (prep.TARGET, self.original, 0o755),
            (prep.STATE, prep.provenance(self.original), 0o600),
            (Path("usr/share/vanhyprarch/release.json"), self.identity, 0o644),
            (Path("home/fixture/.config/preferences"), b"user fixture unchanged", 0o600),
            (Path("home/fixture/.local/share/keyrings/login.keyring"), b"opaque fixture", 0o600),
            (Path("var/lib/vanhyprarch/system-integration-v1.json"), b"unchanged fixture", 0o600),
        ):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
        (self.root / prep.STATE).parent.chmod(0o700)
        (self.root / "root").mkdir(mode=0o700)
        (self.root / "run").mkdir(mode=0o755)
        self.operation = prep.Preparation(self.metadata, self.artifact, APPROVED,
            self.report["bundle_sha256"], root=self.root, uid=self.uid, gid=self.gid)

    def interrupt(self, path, *, after=False, restore=False):
        publish = prep.BootstrapIntegration._publish

        def interrupted(api, target, data, mode):
            if target == self.root / path and not after:
                raise Interrupted()
            publish(api, target, data, mode)
            if target == self.root / path and after:
                raise Interrupted()
        with mock.patch.object(prep.BootstrapIntegration, "_publish", interrupted):
            with self.assertRaises(Interrupted):
                self.operation.apply(authorized=True, restore=restore)

    def test_authentic_original_and_identity(self):
        self.assertEqual(prep.digest(self.original), prep.ORIGINAL_UPDATER)
        self.assertEqual(prep.digest(self.identity), prep.ORIGINAL_IDENTITY)
        self.assertEqual(self.operation.check()["status"], "replace")

    def test_check_changes_nothing(self):
        before = snapshot(self.root)
        self.operation.check()
        self.assertEqual(snapshot(self.root), before)

    def test_check_existing_lock_changes_nothing(self):
        with self.operation.journal.lock.acquire():
            pass
        before = snapshot(self.root)
        self.operation.check()
        self.assertEqual(snapshot(self.root), before)

    def test_correct_publication_and_matching_provenance(self):
        before = snapshot(self.root)
        self.assertEqual(self.operation.apply(authorized=True)["status"], "prepared")
        self.operation.api.validate()
        self.assertEqual((self.root / prep.TARGET).read_bytes(), self.operation.payload)
        self.assertEqual((self.root / prep.STATE).read_bytes(), prep.provenance(self.operation.payload))
        self.assertEqual((self.root / "usr/share/vanhyprarch/release.json").read_bytes(), self.identity)
        for name, value in before.items():
            if name not in {str(prep.TARGET), str(prep.STATE)}:
                self.assertEqual(snapshot(self.root)[name], value, name)
        self.assertEqual(self.operation.backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.operation.receipt()["source_commit"], APPROVED)
        self.assertFalse(list((self.root / "run").glob("vanhyprarch-preview-*")))

    def test_packager_format_matches_approved_source(self):
        # Compare against the unmodified packager from the approved checkout,
        # not two uses of the refactored formatter under test.
        spec = importlib.util.spec_from_file_location("approved_builder",
                     self.source / "install/update_bootstrap_integration.py")
        authority = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(authority)
        self.assertEqual(self.operation.payload, authority.BootstrapIntegration(self.source).build())
        self.assertEqual(prep.digest(self.operation.payload),
                         "4adcff509dcd55ab97373b595252c96bc13e08be1326807610624fdac91e5369")
        self.assertEqual(self.report["updater_sha256"], prep.digest(self.operation.payload))
        self.assertEqual(self.report["provenance_sha256"], prep.digest(prep.provenance(self.operation.payload)))

    def test_wrong_source_commit_rejected(self):
        with self.assertRaisesRegex(ValueError, "approved"):
            prep.payload_from_bundle(self.metadata, self.artifact, "f" * 40, self.report["bundle_sha256"])

    def test_different_explicit_commit_can_build_and_prepare(self):
        # A future-source fixture, not a ServerPlan implementation or a real
        # approved release. Its commit exists only in this disposable clone.
        source = self.root / "future-source"
        subprocess.run(["git", "clone", "--quiet", "--shared", str(self.source), str(source)],
                       check=True, capture_output=True)
        git(source, "remote", "set-url", "origin", "https://github.com/vanhyprarch/vanilla-hyprarch.git")
        path = source / "install/update_bootstrap.py"
        path.write_bytes(path.read_bytes() + b"\n# Distinct future-source regression fixture.\n")
        git(source, "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
            "commit", "-am", "Distinct source fixture")
        commit = git(source, "rev-parse", "HEAD")
        self.assertNotEqual(commit, APPROVED)
        output = self.root / "future-bundle"
        output.mkdir()
        with mock.patch.object(prep, "authenticate_source") as authenticate:
            report = prep.build_bundle(source, commit, output)
            authenticate.assert_called_once_with(source, commit)
        operation = prep.Preparation(output / "release.json", next(output.glob("*.tar.gz")),
            commit, report["bundle_sha256"], root=self.root, uid=self.uid, gid=self.gid)
        self.assertNotEqual(operation.payload, self.operation.payload)
        self.assertEqual(operation.check()["source_commit"], commit)
        self.assertEqual(operation.apply(authorized=True)["status"], "prepared")
        operation.api.validate()
        self.assertEqual(operation.receipt()["source_commit"], commit)
        self.assertEqual((self.root / "usr/share/vanhyprarch/release.json").read_bytes(), self.identity)
        self.assertEqual(operation.apply(authorized=True)["status"], "prepared")
        # An existing receipt remains bound to its exact source: selecting a
        # different target is never an implicit continuation of preparation.
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            self.operation.check()

    def test_wrong_bundle_hash_rejected(self):
        with self.assertRaisesRegex(ValueError, "approved"):
            prep.payload_from_bundle(self.metadata, self.artifact, APPROVED, "f" * 64)

    def test_dirty_source_rejected(self):
        path = self.source / "untracked-preparation-fixture"
        path.write_text("fixture")
        try:
            with self.assertRaisesRegex(ValueError, "clean"):
                prep.build_bundle(self.source, APPROVED, self.output)
        finally:
            path.unlink()

    def test_current_working_tree_rejected(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            prep.build_bundle(PROJECT, APPROVED, self.output)

    def test_cancellation_without_authorization(self):
        before = snapshot(self.root)
        with self.assertRaisesRegex(ValueError, "authorize"):
            self.operation.apply()
        self.assertEqual(snapshot(self.root), before)

    def test_repeated_preparation(self):
        self.operation.apply(authorized=True)
        before = snapshot(self.root)
        self.operation.apply(authorized=True)
        self.assertEqual(snapshot(self.root), before)

    def test_interrupt_before_publication_then_resume(self):
        self.interrupt(prep.TARGET)
        self.assertEqual(self.operation.check()["status"], "replace")
        self.assertEqual(self.operation.apply(authorized=True)["status"], "prepared")

    def test_interrupt_between_publications_then_resume(self):
        self.interrupt(prep.TARGET, after=True)
        self.assertEqual(self.operation.check()["status"], "resume")
        self.assertEqual(self.operation.apply(authorized=True)["status"], "prepared")

    def test_interrupt_after_publication_then_resume(self):
        self.interrupt(prep.STATE, after=True)
        self.assertEqual(self.operation.check()["status"], "prepared")
        self.operation.apply(authorized=True)

    def test_restore_verified_original_pair(self):
        self.operation.apply(authorized=True)
        self.operation.apply(authorized=True, restore=True)
        self.assertEqual((self.root / prep.TARGET).read_bytes(), self.original)
        self.assertEqual((self.root / prep.STATE).read_bytes(), prep.provenance(self.original))
        self.assertEqual((self.root / "usr/share/vanhyprarch/release.json").read_bytes(), self.identity)

    def test_restore_partial_forward_pair(self):
        self.interrupt(prep.TARGET, after=True)
        self.operation.apply(authorized=True, restore=True)
        self.assertEqual((self.root / prep.TARGET).read_bytes(), self.original)

    def test_interrupt_restoration_then_resume(self):
        self.operation.apply(authorized=True)
        self.interrupt(prep.TARGET, after=True, restore=True)
        self.assertEqual(self.operation.check()["status"], "restore-resume")
        self.operation.apply(authorized=True, restore=True)
        self.assertEqual((self.root / prep.TARGET).read_bytes(), self.original)

    def test_bad_installed_provenance(self):
        (self.root / prep.STATE).write_text('{"schema":2,"sha256":"' + "f" * 64 + '","update_protocol":1}\n')
        with self.assertRaisesRegex(ValueError, "pair"):
            self.operation.check()

    def test_missing_installed_provenance(self):
        (self.root / prep.STATE).unlink()
        with self.assertRaises(ValueError):
            self.operation.check()

    def test_corrupt_backup_blocks_all_recovery(self):
        self.operation.apply(authorized=True)
        (self.operation.backup / "original-updater").write_bytes(b"corrupt fixture")
        for restore in (False, True):
            with self.assertRaisesRegex(ValueError, "checksum"):
                self.operation.apply(authorized=True, restore=restore)

    def test_unexplained_pair_without_receipt(self):
        (self.root / prep.TARGET).write_bytes(self.operation.payload)
        with self.assertRaisesRegex(ValueError, "pair"):
            self.operation.check()

    def test_unexpected_reverse_pair(self):
        self.operation.apply(authorized=True)
        (self.root / prep.TARGET).write_bytes(self.original)
        with self.assertRaisesRegex(ValueError, "pair"):
            self.operation.check()

    def test_release_journal_blocks_preparation_and_restore(self):
        self.operation.apply(authorized=True)
        for restore in (False, True):
            with mock.patch.object(self.operation.journal, "inspect", return_value={"phase": "applying"}):
                with self.assertRaisesRegex(ValueError, "release journal"):
                    self.operation.apply(authorized=True, restore=restore)

    def test_corrupt_real_journal_rejected(self):
        path = self.operation.journal.path
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text("corrupt fixture")
        path.chmod(0o600)
        with self.assertRaises((ValueError, RuntimeError)):
            self.operation.check()

    def test_staging_blocks_preparation(self):
        path = self.root / prep.STAGE_RELATIVE
        path.mkdir(parents=True)
        (path / "incomplete-fixture").mkdir()
        with self.assertRaisesRegex(ValueError, "staging"):
            self.operation.check()

    def test_incomplete_system_transaction_rejected(self):
        path = self.root / prep.GUARDS[0]
        path.write_text("fixture")
        with self.assertRaisesRegex(ValueError, "transaction"):
            self.operation.check()

    def test_another_operation_holds_lock(self):
        with self.operation.journal.lock.acquire():
            second = prep.UpdateJournal(self.root, uid=self.uid, gid=self.gid)
            self.operation.journal = second
            with self.assertRaisesRegex((ValueError, RuntimeError), "lock"):
                self.operation.check()

    def test_identity_changes_make_restore_unsafe(self):
        self.operation.apply(authorized=True)
        value = json.loads(self.identity)
        value["summary"] = "changed release fixture"
        (self.root / "usr/share/vanhyprarch/release.json").write_bytes(prep.contract.metadata_bytes(value))
        with self.assertRaisesRegex(ValueError, "authentic"):
            self.operation.apply(authorized=True, restore=True)

    def test_symlink_and_untrusted_backup_rejected(self):
        self.operation.backup.symlink_to(self.root / "home/fixture", target_is_directory=True)
        with self.assertRaises(ValueError):
            self.operation.check()

    def test_incomplete_backup_does_not_publish(self):
        self.operation.backup.mkdir(mode=0o700)
        with self.assertRaisesRegex(ValueError, "incomplete"):
            self.operation.apply(authorized=True)
        self.assertEqual((self.root / prep.TARGET).read_bytes(), self.original)

    def test_standard_and_custom_config_data_context(self):
        home = Path("/srv/fixture-user")
        for env in ({}, {"XDG_CONFIG_HOME": "/srv/fixture/config", "XDG_DATA_HOME": "/srv/fixture/data"}):
            context = prep.captured_context(env, 1000, home)
            prep.validate_context(context, 1000, home)
            self.assertEqual(context["provider"]["environment"]["XDG_CONFIG_HOME"],
                             env.get("XDG_CONFIG_HOME", str(home / ".config")))

    def test_custom_state_and_cache_rejected(self):
        for key in ("XDG_STATE_HOME", "XDG_CACHE_HOME"):
            with self.assertRaisesRegex(ValueError, "default"):
                prep.captured_context({key: "/srv/fixture/custom"}, 1000, Path("/srv/fixture-user"))

    def test_root_context_not_used_as_fallback(self):
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/root/fixture"}):
            with self.assertRaises(ValueError):
                prep.validate_context({}, 1000, Path("/srv/fixture-user"))

    def test_authentication_uses_normal_git_fetch_and_commit_reachability(self):
        with mock.patch.object(prep.subprocess, "run") as run:
            prep.authenticate_source(self.source, APPROVED)
        self.assertEqual(run.call_args_list, [
            mock.call(["git", "-C", str(self.source), "fetch", "--no-tags", "origin", "main"], check=True, stdout=subprocess.DEVNULL),
            mock.call(["git", "-C", str(self.source), "merge-base", "--is-ancestor", APPROVED, "FETCH_HEAD"], check=True, stdout=subprocess.DEVNULL)])

    def test_process_guard_reads_only_interpreter_and_script_names(self):
        proc = self.root / "proc"
        entry = proc / "999999"
        entry.mkdir(parents=True)
        (entry / "exe").symlink_to("/usr/bin/python3")
        (entry / "cmdline").write_bytes(b"/usr/bin/python3\0/usr/local/bin/vanhyprarch-update\0unused-argument\0")
        self.assertTrue(prep.updater_running(proc))
        (entry / "cmdline").write_bytes(b"/usr/bin/python3\0unrelated-script.py\0/usr/local/bin/vanhyprarch-update\0")
        self.assertFalse(prep.updater_running(proc))

    def test_preview_staging_requires_review(self):
        (self.root / "run/vanhyprarch-preview-fixture").mkdir()
        with self.assertRaisesRegex(ValueError, "preview staging"):
            self.operation.check()

    def test_frontend_captures_before_sudo_without_manual_json(self):
        account = SimpleNamespace(pw_uid=1000, pw_name="fixture", pw_dir="/srv/fixture-user")
        args = ["check", "--metadata", str(self.metadata), "--artifact", str(self.artifact),
                "--approved-commit", APPROVED, "--bundle-sha256", self.report["bundle_sha256"]]
        with (mock.patch.object(prep.os, "getuid", return_value=1000),
              mock.patch.object(prep.pwd, "getpwuid", return_value=account),
              mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": "/srv/fixture/config"}, clear=True),
              mock.patch.object(prep.subprocess, "call", return_value=0) as call):
            self.assertEqual(prep.main(args), 0)
        argv = call.call_args.args[0]
        self.assertEqual(argv[:5], ["/usr/bin/sudo", "--", "/usr/bin/python3", "-I", "-B"])
        self.assertEqual(argv[-3:-1], ["fixture", "--captured-context"])
        context = json.loads(argv[-1])
        self.assertEqual(context["provider"]["environment"]["XDG_CONFIG_HOME"], "/srv/fixture/config")
        self.assertEqual(context["state"], "/srv/fixture-user/.local/state")

    def test_root_cli_requires_explicit_context_and_clean_stdout(self):
        args = ["check", "--metadata", str(self.metadata), "--artifact", str(self.artifact),
                "--approved-commit", APPROVED, "--bundle-sha256", self.report["bundle_sha256"]]
        with (mock.patch.object(prep.os, "getuid", return_value=0),
              contextlib.redirect_stdout(io.StringIO()) as out,
              contextlib.redirect_stderr(io.StringIO())):
            self.assertEqual(prep.main(args), 1)
        self.assertEqual(out.getvalue(), "")

    def test_package_source_set_validation(self):
        with self.assertRaises(ValueError):
            prep.BootstrapIntegration.package_files({})

    def test_noncanonical_changed_metadata_rejected(self):
        metadata = self.root / "release.json"
        metadata.write_text(json.dumps(json.loads(self.metadata.read_text()), indent=2))
        with self.assertRaisesRegex(ValueError, "canonical"):
            prep.payload_from_bundle(metadata, self.artifact, APPROVED, self.report["bundle_sha256"])

    def test_receipt_boolean_schema_is_not_accepted_as_integer(self):
        self.operation.apply(authorized=True)
        path = self.operation.backup / "receipt.json"
        value = json.loads(path.read_bytes())
        value["schema"] = True
        path.write_bytes(prep.encoded(value))
        with self.assertRaisesRegex(ValueError, "receipt differs"):
            self.operation.check()

    def test_authentication_failure_prevents_bundle_construction(self):
        output = self.root / "output"
        output.mkdir()
        with mock.patch.object(prep, "authenticate_source", side_effect=subprocess.CalledProcessError(1, ["git"])):
            with self.assertRaises(subprocess.CalledProcessError):
                prep.build_bundle(self.source, APPROVED, output)
        self.assertFalse(list(output.iterdir()))

    def test_development_identity_absent_rejected(self):
        (self.root / "usr/share/vanhyprarch/release.json").unlink()
        with self.assertRaises(ValueError):
            self.operation.check()

    def test_privileged_bundle_refuses_user_writable_parent(self):
        with self.assertRaises(ValueError):
            prep.protected_bundle(self.metadata, self.artifact)

    def test_root_success_uses_explicit_context_and_outputs_only_json(self):
        context = prep.captured_context({"XDG_CONFIG_HOME": "/srv/fixture/config"}, 1000, Path("/srv/fixture-user"))
        args = ["check", "--metadata", str(self.metadata), "--artifact", str(self.artifact),
                "--approved-commit", APPROVED, "--bundle-sha256", self.report["bundle_sha256"],
                "--target-user", "fixture", "--captured-context", json.dumps(context)]
        operation = mock.Mock()
        operation.check.return_value = {"status": "replace"}
        with (mock.patch.object(prep.os, "getuid", return_value=0),
              mock.patch.object(prep, "protected_source"),
              mock.patch.object(prep, "protected_bundle") as protect,
              mock.patch.object(prep.TargetUser, "resolve", return_value=SimpleNamespace(uid=1000, home=Path("/srv/fixture-user"))) as resolve,
              mock.patch.object(prep, "Preparation", return_value=operation),
              mock.patch.dict(os.environ, {"SUDO_UID": "1000", "XDG_CONFIG_HOME": "/root/incorrect"}, clear=True),
              contextlib.redirect_stdout(io.StringIO()) as out,
              contextlib.redirect_stderr(io.StringIO()) as err):
            self.assertEqual(prep.main(args), 0)
        resolve.assert_called_once_with("fixture", provider_context=context["provider"])
        protect.assert_called_once_with(self.metadata, self.artifact)
        self.assertEqual(json.loads(out.getvalue()), {"status": "replace"})
        self.assertEqual(err.getvalue(), "")
        operation.apply.assert_not_called()

    def test_abrupt_process_death_at_each_publication_boundary(self):
        code = '''import importlib.util,os,sys
from pathlib import Path
spec=importlib.util.spec_from_file_location('preparation',sys.argv[1])
p=importlib.util.module_from_spec(spec); spec.loader.exec_module(p)
root=Path(sys.argv[2]); target=root/sys.argv[7]
original=p.BootstrapIntegration._publish
def publish(api,path,data,mode):
 if path==target and sys.argv[8]=='before': os._exit(87)
 original(api,path,data,mode)
 if path==target: os._exit(87)
p.BootstrapIntegration._publish=publish
p.Preparation(Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5],sys.argv[6],root=root,uid=os.getuid(),gid=os.getgid()).apply(authorized=True)
'''
        for path, when in ((prep.TARGET, "before"), (prep.TARGET, "after"), (prep.STATE, "after")):
            with self.subTest(path=str(path), when=when):
                result = subprocess.run([sys.executable, "-I", "-B", "-c", code,
                    str(PROJECT / "admin/prepare-updater.py"), str(self.root), str(self.metadata),
                    str(self.artifact), APPROVED, self.report["bundle_sha256"], str(path), when],
                    capture_output=True, text=True)
                self.assertEqual(result.returncode, 87, result.stderr)
                self.operation.apply(authorized=True)
                self.operation.api.validate()
                self.operation.apply(authorized=True, restore=True)
                # Reset only this disposable fixture's administrative backup
                # between independent crash cases, never a live installation.
                shutil.rmtree(self.operation.backup)

    def test_prepared_frontend_forwards_custom_context_before_sudo(self):
        # Import only the verified zipapp's frontend in a disposable interpreter;
        # replace sudo and UID/account probes before invoking its main function.
        payload = self.base / "prepared-updater"
        payload.write_bytes(self.operation.payload)
        code = '''import json,sys
from unittest import mock
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
from install import update_bootstrap as b
with mock.patch.object(b.os,'getuid',return_value=1000), mock.patch.object(b.pwd,'getpwuid',return_value=SimpleNamespace(pw_name='fixture',pw_dir='/srv/fixture-user')), mock.patch.object(b.subprocess,'call',return_value=0) as call, mock.patch.dict(b.os.environ,{'XDG_CONFIG_HOME':'/srv/fixture/config','XDG_DATA_HOME':'/srv/fixture/data'},clear=True):
 b.main([])
 argv=call.call_args.args[0]
 assert argv[:5]==['/usr/bin/sudo','--','/usr/local/bin/vanhyprarch-update','--target-user','fixture']
 assert argv[5]=='--target-context-json'
 value=json.loads(argv[6])
 assert value['environment']['XDG_CONFIG_HOME']=='/srv/fixture/config'
 assert value['environment']['XDG_DATA_HOME']=='/srv/fixture/data'
 print('context forwarding verified')
'''
        result = subprocess.run([sys.executable, "-I", "-c", code, str(payload)], check=True,
                                capture_output=True, text=True, cwd=self.base)
        self.assertEqual(result.stdout, "context forwarding verified\n")


if __name__ == "__main__":
    unittest.main()
