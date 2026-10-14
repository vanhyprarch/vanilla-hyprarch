#!/usr/bin/python
"""Real libalpm relationship checks against disposable metadata databases."""
from __future__ import annotations

import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("relationships", ROOT / "install/package_relationships.py")
MODULE = importlib.util.module_from_spec(spec)
spec.loader.exec_module(MODULE)


def package(name, version="1-1", **fields):
    return {"NAME": [name], "VERSION": [version], "ARCH": ["x86_64"], **fields}


def description(row):
    return "".join(f"%{key}%\n" + "\n".join(values) + "\n\n" for key, values in row.items()).encode()


class RelationshipTests(unittest.TestCase):
    def check(self, proposed, installed=(), *, transaction=None):
        with tempfile.TemporaryDirectory(prefix="vha-alpm-") as temporary:
            root = Path(temporary)
            db = root / "db"
            local = db / "local"
            local.mkdir(parents=True)
            (local / "ALPM_DB_VERSION").write_text("9\n")
            for row in installed:
                target = local / (row["NAME"][0] + "-" + row["VERSION"][0])
                target.mkdir()
                (target / "desc").write_bytes(description(row))
            (db / "sync").mkdir()
            with tarfile.open(db / "sync/extra.db", "w:gz") as archive:
                for row in proposed:
                    content = description(row)
                    info = tarfile.TarInfo(row["NAME"][0] + "-" + row["VERSION"][0] + "/desc")
                    info.size = len(content)
                    archive.addfile(info, io.BytesIO(content))
            if transaction is None:
                transaction = [[row["NAME"][0], row["VERSION"][0], "extra"] for row in proposed]
            before = {str(path.relative_to(root)): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).digest())
                      for path in root.rglob("*") if path.is_file()}
            try:
                return MODULE.validate(transaction, root=root, dbpath=db)
            finally:
                after = {str(path.relative_to(root)): (path.stat().st_mtime_ns, hashlib.sha256(path.read_bytes()).digest())
                         for path in root.rglob("*") if path.is_file()}
                self.assertEqual(before, after)
                self.assertFalse((db / "db.lck").exists())

    def test_harmless_man_db_virtual_provider_and_complete_dex_chain(self):
        result = self.check([package("libpipeline"), package("less"),
                             package("man-db", PROVIDES=["man"], CONFLICTS=["man"], REPLACES=["man"],
                                     DEPENDS=["libpipeline", "less"]),
                             package("dex", DEPENDS=["man", "python"])], [package("python")])
        self.assertEqual(result, {"safe": True, "packages": ["dex", "less", "libpipeline", "man-db"]})

    def test_installed_alternative_provider_is_preserved(self):
        self.assertTrue(self.check([package("dex", DEPENDS=["man"])],
                                   [package("mandoc", PROVIDES=["man"])])["safe"])

    def test_actual_name_conflict_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "conflicts"):
            self.check([package("new", CONFLICTS=["old"])], [package("old")])

    def test_virtual_provider_conflict_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "conflicts"):
            self.check([package("new", CONFLICTS=["feature"])], [package("old", PROVIDES=["feature"])])

    def test_reverse_installed_conflict_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "conflicts"):
            self.check([package("new", PROVIDES=["feature=2"])], [package("old", CONFLICTS=["feature>=2"])])

    def test_conflict_between_two_planned_packages_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "conflicts"):
            self.check([package("one", CONFLICTS=["feature"]), package("two", PROVIDES=["feature"])])

    def test_replacement_between_planned_packages_is_ambiguous(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "replacement"):
            self.check([package("one", REPLACES=["feature"]), package("two", PROVIDES=["feature"])])

    def test_actual_name_replacement_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "replacement"):
            self.check([package("new", REPLACES=["old"])], [package("old")])

    def test_actual_virtual_provider_replacement_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "replacement"):
            self.check([package("new", REPLACES=["feature>=2"])], [package("old", PROVIDES=["feature=2"])])

    def test_unmatched_versioned_relationships_are_harmless(self):
        self.assertTrue(self.check([package("new", REPLACES=["feature>=3"], CONFLICTS=["feature>=3"])],
                                   [package("old", PROVIDES=["feature=2"])])["safe"])

    def test_versioned_providers_and_unversioned_provider_rules(self):
        self.assertTrue(self.check([package("new", DEPENDS=["feature>=2"])],
                                   [package("old", PROVIDES=["feature=2"])])["safe"])
        with self.assertRaisesRegex(MODULE.RelationshipError, "unresolved"):
            self.check([package("new", DEPENDS=["feature>=2"])], [package("old", PROVIDES=["feature"])])

    def test_epoch_version_comparison_is_upstream(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "conflicts"):
            self.check([package("new", CONFLICTS=["old>99-1"])], [package("old", "1:1-1")])

    def test_all_version_operators_use_upstream_matching(self):
        for expression in ("old=2", "old>=2", "old<=2", "old>1", "old<3"):
            with self.subTest(expression=expression), self.assertRaisesRegex(MODULE.RelationshipError, "conflicts"):
                self.check([package("new", CONFLICTS=[expression])], [package("old", "2-1")])

    def test_reverse_conflict_with_unmatched_version_is_harmless(self):
        self.assertTrue(self.check([package("new", PROVIDES=["feature=2"])],
                                   [package("old", CONFLICTS=["feature>2"])])["safe"])

    def test_installed_package_change_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "installed"):
            self.check([package("old", "2-1")], [package("old")])

    def test_missing_dependency_in_complete_plan_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "unresolved"):
            self.check([package("new", DEPENDS=["missing"])])

    def test_preview_version_mismatch_blocks(self):
        with self.assertRaisesRegex(MODULE.RelationshipError, "differs"):
            self.check([package("new")], transaction=[["new", "2-1", "extra"]])

    def test_wrong_repository_or_missing_package_blocks(self):
        for transaction in ([["new", "1-1", "absent"]], [["absent", "1-1", "extra"]]):
            with self.subTest(transaction=transaction), self.assertRaises(MODULE.RelationshipError):
                self.check([package("new")], transaction=transaction)

    def test_malformed_and_duplicate_preview_block(self):
        for transaction in (None, [], [["new", "1-1"]], [["../new", "1-1", "extra"]],
                            [["new", "1-1", "../extra"]], [["new", "1-1", "extra"]] * 2):
            with self.subTest(transaction=transaction), self.assertRaises(MODULE.RelationshipError):
                MODULE.validate(transaction)

    def test_missing_database_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(MODULE.RelationshipError):
                MODULE.validate([["new", "1-1", "extra"]], root=Path(temporary), dbpath=Path(temporary) / "missing")

    def test_unsupported_library_abi_fails_closed(self):
        fake = mock.Mock()
        fake.alpm_version.return_value = b"17.0.0"
        with mock.patch.object(MODULE.C, "CDLL", return_value=fake):
            with self.assertRaisesRegex(MODULE.RelationshipError, "ABI"):
                MODULE.library()
        fake.alpm_initialize.assert_not_called()

    def test_unavailable_library_fails_closed_cli_without_output_disclosure(self):
        with (mock.patch.object(MODULE, "validate", side_effect=OSError("untrusted diagnostic details")),
              mock.patch.object(MODULE.subprocess, "run", return_value=mock.Mock(stdout="/\n")),
              mock.patch.object(sys, "stdout", new_callable=io.StringIO) as output,
              mock.patch.object(sys, "stderr", new_callable=io.StringIO) as error):
            self.assertEqual(MODULE.main(["--transaction-json", "[]"]), 1)
        self.assertEqual(output.getvalue(), "")
        self.assertNotIn("untrusted", error.getvalue())


if __name__ == "__main__":
    unittest.main()
