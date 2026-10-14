#!/usr/bin/env python3
"""Offline metadata adversaries with real Minisign and ephemeral TEST-ONLY keys.

Set MINISIGN to an absolute verified executable when it is not installed. A
missing verifier is a test failure, never a skipped cryptographic test.
"""

from __future__ import annotations

import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from release import distribution as D  # noqa: E402

SPEC = importlib.util.spec_from_file_location("release_fixture", PROJECT / "tests/release-artifact.py")
FIXTURE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FIXTURE)

ISSUED = "2026-01-01T00:00:00Z"
EXPIRES = "2026-02-01T00:00:00Z"
# A deliberately longer TEST-ONLY root interval is independent of catalog policy.
ROOT_EXPIRES = "2028-01-01T00:00:00Z"
CLOCK = D.Clock(D.timestamp("2026-01-02T00:00:00Z"))


class SignedDistributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix="vanhyprarch-test-only-keys-")
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        cls.minisign = D.Minisign(Path(os.environ.get("MINISIGN", "/usr/bin/minisign")))
        cls.keys = []
        for number in range(2):
            secret, public = cls.base / f"TEST-ONLY-{number}.key", cls.base / f"key-{number}.pub"
            # -W is exclusively for these disposable test keys in a mode-0700 dir.
            subprocess.run([str(cls.minisign.executable), "-G", "-W", "-s", str(secret),
                            "-p", str(public)], check=True, capture_output=True)
            secret.chmod(0o600)
            cls.keys.append((secret, public.read_text().splitlines()[1]))
        cls.secret, cls.public = cls.keys[0]
        cls.root_payload = D.make_root(cls.public, issued_at=ISSUED, expires_at=ROOT_EXPIRES)
        cls.root_signature = cls.minisign.sign(cls.root_payload, cls.secret, cls.public)
        cls.root_envelope = D.envelope(cls.root_payload, [(cls.public, cls.root_signature)])
        cls.root = D.TrustedRoot.initial(cls.root_envelope, pinned_public_key=cls.public,
                                        pinned_root_sha256=D.digest(cls.root_payload),
                                        minisign=cls.minisign, clock=CLOCK)
        cls.state = D.initial_state(cls.root)
        repo = cls.base / "repo"
        repo.mkdir()
        commit = FIXTURE.write_fixture(repo)
        output = cls.base / "output"
        output.mkdir()
        cls.metadata_path, cls.archive_path = D.contract.build(repo, commit, output)
        cls.metadata = cls.metadata_path.read_bytes()
        cls.identity = D.contract.parse_metadata(cls.metadata)
        cls.manifest = D.make_manifest(cls.metadata_path, cls.archive_path, root_version=1)
        cls.signature = cls.minisign.sign(cls.manifest, cls.secret, cls.public)
        cls.entry = D.catalog_entry(cls.manifest, cls.signature)

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.work = Path(self.scratch.name)

    def changed(self, data, **changes):
        value = D.decode(data, D.MAX_CATALOG)
        value.update(changes)
        return D.canonical(value)

    def catalog_payload(self, channel="candidate", sequence=1, entries=None, **changes):
        payload = D.make_catalog(channel, sequence, [self.entry] if entries is None else entries,
                                 root_version=1, issued_at=ISSUED, expires_at=EXPIRES)
        return self.changed(payload, **changes)

    def signed(self, payload, *, other=False):
        secret, public = self.keys[int(other)]
        return D.envelope(payload, [(public, self.minisign.sign(payload, secret, public))])

    def verified(self, payload=None, *, state=None, clock=CLOCK, channel="candidate"):
        return D.verify_catalog(self.signed(payload or self.catalog_payload()), self.root,
                                channel=channel, state=state or self.state,
                                minisign=self.minisign, clock=clock)

    def verify_release(self, *, manifest=None, signature=None, metadata=None, catalog=None,
                       version="v1.0.0-rc1", root=None, clock=CLOCK):
        return D.verify_release(manifest or self.manifest, signature or self.signature,
                                metadata or self.metadata, catalog or self.verified(), version,
                                root or self.root, minisign=self.minisign, clock=clock)

    def reject(self, data):
        with self.assertRaises(D.DistributionError):
            D.validate_object(data)

    def test_real_minisign_authenticates_exact_bytes(self):
        self.minisign.verify(self.manifest, self.signature, self.public)

    def test_wrong_key_rejected_by_native_minisign(self):
        with self.assertRaises(D.DistributionError):
            self.minisign.verify(self.manifest, self.signature, self.keys[1][1])

    def test_tampered_bytes_rejected_by_native_minisign(self):
        with self.assertRaises(D.DistributionError):
            self.minisign.verify(self.manifest + b" ", self.signature, self.public)

    def test_truncated_signature_rejected(self):
        with self.assertRaises(D.DistributionError):
            self.minisign.verify(self.manifest, self.signature[:40], self.public)

    def test_legacy_unhashed_signature_rejected(self):
        message, signature = self.work / "message", self.work / "signature"
        message.write_bytes(self.manifest)
        subprocess.run([str(self.minisign.executable), "-S", "-l", "-s", str(self.secret),
                        "-m", str(message), "-x", str(signature)], check=True, capture_output=True)
        with self.assertRaises(D.DistributionError):
            self.minisign.verify(self.manifest, signature.read_bytes(), self.public)

    def test_untrusted_comment_is_not_authority(self):
        lines = self.root_signature.splitlines(keepends=True)
        lines[0] = b"untrusted comment: attacker-selected identity and key hint\n"
        changed = D.envelope(self.root_payload, [(self.public, b"".join(lines))])
        actual = D.TrustedRoot.initial(changed, pinned_public_key=self.public,
                                      pinned_root_sha256=D.digest(self.root_payload),
                                      minisign=self.minisign, clock=CLOCK)
        self.assertEqual(actual, self.root)

    def test_trusted_comment_tampering_rejected(self):
        lines = self.root_signature.splitlines(keepends=True)
        lines[2] = b"trusted comment: attacker\n"
        with self.assertRaises(D.DistributionError):
            self.minisign.verify(self.root_payload, b"".join(lines), self.public)

    def test_missing_verifier_fails_closed(self):
        with self.assertRaisesRegex(D.DistributionError, "unavailable"):
            D.Minisign(self.work / "absent").verify(self.manifest, self.signature, self.public)

    def test_verifier_timeout_fails_closed(self):
        with mock.patch.object(D.subprocess, "run", side_effect=subprocess.TimeoutExpired("minisign", 15)):
            with self.assertRaises(D.DistributionError):
                self.minisign.verify(self.manifest, self.signature, self.public)

    def test_minisign_invocation_does_not_use_path_key_defaults_or_emit_comments(self):
        with mock.patch.object(D.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
            self.minisign.verify(self.manifest, self.signature, self.public)
        args, kwargs = run.call_args
        self.assertEqual(args[0][:5], [str(self.minisign.executable), "-V", "-H", "-q", "-P"])
        self.assertEqual(args[0][5], self.public)
        self.assertEqual(kwargs["stdin"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stdout"], subprocess.DEVNULL)
        self.assertEqual(kwargs["stderr"], subprocess.DEVNULL)

    def test_canonical_metadata_deterministic_and_native_signatures_valid(self):
        # Upstream may randomize Ed25519 signatures. Never replace its algorithm
        # to obtain reproducible signatures; published signature bytes are frozen.
        signature = self.minisign.sign(self.manifest, self.secret, self.public)
        self.minisign.verify(self.manifest, signature, self.public)
        self.assertEqual(D.make_manifest(self.metadata_path, self.archive_path, root_version=1), self.manifest)

    def test_signing_rejects_invalid_protocol_before_key_use(self):
        with mock.patch.object(D.subprocess, "run") as run:
            with self.assertRaises(D.DistributionError):
                self.minisign.sign(b"{}\n", self.secret, self.public)
            run.assert_not_called()

    def test_signing_checks_expected_public_key(self):
        with self.assertRaises(D.DistributionError):
            self.minisign.sign(self.manifest, self.secret, self.keys[1][1])

    def test_no_private_keys_in_repository(self):
        self.assertEqual(self.secret.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.base.stat().st_mode & 0o777, 0o700)
        self.assertFalse(self.secret.is_relative_to(PROJECT))

    def test_initial_root_uses_external_public_key_and_exact_record_pin(self):
        self.assertEqual(self.root.value["public_key"], self.public)
        self.assertEqual(self.root.value["root_version"], 1)

    def test_transport_key_substitution_rejected(self):
        payload = D.make_root(self.keys[1][1], issued_at=ISSUED, expires_at=ROOT_EXPIRES)
        with self.assertRaises(D.DistributionError):
            D.TrustedRoot.initial(self.signed(payload, other=True), pinned_public_key=self.public,
                                  pinned_root_sha256=D.digest(self.root_payload),
                                  minisign=self.minisign, clock=CLOCK)

    def test_transport_root_record_change_rejected_even_with_publisher_signature(self):
        payload = self.changed(self.root_payload, channel_floors={"stable": 2, "candidate": 2})
        with self.assertRaises(D.DistributionError):
            D.TrustedRoot.initial(self.signed(payload), pinned_public_key=self.public,
                                  pinned_root_sha256=D.digest(self.root_payload),
                                  minisign=self.minisign, clock=CLOCK)

    def test_no_automatic_root_rotation_in_phase_one(self):
        payload = self.changed(self.root_payload, root_version=2,
                               previous_root_sha256=D.digest(self.root_payload))
        with self.assertRaises(D.DistributionError):
            D.TrustedRoot.initial(self.signed(payload), pinned_public_key=self.public,
                                  pinned_root_sha256=D.digest(payload), minisign=self.minisign, clock=CLOCK)

    def test_full_key_fingerprint(self):
        self.assertEqual(D.public_key_id(self.public), D.digest(base64.b64decode(self.public)))
        for value in ("", self.public[:-1], "x" * 56, True):
            with self.subTest(value=value), self.assertRaises(D.DistributionError):
                D.public_key_id(value)

    def test_expired_initial_root_rejected(self):
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            D.TrustedRoot.initial(self.root_envelope, pinned_public_key=self.public,
                                  pinned_root_sha256=D.digest(self.root_payload),
                                  minisign=self.minisign,
                                  clock=D.Clock(D.timestamp(ROOT_EXPIRES), 90 * 86400))

    def test_invalid_root_predecessor_and_channel_floors(self):
        for changes in ({"previous_root_sha256": "0" * 64},
                        {"root_version": 2, "previous_root_sha256": None},
                        {"channel_floors": {"stable": 1}},
                        {"channel_floors": {"stable": 0, "candidate": 1}}):
            self.reject(self.changed(self.root_payload, **changes))

    def test_noncanonical_encodings_rejected(self):
        value = json.loads(self.manifest)
        for data in (self.manifest.rstrip(), b" " + self.manifest,
                     json.dumps(value, indent=2).encode(), b"\xef\xbb\xbf" + self.manifest,
                     self.manifest.replace(b"vanilla", b"\\u0076anilla", 1)):
            with self.subTest(data=data[:35]):
                self.reject(data)

    def test_duplicate_keys_at_any_depth_rejected(self):
        for data in (self.manifest.replace(b'"schema":1', b'"schema":1,"schema":1', 1),
                     self.manifest.replace(b'"length":', b'"length":1,"length":', 1)):
            self.reject(data)

    def test_unknown_fields_at_every_schema_boundary(self):
        for original in (self.root_payload, self.manifest, self.catalog_payload()):
            self.reject(self.changed(original, extra=True))
        value = json.loads(self.manifest)
        for path in ("release", "release_json", "archive"):
            changed = copy.deepcopy(value)
            changed[path]["extra"] = True
            self.reject(D.canonical(changed))
        entry = copy.deepcopy(self.entry)
        entry["extra"] = 1
        with self.assertRaises(D.DistributionError):
            D.make_catalog("candidate", 1, [entry], root_version=1, issued_at=ISSUED, expires_at=EXPIRES)

    def test_unknown_schema_protocol_project_and_kind_rejected(self):
        for original in (self.root_payload, self.manifest, self.catalog_payload()):
            for changes in ({"schema": 2}, {"schema": True}, {"distribution_protocol": 2},
                            {"distribution_protocol": True}, {"project": "other"}, {"kind": "other"}):
                self.reject(self.changed(original, **changes))

    def test_missing_fields_and_mixed_objects_rejected(self):
        for original in (self.root_payload, self.manifest, self.catalog_payload()):
            value = json.loads(original)
            for key in value:
                changed = dict(value)
                del changed[key]
                self.reject(D.canonical(changed))
            self.reject(original[:len(original) // 2])
            self.reject(original + self.manifest)
        self.reject(self.changed(self.manifest, kind="catalog"))

    def test_metadata_sizes_and_recursion_bounded(self):
        for data in (b" " * (D.MAX_CATALOG + 1), b'[' * 2000 + b']' * 2000):
            self.reject(data)
        with self.assertRaises(D.DistributionError):
            D.verify_catalog(b" " * (D.MAX_ENVELOPE + 1), self.root, channel="candidate",
                             state=self.state, minisign=self.minisign, clock=CLOCK)

    def test_nonfinite_numbers_booleans_and_counter_bounds(self):
        self.reject(self.catalog_payload().replace(b'"sequence":1', b'"sequence":NaN'))
        for field in ("sequence", "root_version"):
            for value in (True, False, 1.0, "1", 0, -1, D.MAX_COUNTER + 1):
                self.reject(self.changed(self.catalog_payload(), **{field: value}))

    def test_unsafe_paths_and_urls_rejected(self):
        for path in ("../release.json", "/assets/release.json", "assets//release.json",
                     "assets/./release.json", "assets/../release.json", "assets\\release.json",
                     "https://example.invalid/release.json", "assets/release.json?key=value"):
            value = json.loads(self.manifest)
            value["release_json"]["path"] = path
            self.reject(D.canonical(value))
            value = json.loads(self.catalog_payload())
            value["releases"][0]["manifest"]["path"] = path
            self.reject(D.canonical(value))

    def test_descriptor_types_hashes_lengths_and_bounds(self):
        for changes in ({"length": True}, {"length": 0}, {"length": D.MAX_MANIFEST + 1},
                        {"sha256": "A" * 64}, {"sha256": "x"}, {"extra": 1}):
            value = json.loads(self.catalog_payload())
            value["releases"][0]["manifest"].update(changes)
            self.reject(D.canonical(value))

    def test_invalid_product_identity_rejected(self):
        for changes in ({"version": "v01.0.0-rc1"}, {"channel": "stable"},
                        {"architecture": "aarch64"}, {"update_protocol": 2},
                        {"commit": "bad"}, {"migration_level": -1}, {"summary": "bad\n"},
                        {"extra": 1}):
            value = json.loads(self.manifest)
            value["release"].update(changes)
            self.reject(D.canonical(value))

    def test_manifest_archive_descriptor_must_equal_generated_identity(self):
        for changes in ({"length": 1}, {"sha256": "0" * 64}, {"path": "assets/other.tar.gz"}):
            value = json.loads(self.manifest)
            value["archive"].update(changes)
            self.reject(D.canonical(value))

    def test_manifest_generation_uses_existing_release_verifier(self):
        self.assertEqual(D.make_manifest(self.metadata_path, self.archive_path, root_version=1), self.manifest)
        self.assertEqual(json.loads(self.manifest)["release"], self.identity)

    def test_correct_release_authentication_and_archive_verification(self):
        authenticated = self.verify_release()
        self.assertEqual(authenticated, self.identity)
        D.verify_artifact(authenticated, self.metadata_path, self.archive_path)

    def test_artifact_wrong_hash_and_length_rejected(self):
        archive = self.work / self.archive_path.name
        for data in (self.archive_path.read_bytes()[:-1], b"x" * self.archive_path.stat().st_size):
            archive.write_bytes(data)
            with self.assertRaises(D.DistributionError):
                D.verify_artifact(self.identity, self.metadata_path, archive)

    def test_artifact_verification_requires_exact_canonical_metadata_bytes(self):
        metadata = self.work / "release.json"
        metadata.write_bytes(json.dumps(self.identity, indent=2).encode())
        with self.assertRaises(D.DistributionError):
            D.verify_artifact(self.identity, metadata, self.archive_path)

    def test_wrong_release_json_hash_or_length_rejected(self):
        for metadata in (self.metadata[:-1], self.metadata.replace(b"First", b"Other")):
            with self.assertRaises(D.DistributionError):
                self.verify_release(metadata=metadata)

    def test_signed_but_incorrect_release_json_descriptor_rejected(self):
        value = json.loads(self.manifest)
        value["release_json"]["sha256"] = "0" * 64
        manifest = D.canonical(value)
        signature = self.minisign.sign(manifest, self.secret, self.public)
        catalog = self.verified(self.catalog_payload(entries=[D.catalog_entry(manifest, signature)]))
        with self.assertRaises(D.DistributionError):
            self.verify_release(manifest=manifest, signature=signature, catalog=catalog)

    def test_catalog_hash_binding_rejects_mixed_manifest_or_signature(self):
        other = self.minisign.sign(self.manifest, self.keys[1][0], self.keys[1][1])
        for changes in ({"manifest": self.changed(self.manifest, root_version=2)}, {"signature": other}):
            with self.assertRaises(D.DistributionError):
                self.verify_release(**changes)

    def test_wrong_manifest_signer_rejected_even_when_catalog_binds_signature(self):
        signature = self.minisign.sign(self.manifest, self.keys[1][0], self.keys[1][1])
        catalog = self.verified(self.catalog_payload(entries=[D.catalog_entry(self.manifest, signature)]))
        with self.assertRaises(D.DistributionError):
            self.verify_release(signature=signature, catalog=catalog)

    def test_manifest_and_catalog_root_versions_must_match_trust(self):
        with self.assertRaisesRegex(D.DistributionError, "root"):
            self.verified(self.catalog_payload(root_version=2))
        manifest = self.changed(self.manifest, root_version=2)
        signature = self.minisign.sign(manifest, self.secret, self.public)
        catalog = self.verified(self.catalog_payload(entries=[D.catalog_entry(manifest, signature)]))
        with self.assertRaises(D.DistributionError):
            self.verify_release(manifest=manifest, signature=signature, catalog=catalog)

    def test_catalog_version_cannot_relabel_manifest(self):
        entry = self.version_entry("v1.0.0-rc2")
        catalog = self.verified(self.catalog_payload(entries=[entry]))
        with self.assertRaisesRegex(D.DistributionError, "identity mismatch"):
            self.verify_release(version="v1.0.0-rc2", catalog=catalog)

    def test_inconsistent_identity_rejected_even_if_metadata_digest_is_signed(self):
        value = json.loads(self.manifest)
        value["release"]["summary"] = "Different signed identity"
        manifest = D.canonical(value)
        signature = self.minisign.sign(manifest, self.secret, self.public)
        catalog = self.verified(self.catalog_payload(entries=[D.catalog_entry(manifest, signature)]))
        with self.assertRaisesRegex(D.DistributionError, "identity mismatch"):
            self.verify_release(manifest=manifest, signature=signature, catalog=catalog)

    def test_release_must_belong_to_signed_catalog(self):
        with self.assertRaises(D.DistributionError):
            self.verify_release(version="v1.0.1")

    def test_unsigned_or_wrong_key_catalog_rejected(self):
        for data in (self.catalog_payload(), self.signed(self.catalog_payload(), other=True)):
            with self.assertRaises(D.DistributionError):
                D.verify_catalog(data, self.root, channel="candidate", state=self.state,
                                 minisign=self.minisign, clock=CLOCK)

    def test_catalog_tampering_rejected(self):
        value = json.loads(self.signed(self.catalog_payload()))
        value["payload"] = base64.b64encode(self.catalog_payload(sequence=2)).decode()
        with self.assertRaises(D.DistributionError):
            D.verify_catalog(D.canonical(value), self.root, channel="candidate", state=self.state,
                             minisign=self.minisign, clock=CLOCK)

    def test_channel_substitution_rejected(self):
        with self.assertRaises(D.DistributionError):
            self.verified(channel="stable")

    def test_stable_catalog_cannot_contain_candidate(self):
        self.reject(self.changed(self.catalog_payload(), channel="stable"))

    def test_duplicate_unsorted_and_excessive_catalog_entries(self):
        value = json.loads(self.catalog_payload())
        for entries in ([self.entry, self.entry], [self.entry] * (D.MAX_RELEASES + 1)):
            value["releases"] = entries
            self.reject(D.canonical(value))
        second = self.version_entry("v1.0.1-rc1")
        value["releases"] = [second, self.entry]
        self.reject(D.canonical(value))

    def version_entry(self, version):
        entry = copy.deepcopy(self.entry)
        entry["version"] = version
        for name, suffix in (("manifest", ""), ("signature", ".sig")):
            entry[name]["path"] = f"releases/{version}/manifest.json{suffix}"
        return entry

    def test_stable_selection_and_no_candidate_opt_in(self):
        installed = copy.deepcopy(self.identity)
        installed.update(version="v1.0.0", channel="stable")
        installed["artifact"]["name"] = D.contract.artifact_name("v1.0.0")
        catalog = self.verified(self.catalog_payload("stable", entries=[self.version_entry("v1.0.1")]),
                                channel="stable")
        self.assertEqual(D.select_release(catalog, installed, clock=CLOCK), "v1.0.1")
        with self.assertRaises(D.DistributionError):
            D.select_release(self.verified(), installed, clock=CLOCK)

    def test_candidate_selection_stays_in_product_version_and_allows_final(self):
        entries = [self.version_entry(v) for v in ("v1.0.0-rc2", "v1.0.0", "v1.0.1-rc1")]
        catalog = self.verified(self.catalog_payload(entries=entries))
        self.assertEqual(D.select_release(catalog, self.identity, clock=CLOCK), "v1.0.0")

    def test_no_eligible_release_returns_none(self):
        self.assertIsNone(D.select_release(self.verified(), self.identity, clock=CLOCK))

    def test_release_compatibility_preserves_version_and_migration_guards(self):
        target = copy.deepcopy(self.identity)
        target["version"] = "v1.0.0-rc2"
        target["artifact"]["name"] = D.contract.artifact_name(target["version"])
        D.compatible_release(self.identity, target)
        for changes in ({"minimum_installed_version": "v1.0.0-rc2"},
                        {"minimum_migration_level": 1, "migration_level": 1},
                        {"architecture": "aarch64"}):
            altered = copy.deepcopy(target)
            altered.update(changes)
            with self.assertRaises(D.DistributionError):
                D.compatible_release(self.identity, altered)
        with self.assertRaises(D.DistributionError):
            D.compatible_release(self.identity, self.identity)

    def test_stable_to_candidate_and_migration_downgrade_rejected(self):
        installed = copy.deepcopy(self.identity)
        installed.update(version="v0.9.0", channel="stable", migration_level=1)
        installed["artifact"]["name"] = D.contract.artifact_name(installed["version"])
        with self.assertRaises(D.DistributionError):
            D.compatible_release(installed, self.identity)
        target = copy.deepcopy(self.identity)
        target.update(version="v1.0.0", channel="stable")
        target["artifact"]["name"] = D.contract.artifact_name(target["version"])
        with self.assertRaisesRegex(D.DistributionError, "migration"):
            D.compatible_release(installed, target)

    def test_sequence_rollback_rejected_before_selection(self):
        accepted = self.verified(self.catalog_payload(sequence=2))
        with self.assertRaisesRegex(D.DistributionError, "rollback"):
            self.verified(state=accepted.proposed_state)

    def test_same_sequence_identical_payload_is_idempotent(self):
        accepted = self.verified()
        again = self.verified(state=accepted.proposed_state)
        self.assertEqual(accepted.proposed_state, again.proposed_state)

    def test_same_sequence_equivocation_rejected(self):
        accepted = self.verified()
        with self.assertRaisesRegex(D.DistributionError, "equivocation"):
            self.verified(self.catalog_payload(entries=[]), state=accepted.proposed_state)

    def test_immutable_binding_change_at_higher_sequence_rejected(self):
        accepted = self.verified()
        entry = copy.deepcopy(self.entry)
        entry["manifest"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(D.DistributionError, "immutable"):
            self.verified(self.catalog_payload(sequence=2, entries=[entry]), state=accepted.proposed_state)

    def test_immutable_release_signature_cannot_be_replaced(self):
        accepted = self.verified()
        signature = self.signature.replace(b"untrusted comment:", b"untrusted comment: changed", 1)
        entry = D.catalog_entry(self.manifest, signature)
        with self.assertRaisesRegex(D.DistributionError, "immutable"):
            self.verified(self.catalog_payload(sequence=2, entries=[entry]), state=accepted.proposed_state)

    def test_bindings_survive_catalog_pruning(self):
        accepted = self.verified()
        pruned = self.verified(self.catalog_payload(sequence=2, entries=[]), state=accepted.proposed_state)
        self.assertIn(self.identity["version"], D.parse_state(pruned.proposed_state)["bindings"])

    def test_channels_have_independent_sequence_floors_and_shared_bindings(self):
        accepted = self.verified(self.catalog_payload(sequence=5))
        stable = self.verified(self.catalog_payload("stable", entries=[]), channel="stable",
                               state=accepted.proposed_state)
        self.assertEqual(D.parse_state(stable.proposed_state)["channels"]["candidate"]["sequence"], 5)

    def test_conflicting_bindings_across_channels_rejected(self):
        entry = self.version_entry("v1.0.0")
        accepted = self.verified(self.catalog_payload(entries=[entry]))
        changed = copy.deepcopy(entry)
        changed["manifest"]["sha256"] = "0" * 64
        with self.assertRaisesRegex(D.DistributionError, "immutable"):
            self.verified(self.catalog_payload("stable", entries=[changed]), channel="stable",
                          state=accepted.proposed_state)

    def test_root_sequence_floor_applies_to_initial_fetch(self):
        payload = D.make_root(self.public, issued_at=ISSUED, expires_at=ROOT_EXPIRES, candidate_floor=2)
        root = D.TrustedRoot.initial(self.signed(payload), pinned_public_key=self.public,
                                    pinned_root_sha256=D.digest(payload), minisign=self.minisign, clock=CLOCK)
        with self.assertRaisesRegex(D.DistributionError, "floor"):
            D.verify_catalog(self.signed(self.catalog_payload()), root, channel="candidate",
                             state=D.initial_state(root), minisign=self.minisign, clock=CLOCK)

    def test_clock_rollback_rejected(self):
        accepted = self.verified()
        clock = D.Clock(CLOCK.now - 1, CLOCK.maximum_catalog_lifetime)
        with self.assertRaisesRegex(D.DistributionError, "clock rollback"):
            self.verified(state=accepted.proposed_state, clock=clock)
        with self.assertRaisesRegex(D.DistributionError, "clock rollback"):
            D.select_release(accepted, self.identity, clock=clock)

    def test_expired_catalog_rejected_at_exact_boundary(self):
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.verified(clock=D.Clock(D.timestamp(EXPIRES), 90 * 86400))

    def test_expired_root_rejected(self):
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.verified(clock=D.Clock(D.timestamp(ROOT_EXPIRES), 90 * 86400))

    def test_future_issuance_and_excessive_lifetime_rejected(self):
        for payload in (self.catalog_payload(issued_at="2026-01-03T00:00:00Z"),
                        self.catalog_payload(expires_at="2027-01-01T00:00:01Z")):
            with self.assertRaises(D.DistributionError):
                self.verified(payload)

    def test_stricter_local_catalog_policy_remains_supported(self):
        payload = self.catalog_payload(expires_at="2026-03-01T00:00:00Z")
        with self.assertRaises(D.DistributionError):
            self.verified(payload, clock=D.Clock(CLOCK.now, 30 * 86400))
        for days in (90, 180):
            self.verified(payload, clock=D.Clock(CLOCK.now, days * 86400))

    def test_skew_cannot_extend_expired_metadata_or_move_high_water_backward(self):
        accepted = self.verified()
        slight_rollback = D.Clock(CLOCK.now - 10, 90 * 86400, 30)
        again = self.verified(state=accepted.proposed_state, clock=slight_rollback)
        self.assertEqual(D.parse_state(again.proposed_state)["clock_high_water"], CLOCK.now)
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.verified(clock=D.Clock(D.timestamp(EXPIRES), 90 * 86400, 300))

    def test_clock_policy_itself_is_validated(self):
        for clock in (D.Clock(True, 90 * 86400), D.Clock(CLOCK.now, 0),
                      D.Clock(CLOCK.now, 90 * 86400, 301), D.Clock(CLOCK.now, 90 * 86400, -1),
                      D.Clock(CLOCK.now, D.MAX_CATALOG_LIFETIME + 1)):
            with self.assertRaises(D.DistributionError):
                self.verified(clock=clock)

    def test_default_catalog_lifetime_is_exactly_365_days_for_both_channels(self):
        self.assertEqual(D.DEFAULT_CATALOG_LIFETIME, 31536000)
        self.assertEqual(D.MAX_CATALOG_LIFETIME, 31536000)
        self.assertEqual(CLOCK.maximum_catalog_lifetime, 31536000)
        for channel in ("stable", "candidate"):
            with self.subTest(channel=channel):
                payload = D.make_catalog(channel, 1, [], root_version=1, issued_at=ISSUED)
                value = D.validate_object(payload)
                self.assertEqual(value["expires_at"], "2027-01-01T00:00:00Z")
                self.assertEqual(D.timestamp(value["expires_at"]) - D.timestamp(ISSUED), 31536000)
                self.verified(payload, channel=channel)

    def test_explicit_shorter_catalog_validities_for_both_channels(self):
        for channel in ("stable", "candidate"):
            for days, expiry in ((30, "2026-01-31T00:00:00Z"),
                                 (90, "2026-04-01T00:00:00Z"),
                                 (180, "2026-06-30T00:00:00Z")):
                with self.subTest(channel=channel, days=days):
                    payload = D.make_catalog(channel, 1, [], root_version=1,
                                             issued_at=ISSUED, expires_at=expiry)
                    value = D.validate_object(payload)
                    self.assertEqual(D.timestamp(value["expires_at"]) - D.timestamp(ISSUED), days * 86400)
                    self.verified(payload, channel=channel)

    def test_exact_lifetime_limit_accepted_and_expiry_is_exclusive(self):
        payload = D.make_catalog("candidate", 1, [], root_version=1, issued_at=ISSUED,
                                 expires_at="2027-01-01T00:00:00Z")
        expiry = D.timestamp("2027-01-01T00:00:00Z")
        self.verified(payload, clock=D.Clock(expiry - 1))
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.verified(payload, clock=D.Clock(expiry))

    def test_lifetime_above_365_days_rejected_by_parser_publisher_and_client(self):
        for channel in ("stable", "candidate"):
            with self.subTest(channel=channel):
                valid = D.make_catalog(channel, 1, [], root_version=1, issued_at=ISSUED)
                invalid = self.changed(valid, expires_at="2027-01-01T00:00:01Z")
                self.reject(invalid)
                with self.assertRaisesRegex(D.DistributionError, "protocol maximum"):
                    D.make_catalog(channel, 1, [], root_version=1, issued_at=ISSUED,
                                   expires_at="2027-01-01T00:00:01Z")
                # Model a transport-delivered object without the publisher's guard.
                envelope = json.loads(self.signed(valid))
                envelope["payload"] = base64.b64encode(invalid).decode("ascii")
                with self.assertRaisesRegex(D.DistributionError, "protocol maximum"):
                    D.verify_catalog(D.canonical(envelope), self.root, channel=channel,
                                     state=self.state, minisign=self.minisign, clock=CLOCK)

    def test_renewal_without_new_release_requires_and_accepts_higher_sequence(self):
        for channel in ("stable", "candidate"):
            with self.subTest(channel=channel):
                first = D.make_catalog(channel, 1, [], root_version=1, issued_at=ISSUED)
                accepted = self.verified(first, channel=channel)
                renewal = D.make_catalog(channel, 2, [], root_version=1,
                                         issued_at="2026-01-02T00:00:00Z")
                renewed = self.verified(renewal, channel=channel, state=accepted.proposed_state)
                self.assertEqual(renewed.value["expires_at"], "2027-01-02T00:00:00Z")
                self.assertEqual(renewed.value["releases"], accepted.value["releases"])
                self.assertEqual(D.parse_state(renewed.proposed_state)["channels"][channel]["sequence"], 2)
                with self.assertRaisesRegex(D.DistributionError, "sequence rollback"):
                    self.verified(first, channel=channel, state=renewed.proposed_state)

    def test_same_sequence_expiration_renewal_is_equivocation_for_both_channels(self):
        for channel in ("stable", "candidate"):
            with self.subTest(channel=channel):
                first = D.make_catalog(channel, 1, [], root_version=1, issued_at=ISSUED)
                accepted = self.verified(first, channel=channel)
                renewal = D.make_catalog(channel, 1, [], root_version=1,
                                         issued_at="2026-01-02T00:00:00Z")
                with self.assertRaisesRegex(D.DistributionError, "equivocation"):
                    self.verified(renewal, channel=channel, state=accepted.proposed_state)

    def test_shortening_does_not_retroactively_revoke_unobserved_catalog(self):
        original = D.make_catalog("candidate", 1, [], root_version=1, issued_at=ISSUED)
        accepted = self.verified(original)
        shortened = D.make_catalog("candidate", 2, [], root_version=1, issued_at=ISSUED,
                                   expires_at="2026-01-31T00:00:00Z")
        updated = self.verified(shortened, state=accepted.proposed_state)
        later = D.Clock(D.timestamp("2026-02-02T00:00:00Z"))
        # A client that has not seen sequence 2 can still accept sequence 1.
        self.verified(original, state=accepted.proposed_state, clock=later)
        with self.assertRaisesRegex(D.DistributionError, "sequence rollback"):
            self.verified(original, state=updated.proposed_state, clock=later)
        with self.assertRaisesRegex(D.DistributionError, "expired"):
            self.verified(shortened, state=updated.proposed_state, clock=later)

    def test_default_expiry_uses_elapsed_seconds_across_leap_days(self):
        payload = D.make_catalog("candidate", 1, [], root_version=1,
                                 issued_at="2028-02-29T12:34:56Z")
        self.assertEqual(D.validate_object(payload)["expires_at"], "2029-02-28T12:34:56Z")

    def test_default_expiry_overflow_fails_closed(self):
        with self.assertRaises(D.DistributionError):
            D.make_catalog("candidate", 1, [], root_version=1, issued_at="9999-12-31T00:00:00Z")

    def test_root_lifetime_remains_explicit_and_independent(self):
        root = self.root.value
        self.assertGreater(D.timestamp(root["expires_at"]) - D.timestamp(root["issued_at"]),
                           D.MAX_CATALOG_LIFETIME)
        CLOCK.validate(root)
        with self.assertRaises(TypeError):
            D.make_root(self.public, issued_at=ISSUED)

    def test_clock_rollback_rejected_after_365_day_catalog_acceptance(self):
        payload = D.make_catalog("candidate", 1, [], root_version=1, issued_at=ISSUED)
        accepted = self.verified(payload)
        with self.assertRaisesRegex(D.DistributionError, "clock rollback"):
            self.verified(payload, state=accepted.proposed_state, clock=D.Clock(CLOCK.now - 1))

    def test_invalid_timestamps_and_intervals(self):
        for issued in ("2026-02-30T00:00:00Z", "2026-01-01T00:00:00+00:00", "2026-01-01", 1):
            self.reject(self.catalog_payload(issued_at=issued))
        self.reject(self.catalog_payload(issued_at=EXPIRES))

    def test_expiry_rechecked_before_release_use(self):
        with self.assertRaises(D.DistributionError):
            self.verify_release(catalog=self.verified(), clock=D.Clock(D.timestamp(EXPIRES), 90 * 86400))

    def test_state_has_no_write_side_effect_and_rejects_partial_serialization(self):
        original = self.state
        accepted = self.verified()
        self.assertEqual(self.state, original)
        self.assertNotEqual(accepted.proposed_state, original)
        for data in (b"", accepted.proposed_state[:-1], accepted.proposed_state[:30]):
            with self.assertRaises(D.DistributionError):
                D.parse_state(data)

    def test_corrupt_or_unknown_state_never_reinitialized(self):
        for data in (b"{}\n", self.changed(self.state, extra=1), self.changed(self.state, root_sha256="0" * 64)):
            with self.assertRaises(D.DistributionError):
                self.verified(state=data)

    def test_state_rejects_invalid_counters_bindings_and_unknown_channels(self):
        accepted = D.parse_state(self.verified().proposed_state)
        for changes in ({"clock_high_water": True}, {"root_version": 0},
                        {"channels": {"other": {"sequence": 1, "sha256": "0" * 64}}},
                        {"channels": {"candidate": {"sequence": 0, "sha256": "0" * 64}}},
                        {"bindings": {"v1.0.0": self.entry}}):
            value = dict(accepted)
            value.update(changes)
            with self.assertRaises(D.DistributionError):
                D.parse_state(D.canonical(value))

    def test_public_properties_cannot_mutate_authenticated_payload(self):
        catalog = self.verified()
        view = catalog.value
        view["sequence"] = 0
        view["releases"].clear()
        self.assertEqual(catalog.value["sequence"], 1)
        self.assertEqual(catalog.value["releases"], [self.entry])
        root = self.root.value
        root["public_key"] = self.keys[1][1]
        self.assertEqual(self.root.value["public_key"], self.public)

    def test_authenticated_catalog_bound_to_exact_trust_root(self):
        payload = D.make_root(self.public, issued_at=ISSUED, expires_at=ROOT_EXPIRES, stable_floor=2)
        root = D.TrustedRoot.initial(self.signed(payload), pinned_public_key=self.public,
                                    pinned_root_sha256=D.digest(payload), minisign=self.minisign, clock=CLOCK)
        with self.assertRaises(D.DistributionError):
            self.verify_release(catalog=self.verified(), root=root)

    def test_envelope_unknown_fields_duplicates_and_bad_payload_encoding(self):
        original = json.loads(self.root_envelope)
        for changes in ({"extra": 1}, {"schema": True}, {"payload": "!!!"},
                        {"signatures": []}, {"signatures": original["signatures"] * 2}):
            value = dict(original)
            value.update(changes)
            with self.assertRaises(D.DistributionError):
                D.TrustedRoot.initial(D.canonical(value), pinned_public_key=self.public,
                                      pinned_root_sha256=D.digest(self.root_payload),
                                      minisign=self.minisign, clock=CLOCK)

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "release.distribution", "--minisign",
                               str(self.minisign.executable), *map(str, arguments)],
                              cwd=PROJECT, capture_output=True, text=True)

    def test_local_cli_builds_manifest_without_mutating_originals(self):
        output = self.work / "manifest.json"
        result = self.cli("manifest", "--metadata", self.metadata_path, "--archive", self.archive_path,
                          "--root-version", "1", "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.assertEqual(output.read_bytes(), self.manifest)
        self.assertEqual(self.metadata_path.read_bytes(), self.metadata)
        again = self.cli("manifest", "--metadata", self.metadata_path, "--archive", self.archive_path,
                         "--root-version", "1", "--output", output)
        self.assertNotEqual(again.returncode, 0)
        self.assertEqual(output.read_bytes(), self.manifest)

    def test_local_cli_signs_and_verifies_without_private_output(self):
        source, output = self.work / "manifest", self.work / "signature"
        source.write_bytes(self.manifest)
        result = self.cli("sign", "--input", source, "--secret-key", self.secret,
                          "--public-key", self.public, "--output", output)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")
        self.minisign.verify(self.manifest, output.read_bytes(), self.public)

    def test_local_cli_root_catalog_and_envelope(self):
        root, manifest, signature = self.work / "root", self.work / "manifest", self.work / "signature"
        result = self.cli("root", "--public-key", self.public, "--issued-at", ISSUED,
                          "--expires-at", ROOT_EXPIRES, "--output", root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(root.read_bytes(), self.root_payload)
        manifest.write_bytes(self.manifest)
        signature.write_bytes(self.signature)
        catalog, signed = self.work / "catalog", self.work / "signed"
        result = self.cli("catalog", "--channel", "candidate", "--sequence", "1",
                          "--root-version", "1", "--issued-at", ISSUED, "--expires-at", EXPIRES,
                          "--release", manifest, signature, "--output", catalog)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(catalog.read_bytes(), self.catalog_payload())
        result = self.cli("sign", "--input", catalog, "--secret-key", self.secret,
                          "--public-key", self.public, "--envelope", "--output", signed)
        self.assertEqual(result.returncode, 0, result.stderr)
        D.verify_catalog(signed.read_bytes(), self.root, channel="candidate", state=self.state,
                         minisign=self.minisign, clock=CLOCK)

    def test_local_cli_catalog_defaults_to_365_days_and_rejects_longer_interval(self):
        for channel in ("stable", "candidate"):
            output = self.work / channel
            args = ["catalog", "--channel", channel, "--sequence", "1", "--root-version", "1",
                    "--issued-at", ISSUED, "--output", output]
            result = self.cli(*args)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(D.validate_object(output.read_bytes())["expires_at"], "2027-01-01T00:00:00Z")
            invalid = self.work / (channel + "-invalid")
            result = self.cli(*args[:-1], invalid, "--expires-at", "2027-01-01T00:00:01Z")
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(invalid.exists())

    def test_local_cli_root_still_requires_explicit_expiration(self):
        output = self.work / "root"
        result = self.cli("root", "--public-key", self.public, "--issued-at", ISSUED, "--output", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("--expires-at", result.stderr)
        self.assertFalse(output.exists())

    def test_local_cli_rejects_incorrect_signing_layout_and_symlinks(self):
        source = self.work / "catalog"
        source.write_bytes(self.catalog_payload())
        output = self.work / "output"
        result = self.cli("sign", "--input", source, "--secret-key", self.secret,
                          "--public-key", self.public, "--output", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        link = self.work / "link"
        link.symlink_to(source)
        result = self.cli("sign", "--input", link, "--secret-key", self.secret,
                          "--public-key", self.public, "--envelope", "--output", output)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
