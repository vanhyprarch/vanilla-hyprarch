#!/usr/bin/env python3
"""Offline publisher/HTTPS observation adversaries with disposable Minisign keys."""
from __future__ import annotations

import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import unittest
from unittest import mock
import urllib.error

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from release import distribution as D
from release.publication import Publisher


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, PROJECT / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F = load("static_publication_fixtures", "tests/signed-updater.py")
H = load("hosting_acceptance_fixture", "admin/hosting-acceptance.py")


class PublicationTests(F.SignedUpdaterFixture):
    def setUp(self):
        super().setUp()
        self.workspace = Path(self.temporary.name) / "publisher"
        self.publisher = Publisher.initialize(self.workspace, self.root_record, self.public,
            D.digest(self.root_payload), minisign=self.minisign, now=lambda: self.clock)

    def release(self, **kwargs):
        return self.publisher.add_release(self.metadata_path, self.artifact_path, self.target["commit"],
                                          kwargs.get("secret", self.secret))

    def catalog(self, sequence=1, **kwargs):
        return self.publisher.catalog(kwargs.pop("channel", "candidate"), sequence,
            kwargs.pop("versions", [self.target["version"]]), kwargs.pop("issued", F.foundation.ISSUED),
            secret_key=kwargs.pop("secret", self.secret), **kwargs)

    def snapshot(self):
        return {str(path.relative_to(self.workspace)): path.read_bytes()
                for path in self.workspace.rglob("*") if path.is_file()}

    def test_complete_static_tree_and_signatures(self):
        self.release()
        self.catalog()
        result = self.publisher.check()
        self.assertEqual(result["releases"], [self.target["version"]])
        self.assertEqual(result["pending_channels"], [])
        self.assertEqual({p.name for p in self.publisher.public.iterdir()}, {"roots", "channels", "releases"})
        channel = self.publisher.public / "channels/candidate.json"
        verified = D.verify_catalog(channel.read_bytes(), F.foundation.SignedDistributionTests.root,
            channel="candidate", state=D.initial_state(F.foundation.SignedDistributionTests.root),
            minisign=self.minisign, clock=D.Clock(self.clock))
        directory = self.publisher.public / "releases" / self.target["version"]
        identity = D.verify_release((directory / "manifest.json").read_bytes(),
            (directory / "manifest.json.sig").read_bytes(), (directory / "assets/release.json").read_bytes(),
            verified, self.target["version"], F.foundation.SignedDistributionTests.root,
            minisign=self.minisign, clock=D.Clock(self.clock))
        self.assertEqual(identity, self.target)

    def test_release_retry_reuses_frozen_native_signature_without_key(self):
        self.release()
        before = self.snapshot()
        with mock.patch.object(self.minisign, "sign", side_effect=AssertionError("must not resign")):
            self.release(secret=None)
        self.assertEqual(self.snapshot(), before)

    def test_wrong_approved_source_commit_rejected(self):
        with self.assertRaisesRegex(D.DistributionError, "approved exact commit"):
            self.publisher.add_release(self.metadata_path, self.artifact_path, "0" * 40, self.secret)
        self.assertEqual(list((self.publisher.public / "releases").iterdir()), [])

    def test_reinitialization_refuses_existing_workspace_without_changes(self):
        self.release()
        before = self.snapshot()
        with self.assertRaises(FileExistsError):
            Publisher.initialize(self.workspace, self.root_record, self.public, D.digest(self.root_payload),
                                 minisign=self.minisign, now=lambda: self.clock)
        self.assertEqual(self.snapshot(), before)

    def test_immutable_version_cannot_be_reassigned(self):
        self.release()
        other = Path(self.temporary.name) / "other.json"
        value = copy.deepcopy(self.target)
        value["commit"] = "0" * 40
        other.write_bytes(D.canonical(value))
        with self.assertRaisesRegex(D.DistributionError, "immutable version"):
            self.publisher.add_release(other, self.artifact_path, value["commit"], self.secret)

    def test_modified_manifest_signature_metadata_archive_rejected(self):
        self.release()
        directory = self.publisher.public / "releases" / self.target["version"]
        for path in directory.rglob("*"):
            if not path.is_file(): continue
            original = path.read_bytes()
            with self.subTest(name=path.name):
                path.write_bytes(original + b"x")
                with self.assertRaises((D.DistributionError, OSError)):
                    self.publisher.check()
                path.write_bytes(original)

    def test_unknown_duplicate_immutable_directory_is_not_adopted(self):
        destination = self.publisher.public / "releases" / self.target["version"]
        destination.mkdir()
        with self.assertRaisesRegex(D.DistributionError, "unregistered"):
            self.release()

    def test_missing_frozen_receipt_blocks_existing_public_release(self):
        self.release()
        shutil.rmtree(self.publisher.receipts / "releases" / self.target["version"])
        with self.assertRaisesRegex(D.DistributionError, "unregistered"):
            self.release()

    def test_incomplete_immutable_directory_blocks_catalog(self):
        self.release()
        (self.publisher.public / "releases" / self.target["version"] / "manifest.json").unlink()
        with self.assertRaises((D.DistributionError, OSError)):
            self.catalog()

    def test_wrong_artifact_hash_never_freezes_or_publishes(self):
        path = Path(self.temporary.name) / self.artifact_path.name
        path.write_bytes(self.artifact_path.read_bytes() + b"x")
        with self.assertRaises(D.DistributionError):
            self.publisher.add_release(self.metadata_path, path, self.target["commit"], self.secret)
        self.assertEqual(list((self.publisher.receipts / "releases").iterdir()), [])

    def test_input_mutation_during_copy_cannot_publish(self):
        inputs = Path(self.temporary.name) / "changing-inputs"
        inputs.mkdir()
        metadata, archive = inputs / "release.json", inputs / self.artifact_path.name
        shutil.copyfile(self.metadata_path, metadata)
        shutil.copyfile(self.artifact_path, archive)
        native = self.publisher._copy
        def corrupt(source, output, length):
            source.write_bytes(source.read_bytes() + b"x")
            return native(source, output, length)
        with mock.patch.object(self.publisher, "_copy", side_effect=corrupt):
            with self.assertRaises((D.DistributionError, D.contract.ReleaseError)):
                self.publisher.add_release(metadata, archive, self.target["commit"], self.secret)
        self.assertEqual(list((self.publisher.receipts / "releases").iterdir()), [])

    def test_release_interruption_after_receipt_resumes_without_resigning(self):
        native = os.rename
        def interrupted(source, destination):
            if Path(destination).parent == self.publisher.public / "releases":
                raise OSError("publication interrupted")
            return native(source, destination)
        with mock.patch("release.publication.os.rename", side_effect=interrupted):
            with self.assertRaises(OSError): self.release()
        self.assertTrue((self.publisher.receipts / "releases" / self.target["version"]).is_dir())
        with mock.patch.object(self.minisign, "sign", side_effect=AssertionError("must reuse signature")):
            self.release(secret=None)
        self.assertEqual(self.publisher.check()["releases"], [self.target["version"]])

    def test_catalog_renewal_requires_higher_sequence_and_same_binding(self):
        self.release()
        first = self.catalog()
        second = self.catalog(2, expires_at="2026-07-01T00:00:00Z")
        self.assertEqual(first["releases"], second["releases"])
        self.assertEqual(self.publisher.history(self.publisher.root())[1]["candidate"][1].value, second)

    def test_same_sequence_idempotence_reuses_exact_envelope(self):
        self.release()
        self.catalog()
        before = (self.publisher.public / "channels/candidate.json").read_bytes()
        with mock.patch.object(self.minisign, "sign", side_effect=AssertionError("must not resign")):
            self.catalog(secret=None)
        self.assertEqual((self.publisher.public / "channels/candidate.json").read_bytes(), before)

    def test_same_sequence_expiration_or_membership_equivocation_rejected(self):
        self.release()
        self.catalog()
        for kwargs in ({"expires_at": "2026-07-01T00:00:00Z"}, {"versions": []}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaisesRegex(D.DistributionError, "equivocation"): self.catalog(**kwargs)

    def test_old_and_skipped_catalog_sequences_rejected(self):
        self.release()
        self.catalog()
        self.catalog(2)
        for sequence in (1, 4):
            with self.assertRaisesRegex(D.DistributionError, "next reserved sequence"):
                self.catalog(sequence)

    def test_stable_channel_cannot_publish_candidate(self):
        self.release()
        with self.assertRaises(D.DistributionError): self.catalog(channel="stable")
        self.catalog(channel="stable", versions=[])
        self.catalog()
        self.publisher.check()

    def test_catalog_lifetime_and_expiry_policy(self):
        self.release()
        with self.assertRaises(D.DistributionError): self.catalog(expires_at="2027-01-01T00:00:01Z")
        self.catalog()
        self.clock = D.timestamp("2027-01-01T00:00:00Z")
        with self.assertRaisesRegex(D.DistributionError, "expired"): self.publisher.resume_channel("candidate")
        self.catalog(2, issued="2027-01-01T00:00:00Z")
        self.publisher.check()

    def test_catalog_issuance_and_clock_rollback_rejected(self):
        self.release()
        self.catalog(issued="2026-01-02T00:00:00Z")
        with self.assertRaisesRegex(D.DistributionError, "issuance rollback"):
            self.catalog(2)
        self.clock -= 1
        with self.assertRaisesRegex(D.DistributionError, "clock rollback|issued in future"):
            self.publisher.check()

    def test_catalog_pointer_failure_reserves_sequence_before_publication(self):
        self.release()
        with mock.patch.object(self.publisher, "_replace_channel", side_effect=OSError("interrupted")):
            with self.assertRaises(OSError): self.catalog()
        self.assertEqual(self.publisher.check()["pending_channels"], ["candidate"])
        with self.assertRaisesRegex(D.DistributionError, "equivocation"):
            self.catalog(versions=[])
        self.publisher.resume_channel("candidate")
        self.assertEqual(self.publisher.check()["pending_channels"], [])

    def test_sigkill_after_catalog_receipt_and_fresh_instance_resume(self):
        self.release()
        pid = os.fork()
        if pid == 0:
            self.publisher._replace_channel = lambda *_: os.kill(os.getpid(), signal.SIGKILL)
            self.catalog()
            os._exit(99)
        _, status = os.waitpid(pid, 0)
        self.assertTrue(os.WIFSIGNALED(status))
        self.assertEqual(os.WTERMSIG(status), signal.SIGKILL)
        publisher = Publisher(self.workspace, minisign=self.minisign, now=lambda: self.clock)
        publisher.resume_channel("candidate")
        self.assertEqual(publisher.check()["pending_channels"], [])

    def test_failure_after_catalog_replace_is_idempotently_recoverable(self):
        self.release()
        original = self.publisher._replace_channel
        def interrupted(channel, data):
            original(channel, data)
            raise OSError("after pointer replacement")
        with mock.patch.object(self.publisher, "_replace_channel", side_effect=interrupted):
            with self.assertRaises(OSError): self.catalog()
        before = (self.publisher.public / "channels/candidate.json").read_bytes()
        self.publisher.resume_channel("candidate")
        self.assertEqual((self.publisher.public / "channels/candidate.json").read_bytes(), before)

    def test_path_traversal_symlink_and_hardlink_rejected(self):
        for version in ("../v1.0.0", "/v1.0.0", "v1.0.0/../../x"):
            with self.assertRaises(D.DistributionError): self.catalog(versions=[version])
        self.release()
        metadata = self.publisher.public / "releases" / self.target["version"] / "assets/release.json"
        alias = Path(self.temporary.name) / "alias"
        os.link(metadata, alias)
        with self.assertRaises(D.DistributionError): self.publisher.check()
        alias.unlink()
        original = metadata.read_bytes()
        metadata.unlink()
        alias.write_bytes(original)
        metadata.symlink_to(alias)
        with self.assertRaises(D.DistributionError): self.publisher.check()

    def test_no_key_inside_workspace_and_wrong_signer_rejected(self):
        with self.assertRaisesRegex(D.DistributionError, "outside"):
            self.release(secret=self.workspace / "private.key")
        with self.assertRaises(D.DistributionError): self.release(secret=self.keys[1][0])

    def test_unknown_root_or_root_modification_rejected(self):
        root = self.publisher.public / "roots/1.json"
        root.write_bytes(root.read_bytes() + b"x")
        with self.assertRaises(D.DistributionError): self.publisher.check()

    def test_missing_or_corrupt_catalog_receipt_never_resets_history(self):
        self.release()
        self.catalog()
        receipt = self.publisher.receipts / "catalogs/candidate/1.json"
        original = receipt.read_bytes()
        receipt.write_bytes(b"{}\n")
        with self.assertRaises(D.DistributionError): self.publisher.check()
        receipt.write_bytes(original)
        receipt.unlink()
        with self.assertRaises(D.DistributionError): self.publisher.check()

    def test_unknown_public_pointer_rejected_without_overwrite(self):
        self.release()
        self.catalog()
        pointer = self.publisher.public / "channels/candidate.json"
        pointer.write_bytes(b"incomplete upload")
        with self.assertRaises(D.DistributionError): self.publisher.resume_channel("candidate")
        self.assertEqual(pointer.read_bytes(), b"incomplete upload")

    def test_read_only_check_and_concurrent_publisher(self):
        self.release()
        self.catalog()
        before = self.snapshot()
        self.publisher.check()
        self.assertEqual(self.snapshot(), before)
        with self.publisher.locked():
            with self.assertRaisesRegex(D.DistributionError, "another publisher"):
                Publisher(self.workspace, minisign=self.minisign).check()

    def test_generated_tree_acquired_with_github_unavailable(self):
        self.release()
        self.catalog()
        self.transport.files = {str(path.relative_to(self.publisher.public)): path.read_bytes()
            for path in self.publisher.public.rglob("*") if path.is_file()}
        result, _ = self.run_update()
        self.assertEqual(result, 0)
        self.assertEqual(self.calls, ["plan", "apply"])
        self.assertTrue(any(url.startswith(F.S.SERVERPLAN) for url in self.transport.calls))


class HostingTests(F.SignedUpdaterFixture):
    def setUp(self):
        super().setUp()
        self.directory = Path(self.temporary.name) / "hosting-fixture"
        self.production = (PROJECT / "release/trust.json").read_bytes()
        self.proposal = H.prepare(self.directory, self.minisign, now=lambda: self.clock)
        self.base, self.test_root, self.files = H.fixture(self.directory, self.minisign, now=lambda: self.clock)

    def test_test_only_keys_deleted_and_production_trust_untouched(self):
        self.assertTrue(self.proposal["private_keys_removed"])
        self.assertFalse(self.proposal["remote_writes_authorized"])
        self.assertTrue(self.base.startswith(H.BASE))
        self.assertFalse(list(self.directory.rglob("*.key")))
        self.assertEqual((PROJECT / "release/trust.json").read_bytes(), self.production)
        with self.assertRaises(D.DistributionError):
            D.TrustedRoot.initial(self.files["upload/root.json"], pinned_public_key=self.public,
                pinned_root_sha256=D.digest(self.root_payload), minisign=self.minisign, clock=D.Clock(self.clock))

    def sequence_get(self, sequence):
        def get(base, path, **kwargs):
            self.assertEqual(base, self.base)
            if kwargs.get("allow_304"): return 304, b"", {"ETag": '"one"'}
            values = {"root.json": self.files["upload/root.json"], "immutable/probe.bin": H.PROBE,
                "pointer.json": self.files["upload/pointer.json" if sequence == 1 else "switch/pointer-v2.json.part"]}
            return 200, values[path], {"ETag": f'"{sequence}"', "Cache-Control": "no-cache, must-revalidate"}
        return get

    def test_https_delivery_inspection_and_duplicate_immutable_refusal(self):
        result = H.inspect(self.directory, self.minisign, now=lambda: self.clock, get=self.sequence_get(1))
        self.assertFalse(result["atomicity_guaranteed"])
        self.assertIn("REFUSE", result["duplicate_immutable_upload"])
        self.assertEqual(result["observations"]["pointer.json"]["conditional_status"], 304)

    def test_complete_staged_upload_verified_before_rename(self):
        def get(base, path, **kwargs):
            if path == "pointer.json.complete":
                return 200, self.files["switch/pointer-v2.json.part"], {}
            return self.sequence_get(1)(base, path, **kwargs)
        result = H.inspect(self.directory, self.minisign, staged=True, now=lambda: self.clock, get=get)
        self.assertIn("pointer.json.complete", result["observations"])
        def incomplete(base, path, **kwargs):
            if path == "pointer.json.complete": return 200, b"partial", {}
            return get(base, path, **kwargs)
        with self.assertRaisesRegex(D.DistributionError, "staged pointer"):
            H.inspect(self.directory, self.minisign, staged=True, now=lambda: self.clock, get=incomplete)

    def test_test_key_cleanup_after_signing_failure(self):
        directory = Path(self.temporary.name) / "failed-host-fixture"
        native_temporary = H.tempfile.TemporaryDirectory
        created = []
        def temporary(**kwargs):
            result = native_temporary(**kwargs)
            created.append(Path(result.name))
            return result
        with mock.patch.object(H.tempfile, "TemporaryDirectory", side_effect=temporary), \
             mock.patch.object(self.minisign, "sign", side_effect=D.DistributionError("fixture failure")):
            with self.assertRaises(D.DistributionError):
                H.prepare(directory, self.minisign, now=lambda: self.clock)
        self.assertTrue(created)
        self.assertTrue(all(not path.exists() for path in created))

    def test_complete_old_to_new_pointer_observation_is_not_atomicity_proof(self):
        values = iter((1, 1, 2, 2))
        result = H.watch(self.directory, self.minisign, samples=4, interval=0, now=lambda: self.clock,
            get=lambda *args, **kwargs: self.sequence_get(next(values))(*args, **kwargs))
        self.assertEqual(result["sequences_seen"], [1, 2])
        self.assertFalse(result["atomicity_guaranteed"])

    def test_truncated_or_incomplete_pointer_upload_rejected(self):
        with self.assertRaises(D.DistributionError):
            H.watch(self.directory, self.minisign, samples=1, interval=0, now=lambda: self.clock,
                get=lambda *args, **kwargs: (200, self.files["switch/incomplete.json.part"], {}))

    def test_modified_immutable_remote_object_rejected(self):
        with self.assertRaisesRegex(D.DistributionError, "immutable"):
            H.inspect(self.directory, self.minisign, now=lambda: self.clock,
                      get=lambda *args, **kwargs: (200, b"changed", {}))

    def test_stale_cached_catalog_after_new_sequence_is_rollback(self):
        values = iter((2, 1))
        with self.assertRaisesRegex(D.DistributionError, "rollback"):
            H.watch(self.directory, self.minisign, samples=2, interval=0, now=lambda: self.clock,
                get=lambda *args, **kwargs: self.sequence_get(next(values))(*args, **kwargs))

    def test_reused_etag_for_changed_bytes_rejected(self):
        values = iter((1, 2))
        def get(*args, **kwargs):
            status, body, headers = self.sequence_get(next(values))(*args, **kwargs)
            return status, body, {**headers, "ETag": '"same"'}
        with self.assertRaisesRegex(D.DistributionError, "ETag reused"):
            H.watch(self.directory, self.minisign, samples=2, interval=0, now=lambda: self.clock, get=get)

    def test_no_observed_replacement_is_not_acceptance(self):
        with self.assertRaisesRegex(D.DistributionError, "not observed"):
            H.watch(self.directory, self.minisign, samples=1, interval=0, now=lambda: self.clock,
                    get=self.sequence_get(1))

    def test_expired_fixture_rejected(self):
        self.clock += D.SECONDS_PER_DAY
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            H.fixture(self.directory, self.minisign, now=lambda: self.clock)

    def test_local_fixture_tampering_and_path_traversal_rejected(self):
        receipt_path = self.directory / "fixture.json"
        receipt = json.loads(receipt_path.read_bytes())
        receipt["test_id"] = "../../vanilla-hyprarch/channels"
        receipt_path.write_bytes(D.canonical(receipt))
        with self.assertRaises(D.DistributionError): H.fixture(self.directory, self.minisign)

    def test_network_probe_cannot_target_production_or_another_host(self):
        with mock.patch.object(H.urllib.request, "build_opener") as opener:
            for base in (F.S.SERVERPLAN, "https://other.invalid/", H.BASE + "../"):
                with self.assertRaises(D.DistributionError): H.fetch(base, "pointer.json")
            with self.assertRaises(D.DistributionError): H.fetch(self.base, "../channels/stable.json")
            opener.assert_not_called()

    def test_http_bounded_bytes_headers_and_no_credentials(self):
        class Response:
            status = 200
            url = self.base + "pointer.json"
            headers = {"Content-Length": "3", "ETag": '"example"', "Set-Cookie": "DO NOT LOG"}
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def read(self, maximum): return b"abc"
        opened = mock.Mock(return_value=Response())
        with mock.patch.object(H.urllib.request, "build_opener", return_value=type("Opener", (), {"open": opened})()):
            _, data, headers = H.fetch(self.base, "pointer.json")
            self.assertEqual(data, b"abc")
            self.assertNotIn("Set-Cookie", headers)
            request = opened.call_args.args[0]
            self.assertNotIn("Authorization", request.headers)
        Response.headers["Content-Length"] = "4"
        with mock.patch.object(H.urllib.request, "build_opener", return_value=type("Opener", (), {"open": opened})()):
            with self.assertRaises(D.DistributionError): H.fetch(self.base, "pointer.json")

    def test_http_404_and_redirect_are_not_success(self):
        error = urllib.error.HTTPError(self.base + "pointer.json", 404, "missing", {}, io.BytesIO())
        with mock.patch.object(H.urllib.request, "build_opener", return_value=type("Opener", (), {
            "open": lambda *args, **kwargs: (_ for _ in ()).throw(error)})()):
            with self.assertRaisesRegex(D.DistributionError, "404"): H.fetch(self.base, "pointer.json")
        with self.assertRaises(D.DistributionError): H.NoRedirect().redirect_request(None)


if __name__ == "__main__":
    unittest.main()
