#!/usr/bin/env python3
"""Isolated signed acquisition, transport fallback, durable state, and recovery."""
from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from install import update_bootstrap as B
from install import signed_distribution as S
from install.release_update import ReleaseUpdate, TargetUser
from install.update_bootstrap_integration import BootstrapIntegration, STATE, TARGET
from release import distribution as D


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, PROJECT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


foundation = load("signed_foundation_fixture", "tests/signed-distribution.py")
driver = load("signed_driver_fixture", "tests/release-update-driver.py")
preparation = load("signed_preparation_fixture", "admin/prepare-updater.py")


class LocalTransport:
    def __init__(self, files):
        self.files = dict(files)
        self.github = {}
        self.calls = []
        self.offline = False

    def fetch(self, url, limit, destination=None):
        self.calls.append(url)
        if self.offline:
            raise S.Unavailable("offline fixture")
        if url.startswith(S.SERVERPLAN):
            data = self.files.get(url.removeprefix(S.SERVERPLAN))
        else:
            data = self.github.get(url)
        if isinstance(data, Exception):
            raise data
        if data is None:
            raise S.Unavailable("HTTP 404 fixture")
        if len(data) > limit:
            raise B.BootstrapError("fixture download exceeds bound")
        if destination is None:
            return data
        with destination.open("xb") as stream:
            stream.write(data)
        return None


class SignedUpdaterFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = foundation.SignedDistributionTests
        cls.addClassCleanup(fixture.doClassCleanups)
        fixture.setUpClass()
        cls.keys, cls.minisign = fixture.keys, fixture.minisign
        cls.secret, cls.public = cls.keys[0]
        cls.root_record, cls.root_payload = fixture.root_envelope, fixture.root_payload
        cls.anchor = D.canonical({"schema": 1, "public_key": cls.public,
                                  "root_sha256": D.digest(cls.root_payload), "root": S.encode(cls.root_record)})
        base = fixture.base / "upgrade"
        base.mkdir()
        cls.source, cls.metadata_path, cls.artifact_path, cls.target = driver.BundleFixture.build(base)
        # Include the actual packaged updater, not placeholder source members.
        # This catches publication/restart failures across the real zipapp boundary.
        from install.update_bootstrap_integration import FILES
        repo = base / "repo"
        for name in FILES:
            path = repo / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / name, path)
        (repo / "release/trust.json").write_bytes(cls.anchor)
        driver.git(repo, "add", ".")
        driver.git(repo, "commit", "-qm", "TEST-ONLY authenticated updater fixture")
        output = base / "signed-output"
        output.mkdir()
        cls.metadata_path, cls.artifact_path = D.contract.build(repo, driver.git(repo, "rev-parse", "HEAD"), output)
        cls.target = D.contract.parse_metadata(cls.metadata_path.read_bytes())
        cls.manifest = D.make_manifest(cls.metadata_path, cls.artifact_path, root_version=1)
        cls.signature = cls.minisign.sign(cls.manifest, cls.secret, cls.public)
        cls.entry = D.catalog_entry(cls.manifest, cls.signature)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "root"
        (self.root / "run").mkdir(parents=True)
        self.root.chmod(0o755)
        self.identity_path = self.root / "usr/share/vanhyprarch/release.json"
        self.identity_path.parent.mkdir(parents=True)
        self.identity_path.write_bytes(D.canonical(self.source))
        self.identity_path.chmod(0o644)
        self.user = TargetUser("fixture", os.getuid(), os.getgid(), Path("/srv/fixture"), (os.getgid(),))
        self.clock = foundation.CLOCK.now
        executable = self.root / TARGET
        executable.parent.mkdir(parents=True)
        executable.write_bytes(b"isolated signed updater fixture")
        executable.chmod(0o755)
        self.provenance = self.root / STATE
        self.provenance.parent.mkdir(parents=True)
        self.provenance.parent.chmod(0o700)
        self.provenance.write_bytes((json.dumps({"schema": 3,
            "sha256": D.digest(executable.read_bytes()), "update_protocol": 1,
            "distribution_initialized": False, "distribution_anchor_sha256": D.digest(self.root_payload)},
            sort_keys=True) + "\n").encode())
        self.provenance.chmod(0o600)
        version = self.target["version"]
        self.transport = LocalTransport({
            f"releases/{version}/manifest.json": self.manifest,
            f"releases/{version}/manifest.json.sig": self.signature,
            f"releases/{version}/assets/release.json": self.metadata_path.read_bytes(),
            f"releases/{version}/assets/{self.artifact_path.name}": self.artifact_path.read_bytes(),
        })
        self.updater = B.Bootstrap(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                                   transport=self.transport)
        self.security = S.SecurityStore(self.updater.journal, anchor=self.anchor,
                                         minisign=self.minisign, now=lambda: self.clock)
        self.updater.security = self.security
        self.client = S.Acquisition(self.security, self.transport)
        self.calls = []
        self.updater._driver = self.fake_driver
        self.set_catalog()

    def signed(self, payload, *, other=False):
        secret, public = self.keys[int(other)]
        return D.envelope(payload, [(public, self.minisign.sign(payload, secret, public))])

    def set_catalog(self, *, entries=None, sequence=1, issued=foundation.ISSUED,
                    channel="candidate", root_version=1, other=False):
        payload = D.make_catalog(channel, sequence, [self.entry] if entries is None else entries,
                                 root_version=root_version, issued_at=issued)
        self.transport.files["channels/" + channel + ".json"] = self.signed(payload, other=other)
        return payload

    def fake_driver(self, bundle, operation):
        self.calls.append(operation)
        self.assertEqual(bundle.stage.parent, self.root / "run")
        if operation == "plan":
            return json.dumps({"source": self.source["version"], "target": self.target["version"],
                               "target_sha256": self.target["artifact"]["sha256"],
                               "migrations": [], "authorities": {}})
        self.identity_path.write_bytes(self.metadata_path.read_bytes())
        return "complete"

    def start(self):
        with self.updater.journal.lock.acquire():
            return self.security.start()

    def acquire(self):
        directory = self.root / "run" / ("download-" + str(len(list((self.root / "run").iterdir()))))
        directory.mkdir(mode=0o700)
        with self.updater.journal.lock.acquire():
            self.security.start()
            return self.client.acquire(self.source, directory)

    def run_update(self, answer="y"):
        with contextlib.redirect_stdout(io.StringIO()) as output:
            result = self.updater.run_update(answer=lambda _: answer)
        return result, output.getvalue()


