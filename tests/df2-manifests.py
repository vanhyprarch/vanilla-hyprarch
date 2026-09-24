#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import re
import sys
import tarfile
import tomllib
import unittest
from pathlib import Path


CHECK_REPOSITORIES = "--check-repositories" in sys.argv
if CHECK_REPOSITORIES:
    sys.argv.remove("--check-repositories")

REPOSITORY = Path(__file__).resolve().parent.parent
PACKAGE_MANIFEST = REPOSITORY / "packages/manifest-v1.toml"
OWNERSHIP_MANIFEST = REPOSITORY / "deployment/ownership-v2.toml"
SERVICE_MANIFEST = REPOSITORY / "deployment/service-policy-v1.toml"

PACKAGE_ROLES = {"required", "recommended", "optional", "build", "development"}
PACKAGE_SOURCES = {"official", "aur"}
COMPONENT_CLASSES = {"recommended", "optional"}
OWNERSHIP_CLASSES = {
    "VANILLA_MANAGED",
    "VANILLA_MANAGED_SYSTEM",
    "CREATE_ONCE_MACHINE",
    "CREATE_ONCE_USER",
    "USER_OWNED",
    "BACKEND_OWNED",
    "GENERATED",
    "RUNTIME",
    "PACKAGE_OWNED",
    "EXTERNAL_OWNED",
    "ADOPTED_PRIVILEGED",
    "OPTIONAL_COMPONENT_PAYLOAD",
}
NON_DEPLOYABLE_CLASSES = {
    "USER_OWNED",
    "BACKEND_OWNED",
    "GENERATED",
    "RUNTIME",
    "PACKAGE_OWNED",
    "EXTERNAL_OWNED",
    "OPTIONAL_COMPONENT_PAYLOAD",
}
REQUIRED_DEFAULT = {
    "7zip",
    "bazaar",
    "bluez",
    "bubblewrap",
    "curl",
    "ddcutil",
    "dunst",
    "file",
    "firefox",
    "flatpak",
    "foot",
    "gnome-text-editor",
    "grim",
    "gvfs",
    "gtk3",
    "hypridle",
    "hyprland",
    "hyprlock",
    "hyprpaper",
    "hyprpolkitagent",
    "hyprshutdown",
    "imv",
    "libxkbcommon",
    "sddm",
    "mesa",
    "mpv",
    "networkmanager",
    "noto-fonts",
    "noto-fonts-emoji",
    "papirus-icon-theme",
    "pipewire",
    "pipewire-alsa",
    "pipewire-audio",
    "pipewire-jack",
    "pipewire-pulse",
    "python",
    "python-dbus",
    "python-gobject",
    "qt6-svg",
    "quickshell",
    "slurp",
    "thunar",
    "thunar-archive-plugin",
    "ttf-dejavu",
    "ttf-liberation",
    "tumbler",
    "unzip",
    "wayland",
    "wireplumber",
    "wl-clipboard",
    "xarchiver",
    "xdg-desktop-portal",
    "xdg-desktop-portal-gtk",
    "xdg-desktop-portal-hyprland",
    "xdg-terminal-exec",
    "xdg-user-dirs",
    "xdg-utils",
    "xkeyboard-config",
    "zip",
    "zstd",
}
FORBIDDEN_DIRECT_PACKAGES = {
    "cups-filters",
    "desktop-file-utils",
    "gzip",
    "i2c-tools",
    "p7zip",
    "polkit",
    "tar",
    "udisks2",
    "xz",
    "bzip2",
    "zig",
}


def load_toml(path: Path) -> dict[str, object]:
    with path.open("rb") as stream:
        return tomllib.load(stream)


class PackageManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_toml(PACKAGE_MANIFEST)
        cls.packages = cls.document["package"]
        cls.components = cls.document["component"]
        cls.by_name = {item["name"]: item for item in cls.packages}
        cls.components_by_id = {item["id"]: item for item in cls.components}

    def names(self, **criteria: object) -> set[str]:
        return {
            item["name"]
            for item in self.packages
            if all(item.get(key) == value for key, value in criteria.items())
        }

    def test_schema_is_minimal_and_explicit(self) -> None:
        self.assertEqual(self.document["schema_version"], 1)
        self.assertEqual(self.document["architecture"], "x86_64")
        self.assertEqual(self.document["policy"]["dependency_authority"], "pacman")
        self.assertFalse(self.document["policy"]["versions_are_pinned"])
        self.assertEqual(len(self.by_name), len(self.packages))
        for item in self.packages:
            self.assertRegex(item["name"], r"^[a-z0-9][a-z0-9@._+-]*$")
            self.assertIn(item["source"], PACKAGE_SOURCES)
            self.assertIn(item["role"], PACKAGE_ROLES)
            self.assertIs(type(item["default_install"]), bool)
            self.assertIs(item["direct"], True)
            self.assertTrue(item["owner"])
            self.assertTrue(item["reason"])
            if "component" in item:
                self.assertIn(item["component"], self.components_by_id)

    def test_components_are_known_and_non_recursive(self) -> None:
        self.assertEqual(len(self.components_by_id), len(self.components))
        self.assertEqual(
            set(self.components_by_id),
            {
                "printing",
                "network-printing",
                "dictation",
                "dictation-vulkan",
                "zig-screensaver",
            },
        )
        for item in self.components:
            self.assertIn(item["classification"], COMPONENT_CLASSES)
            self.assertIs(type(item["default_install"]), bool)
            self.assertIs(type(item["manager_in_baseline"]), bool)
            for requirement in item.get("requires", []):
                self.assertIn(requirement, self.components_by_id)
                self.assertNotEqual(requirement, item["id"])

    def test_required_default_set_is_frozen(self) -> None:
        self.assertEqual(
            self.names(source="official", role="required", default_install=True),
            REQUIRED_DEFAULT,
        )
        self.assertFalse(self.names(role="required", default_install=False))

    def test_recommended_role_is_independent_from_default_policy(self) -> None:
        self.assertEqual(
            self.names(role="recommended", default_install=True),
            {"bluez-utils", "pavucontrol"},
        )
        self.assertEqual(
            self.names(role="recommended", default_install=False),
            {"cups", "cups-pk-helper", "system-config-printer"},
        )

    def test_printing_is_a_non_default_component(self) -> None:
        printing = self.components_by_id["printing"]
        self.assertEqual(printing["classification"], "recommended")
        self.assertFalse(printing["default_install"])
        self.assertEqual(
            self.names(component="printing"),
            {"cups", "cups-pk-helper", "system-config-printer"},
        )
        self.assertEqual(self.names(component="network-printing"), {"avahi"})
        for name in self.names(component="printing") | {"avahi"}:
            self.assertFalse(self.by_name[name]["default_install"])

    def test_yay_is_the_only_approved_aur_package(self) -> None:
        self.assertEqual(self.names(source="aur"), {"yay"})
        self.assertEqual(self.document["aur"]["approved_default"], ["yay"])
        self.assertFalse(self.document["aur"]["build_as_root"])
        self.assertEqual(
            self.document["aur"]["bootstrap_official"], ["base-devel", "git"]
        )
        yay = self.by_name["yay"]
        self.assertEqual(yay["role"], "required")
        self.assertTrue(yay["default_install"])
        self.assertEqual(
            self.names(source="official", role="build", default_install=True),
            {"base-devel", "git"},
        )
        self.assertNotIn("go", self.by_name)

    def test_sddm_replaces_ly_as_the_direct_default_display_manager(self) -> None:
        self.assertNotIn("ly", self.by_name)
        sddm = self.by_name["sddm"]
        self.assertEqual(sddm["source"], "official")
        self.assertEqual(sddm["role"], "required")
        self.assertTrue(sddm["default_install"])
        self.assertTrue(sddm["direct"])
        self.assertEqual(sddm["owner"], "session")

    def test_dictation_packages_do_not_leak_into_default_install(self) -> None:
        self.assertEqual(self.names(component="dictation"), {"gnupg", "wtype"})
        self.assertEqual(
            self.names(component="dictation-vulkan"),
            {"vulkan-icd-loader", "vulkan-intel", "vulkan-radeon"},
        )
        for name in self.names(component="dictation") | self.names(component="dictation-vulkan"):
            self.assertEqual(self.by_name[name]["role"], "optional")
            self.assertFalse(self.by_name[name]["default_install"])
        self.assertNotIn("nvidia-utils", self.by_name)

    def test_screensaver_manager_and_payload_distinction_is_explicit(self) -> None:
        component = self.components_by_id["zig-screensaver"]
        self.assertTrue(component["manager_in_baseline"])
        self.assertTrue(component["external_payload"])
        self.assertFalse(component["installed_compiler_required"])
        self.assertNotIn("zig", self.by_name)

    def test_archive_stack_and_exclusions_are_frozen(self) -> None:
        expected = {
            "thunar",
            "thunar-archive-plugin",
            "xarchiver",
            "7zip",
            "zip",
            "unzip",
            "zstd",
            "gvfs",
            "tumbler",
        }
        self.assertTrue(expected <= self.names(default_install=True))
        self.assertTrue(FORBIDDEN_DIRECT_PACKAGES.isdisjoint(self.by_name))
        self.assertNotIn("thunar-volman", self.by_name)
        self.assertNotIn("gvfs-mtp", self.by_name)
        self.assertNotIn("ffmpegthumbnailer", self.by_name)
        self.assertNotIn("unrar", self.by_name)

    def test_direct_fresh_install_application_decisions_are_present(self) -> None:
        for name, owner in {
            "bazaar": "default-applications",
            "dunst": "notifications",
            "gnome-text-editor": "default-applications",
            "imv": "default-applications",
            "mpv": "default-applications",
            "pipewire-jack": "audio",
        }.items():
            item = self.by_name[name]
            self.assertEqual(item["source"], "official")
            self.assertEqual(item["owner"], owner)
            self.assertEqual(item["role"], "required")
            self.assertTrue(item["default_install"])
            self.assertTrue(item["direct"])

    @unittest.skipUnless(CHECK_REPOSITORIES, "optional local Arch database validation")
    def test_official_names_exist_in_local_arch_databases(self) -> None:
        database_root = Path("/var/lib/pacman/sync")
        database_paths = sorted(database_root.glob("*.db"))
        self.assertTrue(database_paths, "no local Arch sync databases")
        available: set[str] = set()
        for path in database_paths:
            with tarfile.open(path, "r:*") as archive:
                for member in archive.getmembers():
                    if not member.name.endswith("/desc"):
                        continue
                    stream = archive.extractfile(member)
                    self.assertIsNotNone(stream)
                    fields = stream.read().decode("utf-8", "strict").splitlines()
                    try:
                        index = fields.index("%NAME%")
                    except ValueError:
                        continue
                    available.add(fields[index + 1])
        missing = self.names(source="official") - available
        self.assertEqual(missing, set())


class OwnershipManifestTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_toml(OWNERSHIP_MANIFEST)
        cls.classes = {item["name"]: item for item in cls.document["ownership_class"]}
        cls.artifacts = cls.document["artifact"]
        cls.by_id = {item["id"]: item for item in cls.artifacts}

    def test_schema_classes_and_modes_are_explicit(self) -> None:
        self.assertEqual(self.document["schema_version"], 2)
        self.assertEqual(self.document["installed_mode"], "regular-files")
        self.assertEqual(self.document["development_mode"], "repository-symlinks-allowed")
        self.assertTrue(self.document["runtime_source_independent"])
        self.assertEqual(set(self.classes), OWNERSHIP_CLASSES)
        self.assertEqual(len(self.by_id), len(self.artifacts))
        self.assertEqual(
            len({item["target"] for item in self.artifacts}), len(self.artifacts)
        )
        for name, policy in self.classes.items():
            self.assertIs(type(policy["deployable"]), bool, name)
            self.assertTrue(policy["source_policy"], name)
            self.assertTrue(policy["install_action"], name)
            self.assertTrue(policy["update_action"], name)

    def test_artifact_mappings_are_structurally_valid(self) -> None:
        valid_kinds = {"file", "tree", "pattern"}
        valid_status = {"implemented", "planned"}
        for item in self.artifacts:
            self.assertRegex(item["id"], r"^[a-z0-9][a-z0-9-]*$")
            self.assertIn(item["class"], self.classes)
            self.assertIn(item["kind"], valid_kinds)
            self.assertIn(item["status"], valid_status)
            self.assertTrue(item["component"])
            self.assertTrue(item["authority"])
            self.assertIs(type(item["user_editable"]), bool)
            self.assertIs(type(item["machine_specific"]), bool)
            target = item["target"]
            allowed_roots = ("$HOME/", "${XDG_", "/etc/", "/usr/", "/var/lib/")
            if item["class"] == "BACKEND_OWNED":
                allowed_roots += ("/run/",)
            self.assertTrue(
                target.startswith(allowed_roots),
                target,
            )
            self.assertNotIn(";", target)
            if "mode" in item:
                self.assertRegex(item["mode"], r"^0[0-7]{3}$")
            source = item.get("source")
            if source is not None:
                self.assertFalse(Path(source).is_absolute(), source)
                self.assertNotIn("..", Path(source).parts)
                source_path = REPOSITORY / source
                self.assertTrue(source_path.exists(), source)
                if item["kind"] == "file":
                    self.assertTrue(source_path.is_file(), source)
                elif item["kind"] == "tree":
                    self.assertTrue(source_path.is_dir(), source)
                    self.assertEqual(item.get("mode_policy"), "explicit")
                    self.assertRegex(item["directory_mode"], r"^0[0-7]{3}$")
                    self.assertRegex(item["file_mode"], r"^0[0-7]{3}$")
                    if item.get("executable"):
                        self.assertRegex(item["executable_mode"], r"^0[0-7]{3}$")
                    for relative in item.get("included", []):
                        self.assertFalse(Path(relative).is_absolute(), relative)
                        self.assertNotIn("..", Path(relative).parts)
                        self.assertTrue((source_path / relative).is_file(), relative)
            if item["kind"] == "file" and item["class"] not in {
                "BACKEND_OWNED",
                "PACKAGE_OWNED",
            }:
                self.assertIn("mode", item)

    def test_class_source_and_deployment_invariants(self) -> None:
        for item in self.artifacts:
            ownership_class = item["class"]
            policy = self.classes[ownership_class]
            if ownership_class in NON_DEPLOYABLE_CLASSES:
                self.assertFalse(policy["deployable"])
                self.assertNotIn("source", item)
            if ownership_class in {"GENERATED", "RUNTIME"}:
                self.assertEqual(policy["install_action"], "never" if ownership_class == "RUNTIME" else "generate-through-backend")
            if ownership_class == "PACKAGE_OWNED":
                self.assertTrue(item["target"].startswith("/usr/"))
            if item["status"] == "planned":
                self.assertIn(ownership_class, {"CREATE_ONCE_USER", "CREATE_ONCE_MACHINE"})
                self.assertNotIn("source", item)
            elif policy["source_policy"] in {"required", "required-when-implemented"}:
                self.assertIn("source", item)

    def test_create_once_targets_can_never_be_replaceable(self) -> None:
        for name in ("CREATE_ONCE_MACHINE", "CREATE_ONCE_USER"):
            self.assertEqual(self.classes[name]["install_action"], "create-if-absent")
            self.assertEqual(self.classes[name]["update_action"], "preserve")
        self.assertEqual(self.by_id["machine-hyprland"]["class"], "CREATE_ONCE_MACHINE")
        self.assertEqual(self.by_id["user-hyprland-override"]["class"], "CREATE_ONCE_USER")
        self.assertEqual(self.by_id["mpv-config"]["class"], "CREATE_ONCE_USER")
        self.assertEqual(self.by_id["mimeapps-config"]["class"], "CREATE_ONCE_USER")

    def test_flatpak_export_scaffolds_have_external_ownership(self) -> None:
        policy = self.classes["EXTERNAL_OWNED"]
        self.assertFalse(policy["deployable"])
        self.assertEqual(policy["install_action"], "ensure-directory-only")
        self.assertEqual(policy["update_action"], "preserve")
        expected = {
            "flatpak-system-application-exports": "/var/lib/flatpak/exports/share/applications",
            "flatpak-user-application-exports":
                "${XDG_DATA_HOME:-$HOME/.local/share}/flatpak/exports/share/applications",
        }
        for identifier, target in expected.items():
            record = self.by_id[identifier]
            self.assertEqual(record["target"], target)
            self.assertEqual(record["class"], "EXTERNAL_OWNED")
            self.assertEqual(record["authority"], "flatpak")
            self.assertEqual(record["kind"], "tree")
            self.assertEqual(record["mode"], "0755")
            self.assertNotIn("source", record)
        for document in ("installation-strategy.md", "system-integration.md",
                         "compatibility.md"):
            self.assertIn(expected["flatpak-system-application-exports"],
                          (REPOSITORY / "docs" / document).read_text())
        for document in ("installation-strategy.md", "create-once-initialization.md"):
            self.assertIn(expected["flatpak-user-application-exports"],
                          (REPOSITORY / "docs" / document).read_text())

    def test_managed_deployment_provenance_is_backend_owned(self) -> None:
        identifier = self.document["managed_deployment_provenance"]
        self.assertEqual(identifier, "managed-deployment-provenance")
        provenance = self.by_id[identifier]
        self.assertEqual(provenance["class"], "BACKEND_OWNED")
        self.assertEqual(provenance["authority"], "vanhyprarch-managed-deploy")
        self.assertEqual(provenance["mode"], "0600")
        self.assertNotIn("source", provenance)

    def test_installed_release_identity_is_privileged_backend_state(self) -> None:
        identity = self.by_id["installed-release-identity"]
        self.assertEqual(identity["target"], "/usr/share/vanhyprarch/release.json")
        self.assertEqual(identity["class"], "BACKEND_OWNED")
        self.assertEqual(identity["authority"], "vanhyprarch-release-identity")
        self.assertEqual(identity["mode"], "0644")
        self.assertFalse(identity["user_editable"])
        self.assertNotIn("source", identity)

    def test_create_once_lifecycle_inventory_is_backend_owned(self) -> None:
        self.assertEqual(self.document["create_once_lifecycle_state"],
                         "create-once-lifecycle-state")
        lifecycle = self.by_id["create-once-lifecycle-state"]
        self.assertEqual(lifecycle["target"],
                         "${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/create-once-lifecycle-v1.json")
        self.assertEqual(lifecycle["class"], "BACKEND_OWNED")
        self.assertEqual(lifecycle["authority"], "vanhyprarch-create-once")
        self.assertEqual(lifecycle["mode"], "0600")
        self.assertNotIn("source", lifecycle)

    def test_release_update_journal_and_lock_are_privileged_backend_state(self) -> None:
        for key, identifier, target in (
            ("release_update_journal", "release-update-journal",
             "/var/lib/vanhyprarch/update/journal.json"),
            ("release_update_lock", "release-update-lock",
             "/run/vanhyprarch/update.lock"),
        ):
            self.assertEqual(self.document[key], identifier)
            artifact = self.by_id[identifier]
            self.assertEqual(artifact["target"], target)
            self.assertEqual(artifact["class"], "BACKEND_OWNED")
            self.assertEqual(artifact["authority"], "vanhyprarch-update-journal")
            self.assertEqual(artifact["mode"], "0600")
            self.assertNotIn("source", artifact)

    def test_generated_runtime_and_package_paths_are_never_deployable(self) -> None:
        for item in self.artifacts:
            if item["class"] in {"GENERATED", "RUNTIME", "PACKAGE_OWNED"}:
                self.assertFalse(self.classes[item["class"]]["deployable"])
                self.assertNotIn("source", item)
        for item in self.artifacts:
            if item["target"].startswith("/usr/lib/systemd/"):
                self.assertEqual(item["class"], "PACKAGE_OWNED")
            if item["target"].startswith("/usr/share/wayland-sessions/"):
                expected = (
                    "VANILLA_MANAGED_SYSTEM"
                    if item["id"] == "vanhyprarch-wayland-session"
                    else "PACKAGE_OWNED"
                )
                self.assertEqual(item["class"], expected)

    def test_installed_quickshell_and_commands_do_not_depend_on_source_tree(self) -> None:
        shell = self.by_id["quickshell-config"]
        self.assertEqual(shell["kind"], "tree")
        self.assertEqual(shell["class"], "VANILLA_MANAGED")
        self.assertNotIn("Projects", shell["target"])
        commands = [
            item
            for item in self.artifacts
            if item["target"].startswith("$HOME/.local/bin/vanhyprarch-")
            and str(item.get("source", "")).startswith("bin/")
        ]
        self.assertEqual(
            {item["target"].rsplit("/", 1)[-1] for item in commands},
            {
                "vanhyprarch-appearance",
                "vanhyprarch-default-apps",
                "vanhyprarch-dictation",
                "vanhyprarch-idle",
                "vanhyprarch-keyboard-sync",
                "vanhyprarch-monitor",
                "vanhyprarch-polkit-session",
                "vanhyprarch-screensaver",
                "vanhyprarch-screenshot",
            },
        )
        for item in commands:
            self.assertEqual(item["class"], "VANILLA_MANAGED")
            self.assertEqual(item["mode"], "0755")

    def test_monitor_installer_boundary_is_frozen(self) -> None:
        machine = self.by_id["machine-hyprland"]
        self.assertEqual(machine["class"], "CREATE_ONCE_MACHINE")
        manifest_text = OWNERSHIP_MANIFEST.read_text(encoding="utf-8")
        self.assertNotRegex(manifest_text, r"\b(?:DP|HDMI|eDP)-[0-9]+\b")
        runtime = self.by_id["monitor-runtime"]
        self.assertEqual(runtime["class"], "RUNTIME")
        self.assertNotIn("source", runtime)

    def test_no_personal_or_worktree_paths_exist(self) -> None:
        for path in (PACKAGE_MANIFEST, OWNERSHIP_MANIFEST, SERVICE_MANIFEST):
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("/home/giacomo", content)
            self.assertNotIn("/Projects/", content)


class ServicePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.document = load_toml(SERVICE_MANIFEST)
        cls.services = cls.document["service"]
        cls.by_name = {item["name"]: item for item in cls.services}
        package_document = load_toml(PACKAGE_MANIFEST)
        cls.component_ids = {item["id"] for item in package_document["component"]}

    def test_schema_and_service_records(self) -> None:
        self.assertEqual(self.document["schema_version"], 1)
        self.assertEqual(len(self.by_name), len(self.services))
        for item in self.services:
            self.assertIn(item["scope"], {"system", "user"})
            self.assertIn(item["owner"], {"package", "vanilla", "optional-component"})
            self.assertIs(type(item["default_install"]), bool)
            self.assertTrue(item["policy"])
            self.assertTrue(item["startup_owner"])
            if "component" in item:
                self.assertIn(item["component"], self.component_ids)

    def test_required_system_service_policy(self) -> None:
        for name in ("NetworkManager.service", "bluetooth.service", "sddm.service"):
            self.assertEqual(self.by_name[name]["policy"], "enabled")
            self.assertTrue(self.by_name[name]["default_install"])
        self.assertNotIn("ly@tty2.service", self.by_name)
        self.assertNotIn("getty@tty2.service", self.by_name)

    def test_printing_services_are_component_only(self) -> None:
        for name in ("cups.service", "cups.socket", "cups.path"):
            item = self.by_name[name]
            self.assertEqual(item["policy"], "component")
            self.assertEqual(item["component"], "printing")
            self.assertFalse(item["default_install"])

    def test_package_activation_is_not_reimplemented(self) -> None:
        for name in (
            "pipewire.service",
            "pipewire-pulse.service",
            "wireplumber.service",
        ):
            self.assertEqual(self.by_name[name]["policy"], "package-activation")
        for name in (
            "xdg-desktop-portal.service",
            "xdg-desktop-portal-hyprland.service",
            "xdg-desktop-portal-gtk.service",
            "dunst.service",
        ):
            self.assertEqual(self.by_name[name]["policy"], "dbus-activation")

    def test_static_and_session_owned_units_are_never_enabled(self) -> None:
        self.assertEqual(self.by_name["hypridle.service"]["policy"], "disabled")
        self.assertEqual(self.by_name["hypridle.service"]["startup_owner"], "hyprland-direct")
        self.assertEqual(self.by_name["hyprpolkitagent.service"]["policy"], "not-enabled")
        self.assertEqual(self.by_name["vanhyprarch-keyboard-sync.service"]["policy"], "static")
        self.assertEqual(
            self.by_name["vanhyprarch-monitor-safe-apply.service"]["policy"],
            "static-transaction",
        )
        self.assertFalse(self.by_name["vanhyprarch-voxtype.service"]["default_install"])


