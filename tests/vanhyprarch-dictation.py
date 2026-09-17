#!/usr/bin/python
# SPDX-License-Identifier: GPL-2.0-only

from __future__ import annotations

import hashlib
import importlib.machinery
import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import textwrap
import tomllib
import unittest
from unittest import mock
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parent.parent
MANAGER = REPOSITORY / "bin/vanhyprarch-dictation"
RESOURCES = REPOSITORY / "install/dictation"


def load_manager_module():
    loader = importlib.machinery.SourceFileLoader(
        "vanhyprarch_dictation", str(MANAGER))
    specification = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(specification)
    assert specification.loader is not None
    specification.loader.exec_module(module)
    return module


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FakeClock:
    def __init__(self) -> None:
        self.value = 0.0
        self.sleeps: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, duration: float) -> None:
        self.sleeps.append(duration)
        self.value += duration


class DictationManagerTest(unittest.TestCase):
    maxDiff = None

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="vanhyprarch-dictation-test.")
        self.root = Path(self.temporary.name)
        self.home = self.root / "home"
        self.config_home = self.home / "config"
        self.data_home = self.home / "data"
        self.runtime_home = self.home / "runtime"
        self.runtime_home.mkdir(parents=True)
        self.resources = self.root / "resources"
        self.resources.mkdir()
        shutil.copy2(RESOURCES / "config.toml", self.resources / "config.toml")
        shutil.copy2(RESOURCES / "vanhyprarch-voxtype.service", self.resources / "vanhyprarch-voxtype.service")
        self.models_source = self.root / "model-source"
        self.models_source.mkdir()
        self.small_en = self.models_source / "ggml-small.en.bin"
        self.small = self.models_source / "ggml-small.bin"
        self.small_en.write_bytes(b"fixture small english model\n")
        self.small.write_bytes(b"fixture small multilingual model\n")
        self._write_model_manifest()
        self.fake_binary = self.root / "voxtype-0.0.0-linux-x86_64-avx2"
        self._write_fake_voxtype()
        self.fingerprint = "A" * 40
        self.key = self.resources / "voxtype-ci-signing-key.asc"
        self.key.write_text("mock public key\n", encoding="utf-8")
        self.signature = self.root / (self.fake_binary.name + ".asc")
        self.signature.write_text("mock detached signature\n", encoding="utf-8")
        self.metadata = self.resources / "voxtype.conf"
        self.metadata.write_text(textwrap.dedent(f"""\
            VANHYPRARCH_VOXTYPE_VERSION=0.0.0
            VANHYPRARCH_VOXTYPE_ARCHITECTURE=x86_64
            VANHYPRARCH_VOXTYPE_ASSET={self.fake_binary.name}
            VANHYPRARCH_VOXTYPE_SHA256={digest(self.fake_binary)}
            VANHYPRARCH_VOXTYPE_SIGNING_FINGERPRINT={self.fingerprint}
            VANHYPRARCH_VOXTYPE_RELEASE_URL=https://example.invalid/releases/tag/v0.0.0
            VANHYPRARCH_VOXTYPE_DOWNLOAD_URL=https://example.invalid/{self.fake_binary.name}
            VANHYPRARCH_VOXTYPE_SIGNATURE_URL=https://example.invalid/{self.fake_binary.name}.asc
        """), encoding="utf-8")
        self.fake_wtype = self.root / "wtype"
        self.fake_curl = self.root / "curl"
        self.fake_gpg = self.root / "gpg"
        self.fake_systemctl = self.root / "systemctl"
        self.fake_wtype.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        self.fake_curl.write_text("#!/bin/sh\nexit 99\n", encoding="utf-8")
        self.fake_gpg.write_text(textwrap.dedent(f"""\
            #!/bin/sh
            case "$*" in
                *'--import-options show-only --import'*)
                    printf 'pub:-:255:22:AAAAAAAA:0:0::::::scESC:::::ed25519:::0:\\n'
                    printf 'fpr:::::::::{self.fingerprint}:\\n'
                    ;;
                *'--status-fd 1 --verify'*)
                    [ "${{GPG_FAIL_VERIFY:-}}" != 1 ] || exit 1
                    printf '[GNUPG:] VALIDSIG {self.fingerprint} {self.fingerprint}\\n'
                    ;;
                *'--import'*) ;;
                *) exit 64 ;;
            esac
        """).lstrip(), encoding="utf-8")
        self._write_fake_systemctl()
        for path in (self.fake_wtype, self.fake_curl, self.fake_gpg, self.fake_systemctl):
            path.chmod(0o755)
        self.environment = os.environ.copy()
        self.environment.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config_home),
            "XDG_DATA_HOME": str(self.data_home),
            "XDG_RUNTIME_DIR": str(self.runtime_home),
            "VANHYPRARCH_ALLOW_TEST_OVERRIDES": "1",
            "VANHYPRARCH_DICTATION_RESOURCE_DIR": str(self.resources),
            "VANHYPRARCH_VOXTYPE_METADATA": str(self.metadata),
            "VANHYPRARCH_VOXTYPE_SIGNING_KEY": str(self.key),
            "VANHYPRARCH_TEST_BINARY": str(self.fake_binary),
            "VANHYPRARCH_TEST_SIGNATURE": str(self.signature),
            "VANHYPRARCH_CURL_EXECUTABLE": str(self.fake_curl),
            "VANHYPRARCH_GPG_EXECUTABLE": str(self.fake_gpg),
            "VANHYPRARCH_WTYPE_EXECUTABLE": str(self.fake_wtype),
            "VANHYPRARCH_SYSTEMCTL_EXECUTABLE": str(self.fake_systemctl),
            "VANHYPRARCH_CPU_FLAGS": "avx2 fma bmi1 bmi2 f16c movbe",
            "VANHYPRARCH_HEALTH_TIMEOUT_SECONDS": "0.3",
            "VOXTYPE_MODEL_SOURCE_DIR": str(self.models_source),
            "SYSTEMCTL_STATE": str(self.root / "systemctl.state"),
            "SYSTEMCTL_LOG": str(self.root / "systemctl.log"),
        })

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def _write_model_manifest(self) -> None:
        records = []
        for model_id, filename, source, family, label in (
            ("small.en", "ggml-small.en.bin", self.small_en, "english", "Small — English"),
            ("small", "ggml-small.bin", self.small, "multilingual", "Small — Multilingual"),
        ):
            records.append(textwrap.dedent(f"""\
                [[models]]
                id = "{model_id}"
                label = "{label}"
                family = "{family}"
                filename = "{filename}"
                size = {source.stat().st_size}
                sha256 = "{digest(source)}"
                transport_url = "https://example.invalid/{filename}"
                provenance_url = "https://example.invalid/test-revision/{filename}"
            """))
        (self.resources / "models.toml").write_text(
            'schema_version = 1\nprovenance_revision = "test-revision"\n\n' + "\n".join(records),
            encoding="utf-8")

    def _write_fake_voxtype(self) -> None:
        self.fake_binary.write_text(textwrap.dedent("""\
            #!/usr/bin/python
            import json, os, pathlib, shutil, sys, tomllib

            args = sys.argv[1:]
            if args == ["--version"]:
                print("voxtype 0.0.0")
                raise SystemExit(0)
            if args[:1] == ["setup"]:
                model = args[args.index("--model") + 1]
                filename = "ggml-" + model + ".bin"
                generated = pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "voxtype/config.toml"
                generated.parent.mkdir(parents=True, exist_ok=True)
                generated.write_text('[audio]\\nmax_duration_secs = 60\\n\\n[whisper]\\nmodel = "base.en"\\nlanguage = "en"\\n')
                if os.environ.get("VOXTYPE_SETUP_CONFIG_OBSERVED"):
                    pathlib.Path(os.environ["VOXTYPE_SETUP_CONFIG_OBSERVED"]).write_text(json.dumps({
                        "config_home": os.environ["XDG_CONFIG_HOME"],
                        "config_home_mode": pathlib.Path(
                            os.environ["XDG_CONFIG_HOME"]).stat().st_mode & 0o777,
                        "data_home": os.environ["XDG_DATA_HOME"],
                        "generated": generated.read_text(),
                        "live_config_existed_during_setup": pathlib.Path(
                            os.environ["VOXTYPE_LIVE_CONFIG_PATH"]).exists(),
                    }))
                source = pathlib.Path(os.environ["VOXTYPE_MODEL_SOURCE_DIR"]) / filename
                target = pathlib.Path(os.environ["XDG_DATA_HOME"]) / "voxtype/models" / filename
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                raise SystemExit(0)
            if args[:1] == ["status"]:
                side_effect = os.environ.get("VOXTYPE_FIXTURE_ROLLBACK_SIDE_EFFECTS")
                if side_effect:
                    config_dir = pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "voxtype"
                    data_dir = pathlib.Path(os.environ["XDG_DATA_HOME"]) / "voxtype"
                    runtime_dir = pathlib.Path(os.environ["XDG_RUNTIME_DIR"]) / "voxtype"
                    config_dir.mkdir(parents=True, exist_ok=True)
                    data_dir.mkdir(parents=True, exist_ok=True)
                    runtime_dir.mkdir(parents=True, exist_ok=True)
                    (config_dir / "transaction-created").write_text("config side effect\\n")
                    (data_dir / "transaction-created").write_text("data side effect\\n")
                    (runtime_dir / "voxtype.lock").write_text("99999999\\n")
                    (runtime_dir / "version").write_text("0.0.0\\n")
                    if side_effect == "unsafe-config-symlink":
                        (config_dir / "unsafe-link").symlink_to(
                            pathlib.Path(os.environ["VOXTYPE_FIXTURE_OUTSIDE_TARGET"]))
                if os.environ.get("VOXTYPE_FIXTURE_HEALTH_FAIL") == "1":
                    raise SystemExit(1)
                config = pathlib.Path(os.environ["XDG_CONFIG_HOME"]) / "voxtype/config.toml"
                data = tomllib.loads(config.read_text())
                print(json.dumps({"alt": "idle", "class": "idle",
                    "model": data["whisper"]["model"], "backend": "unknown"}))
                raise SystemExit(0)
            if len(args) >= 4 and args[0] == "--config" and args[2:4] == ["config", "set"]:
                path = pathlib.Path(args[1]); key = args[4]; raw = args[5]
                table, field = key.split(".", 1)
                lines = path.read_text().splitlines(keepends=True)
                section = ""; changed = False
                if raw in ("true", "false"):
                    encoded = raw
                elif raw.isdigit():
                    encoded = raw
                else:
                    encoded = json.dumps(raw)
                for index, line in enumerate(lines):
                    stripped = line.strip()
                    if stripped.startswith("[") and stripped.endswith("]"):
                        section = stripped[1:-1]
                    elif section == table and stripped.startswith(field + " "):
                        newline = "\\n" if line.endswith("\\n") else ""
                        lines[index] = f"{field} = {encoded}{newline}"
                        changed = True
                if not changed:
                    raise SystemExit(2)
                path.write_text("".join(lines))
                raise SystemExit(0)
            if len(args) >= 5 and args[0] == "--config" and args[2:5] == ["config", "schema", "--json"]:
                data = tomllib.loads(pathlib.Path(args[1]).read_text())
                language = data["whisper"]["language"]
                if isinstance(language, list): language = ",".join(language)
                keys = [
                    {"key": "whisper.model", "value": data["whisper"]["model"]},
                    {"key": "whisper.language", "value": language},
                    {"key": "whisper.translate", "value": data["whisper"]["translate"]},
                    {"key": "audio.max_duration_secs", "value": data["audio"]["max_duration_secs"]},
                ]
                print(json.dumps({"keys": keys}))
                raise SystemExit(0)
            raise SystemExit(64)
        """).lstrip(), encoding="utf-8")
        self.fake_binary.chmod(0o755)

    def _write_fake_systemctl(self) -> None:
        self.fake_systemctl.write_text(textwrap.dedent("""\
            #!/bin/sh
            printf '%s\n' "$*" >> "$SYSTEMCTL_LOG"
            case "$*" in
                '--user is-active vanhyprarch-voxtype.service')
                    if [ -f "$SYSTEMCTL_STATE" ]; then cat "$SYSTEMCTL_STATE"; else printf 'inactive\n'; fi
                    ;;
                '--user stop vanhyprarch-voxtype.service')
                    [ "${SYSTEMCTL_FAIL_STOP:-}" != 1 ] || exit 1
                    [ -z "${MODEL_REQUIRED_BEFORE_STOP:-}" ] ||
                        [ -f "$MODEL_REQUIRED_BEFORE_STOP" ] || exit 77
                    printf 'inactive\n' > "$SYSTEMCTL_STATE"
                    ;;
                '--user start vanhyprarch-voxtype.service')
                    [ "${SYSTEMCTL_FAIL_START:-}" != 1 ] || exit 1
                    printf 'active\n' > "$SYSTEMCTL_STATE"
                    ;;
                '--user daemon-reload') ;;
                *) exit 64 ;;
            esac
        """).lstrip(), encoding="utf-8")

    def manager(self, *arguments: str, check: bool = True, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        environment = self.environment.copy()
        if extra_env:
            environment.update(extra_env)
        result = subprocess.run([str(MANAGER), *arguments], env=environment,
            text=True, capture_output=True, check=False)
        if check and result.returncode != 0:
            self.fail(f"manager failed ({result.returncode}): {result.stderr or result.stdout}")
        return result

    def assert_messages_in_order(self, output: str, messages: list[str]) -> None:
        position = -1
        for message in messages:
            next_position = output.find(message, position + 1)
            self.assertGreater(next_position, position,
                f"missing or out-of-order message {message!r} in:\n{output}")
            position = next_position

    def install(self) -> subprocess.CompletedProcess[str]:
        result = self.manager("install")
        self.assert_messages_in_order(result.stdout, [
            "Preparing Local Dictation installation...",
            "Verifying Voxtype release integrity...",
            "Downloading model Small — English (approximately 0 MiB)...",
            "Verifying model integrity...",
            "Installing Local Dictation integration...",
            "Starting Local Dictation service...",
            "Validating Local Dictation...",
            "Installed Local Dictation successfully.",
            "Local Dictation service is running and healthy.",
        ])
        self.assertEqual((self.root / "systemctl.state").read_text().strip(), "active")
        systemctl_log = (self.root / "systemctl.log").read_text()
        self.assertIn("--user daemon-reload\n", systemctl_log)
        self.assertIn("--user start vanhyprarch-voxtype.service\n", systemctl_log)
        self.assertNotIn("enable", systemctl_log)
        return result

    def test_install_start_and_health_failures_roll_back_fresh_state(self) -> None:
        for label, environment, expected_error in (
                ("start", {"SYSTEMCTL_FAIL_START": "1"}, "systemctl failed"),
                ("health", {"VOXTYPE_FIXTURE_HEALTH_FAIL": "1",
                    "VOXTYPE_FIXTURE_ROLLBACK_SIDE_EFFECTS": "safe"},
                    "did not become healthy after installation")):
            with self.subTest(label=label):
                failed = self.manager("install", check=False, extra_env=environment)
                self.assertNotEqual(failed.returncode, 0)
                self.assertIn(expected_error, failed.stderr)
                self.assertNotIn("Installed Local Dictation successfully.", failed.stdout)
                self.assertFalse((self.data_home / "vanhyprarch/components/dictation").exists())
                self.assertFalse((self.home / ".local/bin/voxtype").exists())
                self.assertFalse((self.config_home / "systemd/user/vanhyprarch-voxtype.service").exists())
                self.assertFalse((self.config_home / "voxtype").exists())
                self.assertFalse((self.data_home / "voxtype").exists())
                self.assertFalse((self.runtime_home / "voxtype").exists())
                status = json.loads(self.manager("status", "--json").stdout)
                self.assertEqual(status["state"], "not-installed")
                self.assertFalse(status["installed"])
                self.assertEqual(status["service_state"], "absent")
                self.assertEqual(status["marker"], "absent")
                (self.root / "systemctl.log").unlink(missing_ok=True)
                (self.root / "systemctl.state").unlink(missing_ok=True)

    def test_model_setup_isolates_upstream_generated_config(self) -> None:
        live_config = self.config_home / "voxtype/config.toml"
        observation = self.root / "setup-config-observation.json"
        self.assertFalse(live_config.exists())

        result = self.manager("install", extra_env={
            "VOXTYPE_SETUP_CONFIG_OBSERVED": str(observation),
            "VOXTYPE_LIVE_CONFIG_PATH": str(live_config),
        })

        observed = json.loads(observation.read_text())
        isolated_home = Path(observed["config_home"])
        self.assertNotEqual(isolated_home, self.config_home)
        self.assertTrue(isolated_home.name.startswith("vanhyprarch-voxtype-config."))
        self.assertEqual(observed["config_home_mode"], 0o700)
        self.assertEqual(observed["data_home"], str(self.data_home))
        self.assertFalse(observed["live_config_existed_during_setup"])
        self.assertIn('model = "base.en"', observed["generated"])
        self.assertIn("max_duration_secs = 60", observed["generated"])
        self.assertFalse(isolated_home.exists())
        self.assertEqual(live_config.read_bytes(), (self.resources / "config.toml").read_bytes())
        parsed = tomllib.loads(live_config.read_text())
        self.assertEqual(parsed["whisper"]["model"], "small.en")
        self.assertEqual(parsed["whisper"]["language"], "en")
        self.assertEqual(parsed["audio"]["max_duration_secs"], 120)
        self.assertFalse(parsed["hotkey"]["enabled"])
        self.assertEqual(parsed["output"]["driver_order"], ["wtype"])
        self.assertEqual(parsed["audio"]["feedback"], {
            "enabled": True, "theme": "default", "volume": 1.0})
        self.assertEqual((self.root / "systemctl.state").read_text().strip(), "active")
        status = json.loads(self.manager("status", "--json").stdout)
        self.assertEqual(status["state"], "installed")
        self.assertEqual(status["model"], "small.en")
        self.assert_messages_in_order(result.stdout, [
            "Downloading model Small — English (approximately 0 MiB)...",
            "Verifying model integrity...",
            "Installing Local Dictation integration...",
            "Starting Local Dictation service...",
            "Validating Local Dictation...",
            "Installed Local Dictation successfully.",
        ])

    def test_fresh_install_rollback_refuses_unsafe_generated_tree(self) -> None:
        outside = self.root / "outside-rollback-target"
        outside.write_text("preserve me\n")
        failed = self.manager("install", check=False, extra_env={
            "VOXTYPE_FIXTURE_HEALTH_FAIL": "1",
            "VOXTYPE_FIXTURE_ROLLBACK_SIDE_EFFECTS": "unsafe-config-symlink",
            "VOXTYPE_FIXTURE_OUTSIDE_TARGET": str(outside),
        })
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("rollback also failed", failed.stderr)
        self.assertIn("contains a symlink", failed.stderr)
        self.assertEqual(outside.read_text(), "preserve me\n")
        self.assertTrue((self.config_home / "voxtype/unsafe-link").is_symlink())
        self.assertTrue((self.data_home / "voxtype").exists())
        self.assertTrue((self.runtime_home / "voxtype").exists())
        self.assertFalse((self.data_home / "vanhyprarch/components/dictation").exists())

    def test_preexisting_user_config_is_refused_and_preserved(self) -> None:
        config = self.config_home / "voxtype/config.toml"
        config.parent.mkdir(parents=True)
        custom = b'[whisper]\nmodel = "base.en"\n# user-owned config\n'
        config.write_bytes(custom)

        failed = self.manager("install", check=False)

        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("existing Voxtype config needs review", failed.stderr)
        self.assertEqual(config.read_bytes(), custom)
        self.assertFalse((self.data_home / "voxtype").exists())
        self.assertFalse((self.home / ".local/bin/voxtype").exists())
        self.assertFalse((self.data_home / "vanhyprarch/components/dictation").exists())

    def test_failed_reinstall_restores_known_previous_state(self) -> None:
        self.install()
        config = self.config_home / "voxtype/config.toml"
        config.write_text(config.read_text().replace(
            "max_duration_secs = 120", "max_duration_secs = 60"))
        paths = (
            self.home / ".local/bin/voxtype",
            self.config_home / "systemd/user/vanhyprarch-voxtype.service",
            self.data_home / "vanhyprarch/components/dictation",
            config,
            self.data_home / "voxtype/models/ggml-small.en.bin",
        )
        before = {path: path.read_bytes() for path in paths}

        failed = self.manager("install", check=False,
            extra_env={"VOXTYPE_FIXTURE_HEALTH_FAIL": "1"})

        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("did not become healthy after installation", failed.stderr)
        self.assertNotIn("Installed Local Dictation successfully.", failed.stdout)
        self.assertEqual({path: path.read_bytes() for path in paths}, before)
        self.assertEqual((self.root / "systemctl.state").read_text().strip(), "active")
        status = json.loads(self.manager("status", "--json").stdout)
        self.assertEqual(status["state"], "installed")
        self.assertEqual(status["max_duration"], 60)

    def test_progress_is_flushed_and_model_download_precedes_blocking_work(self) -> None:
        module = load_manager_module()
        document = tomllib.loads((RESOURCES / "models.toml").read_text())
        model = next(item for item in document["models"] if item["id"] == "small")
        path_map = {"models": self.root / "progress-models"}
        events: list[str] = []

        def fake_run(*_args, **_kwargs):
            events.append("blocking-download")
            return subprocess.CompletedProcess([], 0, "", "")

        with mock.patch.object(module, "progress",
                side_effect=lambda message: events.append(message)), \
                mock.patch.object(module, "run", side_effect=fake_run), \
                mock.patch.object(module, "model_integrity", return_value="verified"):
            module.ensure_model(self.root / "voxtype", model, path_map)

        self.assertEqual(events, [
            "Downloading model Small — Multilingual (approximately 465 MiB)...",
            "blocking-download",
            "Verifying model integrity...",
        ])
        with mock.patch("builtins.print") as print_mock:
            module.progress("phase")
        print_mock.assert_called_once_with("phase", flush=True)

    def test_dependency_install_phase_precedes_blocking_package_operation(self) -> None:
        module = load_manager_module()
        events: list[str] = []

        def fake_run(*_args, **_kwargs):
            events.append("blocking-package-operation")
            return subprocess.CompletedProcess([], 0, "", "")

        with mock.patch.object(module, "dependency_state",
                side_effect=(["gnupg", "wtype"], [])), \
                mock.patch.object(module.sys.stdin, "isatty", return_value=True), \
                mock.patch("builtins.input", return_value="yes"), \
                mock.patch.object(module, "progress",
                    side_effect=lambda message: events.append(message)), \
                mock.patch.object(module, "run", side_effect=fake_run):
            module.ensure_dependencies()

        self.assertEqual(events, [
            "Installing optional official dependencies: gnupg, wtype...",
            "blocking-package-operation",
        ])

    def test_production_manifest_and_catalog_are_exact(self) -> None:
        document = tomllib.loads((RESOURCES / "models.toml").read_text())
        self.assertEqual(document["provenance_revision"], "5359861c739e955e79d9a303bcbc70fb988958b1")
        expected = {
            "tiny": ("ggml-tiny.bin", 77691713, "be07e048e1e599ad46341c8d2a135645097a538221678b7acdd1b1919c6e1b21"),
            "tiny.en": ("ggml-tiny.en.bin", 77704715, "921e4cf8686fdd993dcd081a5da5b6c365bfde1162e72b08d75ac75289920b1f"),
            "base": ("ggml-base.bin", 147951465, "60ed5bc3dd14eea856493d334349b405782ddcaf0028d4b5df4088345fba2efe"),
            "base.en": ("ggml-base.en.bin", 147964211, "a03779c86df3323075f5e796cb2ce5029f00ec8869eee3fdfb897afe36c6d002"),
            "small": ("ggml-small.bin", 487601967, "1be3a9b2063867b937e64e2ec7483364a79917e157fa98c5d94b5c1fffea987b"),
            "small.en": ("ggml-small.en.bin", 487614201, "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"),
            "medium": ("ggml-medium.bin", 1533763059, "6c14d5adee5f86394037b4e4e8b59f1673b6cee10e3cf0b11bbdbee79c156208"),
            "medium.en": ("ggml-medium.en.bin", 1533774781, "cc37e93478338ec7700281a7ac30a10128929eb8f427dda2e865faa8f6da4356"),
            "large-v3": ("ggml-large-v3.bin", 3095033483, "64d182b440b98d5203c4f9bd541544d84c605196c4f7b845dfa11fb23594d1e2"),
            "large-v3-turbo": ("ggml-large-v3-turbo.bin", 1624555275, "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"),
        }
        actual = {item["id"]: (item["filename"], item["size"], item["sha256"]) for item in document["models"]}
        self.assertEqual(actual, expected)
        for item in document["models"]:
            self.assertIn(document["provenance_revision"], item["provenance_url"])

    def test_status_and_catalog_without_component(self) -> None:
        status_result = self.manager("status", "--json")
        catalog_result = self.manager("catalog", "--json")
        status = json.loads(status_result.stdout)
        catalog = json.loads(catalog_result.stdout)
        self.assertEqual(len(status_result.stdout.splitlines()), 1)
        self.assertEqual(len(catalog_result.stdout.splitlines()), 1)
        for output in (status_result.stdout, catalog_result.stdout):
            self.assertNotIn("Preparing Local Dictation", output)
            self.assertNotIn("Downloading model", output)
            self.assertNotIn("Verifying model integrity", output)
        self.assertEqual(status["schema_version"], 1)
        self.assertEqual(status["state"], "not-installed")
        self.assertFalse(status["installed"])
        self.assertEqual(status["max_duration"], 120)
        self.assertEqual(catalog["defaults"]["max_duration"], 120)
        self.assertEqual(catalog["accelerations"], [{"id": "cpu", "label": "CPU"}])

    def test_malformed_installed_state_is_explicit_error(self) -> None:
        self.install()
        config = self.config_home / "voxtype/config.toml"
        config.write_text("not valid toml = [\n")
        status = json.loads(self.manager("status", "--json").stdout)
        self.assertEqual(status["state"], "error")
        self.assertTrue(status["installed"])
        self.assertTrue(status["errors"])
        self.assertIsNone(status["model"])
        self.assertFalse(status["matches_defaults"])

    def test_daemon_health_uses_runtime_state_not_backend_label(self) -> None:
        module = load_manager_module()
        valid = {"alt": "idle", "class": "idle", "model": "small.en",
            "backend": "unknown"}
        self.assertTrue(module.valid_daemon_status(valid, "small.en"))
        self.assertFalse(module.valid_daemon_status(
            {**valid, "model": "small"}, "small.en"))
        self.assertFalse(module.valid_daemon_status(
            {**valid, "alt": "error", "class": "error"}, "small.en"))
        self.assertFalse(module.valid_daemon_status(
            {**valid, "error": "daemon failure"}, "small.en"))

    def test_daemon_health_failures_and_bounded_retry(self) -> None:
        module = load_manager_module()
        binary = self.root / "health-binary"
        binary.write_bytes(b"managed cpu artifact\n")
        expected_digest = digest(binary)

        def health(service_states, results, timeout=0.3):
            clock = FakeClock()
            service_mock = mock.Mock(side_effect=service_states)
            run_mock = mock.Mock(side_effect=results)
            with mock.patch.object(module, "service_state", service_mock), \
                    mock.patch.object(module, "run", run_mock), \
                    mock.patch.object(module.time, "monotonic", clock.monotonic), \
                    mock.patch.object(module.time, "sleep", clock.sleep):
                outcome = module.daemon_healthy(binary, "small.en", expected_digest,
                    timeout_seconds=timeout, retry_interval=0.1)
            return outcome, clock, service_mock, run_mock

        malformed = subprocess.CompletedProcess([], 0, "{bad", "")
        failed = subprocess.CompletedProcess([], 1, "", "status failed")
        healthy = subprocess.CompletedProcess([], 0,
            json.dumps({"alt": "idle", "class": "idle", "model": "small.en",
                "backend": "unknown"}), "")
        wrong_model = subprocess.CompletedProcess([], 0,
            json.dumps({"alt": "idle", "model": "small"}), "")

        for label, result in (("malformed", malformed), ("command failure", failed),
                ("wrong model", wrong_model)):
            with self.subTest(label=label):
                outcome, clock, _, _ = health(lambda: "active", lambda *args, **kwargs: result)
                self.assertFalse(outcome)
                self.assertGreaterEqual(len(clock.sleeps), 2)

        outcome, clock, _, run_mock = health(lambda: "inactive", lambda *args, **kwargs: healthy)
        self.assertFalse(outcome)
        self.assertFalse(run_mock.called)
        self.assertLessEqual(clock.value, 0.4)

        service_values = iter(("inactive", "active", "active"))
        status_values = iter((failed, healthy))
        outcome, clock, service_mock, run_mock = health(
            lambda: next(service_values), lambda *args, **kwargs: next(status_values),
            timeout=1.0)
        self.assertTrue(outcome)
        self.assertEqual(service_mock.call_count, 3)
        self.assertEqual(run_mock.call_count, 2)
        self.assertEqual(len(clock.sleeps), 2)

        with mock.patch.object(module, "service_state") as service_mock:
            self.assertFalse(module.daemon_healthy(binary, "small.en", "0" * 64,
                timeout_seconds=0.1, retry_interval=0.1))
            service_mock.assert_not_called()

    def test_deployed_manager_has_no_checkout_dependency(self) -> None:
        deployed_manager = self.home / ".local/bin/vanhyprarch-dictation"
        deployed_manager.parent.mkdir(parents=True)
        shutil.copy2(MANAGER, deployed_manager)
        deployed_resources = self.data_home / "vanhyprarch/dictation"
        shutil.copytree(RESOURCES, deployed_resources)
        environment = os.environ.copy()
        environment.update({
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.config_home),
            "XDG_DATA_HOME": str(self.data_home),
        })
        result = subprocess.run([str(deployed_manager), "status", "--json"],
            env=environment, text=True, capture_output=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["state"], "not-installed")

    def test_binary_trust_failures_preserve_existing_binary(self) -> None:
        target = self.home / ".local/bin/voxtype"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"known-good binary\n")
        original_metadata = self.metadata.read_text()
        replacements = {
            "hash": ("VANHYPRARCH_VOXTYPE_SHA256=", "0" * 64, {}),
            "fingerprint": ("VANHYPRARCH_VOXTYPE_SIGNING_FINGERPRINT=", "B" * 40, {}),
            "version": ("VANHYPRARCH_VOXTYPE_VERSION=", "9.9.9", {}),
            "signature": (None, None, {"GPG_FAIL_VERIFY": "1"}),
        }
        for name, (prefix, value, extra) in replacements.items():
            with self.subTest(name=name):
                self.metadata.write_text(original_metadata)
                if prefix is not None:
                    lines = [prefix + value if line.startswith(prefix) else line
                        for line in original_metadata.splitlines()]
                    self.metadata.write_text("\n".join(lines) + "\n")
                failed = self.manager("install", check=False, extra_env=extra)
                self.assertNotEqual(failed.returncode, 0)
                self.assertEqual(target.read_bytes(), b"known-good binary\n")
                self.assertFalse((self.data_home / "vanhyprarch/components/dictation").exists())
        self.metadata.write_text(original_metadata)

    def test_install_apply_noop_rollback_and_uninstall(self) -> None:
        self.install()
        marker = self.data_home / "vanhyprarch/components/dictation"
        config = self.config_home / "voxtype/config.toml"
        manager_before = MANAGER.read_bytes()
        self.assertEqual(marker.read_bytes(), b"vanhyprarch-dictation-v1\n")
        self.assertEqual(tomllib.loads(config.read_text())["audio"]["max_duration_secs"], 120)
        (self.root / "systemctl.state").write_text("active\n")
        original = config.read_text()
        config.write_text(original.replace('[audio]\n', '# preserved comment\n[audio]\n'))
        applied = self.manager("apply", "--model", "small", "--language-mode", "selected",
            "--language", "it", "--language", "en", "--acceleration", "cpu",
            "--max-duration", "300", extra_env={
                "MODEL_REQUIRED_BEFORE_STOP": str(
                    self.data_home / "voxtype/models/ggml-small.bin")
            })
        self.assert_messages_in_order(applied.stdout, [
            "Preparing Local Dictation update...",
            "Downloading model Small — Multilingual (approximately 0 MiB)...",
            "Verifying model integrity...",
            "Preparing configuration...",
            "Restarting Local Dictation service...",
            "Validating Local Dictation...",
            "Applied dictation settings successfully.",
        ])
        updated = config.read_text()
        self.assertIn("# preserved comment", updated)
        parsed = tomllib.loads(updated)
        self.assertEqual(parsed["whisper"]["model"], "small")
        self.assertEqual(parsed["whisper"]["language"], ["it", "en"])
        self.assertEqual(parsed["audio"]["max_duration_secs"], 300)
        log_before = (self.root / "systemctl.log").read_text()
        result = self.manager("apply", "--model", "small", "--language-mode", "selected",
            "--language", "it", "--language", "en", "--acceleration", "cpu",
            "--max-duration", "300")
        self.assertIn("Reusing verified model Small — Multilingual.", result.stdout)
        self.assertNotIn("Downloading model Small — Multilingual", result.stdout)
        self.assertIn("service was not restarted", result.stdout)
        self.assertEqual((self.root / "systemctl.log").read_text(), log_before)

        before_failure = config.read_bytes()
        failed = self.manager("apply", "--model", "small", "--language-mode", "specific",
            "--language", "it", "--acceleration", "cpu", "--max-duration", "60",
            check=False, extra_env={"VOXTYPE_FIXTURE_HEALTH_FAIL": "1"})
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("did not become healthy", failed.stderr)
        self.assert_messages_in_order(failed.stdout, [
            "Preparing Local Dictation update...",
            "Reusing verified model Small — Multilingual.",
            "Preparing configuration...",
            "Restarting Local Dictation service...",
            "Validating Local Dictation...",
        ])
        self.assertNotIn("Applied dictation settings successfully.", failed.stdout)
        self.assertEqual(config.read_bytes(), before_failure)
        self.assertEqual((self.root / "systemctl.state").read_text().strip(), "active")

        config_dir = self.config_home / "voxtype"
        data_dir = self.data_home / "voxtype"
        service = self.config_home / "systemd/user/vanhyprarch-voxtype.service"
        cached_metadata = data_dir / "CACHEDIR.TAG"
        cached_metadata.write_text("Signature: test cache metadata\n")
        manager_resources = self.data_home / "vanhyprarch/dictation"
        manager_resources.mkdir(parents=True)
        resource_sentinel = manager_resources / "models.toml"
        resource_sentinel.write_text("immutable manager resource\n")
        uninstalled = self.manager("uninstall")
        self.assert_messages_in_order(uninstalled.stdout, [
            "Preparing Local Dictation uninstall...",
            "Stopping Local Dictation service...",
            "Removing Local Dictation and all Voxtype data...",
            "Uninstalled Local Dictation and removed all Voxtype data successfully.",
        ])
        self.assertFalse(marker.exists())
        self.assertFalse((self.home / ".local/bin/voxtype").exists())
        self.assertFalse(service.exists())
        self.assertFalse(config_dir.exists())
        self.assertFalse(data_dir.exists())
        self.assertFalse(cached_metadata.exists())
        self.assertEqual(MANAGER.read_bytes(), manager_before)
        self.assertEqual(resource_sentinel.read_text(), "immutable manager resource\n")
        self.assertTrue(self.fake_gpg.exists())
        self.assertTrue(self.fake_wtype.exists())
        status_result = self.manager("status", "--json")
        self.assertEqual(len(status_result.stdout.splitlines()), 1)
        self.assertNotIn("Preparing Local Dictation", status_result.stdout)
        status = json.loads(status_result.stdout)
        self.assertEqual(status["state"], "not-installed")
        self.assertFalse(status["installed"])
        self.assertEqual(status["marker"], "absent")

        self.install()
        fresh = tomllib.loads(config.read_text())
        self.assertEqual(fresh["whisper"]["model"], "small.en")
        self.assertEqual(fresh["whisper"]["language"], "en")
        self.assertEqual(fresh["audio"]["max_duration_secs"], 120)
        self.assertNotIn("# preserved comment", config.read_text())
        self.assertTrue((data_dir / "models/ggml-small.en.bin").exists())
        self.assertFalse((data_dir / "models/ggml-small.bin").exists())

    def test_all_multilingual_language_modes_and_three_language_selection(self) -> None:
        self.install()
        (self.root / "systemctl.state").write_text("active\n")
        config = self.config_home / "voxtype/config.toml"
        cases = (
            ("specific", ["it"], "it"),
            ("automatic", [], "auto"),
            ("selected", ["it", "en", "de"], ["it", "en", "de"]),
        )
        for mode, languages, expected in cases:
            with self.subTest(mode=mode):
                command = ["apply", "--model", "small", "--language-mode", mode]
                for language in languages:
                    command.extend(("--language", language))
                command.extend(("--acceleration", "cpu", "--max-duration", "120"))
                self.manager(*command)
                self.assertEqual(
                    tomllib.loads(config.read_text())["whisper"]["language"], expected)

    def test_config_target_and_ambiguous_array_editor_fail_closed(self) -> None:
        config = self.config_home / "voxtype/config.toml"
        config.parent.mkdir(parents=True)
        outside = self.root / "outside-config"
        outside.write_text("sentinel\n")
        config.symlink_to(outside)
        self.assertNotEqual(self.manager("install", check=False).returncode, 0)
        self.assertEqual(outside.read_text(), "sentinel\n")
        config.unlink()
        config.mkdir()
        self.assertNotEqual(self.manager("install", check=False).returncode, 0)
        config.rmdir()

        module = load_manager_module()
        candidate = self.root / "ambiguous.toml"
        candidate.write_text(
            '[audio]\nwhisper.language = "en"\n[whisper]\nlanguage = "en"\n')
        before = candidate.read_bytes()
        with self.assertRaises(module.ManagerError):
            module.replace_constrained_language(candidate, ["it", "en"])
        self.assertEqual(candidate.read_bytes(), before)

        regular = self.root / "foreign.toml"
        regular.write_text("value = 1\n")
        with mock.patch.object(module.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(module.ManagerError):
                module.require_regular(regular, "config", owner=True)

    def test_invalid_new_and_preexisting_models_fail_closed(self) -> None:
        self.install()
        target = self.data_home / "voxtype/models/ggml-small.bin"
        self.small.write_bytes(b"wrong newly downloaded bytes")
        failed = self.manager("apply", "--model", "small", "--language-mode", "specific",
            "--language", "it", "--acceleration", "cpu", "--max-duration", "120", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertFalse(target.exists())
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"pre-existing invalid bytes")
        failed = self.manager("apply", "--model", "small", "--language-mode", "specific",
            "--language", "it", "--acceleration", "cpu", "--max-duration", "120", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertEqual(target.read_bytes(), b"pre-existing invalid bytes")

    def test_apply_rejects_managed_binary_integrity_mismatch_before_stop(self) -> None:
        self.install()
        binary = self.home / ".local/bin/voxtype"
        config = self.config_home / "voxtype/config.toml"
        log = self.root / "systemctl.log"
        config_before = config.read_bytes()
        log_before = log.read_bytes() if log.exists() else b""
        binary.write_bytes(binary.read_bytes() + b"corruption\n")
        failed = self.manager("apply", "--model", "small.en",
            "--language-mode", "specific", "--language", "en",
            "--acceleration", "cpu", "--max-duration", "60", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("not the managed CPU artifact", failed.stderr)
        self.assertEqual(config.read_bytes(), config_before)
        self.assertEqual(log.read_bytes() if log.exists() else b"", log_before)

    def test_remove_unused_model_but_never_active_model(self) -> None:
        self.install()
        (self.root / "systemctl.state").write_text("active\n")
        self.manager("apply", "--model", "small", "--language-mode", "specific",
            "--language", "it", "--acceleration", "cpu", "--max-duration", "120")
        unused = self.data_home / "voxtype/models/ggml-small.en.bin"
        removed = self.manager("remove-model", "small.en")
        self.assert_messages_in_order(removed.stdout, [
            "Removing model Small — English...",
            "Removed model Small — English.",
        ])
        self.assertFalse(unused.exists())
        self.assertNotEqual(self.manager("remove-model", "small", check=False).returncode, 0)

    def test_language_duration_and_active_model_rejections(self) -> None:
        self.install()
        bad_commands = [
            ("--model", "small.en", "--language-mode", "specific", "--language", "it", "--acceleration", "cpu", "--max-duration", "120"),
            ("--model", "small", "--language-mode", "selected", "--language", "it", "--language", "it", "--acceleration", "cpu", "--max-duration", "120"),
            ("--model", "small", "--language-mode", "selected", "--language", "auto", "--language", "en", "--acceleration", "cpu", "--max-duration", "120"),
            ("--model", "small", "--language-mode", "selected", "--acceleration", "cpu", "--max-duration", "120"),
            ("--model", "small", "--language-mode", "specific", "--language", "xx", "--acceleration", "cpu", "--max-duration", "120"),
            ("--model", "small", "--language-mode", "automatic", "--acceleration", "cpu", "--max-duration", "0"),
        ]
        for command in bad_commands:
            with self.subTest(command=command):
                self.assertNotEqual(self.manager("apply", *command, check=False).returncode, 0)
        self.assertNotEqual(self.manager("apply", "--model", "small", "--language-mode", "automatic",
            "--acceleration", "vulkan", "--max-duration", "120", check=False).returncode, 0)
        self.assertNotEqual(self.manager("remove-model", "small.en", check=False).returncode, 0)

    def test_stop_failure_preserves_installed_payload(self) -> None:
        self.install()
        marker = self.data_home / "vanhyprarch/components/dictation"
        binary = self.home / ".local/bin/voxtype"
        config = self.config_home / "voxtype/config.toml"
        service = self.config_home / "systemd/user/vanhyprarch-voxtype.service"
        data_dir = self.data_home / "voxtype"
        config_before = config.read_bytes()
        apply_failed = self.manager("apply", "--model", "small",
            "--language-mode", "specific", "--language", "it",
            "--acceleration", "cpu", "--max-duration", "60", check=False,
            extra_env={"SYSTEMCTL_FAIL_STOP": "1"})
        self.assertNotEqual(apply_failed.returncode, 0)
        self.assertEqual(config.read_bytes(), config_before)
        data_before = {
            path.relative_to(data_dir): path.read_bytes()
            for path in data_dir.rglob("*") if path.is_file()
        }
        failed = self.manager("uninstall", check=False, extra_env={"SYSTEMCTL_FAIL_STOP": "1"})
        self.assertNotEqual(failed.returncode, 0)
        self.assertTrue(marker.exists())
        self.assertTrue(binary.exists())
        self.assertTrue(service.exists())
        self.assertEqual(config.read_bytes(), config_before)
        self.assertTrue((data_dir / "models/ggml-small.en.bin").exists())
        self.assertEqual({
            path.relative_to(data_dir): path.read_bytes()
            for path in data_dir.rglob("*") if path.is_file()
        }, data_before)

    def test_uninstall_refuses_symlinked_config_directory_without_deleting(self) -> None:
        self.install()
        marker = self.data_home / "vanhyprarch/components/dictation"
        binary = self.home / ".local/bin/voxtype"
        service = self.config_home / "systemd/user/vanhyprarch-voxtype.service"
        config_dir = self.config_home / "voxtype"
        data_dir = self.data_home / "voxtype"
        outside = self.root / "outside-config"
        outside.mkdir()
        sentinel = outside / "keep"
        sentinel.write_text("do not delete\n")
        shutil.rmtree(config_dir)
        config_dir.symlink_to(outside, target_is_directory=True)
        log = self.root / "systemctl.log"
        log_before = log.read_bytes() if log.exists() else b""

        failed = self.manager("uninstall", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("not a directory", failed.stderr)
        self.assertEqual(sentinel.read_text(), "do not delete\n")
        self.assertTrue(config_dir.is_symlink())
        self.assertTrue(data_dir.exists())
        self.assertTrue(marker.exists())
        self.assertTrue(binary.exists())
        self.assertTrue(service.exists())
        self.assertEqual(log.read_bytes() if log.exists() else b"", log_before)

    def test_uninstall_refuses_symlinked_data_directory_without_deleting(self) -> None:
        self.install()
        marker = self.data_home / "vanhyprarch/components/dictation"
        binary = self.home / ".local/bin/voxtype"
        service = self.config_home / "systemd/user/vanhyprarch-voxtype.service"
        config_dir = self.config_home / "voxtype"
        data_dir = self.data_home / "voxtype"
        outside = self.root / "outside-data"
        outside.mkdir()
        sentinel = outside / "keep"
        sentinel.write_text("do not delete\n")
        shutil.rmtree(data_dir)
        data_dir.symlink_to(outside, target_is_directory=True)
        log = self.root / "systemctl.log"
        log_before = log.read_bytes() if log.exists() else b""

        failed = self.manager("uninstall", check=False)
        self.assertNotEqual(failed.returncode, 0)
        self.assertIn("not a directory", failed.stderr)
        self.assertEqual(sentinel.read_text(), "do not delete\n")
        self.assertTrue(data_dir.is_symlink())
        self.assertTrue(config_dir.exists())
        self.assertTrue(marker.exists())
        self.assertTrue(binary.exists())
        self.assertTrue(service.exists())
        self.assertEqual(log.read_bytes() if log.exists() else b"", log_before)

    def test_recursive_tree_validation_rejects_wrong_symlinked_and_foreign_trees(self) -> None:
        module = load_manager_module()
        root = self.root / "xdg-root"
        target = root / "voxtype"
        target.mkdir(parents=True)
        (target / "config.toml").write_text("managed data\n")

        with self.assertRaises(module.ManagerError):
            module.validate_voxtype_tree(root, root / "other", "test tree")
        outside = self.root / "outside-tree"
        outside.write_text("keep\n")
        link = target / "linked-entry"
        link.symlink_to(outside)
        with self.assertRaises(module.ManagerError):
            module.validate_voxtype_tree(root, target, "test tree")
        self.assertEqual(outside.read_text(), "keep\n")
        link.unlink()
        with mock.patch.object(module.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(module.ManagerError):
                module.validate_voxtype_tree(root, target, "test tree")


if __name__ == "__main__":
    unittest.main()