class SignedUpdaterTests(SignedUpdaterFixture):
    def test_valid_serverplan_update_with_github_completely_unavailable(self):
        result, output = self.run_update()
        self.assertEqual(result, 0)
        self.assertEqual(self.calls, ["plan", "apply"])
        self.assertIn("update complete", output)
        self.assertEqual(self.identity_path.read_bytes(), self.metadata_path.read_bytes())
        self.assertTrue(self.transport.calls[0].startswith(S.GITHUB_METADATA))
        self.assertTrue(all(url.startswith(S.SERVERPLAN) for url in self.transport.calls[1:]))

    def test_real_transport_http_404_falls_back_to_authenticated_serverplan(self):
        requested = []
        files = self.transport.files
        class Response:
            status = 200
            def __init__(self, url, data):
                self.url, self.stream = url, io.BytesIO(data)
                self.headers = {"Content-Length": str(len(data))}
            def __enter__(self): return self
            def __exit__(self, *_): self.stream.close()
            def read(self, size): return self.stream.read(size)
        def request(req, timeout):
            requested.append(req.full_url)
            if not req.full_url.startswith(S.SERVERPLAN):
                raise B.urllib.error.HTTPError(req.full_url, 404, "fixture unavailable", {}, None)
            return Response(req.full_url, files[req.full_url.removeprefix(S.SERVERPLAN)])
        self.updater.transport = B.Transport()
        with mock.patch.object(B.urllib.request, "build_opener", return_value=type("Opener", (), {"open": staticmethod(request)})()):
            result, _ = self.run_update()
        self.assertEqual(result, 0)
        self.assertEqual(self.calls, ["plan", "apply"])
        self.assertEqual(requested[0], S.endpoint_url("github", "channels/candidate.json"))
        self.assertTrue(all(url.startswith(S.SERVERPLAN) for url in requested[1:]))

    def test_interrupted_archive_download_uses_other_transport_with_same_authentication(self):
        path = f"releases/{self.target['version']}/assets/{self.artifact_path.name}"
        github_url = S.endpoint_url("github", path)
        self.transport.github[github_url] = self.artifact_path.read_bytes()
        original = self.transport.fetch
        def interrupted(url, limit, destination=None):
            if url == S.SERVERPLAN + path:
                destination.write_bytes(b"partial fixture")
                raise S.Unavailable("interrupted fixture")
            return original(url, limit, destination)
        self.transport.fetch = interrupted
        self.run_update()
        self.assertIn(github_url, self.transport.calls)
        self.assertEqual(self.calls, ["plan", "apply"])

    def test_bad_archive_hash_is_not_a_transport_fallback_condition(self):
        path = f"releases/{self.target['version']}/assets/{self.artifact_path.name}"
        self.transport.files[path] = b"x" * self.artifact_path.stat().st_size
        github_url = S.endpoint_url("github", path)
        self.transport.github[github_url] = self.artifact_path.read_bytes()
        with self.assertRaises(D.DistributionError):
            self.run_update()
        self.assertNotIn(github_url, self.transport.calls)
        self.assertEqual(self.calls, [])

    def test_cancel_still_persists_authenticated_observations_without_applying(self):
        self.run_update(answer="")
        self.assertEqual(self.calls, ["plan"])
        self.assertEqual(self.identity_path.read_bytes(), D.canonical(self.source))
        self.assertEqual(self.security._read()["state"]["channels"]["candidate"]["sequence"], 1)

    def test_both_transports_unavailable_is_not_up_to_date(self):
        self.transport.offline = True
        with contextlib.redirect_stdout(io.StringIO()) as output:
            with self.assertRaises(S.Unavailable):
                self.updater.run_update()
        self.assertNotIn("up to date", output.getvalue())
        self.assertEqual(self.calls, [])

    def test_only_authenticated_no_target_reports_up_to_date(self):
        self.set_catalog(entries=[])
        result, output = self.run_update()
        self.assertEqual(result, 0)
        self.assertIn("up to date", output)
        self.assertEqual(self.calls, [])

    def test_primary_signature_failure_blocks_without_serverplan_fallback(self):
        payload = self.set_catalog()
        self.transport.github[S.endpoint_url("github", "channels/candidate.json")] = self.signed(payload, other=True)
        with self.assertRaises(D.DistributionError):
            self.run_update()
        self.assertEqual(len(self.transport.calls), 1)
        self.assertEqual(self.calls, [])

    def test_unknown_serverplan_signer_blocks(self):
        self.set_catalog(other=True)
        with self.assertRaises(D.DistributionError):
            self.run_update()
        self.assertEqual(self.calls, [])

    def test_tampered_catalog_and_unsupported_protocol_block(self):
        original = self.transport.files["channels/candidate.json"]
        envelope = json.loads(original)
        payload = json.loads(S.decoded(envelope["payload"], D.MAX_CATALOG))
        for change in ({"sequence": 2}, {"distribution_protocol": 2}):
            altered = {**payload, **change}
            envelope["payload"] = S.encode(D.canonical(altered))
            self.transport.files["channels/candidate.json"] = D.canonical(envelope)
            with self.assertRaises(D.DistributionError):
                self.run_update()
        self.assertEqual(self.calls, [])

    def test_modified_manifest_metadata_and_signature_never_run_target_code(self):
        prefix = f"releases/{self.target['version']}/"
        for path in (prefix + "manifest.json", prefix + "manifest.json.sig", prefix + "assets/release.json"):
            original = self.transport.files[path]
            self.transport.files[path] = original[:-1] + b"x"
            with self.assertRaises(D.DistributionError):
                self.run_update()
            self.transport.files[path] = original
        self.assertEqual(self.calls, [])

    def test_wrong_archive_hash_and_length_never_run_target_code(self):
        path = f"releases/{self.target['version']}/assets/{self.artifact_path.name}"
        original = self.transport.files[path]
        for data in (original[:-1], bytes([original[0] ^ 1]) + original[1:]):
            self.transport.files[path] = data
            with self.assertRaises(D.DistributionError):
                self.run_update()
        self.assertEqual(self.calls, [])

    def test_missing_release_artifact_remains_a_failure(self):
        del self.transport.files[f"releases/{self.target['version']}/assets/{self.artifact_path.name}"]
        with self.assertRaises(S.Unavailable):
            self.run_update()
        self.assertEqual(self.calls, [])

    def test_expired_and_future_catalogs_block(self):
        self.start()
        self.clock = D.timestamp("2027-01-01T00:00:00Z")
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.run_update()
        self.clock = foundation.CLOCK.now
        self.set_catalog(issued="2026-01-03T00:00:00Z")
        with self.assertRaisesRegex(D.DistributionError, "future"):
            self.run_update()

    def test_sequence_rollback_and_same_sequence_equivocation_block(self):
        self.acquire()
        self.set_catalog(sequence=1, entries=[])
        with self.assertRaisesRegex(D.DistributionError, "equivocation"):
            self.run_update()
        self.set_catalog(sequence=2)
        self.acquire()
        self.set_catalog(sequence=1)
        with self.assertRaisesRegex(D.DistributionError, "sequence rollback"):
            self.run_update()

    def test_conflicting_immutable_binding_blocks(self):
        self.acquire()
        entry = copy.deepcopy(self.entry)
        entry["manifest"]["sha256"] = "0" * 64
        self.set_catalog(sequence=2, entries=[entry])
        with self.assertRaisesRegex(D.DistributionError, "immutable"):
            self.run_update()

    def test_clock_rollback_blocks_even_with_valid_signature(self):
        self.acquire()
        self.clock -= 1
        with self.assertRaisesRegex(D.DistributionError, "clock rollback"):
            self.run_update()

    def test_expired_root_blocks_new_acquisition_before_network(self):
        self.start()
        self.clock = D.timestamp(foundation.ROOT_EXPIRES)
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.run_update()
        self.assertEqual(self.transport.calls, [])

    def test_root_pin_and_provenance_mismatch_block(self):
        value = json.loads(self.provenance.read_bytes())
        value["distribution_anchor_sha256"] = "0" * 64
        self.provenance.write_bytes(D.canonical(value))
        with self.assertRaisesRegex(D.DistributionError, "provenance"):
            self.run_update()
        self.assertEqual(self.transport.calls, [])

    def test_modified_installed_updater_blocks(self):
        (self.root / TARGET).write_bytes(b"modified fixture")
        with self.assertRaisesRegex(D.DistributionError, "provenance"):
            self.run_update()

    def test_missing_initialized_ledger_is_not_reset(self):
        self.start()
        self.security.path.unlink()
        with self.assertRaisesRegex(D.DistributionError, "missing"):
            self.run_update()
        self.assertFalse(self.security.path.exists())

    def test_corrupt_or_insecure_ledger_is_not_reset(self):
        self.start()
        original = self.security.path.read_bytes()
        self.security.path.write_bytes(b"{}\n")
        with self.assertRaises(D.DistributionError):
            self.run_update()
        self.assertEqual(self.security.path.read_bytes(), b"{}\n")
        self.security.path.write_bytes(original)
        self.security.path.chmod(0o644)
        with self.assertRaises(D.DistributionError):
            self.run_update()

    def test_initialization_interruption_between_ledger_and_marker_recovers(self):
        with mock.patch.object(self.security.api, "_publish", side_effect=OSError("fixture interruption")):
            with self.assertRaises(OSError):
                self.start()
        self.assertTrue(self.security.path.exists())
        self.assertFalse(json.loads(self.provenance.read_bytes())["distribution_initialized"])
        self.start()
        self.assertTrue(json.loads(self.provenance.read_bytes())["distribution_initialized"])

    def test_unexplained_pre_marker_state_is_never_adopted(self):
        self.start()
        record = json.loads(self.provenance.read_bytes())
        record["distribution_initialized"] = False
        self.provenance.write_bytes(D.canonical(record))
        ledger = self.security._read()
        ledger["state"]["clock_high_water"] = self.clock
        with self.updater.journal.lock.acquire():
            self.security.publish(ledger)
        with self.assertRaisesRegex(D.DistributionError, "unexpected state"):
            self.start()

    def test_lock_required_and_ledger_mode_is_private(self):
        with self.assertRaisesRegex(D.DistributionError, "lock"):
            self.security.start()
        self.start()
        self.assertEqual(self.security.path.stat().st_mode & 0o777, 0o600)

    def test_interrupted_security_publication_retains_a_complete_old_or_new_record(self):
        self.start()
        before = self.security.path.read_bytes()
        publish = self.security.api._publish
        for after in (False, True):
            def interrupted(path, data, mode):
                if after:
                    publish(path, data, mode)
                raise OSError("interrupted security publication fixture")
            self.set_catalog(sequence=2 if after else 1)
            with mock.patch.object(self.security.api, "_publish", side_effect=interrupted):
                with self.assertRaises(OSError):
                    self.acquire()
            ledger = self.security._read()
            if after:
                self.assertEqual(ledger["state"]["channels"]["candidate"]["sequence"], 2)
            else:
                self.assertEqual(self.security.path.read_bytes(), before)

    def test_security_state_hardlink_and_symlink_are_rejected(self):
        self.start()
        alias = self.root / "security-alias"
        os.link(self.security.path, alias)
        with self.assertRaises(D.DistributionError):
            self.run_update()
        alias.unlink()
        self.security.path.rename(alias)
        self.security.path.symlink_to(alias)
        with self.assertRaises(D.DistributionError):
            self.run_update()

    def test_provenance_marker_survives_bootstrap_replacement_and_blocks_pin_changes(self):
        source = self.root / "candidate-source"
        from install.update_bootstrap_integration import FILES
        for name in FILES:
            path = source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / name, path)
        (source / "release/trust.json").write_bytes(self.anchor)
        api = BootstrapIntegration(source, self.root, uid=os.getuid(), gid=os.getgid())
        api.apply(lifecycle="upgrade")
        self.start()
        (source / "install/update_bootstrap.py").write_bytes(
            (source / "install/update_bootstrap.py").read_bytes() + b"\n# Isolated next-updater fixture.\n")
        with self.assertRaisesRegex(ValueError, "held release-update lock"):
            api.apply(lifecycle="upgrade")
        self.assertTrue(api._record()["distribution_initialized"])
        alternate = json.loads(self.anchor)
        alternate["root_sha256"] = "0" * 64
        (source / "release/trust.json").write_bytes(D.canonical(alternate))
        with self.assertRaisesRegex(ValueError, "trust-anchor"):
            api.plan(lifecycle="upgrade")

    def test_stable_installation_cannot_use_candidate_catalog(self):
        installed = copy.deepcopy(self.source)
        installed.update(version="v1.0.0", channel="stable")
        installed["artifact"]["name"] = D.contract.artifact_name(installed["version"])
        self.identity_path.write_bytes(D.canonical(installed))
        self.transport.files["channels/stable.json"] = self.transport.files["channels/candidate.json"]
        with self.assertRaisesRegex(D.DistributionError, "channel"):
            self.run_update()
        self.assertEqual(self.calls, [])

    def test_genuine_v100_identity_to_signed_stable_fixture_with_zero_migrations(self):
        # Stable-shaped TEST-ONLY target in a temporary root; never published.
        base = self.root / "stable-target-fixture"
        base.mkdir()
        _, self.metadata_path, self.artifact_path, self.target = driver.BundleFixture.build(
            base, target_version="v1.0.1", minimum="v1.0.0", low=0, high=1, registry_ids=[1])
        original = (PROJECT / "tests/fixtures/updater-v1.0.0/release.json").read_bytes()
        self.source = D.contract.parse_metadata(original)
        self.identity_path.write_bytes(original)
        (self.root / "migration-state.txt").write_text("1")
        self.manifest = D.make_manifest(self.metadata_path, self.artifact_path, root_version=1)
        self.signature = self.minisign.sign(self.manifest, self.secret, self.public)
        self.entry = D.catalog_entry(self.manifest, self.signature)
        prefix = "releases/v1.0.1/"
        self.transport.files.update({prefix + "manifest.json": self.manifest,
                                     prefix + "manifest.json.sig": self.signature,
                                     prefix + "assets/release.json": self.metadata_path.read_bytes(),
                                     prefix + "assets/" + self.artifact_path.name: self.artifact_path.read_bytes()})
        self.set_catalog(channel="stable")
        backend = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                                 testing=True, authority=driver.FakeAuthorities(self.root))
        def invoke(bundle, operation):
            if operation == "plan":
                plan = backend.plan(bundle.metadata_path, bundle.artifact_path)
                self.assertEqual(plan.migrations, ())
                return json.dumps(plan.as_dict())
            backend.apply(bundle.metadata_path, bundle.artifact_path)
            return "complete"
        self.updater._driver = invoke
        result, _ = self.run_update()
        self.assertEqual(result, 0)
        self.assertEqual(backend.identity.validate(), self.target)
        self.assertIsNone(backend.journal.inspect())
        self.assertEqual(self.target["migration_level"], 1)

    def test_modified_retained_authorization_blocks_resume(self):
        self.pending_transaction()
        ledger = self.security._read()
        ledger["authorization"]["metadata"] = S.encode(b"{}\n")
        with self.updater.journal.lock.acquire():
            self.security.publish(ledger)
        self.updater._driver = lambda *_: self.fail("target code must not run")
        with self.assertRaises(D.DistributionError):
            self.run_update()

    def test_signed_authorization_is_durable_before_plan_and_apply(self):
        original = self.updater._driver
        def checked(bundle, operation):
            self.security.authorize(bundle.metadata)
            return original(bundle, operation)
        self.updater._driver = checked
        self.run_update()
        self.assertEqual(self.calls, ["plan", "apply"])

    def test_expiration_during_confirmation_prevents_new_apply(self):
        def answer(_):
            self.clock = D.timestamp("2027-01-01T00:00:00Z")
            return "y"
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.updater.run_update(answer=answer)
        self.assertEqual(self.calls, ["plan"])

    def pending_transaction(self):
        self.acquire()
        authority = driver.FakeAuthorities(self.root)
        target_driver = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                                       testing=True, authority=authority)
        authority.fail_before = "system-integration"
        with self.assertRaises(Exception):
            target_driver.apply(self.metadata_path, self.artifact_path)
        self.assertIsNotNone(target_driver.journal.inspect())
        return target_driver

    def test_exact_target_resume_is_offline_and_survives_catalog_and_root_expiry(self):
        target_driver = self.pending_transaction()
        self.clock = D.timestamp(foundation.ROOT_EXPIRES) + 1
        self.transport.calls.clear()
        self.transport.offline = True
        self.updater._driver = lambda _bundle, operation: target_driver.resume() if operation == "resume" else self.fail("wrong operation")
        result, _ = self.run_update()
        self.assertEqual(result, 0)
        self.assertEqual(self.transport.calls, [])
        self.assertIsNone(target_driver.journal.inspect())
        self.assertEqual(self.identity_path.read_bytes(), self.metadata_path.read_bytes())

    def test_interruption_after_staging_before_journal_blocks_new_discovery(self):
        self.acquire()
        self.updater.store.prepare(self.metadata_path, self.artifact_path, permanent=True)
        before = self.security.path.read_bytes()
        self.transport.calls.clear()
        with self.assertRaisesRegex(B.BootstrapError, "uncommitted retained staging"):
            self.run_update()
        self.assertEqual(self.transport.calls, [])
        self.assertEqual(self.security.path.read_bytes(), before)

    def test_bad_or_missing_retained_journal_target_never_discovers_new_release(self):
        self.acquire()
        with self.updater.journal.lock.acquire():
            self.updater.journal.begin(self.source, self.target, target_user=self.user.name)
        self.transport.calls.clear()
        with self.assertRaises(Exception):
            self.run_update()
        self.assertEqual(self.transport.calls, [])
        self.updater.journal.path.write_bytes(b'{"schema":1,"schema":1}\n')
        with self.assertRaises(B.JournalError):
            self.run_update()

    def test_missing_authorization_blocks_resume_without_network_or_target_code(self):
        self.pending_transaction()
        ledger = self.security._read()
        ledger["authorization"] = None
        with self.updater.journal.lock.acquire():
            self.security.publish(ledger)
        self.transport.calls.clear()
        self.updater._driver = lambda *_: self.fail("target code must not run")
        with self.assertRaisesRegex(D.DistributionError, "authorization"):
            self.run_update()
        self.assertEqual(self.transport.calls, [])

    def test_committed_identity_terminal_cleanup_uses_retained_authorization(self):
        self.acquire()
        authority = driver.FakeAuthorities(self.root)
        target_driver = ReleaseUpdate(self.user, root=self.root, uid=os.getuid(), gid=os.getgid(),
                                       testing=True, authority=authority)
        with mock.patch.object(target_driver.journal, "clear_after_commit", side_effect=OSError("interrupted")):
            with self.assertRaises(Exception):
                target_driver.apply(self.metadata_path, self.artifact_path)
        self.transport.calls.clear()
        self.transport.offline = True
        self.updater._driver = lambda *_: target_driver.resume()
        self.run_update()
        self.assertEqual(self.transport.calls, [])
        self.assertIsNone(target_driver.journal.inspect())

    def test_resume_for_other_user_is_blocked(self):
        self.pending_transaction()
        self.updater.user = TargetUser("other", self.user.uid, self.user.gid, self.user.home, self.user.groups)
        with self.assertRaisesRegex(B.BootstrapError, "different target user"):
            self.run_update()

    def test_failed_resume_retains_exact_journal_and_proof(self):
        self.pending_transaction()
        prior = self.security.path.read_bytes()
        self.updater._driver = lambda *_: (_ for _ in ()).throw(B.BootstrapError("fixture incomplete"))
        with self.assertRaises(B.BootstrapError):
            self.run_update()
        self.assertIsNotNone(self.updater.journal.inspect())
        self.assertEqual(self.security.path.read_bytes(), prior)

    def test_rotation_and_historical_manifest_authentication(self):
        payload = D.make_root(self.keys[1][1], issued_at="2026-01-02T00:00:00Z", root_version=2,
                               previous_root_sha256=D.digest(self.root_payload))
        signatures = [(public, self.minisign.sign(payload, secret, public)) for secret, public in self.keys]
        self.transport.files["roots/2.json"] = D.envelope(payload, signatures)
        self.set_catalog(root_version=2, issued="2026-01-02T00:00:00Z", other=True)
        self.run_update()
        self.assertEqual(self.security._read()["state"]["root_version"], 2)
        self.assertEqual(self.calls, ["plan", "apply"])

    def test_unsigned_or_wrong_root_rotation_fails_closed(self):
        payload = D.make_root(self.keys[1][1], issued_at="2026-01-02T00:00:00Z", root_version=2,
                               previous_root_sha256="0" * 64)
        self.transport.files["roots/2.json"] = self.signed(payload, other=True)
        self.set_catalog(root_version=2, issued="2026-01-02T00:00:00Z", other=True)
        with self.assertRaises(D.DistributionError):
            self.run_update()
        self.assertEqual(self.calls, [])

    def test_packaged_unconfigured_anchor_blocks_released_installation(self):
        self.updater.security = None
        unconfigured = D.canonical({"schema": 1, "public_key": None, "root": None, "root_sha256": None})
        with mock.patch.object(B, "SecurityStore", side_effect=lambda journal:
                               S.SecurityStore(journal, anchor=unconfigured)):
            with self.assertRaisesRegex(D.DistributionError, "unconfigured"):
                self.run_update()
        self.assertEqual(self.transport.calls, [])

    def test_preparation_prerequisites_verify_public_pins_without_installing_packages(self):
        from install.update_bootstrap_integration import FILES
        files = {name: (PROJECT / name).read_bytes() for name in FILES}
        files["release/trust.json"] = self.anchor
        operation = preparation.Preparation.__new__(preparation.Preparation)
        operation.payload = BootstrapIntegration.package_files(files)
        operation.api = mock.Mock()
        native_run = subprocess.run
        commands = []
        def run(command, **kwargs):
            commands.append(command)
            if command[:3] == ["/usr/bin/pacman", "-Q", "minisign"]:
                return subprocess.CompletedProcess(command, 0)
            return native_run(command, **kwargs)
        with mock.patch.object(Path, "is_file", return_value=True), \
             mock.patch.object(Path, "is_symlink", return_value=False), \
             mock.patch.object(Path, "stat", return_value=type("Info", (), {"st_uid": 0, "st_mode": 0o100755})()), \
             mock.patch.object(preparation.subprocess, "run", side_effect=run), \
             mock.patch.object(D, "Minisign", return_value=self.minisign):
            operation.prerequisites()
        self.assertEqual([cmd for cmd in commands if cmd[0].endswith("pacman")],
                         [["/usr/bin/pacman", "-Q", "minisign"]])
        self.assertTrue(any("-V" in cmd for cmd in commands))

    def test_preparation_prerequisites_reject_unconfigured_trust_before_package_query(self):
        from install.update_bootstrap_integration import FILES
        operation = preparation.Preparation.__new__(preparation.Preparation)
        files = {name: (PROJECT / name).read_bytes() for name in FILES}
        files["release/trust.json"] = D.canonical({"schema": 1, "public_key": None,
                                                   "root": None, "root_sha256": None})
        operation.payload = BootstrapIntegration.package_files(files)
        operation.api = mock.Mock()
        with mock.patch.object(preparation.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "trust anchor"):
                operation.prerequisites()
            run.assert_not_called()

    def test_unreleased_identity_does_not_create_security_state(self):
        self.identity_path.unlink()
        self.updater.security = None
        with self.assertRaisesRegex(B.BootstrapError, "unreleased/development"):
            self.run_update()
        self.assertFalse(self.security.path.exists())

    def test_only_fixed_transport_paths_are_accepted(self):
        for path in ("../root.json", "/channels/stable.json", "channels/stable.json?x=y",
                     "releases/v1.0.0/assets/other.tar.gz", "https://other.invalid/file"):
            with self.assertRaises(D.DistributionError):
                S.endpoint_url("serverplan", path)


if __name__ == "__main__":
    unittest.main()
