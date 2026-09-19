#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
MANIFEST_PATH = REPOSITORY / "deployment/ownership-v1.toml"
LOADER_PATH = REPOSITORY / "home/.config/hypr/hyprland.lua"
CORE_PATH = REPOSITORY / "home/.config/hypr/vanhyprarch/core.lua"
BINDINGS_PATH = REPOSITORY / "home/.config/hypr/vanhyprarch/bindings.lua"
MACHINE_SEED = REPOSITORY / "seeds/home/.config/vanhyprarch/machine/hyprland.lua"
OVERRIDE_SEED = REPOSITORY / "seeds/home/.config/vanhyprarch/overrides/hyprland.lua"
GENERATED_SOURCE = REPOSITORY / "home/.config/hypr/vanhyprarch-idle.conf"
HYPRLOCK_PATH = REPOSITORY / "home/.config/hypr/hyprlock.conf"
OWNERSHIP_DOC = REPOSITORY / "docs/deployment-ownership.md"

VALID_CLASSES = {
    "MANAGED",
    "MACHINE_CONFIGURATION",
    "USER_CUSTOMIZATION_OVERRIDE",
    "PERSISTENT_STATE_PREFERENCE",
    "PERSISTENT_STATE_PROVENANCE",
    "GENERATED",
    "RUNTIME",
    "USER_CONTENT",
    "OPTIONAL_COMPONENT_PAYLOAD",
    "SYSTEM_ADOPTED_MANAGED",
}

OVERRIDE_HEADER = (
    "-- Vanilla HyprArch user customization override.\n"
    "-- This file is user-owned; project updates do not overwrite it.\n"
    "-- Vanilla HyprArch is Alpha; this override interface is not stable.\n"
    "-- Check release notes for breaking changes and available migration guidance.\n"
)


class DeploymentOwnershipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        with MANIFEST_PATH.open("rb") as stream:
            cls.manifest = tomllib.load(stream)
        cls.artifacts = cls.manifest["artifact"]

    def artifact_for_target(self, target: str) -> dict[str, object]:
        matches = [item for item in self.artifacts if item["target"] == target]
        self.assertEqual(len(matches), 1, target)
        return matches[0]

    def test_manifest_schema_and_classes(self) -> None:
        self.assertEqual(self.manifest["schema_version"], 1)
        classes = {item["class"] for item in self.artifacts}
        self.assertEqual(classes, VALID_CLASSES)
        self.assertEqual(len({item["target"] for item in self.artifacts}), len(self.artifacts))
        for item in self.artifacts:
            self.assertTrue(item["target"])
            self.assertRegex(item["mode"], r"^0[0-7]{3}$")
            self.assertTrue(item["component"])
            self.assertTrue(item["authority"])
            self.assertIs(type(item["user_editable"]), bool)
            self.assertIs(type(item["machine_specific"]), bool)

    def test_manifest_sources_exist(self) -> None:
        for item in self.artifacts:
            source = item.get("source")
            if source is not None:
                self.assertTrue((REPOSITORY / source).is_file(), source)

    def test_generated_idle_fragment_has_no_release_source(self) -> None:
        target = "${XDG_CONFIG_HOME:-$HOME/.config}/hypr/vanhyprarch-idle.conf"
        artifact = self.artifact_for_target(target)
        self.assertEqual(artifact["class"], "GENERATED")
        self.assertNotIn("source", artifact)
        self.assertFalse(GENERATED_SOURCE.exists())

    def test_appearance_preference_renderer_and_manager_ownership(self) -> None:
        preference = self.artifact_for_target(
            "${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/appearance.json"
        )
        self.assertEqual(preference["class"], "PERSISTENT_STATE_PREFERENCE")
        self.assertEqual(preference["authority"], "vanhyprarch-appearance")
        self.assertNotIn("source", preference)

        renderer = self.artifact_for_target(
            "${XDG_CONFIG_HOME:-$HOME/.config}/hypr/hyprpaper.conf"
        )
        self.assertEqual(renderer["class"], "MANAGED")
        self.assertEqual(renderer["source"], "home/.config/hypr/hyprpaper.conf")

        manager = self.artifact_for_target(
            "$HOME/.local/bin/vanhyprarch-appearance"
        )
        self.assertEqual(manager["class"], "MANAGED")
        self.assertEqual(manager["mode"], "0755")

        receipt = self.artifact_for_target(
            "${XDG_STATE_HOME:-$HOME/.local/state}/vanhyprarch/appearance-assets.json"
        )
        self.assertEqual(receipt["class"], "PERSISTENT_STATE_PROVENANCE")
        self.assertEqual(receipt["authority"], "vanhyprarch-appearance")

        user_content = self.artifact_for_target(
            "<XDG Pictures>/Wallpapers/{Light,Dark}/*"
        )
        self.assertEqual(user_content["class"], "USER_CONTENT")
        self.assertEqual(user_content["authority"], "user")
        self.assertTrue(user_content["user_editable"])

        asset_sources = {
            item["source"]
            for item in self.artifacts
            if item["component"] == "appearance-assets" and "source" in item
        }
        self.assertEqual(
            asset_sources,
            {
                "assets/wallpapers/NOTICE.md",
                *(f"assets/wallpapers/Light/Wolkenstein_{number}_light.png" for number in range(1, 5)),
                *(f"assets/wallpapers/Dark/Wolkenstein_{number}_dark.png" for number in range(1, 5)),
            },
        )

    def test_override_is_header_only(self) -> None:
        self.assertEqual(OVERRIDE_SEED.read_text(encoding="utf-8"), OVERRIDE_HEADER)

    def test_machine_and_override_ownership_are_distinct(self) -> None:
        machine = self.artifact_for_target(
            "${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/machine/hyprland.lua"
        )
        override = self.artifact_for_target(
            "${XDG_CONFIG_HOME:-$HOME/.config}/vanhyprarch/overrides/hyprland.lua"
        )
        self.assertEqual(machine["class"], "MACHINE_CONFIGURATION")
        self.assertTrue(machine["machine_specific"])
        self.assertEqual(machine["mode"], "0600")
        self.assertEqual(override["class"], "USER_CUSTOMIZATION_OVERRIDE")
        self.assertFalse(override["machine_specific"])
        self.assertEqual(override["mode"], "0600")

    def test_hyprland_loader_has_exact_order_and_xdg_policy(self) -> None:
        loader = LOADER_PATH.read_text(encoding="utf-8")
        expected = [
            'require(managedHome .. "/core.lua")',
            'require(managedHome .. "/bindings.lua")',
            'require(userHome .. "/machine/hyprland.lua")',
            'require(userHome .. "/overrides/hyprland.lua")',
        ]
        positions = [loader.index(line) for line in expected]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(loader.count("require("), 4)
        self.assertNotIn("dofile(", loader)
        self.assertIn('configHome = home .. "/.config"', loader)
        self.assertIn('"XDG_CONFIG_HOME must be an absolute path"', loader)

        harness = r'''
local loaded = {}
require = function(path)
    table.insert(loaded, path)
    return true
end
assert(loadfile(arg[1]))()
io.write(table.concat(loaded, "\n"))
'''
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary) / "home"
            config = Path(temporary) / "config"
            result = subprocess.run(
                ["/usr/bin/lua", "-", str(LOADER_PATH)],
                input=harness,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                shell=False,
                env={"HOME": str(home), "XDG_CONFIG_HOME": str(config)},
            )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                f"{config}/hypr/vanhyprarch/core.lua",
                f"{config}/hypr/vanhyprarch/bindings.lua",
                f"{config}/vanhyprarch/machine/hyprland.lua",
                f"{config}/vanhyprarch/overrides/hyprland.lua",
            ],
        )

    def test_loader_rejects_relative_xdg_config_home(self) -> None:
        harness = "require = function(path) return true end; assert(loadfile(arg[1]))()\n"
        result = subprocess.run(
            ["/usr/bin/lua", "-", str(LOADER_PATH)],
            input=harness,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            shell=False,
            env={"HOME": "/tmp/vanhyprarch-home", "XDG_CONFIG_HOME": "relative"},
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("XDG_CONFIG_HOME must be an absolute path", result.stderr)

    def test_complete_hyprland_chain_verifies(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            temporary_root = Path(temporary)
            home = temporary_root / "home"
            config = temporary_root / "config"
            runtime = temporary_root / "runtime"
            managed = config / "hypr/vanhyprarch"
            machine = config / "vanhyprarch/machine"
            overrides = config / "vanhyprarch/overrides"
            managed.mkdir(parents=True)
            machine.mkdir(parents=True)
            overrides.mkdir(parents=True)
            runtime.mkdir(mode=0o700)

            entrypoint = config / "hypr/hyprland.lua"
            shutil.copyfile(LOADER_PATH, entrypoint)
            shutil.copyfile(CORE_PATH, managed / "core.lua")
            shutil.copyfile(BINDINGS_PATH, managed / "bindings.lua")
            shutil.copyfile(MACHINE_SEED, machine / "hyprland.lua")
            shutil.copyfile(OVERRIDE_SEED, overrides / "hyprland.lua")

            environment = os.environ.copy()
            environment.update(
                {
                    "HOME": str(home),
                    "XDG_CONFIG_HOME": str(config),
                    "XDG_RUNTIME_DIR": str(runtime),
                }
            )
            result = subprocess.run(
                ["/usr/bin/Hyprland", "--verify-config", "--config", str(entrypoint)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                shell=False,
                env=environment,
                timeout=10,
            )
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn("config ok", result.stdout)

    def test_managed_lua_and_seed_are_portable(self) -> None:
        for path in (LOADER_PATH, CORE_PATH, BINDINGS_PATH, MACHINE_SEED):
            self.assertTrue(path.is_file(), path)
            result = subprocess.run(
                ["/usr/bin/lua", "-", str(path)],
                input="assert(loadfile(arg[1]))\n",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                check=False,
                shell=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

        public_configuration = "\n".join(
            path.read_text(encoding="utf-8") for path in (CORE_PATH, MACHINE_SEED)
        )
        forbidden_patterns = (
            r"\bDP-1\b",
            r"\b3840x2160(?:@60)?\b",
            r"\b1\.25\b",
            r"\bkb_layout\s*=\s*['\"]it['\"]",
            r"\bepic-mouse-v1\b",
            r"\bbitdepth\s*=",
            r"\bcm\s*=\s*['\"]auto['\"]",
        )
        for pattern in forbidden_patterns:
            self.assertNotRegex(public_configuration, pattern)

    def test_machine_seed_has_non_ui_owned_portable_fallback(self) -> None:
        seed = MACHINE_SEED.read_text(encoding="utf-8")
        monitor_blocks = re.findall(r"hl\.monitor\s*\(\s*\{(.*?)\}\s*\)", seed, re.DOTALL)
        self.assertEqual(len(monitor_blocks), 1)

        fields = {}
        for name, value in re.findall(
            r"(?m)^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*([^,\n]+)\s*,?\s*$",
            monitor_blocks[0],
        ):
            fields[name] = value.strip()
        self.assertEqual(
            fields,
            {
                "output": '""',
                "mode": '"preferred"',
                "position": '"auto"',
                "scale": '"auto"',
            },
        )
        self.assertNotRegex(seed, r"(?i)\blocal\s+\w*scale\w*\s*=")
        self.assertNotIn("vanhyprarchMonitorScale", seed)

        ownership_prose = " ".join(
            OWNERSHIP_DOC.read_text(encoding="utf-8").split()
        )
        self.assertIn("specific explicit output profile", ownership_prose)
        self.assertIn("This fallback is machine-owned", ownership_prose)
        self.assertIn("not a Monitor panel write target", ownership_prose)
        self.assertIn("No general multi-monitor schema is", ownership_prose)

    def test_public_commands_keep_regular_user_local_targets(self) -> None:
        command_classes = {
            "vanhyprarch-idle": "MANAGED",
            "vanhyprarch-screenshot": "MANAGED",
            "vanhyprarch-dictation": "MANAGED",
            "vanhyprarch-screensaver": "MANAGED",
        }
        for command, ownership_class in command_classes.items():
            target = f"$HOME/.local/bin/{command}"
            artifact = self.artifact_for_target(target)
            self.assertEqual(artifact["source"], f"bin/{command}")
            self.assertEqual(artifact["class"], ownership_class)
            self.assertEqual(artifact["mode"], "0755")
            source = REPOSITORY / f"bin/{command}"
            self.assertTrue(source.is_file())
            self.assertTrue(os.access(source, os.X_OK))

        player = self.artifact_for_target("$HOME/.local/bin/vanhyprarch-zig-player")
        self.assertEqual(player["class"], "OPTIONAL_COMPONENT_PAYLOAD")
        self.assertNotIn("source", player)
        marker = self.artifact_for_target(
            "${XDG_DATA_HOME:-$HOME/.local/share}/vanhyprarch/components/zig-screensaver"
        )
        self.assertEqual(marker["authority"], "vanhyprarch-screensaver")
        self.assertEqual(marker["mode"], "0644")

    def test_hyprlock_baseline_is_minimal_and_portable(self) -> None:
        config = HYPRLOCK_PATH.read_text(encoding="utf-8")
        self.assertEqual(config.count("general {"), 1)
        self.assertEqual(config.count("background {"), 1)
        self.assertEqual(config.count("input-field {"), 1)
        for directive in (
            "hide_cursor",
            "monitor",
            "color",
            "size",
            "outline_thickness",
            "inner_color",
            "outer_color",
            "font_color",
            "fade_on_empty",
            "placeholder_text",
            "position",
            "halign",
            "valign",
        ):
            self.assertRegex(config, rf"(?m)^\s*{re.escape(directive)}\s*=")
        for forbidden in ("/home/", "DP-", "HDMI-", "path =", "cmd[", "$LAYOUT"):
            self.assertNotIn(forbidden, config)


if __name__ == "__main__":
    unittest.main()