class DocumentationConsistencyTests(unittest.TestCase):
    def test_new_applications_do_not_change_mime_defaults(self) -> None:
        baseline = (REPOSITORY / "docs/system-baseline.md").read_text(encoding="utf-8")
        current = (REPOSITORY / "docs/current-state.md").read_text(encoding="utf-8")
        mime_seed = (REPOSITORY / "seeds/home/.config/mimeapps.list").read_text(encoding="utf-8")
        for package in ("gnome-text-editor", "bazaar"):
            self.assertIn(f"`{package}`", baseline)
            self.assertIn(f"`{package}`", current)
        self.assertIn("text/plain=org.gnome.TextEditor.desktop;", mime_seed)

    def test_removed_flat_manifests_have_no_live_references(self) -> None:
        forbidden = {
            "packages/official.txt",
            "packages/aur.txt",
            "packages/optional-dictation-official.txt",
        }
        paths = [REPOSITORY / "README.md", *sorted((REPOSITORY / "docs").glob("*.md"))]
        for path in paths:
            content = path.read_text(encoding="utf-8")
            for value in forbidden:
                self.assertNotIn(value, content, path)

    def test_published_monitor_hdr_is_not_described_as_pending(self) -> None:
        paths = [REPOSITORY / "README.md", *sorted((REPOSITORY / "docs").glob("*.md"))]
        content = "\n".join(path.read_text(encoding="utf-8") for path in paths)
        for stale in (
            "current uncommitted HDR",
            "local schema-v5 HDR candidate",
            "HDR extension candidate",
            "awaiting controlled acceptance",
            "must pass its own controlled upgrade",
        ):
            self.assertNotIn(stale, content)

    def test_df2_decisions_record_provisional_mpv_and_mime_contracts(self) -> None:
        document = (REPOSITORY / "docs/distribution-foundation-2.md").read_text(
            encoding="utf-8"
        )
        for line in (
            "vo=gpu-next",
            "target-colorspace-hint=auto",
            "target-colorspace-hint-mode=source",
            "fullscreen=yes",
        ):
            self.assertEqual(document.count(line), 1)
        for desktop_id in (
            "firefox.desktop",
            "thunar.desktop",
            "imv.desktop",
            "mpv.desktop",
        ):
            self.assertIn(desktop_id, document)
        self.assertIn("test this MPV baseline on an SDR-only", document)
        self.assertIn("overwrite or automatically merge", document)

    def test_df2_scope_source_and_update_boundaries_are_documented(self) -> None:
        document = (REPOSITORY / "docs/distribution-foundation-2.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Arch Linux x86_64", document)
        self.assertIn("fresh-install or archinstall-derived", document)
        self.assertIn("exact-commit GitHub source archive with curl", document)
        self.assertRegex(
            document,
            r"Installed runtime files are regular copies\s+and do not depend on "
            r"Git, the extracted source, a worktree, or its absolute\s+source path",
        )
        self.assertIn("future pinned tag archives", document)
        self.assertIn("never silently performs `pacman -Syu`", document)
        self.assertIn("unsupported partial upgrade", document)
        self.assertIn("Official `sddm` is required", document)
        self.assertIn("SDDM is the sole supported display manager", document)

    def test_aur_and_git_bootstrap_boundaries_are_documented(self) -> None:
        package_policy = (REPOSITORY / "packages/README.md").read_text(
            encoding="utf-8"
        )
        df2_decisions = (
            REPOSITORY / "docs/distribution-foundation-2.md"
        ).read_text(encoding="utf-8")
        installation = (REPOSITORY / "docs/installation-strategy.md").read_text(
            encoding="utf-8"
        )

        for document in (package_policy, df2_decisions, installation):
            self.assertIn("PKGBUILD", document)
            self.assertIn("makepkg", document)
            self.assertIn("does not", document)
        self.assertIn("`go` is not a direct Vanilla", package_policy)
        self.assertIn("declare `go` directly", df2_decisions)
        self.assertIn("`git` is not an acquisition prerequisite", df2_decisions)
        self.assertRegex(df2_decisions, r"permanent build/bootstrap package\s+baseline")
        self.assertIn("Git is therefore not required merely to obtain Vanilla", installation)
        self.assertRegex(installation, r"permanent build/bootstrap package\s+baseline")
        self.assertIn("ref-based bootstrap is a development installation", installation)
        self.assertIn("already verified, extracted release tree", installation)


if __name__ == "__main__":
    unittest.main()
