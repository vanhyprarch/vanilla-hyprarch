#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only
"""Read-only package relationship validation using pacman's own libalpm.

No transaction is initialized, prepared, committed, or downloaded. Package
objects are read from the databases that pacman-conf selects. Versioned
dependencies, virtual providers, and conflict direction belong to libalpm.
"""

from __future__ import annotations

import argparse
import ctypes as C
import json
from pathlib import Path
import re
import subprocess
import sys


class RelationshipError(ValueError):
    pass


class List(C.Structure):
    pass


ListPointer = C.POINTER(List)
List._fields_ = [("data", C.c_void_p), ("prev", ListPointer), ("next", ListPointer)]


NAME = re.compile(r"[a-z0-9@._+:-]+")
REPOSITORY = re.compile(r"[A-Za-z0-9._+-]+")


def entries(head):
    while head:
        yield head.contents.data
        head = head.contents.next


def library():
    alpm = C.CDLL("/usr/lib/libalpm.so")
    signatures = {
        "alpm_version": (C.c_char_p, []),
        "alpm_initialize": (C.c_void_p, [C.c_char_p, C.c_char_p, C.POINTER(C.c_int)]),
        "alpm_release": (C.c_int, [C.c_void_p]),
        "alpm_errno": (C.c_int, [C.c_void_p]),
        "alpm_get_localdb": (C.c_void_p, [C.c_void_p]),
        "alpm_register_syncdb": (C.c_void_p, [C.c_void_p, C.c_char_p, C.c_int]),
        "alpm_db_get_valid": (C.c_int, [C.c_void_p]),
        "alpm_db_get_pkgcache": (ListPointer, [C.c_void_p]),
        "alpm_db_get_pkg": (C.c_void_p, [C.c_void_p, C.c_char_p]),
        "alpm_pkg_get_version": (C.c_char_p, [C.c_void_p]),
        "alpm_pkg_get_replaces": (ListPointer, [C.c_void_p]),
        "alpm_pkg_get_conflicts": (ListPointer, [C.c_void_p]),
        "alpm_dep_compute_string": (C.c_void_p, [C.c_void_p]),
        "alpm_find_satisfier": (C.c_void_p, [ListPointer, C.c_char_p]),
        "alpm_checkdeps": (ListPointer, [C.c_void_p, ListPointer, ListPointer, ListPointer, C.c_int]),
        "alpm_depmissing_free": (None, [C.c_void_p]),
        "alpm_list_add": (ListPointer, [ListPointer, C.c_void_p]),
        "alpm_list_free": (None, [ListPointer]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(alpm, name)
        function.restype, function.argtypes = result, arguments
    if alpm.alpm_version().split(b".")[0] != b"16":
        raise RelationshipError("unsupported libalpm ABI; review before provisioning")
    return alpm


def validate(transaction, *, root=Path("/"), dbpath=Path("/var/lib/pacman")):
    if (not isinstance(transaction, list) or not 0 < len(transaction) <= 2048
            or any(not isinstance(row, list) or len(row) != 3
                   or any(not isinstance(value, str) or not value or len(value) > 256
                          or any(ord(c) <= 32 for c in value) for value in row)
                   or not NAME.fullmatch(row[0]) or not REPOSITORY.fullmatch(row[2])
                   for row in transaction)
            or len({row[0] for row in transaction}) != len(transaction)):
        raise RelationshipError("ambiguous package transaction")
    if any(not path.is_absolute() or ".." in path.parts for path in (root, dbpath)):
        raise RelationshipError("ambiguous pacman database context")
    alpm = library()
    libc = C.CDLL("libc.so.6")
    libc.free.argtypes = [C.c_void_p]
    libc.free.restype = None
    error = C.c_int()
    handle = alpm.alpm_initialize(bytes(root), bytes(dbpath), C.byref(error))
    if not handle:
        raise RelationshipError("pacman databases are unavailable")
    additions = ListPointer()
    try:
        local = alpm.alpm_get_localdb(handle)
        if not local or alpm.alpm_db_get_valid(local) != 0:
            raise RelationshipError("pacman local database is invalid")
        installed = alpm.alpm_db_get_pkgcache(local)
        if alpm.alpm_errno(handle):
            raise RelationshipError("pacman local database cannot be inspected")
        installed_packages = list(entries(installed))
        databases = {}
        names = {row[0] for row in transaction}
        for name, version, repository in transaction:
            if alpm.alpm_db_get_pkg(local, name.encode()):
                raise RelationshipError("transaction would change an installed package")
            if repository not in databases:
                database = alpm.alpm_register_syncdb(handle, repository.encode(), 0)
                if not database or alpm.alpm_db_get_valid(database) != 0:
                    raise RelationshipError("pacman sync database is invalid")
                databases[repository] = database
            package = alpm.alpm_db_get_pkg(databases[repository], name.encode())
            if not package or alpm.alpm_pkg_get_version(package).decode() != version:
                raise RelationshipError("package preview differs from current databases")
            additions = alpm.alpm_list_add(additions, package)
            if not additions:
                raise RelationshipError("package list allocation failed")

        def matches(dependencies, targets):
            for dependency in entries(dependencies):
                expression = alpm.alpm_dep_compute_string(dependency)
                if not expression:
                    raise RelationshipError("package relationship cannot be inspected")
                try:
                    if alpm.alpm_find_satisfier(targets, C.string_at(expression)):
                        return True
                finally:
                    libc.free(expression)
            return False

        planned = list(entries(additions))
        for package in planned:
            others = ListPointer()
            try:
                for target in [*installed_packages, *planned]:
                    if target != package:
                        others = alpm.alpm_list_add(others, target)
                        if not others:
                            raise RelationshipError("package list allocation failed")
                if matches(alpm.alpm_pkg_get_conflicts(package), others):
                    raise RelationshipError("transaction contains package conflicts or replacements")
                if matches(alpm.alpm_pkg_get_replaces(package), others):
                    raise RelationshipError("transaction declares a package replacement")
            finally:
                alpm.alpm_list_free(others)
        # The installed package may be the side declaring the conflict.
        for package in installed_packages:
            if matches(alpm.alpm_pkg_get_conflicts(package), additions):
                raise RelationshipError("transaction contains reverse package conflicts")
        missing = alpm.alpm_checkdeps(handle, installed, ListPointer(), additions, 1)
        if alpm.alpm_errno(handle):
            raise RelationshipError("package dependencies cannot be inspected")
        try:
            if missing:
                raise RelationshipError("package transaction has unresolved dependencies")
        finally:
            for pointer in entries(missing):
                alpm.alpm_depmissing_free(pointer)
            alpm.alpm_list_free(missing)
        return {"safe": True, "packages": sorted(names)}
    finally:
        alpm.alpm_list_free(additions)
        alpm.alpm_release(handle)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transaction-json", required=True)
    args = parser.parse_args(argv)
    try:
        paths = []
        for setting in ("RootDir", "DBPath"):
            result = subprocess.run(["/usr/bin/pacman-conf", setting], capture_output=True,
                                    text=True, check=True, timeout=15)
            if len(result.stdout.splitlines()) != 1:
                raise RelationshipError("ambiguous pacman database context")
            paths.append(Path(result.stdout.strip()))
        print(json.dumps(validate(json.loads(args.transaction_json), root=paths[0], dbpath=paths[1]), sort_keys=True))
        return 0
    except (RelationshipError, OSError, ValueError, AttributeError, subprocess.SubprocessError):
        print("Package relationship validation failed; preserve installed packages and review the transaction", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
