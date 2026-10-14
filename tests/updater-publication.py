#!/usr/bin/env python3
"""Real signed zipapps, private fixture roots, SIGKILL, and exact pair recovery."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import unittest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("publication_fixtures", PROJECT / "tests/signed-updater.py")
F = importlib.util.module_from_spec(spec)
spec.loader.exec_module(F)
from install.update_bootstrap_integration import BootstrapIntegration, FILES, STATE, TARGET

# This subprocess imports the actual installed zipapp in an isolated interpreter.
# Authorities other than updater publication only write harmless fixture markers.
# No live CLI, package manager, network, user session, or installed system is used.
WORKER = r'''
import importlib.resources
import json
import os
from pathlib import Path
import signal
import subprocess
import sys

executable, fixture, verifier, at, operation, fault, metadata, artifact = sys.argv[1:]
root = Path(fixture)
assert root != Path("/") and root.parent.name.startswith("tmp")
sys.path.insert(0, executable)
from install import update_bootstrap as B
from install import signed_distribution as S
from install import update_bootstrap_integration as I
from install.release_update import ReleaseUpdate, TargetUser, UpdateError
from release import distribution as D
assert B.__file__.startswith(executable + "/")
assert I.__file__.startswith(executable + "/")

original = I.BootstrapIntegration._publish
def publish(self, path, data, mode):
    pending = path == self.state and "publication" in json.loads(data)
    final = path == self.state and not pending
    if (fault == "before-intent" and pending
            or fault == "before-executable" and path == self.target
            or fault == "before-final-provenance" and final):
        os.kill(os.getpid(), signal.SIGKILL)
    original(self, path, data, mode)
    if (fault == "after-executable" and path == self.target
            or fault == "after-provenance" and final):
        os.kill(os.getpid(), signal.SIGKILL)
I.BootstrapIntegration._publish = publish

class Authorities:
    def invoke(self, stage, action, bundle, user):
        if stage == "system-integration":
            api = I.BootstrapIntegration(bundle.tree, root, uid=os.getuid(), gid=os.getgid())
            try:
                if action == "plan": return api.plan(lifecycle="upgrade")
                if action == "apply" and fault == "child-authority":
                    # Match the real driver's sibling-import namespace, clean
                    # environment and parent-held lock, without running packages.
                    code = ('import os,sys; from pathlib import Path; '
                            'sys.path.insert(0,sys.argv[1]+"/install"); '
                            'import update_bootstrap_integration as I; '
                            'assert not I.__package__; '
                            'a=I.BootstrapIntegration(Path(sys.argv[1]),Path(sys.argv[2]),'
                            'uid=os.getuid(),gid=os.getgid()); '
                            'a.apply(lifecycle="upgrade"); a.validate()')
                    result = subprocess.run([sys.executable, "-I", "-B", "-c", code,
                        str(bundle.tree), str(root)], cwd="/", env={"PATH":"/usr/bin:/bin"},
                        capture_output=True, text=True)
                    if result.returncode: raise ValueError(result.stderr)
                elif action == "apply": api.apply(lifecycle="upgrade")
                else: api.validate()
            except ValueError as error:
                raise UpdateError("authority failed", str(error)) from error
            return "fixture updater authority complete"
        if action == "plan": return "fixture plan"
        marker = root / (stage + ".done")
        if action == "apply": marker.write_text(bundle.metadata["artifact"]["sha256"])
        if not marker.exists() or marker.read_text() != bundle.metadata["artifact"]["sha256"]:
            raise UpdateError("authority failed", "fixture stage incomplete")
        return "fixture stage complete"

user = TargetUser("fixture", os.getuid(), os.getgid(), Path("/srv/fixture"), (os.getgid(),))
driver = ReleaseUpdate(user, root=root, uid=os.getuid(), gid=os.getgid(), testing=True, authority=Authorities())
class Offline:
    def fetch(self, *args): raise AssertionError("recovery must not perform network discovery")
updater = B.Bootstrap(user, root=root, uid=os.getuid(), gid=os.getgid(), transport=Offline())
updater.security = S.SecurityStore(updater.journal, minisign=D.Minisign(Path(verifier)), now=lambda: int(at))
def resume(bundle, action):
    assert action == "resume"
    (root / "run/driver-invoked").write_text("authenticated resume")
    driver.resume()
    return "complete"
updater._driver = resume
try:
    if operation == "apply": driver.apply(Path(metadata), Path(artifact))
    elif operation == "resume": updater.run_update()
    elif operation == "check":
        before = updater.security.api.state.read_bytes()
        with updater.journal.lock.acquire():
            updater.security.start()
            updater.security.start()
        assert updater.security.api.state.read_bytes() == before
        assert not updater.resume_if_needed()
    else: raise AssertionError("unknown fixture operation")
except Exception as error:
    print(type(error).__name__ + ": " + str(error), file=sys.stderr)
    raise SystemExit(2)
'''


class PublicationTests(F.SignedUpdaterFixture):
    def setUp(self):
        super().setUp()
        source = self.root / "old-updater-source"
        for name in FILES:
            destination = source / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / name, destination)
        (source / "release/trust.json").write_bytes(self.anchor)
        path = source / "install/update_bootstrap.py"
        path.write_bytes(path.read_bytes() + b"\n# Earlier TEST-ONLY updater generation.\n")
        self.old_api = BootstrapIntegration(source, self.root, uid=os.getuid(), gid=os.getgid())
        self.old_api.apply(lifecycle="upgrade")
        self.old_payload = self.old_api.target.read_bytes()
        self.acquire()
        self.original = self.old_api._record()
        self.worker = Path(self.temporary.name) / "publication-worker.py"
        self.worker.write_text(WORKER)
        self.canary = self.root / "user-owned-preferences"
        self.canary.write_bytes(b"unchanged fixture preferences\n")

    def worker_run(self, operation, fault="", *, success=True):
        result = subprocess.run([sys.executable, "-I", "-B", str(self.worker),
            str(self.root / TARGET), str(self.root), str(self.minisign.executable),
            str(self.clock), operation, fault, str(self.metadata_path), str(self.artifact_path)],
            capture_output=True, text=True, timeout=20)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def interrupted(self, point="after-executable"):
        result = self.worker_run("apply", point, success=False)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stdout + result.stderr)
        self.assertIsNotNone(self.updater.journal.inspect())
        self.assertEqual(self.identity_path.read_bytes(), F.D.canonical(self.source))
        return self.old_api._record()

    def assert_recovered(self):
        ledger = self.security.path.read_bytes()
        self.worker_run("resume")
        self.assertIsNone(self.updater.journal.inspect())
        self.assertEqual(self.identity_path.read_bytes(), self.metadata_path.read_bytes())
        self.assertEqual(self.security.path.read_bytes(), ledger)
        self.assertNotIn("publication", self.old_api._record())
        self.assertEqual(self.old_api._record()["sha256"], self.old_api._installed())
        self.assertTrue(self.old_api._record()["distribution_initialized"])
        self.assertEqual(self.canary.read_bytes(), b"unchanged fixture preferences\n")
        self.worker_run("check")

    def assert_blocked(self):
        before = {path: path.read_bytes() if path.exists() else None
                  for path in (self.root / TARGET, self.root / STATE, self.identity_path, self.security.path)}
        result = self.worker_run("resume", success=False)
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.root / "run/driver-invoked").exists())
        self.assertEqual(before, {path: path.read_bytes() if path.exists() else None for path in before})
        return result

    def test_original_failure_real_zipapp_after_executable_before_provenance(self):
        pending = self.interrupted()
        self.assertEqual({key: value for key, value in pending.items() if key != "publication"}, self.original)
        self.assertEqual(self.old_api._installed(), pending["publication"]["replacement_sha256"])
        self.assertNotEqual(self.old_api._installed(), pending["sha256"])
        self.assert_recovered()

    def test_interruption_before_either_component_or_intent(self):
        self.interrupted("before-intent")
        self.assertEqual(self.old_api._record(), self.original)
        self.assertEqual((self.root / TARGET).read_bytes(), self.old_payload)
        self.assert_recovered()

    def test_interruption_after_intent_before_either_component(self):
        self.interrupted("before-executable")
        self.assertEqual((self.root / TARGET).read_bytes(), self.old_payload)
        self.assert_recovered()

    def test_interruption_after_final_provenance(self):
        self.interrupted("after-provenance")
        self.assertNotIn("publication", self.old_api._record())
        self.assertEqual(self.old_api._installed(), self.old_api._record()["sha256"])
        self.assert_recovered()

    def test_normal_completed_publication_and_idempotence(self):
        self.worker_run("apply")
        self.assertEqual(self.identity_path.read_bytes(), self.metadata_path.read_bytes())
        self.assertNotIn("publication", self.old_api._record())
        self.worker_run("check")
        self.worker_run("check")

    def test_direct_script_authority_child_uses_parent_release_lock(self):
        self.worker_run("apply", "child-authority")
        self.assertEqual(self.identity_path.read_bytes(), self.metadata_path.read_bytes())
        self.worker_run("check")

    def test_repeat_recovery_after_second_process_death(self):
        self.interrupted()
        pending = (self.root / STATE).read_bytes()
        for _ in range(2):
            result = self.worker_run("resume", "before-final-provenance", success=False)
            self.assertEqual(result.returncode, -signal.SIGKILL, result.stdout + result.stderr)
            self.assertEqual((self.root / STATE).read_bytes(), pending)
            self.assertFalse((self.root / "run/driver-invoked").exists())
        self.assert_recovered()

    def test_recovery_death_after_final_provenance(self):
        self.interrupted()
        result = self.worker_run("resume", "after-provenance", success=False)
        self.assertEqual(result.returncode, -signal.SIGKILL, result.stdout + result.stderr)
        self.assert_recovered()

    def test_signed_recovery_after_catalog_and_root_expiry(self):
        self.interrupted()
        self.clock = F.D.timestamp(F.foundation.ROOT_EXPIRES) + 1
        self.assert_recovered()

    def test_missing_journal_blocks(self):
        self.interrupted()
        self.updater.journal.path.unlink()
        self.assert_blocked()

    def test_corrupt_journal_blocks(self):
        self.interrupted()
        self.updater.journal.path.write_bytes(b'{"schema":1,"schema":1}\n')
        self.assert_blocked()

    def test_substituted_journal_or_target_identity_blocks(self):
        self.interrupted()
        original = self.updater.journal.path.read_bytes()
        for field, value in (("commit", "0" * 40), ("version", "v1.0.0-rc3"),
                             ("artifact_sha256", "0" * 64)):
            with self.subTest(field=field):
                journal = json.loads(original)
                journal["target"][field] = value
                self.updater.journal.path.write_bytes(F.D.canonical(journal))
                self.assert_blocked()

    def test_wrong_target_user_blocks(self):
        self.interrupted()
        value = json.loads(self.updater.journal.path.read_bytes())
        value["target_user"] = "other"
        self.updater.journal.path.write_bytes(F.D.canonical(value))
        self.assert_blocked()

    def test_altered_executable_blocks(self):
        self.interrupted()
        path = self.root / TARGET
        path.write_bytes(path.read_bytes() + b"\n# corrupt fixture suffix\n")
        self.assert_blocked()

    def test_forged_original_provenance_blocks(self):
        pending = self.interrupted()
        pending["sha256"] = "0" * 64
        (self.root / STATE).write_bytes(F.D.canonical(pending))
        self.assert_blocked()

    def test_stale_or_unexplained_provenance_blocks(self):
        self.interrupted()
        (self.root / STATE).write_bytes(F.D.canonical(self.original))
        self.assert_blocked()

    def test_missing_provenance_blocks(self):
        self.interrupted()
        (self.root / STATE).unlink()
        self.assert_blocked()

    def test_changed_replacement_hash_blocks(self):
        pending = self.interrupted("before-executable")
        pending["publication"]["replacement_sha256"] = "0" * 64
        (self.root / STATE).write_bytes(F.D.canonical(pending))
        self.assert_blocked()

    def test_missing_or_modified_staged_artifacts_block(self):
        self.interrupted()
        retained = self.updater.store.resume(self.target["artifact"]["sha256"])
        for path in (retained.metadata_path, retained.artifact_path,
                     retained.tree / "install/update_bootstrap.py"):
            original = path.read_bytes()
            with self.subTest(path=path.name, mode="missing"):
                path.unlink()
                self.assert_blocked()
            path.write_bytes(original)
            path.chmod(0o644)
            with self.subTest(path=path.name, mode="modified"):
                path.write_bytes(original + b"\n")
                self.assert_blocked()
            path.write_bytes(original)

    def test_invalid_or_substituted_signed_authorization_blocks(self):
        self.interrupted()
        original = self.security.path.read_bytes()
        for field in ("catalog", "manifest", "signature", "metadata"):
            with self.subTest(field=field):
                ledger = json.loads(original)
                data = bytearray(F.S.decoded(ledger["authorization"][field], F.S.MAX_LEDGER))
                data[len(data) // 2] ^= 1
                ledger["authorization"][field] = F.S.encode(bytes(data))
                self.security.path.write_bytes(F.D.canonical(ledger))
                self.assert_blocked()

    def test_missing_authorization_blocks(self):
        self.interrupted()
        ledger = self.security._read()
        ledger["authorization"] = None
        self.security.path.write_bytes(F.D.canonical(ledger))
        self.assert_blocked()

    def test_valid_signed_authorization_for_another_target_blocks(self):
        self.interrupted()
        other = F.foundation.SignedDistributionTests
        entry = F.D.catalog_entry(other.manifest, other.signature)
        payload = F.D.make_catalog("candidate", 1, [entry], root_version=1,
                                  issued_at=F.foundation.ISSUED)
        ledger = self.security._read()
        ledger["authorization"].update(catalog=F.S.encode(self.signed(payload)),
            manifest=F.S.encode(other.manifest), signature=F.S.encode(other.signature),
            metadata=F.S.encode(other.metadata))
        self.security.path.write_bytes(F.D.canonical(ledger))
        self.assert_blocked()

    def test_original_receipt_disagreement_blocks(self):
        self.interrupted()
        ledger = self.security._read()
        ledger["authorization"]["updater"]["sha256"] = "0" * 64
        self.security.path.write_bytes(F.D.canonical(ledger))
        self.assert_blocked()

    def test_changed_release_identity_blocks(self):
        self.interrupted()
        value = copy.deepcopy(self.source)
        value["commit"] = "0" * 40
        self.identity_path.write_bytes(F.D.canonical(value))
        self.assert_blocked()

    def test_corrupt_or_missing_security_state_blocks(self):
        self.interrupted()
        for data in (b"{}\n", None):
            with self.subTest(missing=data is None):
                if data is None: self.security.path.unlink()
                else: self.security.path.write_bytes(data)
                self.assert_blocked()

    def test_rollback_floors_bindings_root_or_clock_corruption_blocks(self):
        self.interrupted()
        original = self.security._read()
        for case in ("clock", "root", "binding", "equivocation", "floor"):
            with self.subTest(case=case):
                ledger = copy.deepcopy(original)
                state = ledger["state"]
                if case == "clock": state["clock_high_water"] = self.clock + 1
                elif case == "root": state["root_sha256"] = "0" * 64
                elif case == "binding": state["bindings"][self.target["version"]]["manifest"]["sha256"] = "0" * 64
                elif case == "equivocation": state["channels"]["candidate"]["sha256"] = "0" * 64
                else: state["channels"]["candidate"]["sequence"] = 0
                self.security.path.write_bytes(F.D.canonical(ledger))
                self.assert_blocked()

    def test_concurrent_updater_is_rejected_without_mutation(self):
        self.interrupted()
        with self.updater.journal.lock.acquire():
            result = self.assert_blocked()
            self.assertIn("another Vanilla update holds the lock", result.stderr)
        self.assert_recovered()

    def test_absence_of_authorized_pending_transaction_blocks_mismatch(self):
        (self.root / TARGET).write_bytes((self.root / TARGET).read_bytes() + b"\n# unexplained mismatch\n")
        self.assert_blocked()


if __name__ == "__main__":
    unittest.main()
