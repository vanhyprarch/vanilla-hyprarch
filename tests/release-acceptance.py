#!/usr/bin/env python3
"""Exercise the real operator helper with local bundles and controlled OS boundaries."""
from __future__ import annotations

import contextlib
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import signal
import shutil
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

PROJECT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT))
from release import acceptance as A, build
from install import release_update as driver, secret_service_preflight as provider
from install.update_bootstrap_integration import BootstrapIntegration, FILES

spec = importlib.util.spec_from_file_location('acceptance_fixture', PROJECT / 'tests/release-artifact.py')
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)


class AcceptanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='vanhyprarch-acceptance-fixture-')
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.base = Path(cls.temporary.name)
        repo = cls.base / 'repo'
        repo.mkdir()
        fixture.write_fixture(repo)
        for name in FILES:
            destination = repo / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(PROJECT / name, destination)
        # A representative real payload path; the helper never names this file.
        relative = 'home/.config/hypr/vanhyprarch/OMARCHY-NOTICE.txt'
        (repo / relative).parent.mkdir(parents=True, exist_ok=True)
        (repo / relative).write_text('fixture attribution\n')
        shutil.copyfile(PROJECT / 'deployment/ownership-v2.toml', repo / 'deployment/ownership-v2.toml')
        shutil.copyfile(PROJECT / 'deployment/service-policy-v1.toml', repo / 'deployment/service-policy-v1.toml')
        shutil.copyfile(PROJECT / 'release/release.toml', repo / 'release/release.toml')
        shutil.copyfile(PROJECT / 'release/migrations/registry.toml', repo / 'release/migrations/registry.toml')
        for path in (PROJECT/'release/migrations').glob('*.py'):
            shutil.copyfile(path,repo/'release/migrations'/path.name)
        fixture.git(repo, 'add', '.')
        fixture.git(repo, 'commit', '-qm', 'acceptance fixture')
        cls.commit = fixture.git(repo, 'rev-parse', 'HEAD')
        cls.bundle = cls.base / 'bundle'
        cls.bundle.mkdir()
        cls.metadata_path, cls.archive = build.build(repo, cls.commit, cls.bundle)
        cls.metadata = build.parse_metadata(cls.metadata_path.read_bytes())
        cls.metadata_hash = A.digest_file(cls.metadata_path)
        cls.archive_hash = A.digest_file(cls.archive)
        (cls.bundle / 'SHA256SUMS').write_text(cls.metadata_hash + '  release.json\n' +
                                              cls.archive_hash + '  ' + cls.archive.name + '\n')
        cls.updater_hash = hashlib.sha256(BootstrapIntegration(repo).build()).hexdigest()

    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.context = {'name': 'fixture', 'provider': {'uid': os.getuid(), 'environment': {
            'HOME': str(self.root), 'XDG_CONFIG_HOME': str(self.root / 'config'),
            'XDG_DATA_HOME': str(self.root / 'data'), 'XDG_DATA_DIRS': '/usr/local/share:/usr/share'}},
            'state': str(self.root / 'state'), 'cache': str(self.root / 'cache')}
        self.output = io.StringIO()
        self.capture = contextlib.redirect_stdout(self.output)
        self.capture.__enter__()
        self.addCleanup(self.capture.__exit__, None, None, None)

    def prepare(self, **changes):
        args = SimpleNamespace(bundle=self.bundle, output=self.root / 'inputs',
            installed_metadata=self.metadata_path, installed_updater_sha256=self.updater_hash,
            commit=self.commit, metadata_sha256=self.metadata_hash,
            archive_sha256=self.archive_hash, vm_host='acceptance-fixture', publisher=None)
        args.__dict__.update(changes)
        A.prepare(args)
        return args.output

    def completed_authority_documents(self, commit):
        from install import managed_deploy, create_once, system_integration
        # Use the actual writer: completed managed state omits transaction entirely.
        engine=managed_deploy.ManagedDeployment(source_root=PROJECT, release_id=commit,
            target=managed_deploy.TargetContext.build(home=self.root,
                config=self.root/'config',data=self.root/'data',state=self.root/'state'))
        desired,digest=engine._desired()
        managed=engine._state_document(operation='update',status='complete',
            release_digest=digest,records={key:value.record() for key,value in desired.items()})
        for record in managed['artifacts']:
            engine._validate_state_record(record,label='canonical completed fixture')
        lifecycle = create_once.CreateOnceInitializer._validate_lifecycle({
            'schema': create_once.LIFECYCLE_VERSION, 'seeds': ['foot-config'],
            'hooks': ['appearance-defaults'], 'pending': None})
        system = {'schema': system_integration.SCHEMA_VERSION,
            'official_packages': ['qt5-wayland'], 'system_artifacts': {},
            'services': {'desired': {'NetworkManager.service': 'enabled'}},
            'display_manager': {'state': 'sddm-baseline'}, 'bluez': {}}
        # This field is optional in the canonical upgrade baseline, unlike pending
        # in the create-once lifecycle. Verify the producers' actual contracts.
        baseline = system_integration.SystemIntegration._upgrade_baseline(
            SimpleNamespace(_read_state=lambda: system))
        self.assertIs(baseline, system)
        self.assertNotIn('transaction', managed)
        self.assertTrue(managed['artifacts'])
        self.assertNotIn('pending_system_artifact', system)
        return managed, lifecycle, system

    def test_prepare_verifies_real_bundle_and_packager_without_hostname_command(self):
        directory = self.prepare()
        _, record = A.load_record(directory)
        self.assertEqual(record['target_updater_sha256'], self.updater_hash)
        self.assertEqual(A.verify_inputs(directory, record, build)[0], self.metadata)
        self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
        self.assertTrue(all(p.stat().st_mode & 0o777 == 0o600 for p in directory.iterdir()))
        self.assertNotIn('"hostname"', (PROJECT / 'release/acceptance.py').read_text())

    def test_standalone_helper_imports_the_verified_zipapp_without_checkout_modules(self):
        updater=self.root/'updater'
        updater.write_bytes(BootstrapIntegration(self.base/'repo').build())
        updater.chmod(0o755)
        code='''import importlib.util, os, sys
from pathlib import Path
from unittest import mock
spec=importlib.util.spec_from_file_location('operator_acceptance',sys.argv[1])
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.UPDATER=Path(sys.argv[2])
read=module.read_file
# A temporary non-root fixture stands in for the independently trusted root file.
with mock.patch.object(module,'read_file',side_effect=lambda path,**kw:read(path,owner=(os.getuid(),os.getgid()),mode=kw.get('mode'))):
    modules=module.installed_modules(sys.argv[3])
for loaded in modules:
    assert loaded.__file__.startswith(sys.argv[2]+'/'),loaded.__file__
print('PASS: standalone verified zipapp imports')
'''
        result=subprocess.run([sys.executable,'-I','-B','-c',code,str(PROJECT/'release/acceptance.py'),
                               str(updater),self.updater_hash],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('PASS:',result.stdout)

    def test_prepare_rejects_wrong_independent_pins_before_output(self):
        for changes in ({'archive_sha256': '0'*64}, {'metadata_sha256': '0'*64}, {'commit': '0'*40}):
            with self.subTest(changes=changes), self.assertRaises(A.Failure):
                self.prepare(**changes)
        self.assertFalse((self.root / 'inputs').exists())

    def test_prepare_existing_destination_is_never_overwritten(self):
        directory = self.prepare()
        before = (directory / 'approved.json').read_bytes()
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual(before, (directory / 'approved.json').read_bytes())

    def test_prepare_refuses_checkout_or_original_build_output(self):
        for output in (PROJECT/'forbidden-acceptance-output',self.bundle/'forbidden-output'):
            with self.subTest(output=output),self.assertRaises(A.Failure):
                self.prepare(output=output)
            self.assertFalse(output.exists())

    def test_changed_output_copy_cannot_replace_independent_approval(self):
        copy_file=shutil.copyfile
        output=self.root/'inputs'
        def copy(source,destination,*args,**kwargs):
            result=copy_file(source,destination,*args,**kwargs)
            if Path(destination)==output/self.archive.name:
                Path(destination).write_bytes(b'changed copied archive')
            return result
        with mock.patch.object(A.shutil,'copyfile',side_effect=copy),self.assertRaises(A.Failure):
            self.prepare()
        self.assertFalse(output.exists())

    def test_input_tampering_and_extra_files_fail(self):
        directory = self.prepare()
        (directory / 'extra').write_text('unexpected')
        with self.assertRaises(A.Failure): A.load_record(directory)
        (directory / 'extra').unlink()
        (directory / 'release.json').write_text('invalid')
        with self.assertRaises(A.Failure): A.load_record(directory)

    def test_stale_or_changed_helper_is_rejected(self):
        directory=self.prepare()
        (directory/'acceptance.py').write_text('print("stale helper")\n')
        with self.assertRaises(A.Failure): A.load_record(directory)

    def test_checksum_inventory_cannot_reference_unrelated_files(self):
        directory = self.prepare()
        _, record = A.load_record(directory)
        (directory / 'SHA256SUMS').write_text('0'*64 + '  /etc/shadow\n')
        with self.assertRaises(A.Failure): A.verify_inputs(directory, record, build)

    def test_real_manifest_resolves_user_files_without_reading_keyrings(self):
        paths = A.preference_paths(self.archive, self.metadata, A.PreferenceTarget(self.context))
        self.assertIn(self.root / 'config/vanhyprarch/overrides/hyprland.lua', paths)
        self.assertIn(self.root / 'config/foot/foot.ini', paths)
        self.assertFalse(any('keyrings' in str(path) for path in paths))
        self.assertFalse(any('Wallpapers' in str(path) for path in paths))

    def test_notice_path_is_payload_authority_not_a_second_expected_filename_list(self):
        text = A.archive_text(self.archive, self.metadata,
                              'home/.config/hypr/vanhyprarch/OMARCHY-NOTICE.txt')
        self.assertEqual(text, 'fixture attribution\n')
        with self.assertRaises(KeyError):
            A.archive_text(self.archive, self.metadata,
                           'home/.config/quickshell/vanhyprarch/OMARCHY-NOTICE.txt')
        self.assertNotIn('OMARCHY-NOTICE', (PROJECT / 'release/acceptance.py').read_text())

    def test_preference_path_traversal_and_symlinks_are_rejected(self):
        target = A.PreferenceTarget(self.context)
        for suffix in ('../private', '/etc/shadow', 'foo/*'):
            with self.subTest(suffix=suffix), self.assertRaises(A.Failure):
                target.resolve('${XDG_CONFIG_HOME:-$HOME/.config}/' + suffix)
        (self.root / 'link').symlink_to('/etc/passwd')
        with self.assertRaises(A.Failure): A.read_file(self.root / 'link')

    def test_report_private_even_under_open_mask_and_never_overwritten(self):
        path = self.root / 'report.txt'
        old = os.umask(0)
        try:
            with A.private_report(path) as stream: stream.write('original\n')
        finally:
            os.umask(old)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(FileExistsError), A.private_report(path): pass
        self.assertEqual(path.read_text(), 'original\n')

    def test_scoped_privileged_mask_creates_exact_staging_permissions_and_restores(self):
        original = os.umask(0o077)
        try:
            with A.privileged_mask(A.Checks()):
                path = self.root / 'source'
                path.mkdir(mode=0o755)
                self.assertEqual(path.stat().st_mode & 0o777, 0o755)
            observed = os.umask(0o077)
            self.assertEqual(observed, 0o077)
            self.assertIn('inherited 0077; scoped effective 0022', self.output.getvalue())
        finally:
            os.umask(original)

    def test_scoped_mask_restores_after_interruption(self):
        original = os.umask(0o077)
        try:
            with self.assertRaises(KeyboardInterrupt), A.privileged_mask(A.Checks()):
                raise KeyboardInterrupt
            self.assertEqual(os.umask(0o077), 0o077)
        finally:
            os.umask(original)

    def test_real_subprocess_failure_retains_exit_code_and_separate_output(self):
        with self.assertRaises(A.Failure) as caught:
            A.Checks().run([sys.executable, '-B', '-c',
                           'import sys; print("out"); print("err",file=sys.stderr); sys.exit(7)'])
        self.assertEqual(caught.exception.code, 7)
        self.assertIn('STDOUT:\nout', self.output.getvalue())
        self.assertIn('STDERR:\nerr', self.output.getvalue())

    def test_missing_executable_is_127_and_timeout_is_124(self):
        with self.assertRaises(A.Failure) as caught:
            A.Checks().run([str(self.root/'missing-command')])
        self.assertEqual(caught.exception.code,127)
        with self.assertRaises(A.Failure) as caught:
            A.Checks().run([sys.executable,'-B','-c','import time; time.sleep(3)'],timeout=0.02)
        self.assertEqual(caught.exception.code,124)

    def test_interrupted_child_gets_native_cleanup_opportunity(self):
        stage=self.root/'child-staging'
        code='''from pathlib import Path
import shutil, sys, time
p=Path(sys.argv[1])
try:
    p.mkdir()
    print('ready',flush=True)
    time.sleep(5)
finally:
    shutil.rmtree(p)
'''
        with self.assertRaises(A.Failure) as caught:
            A.Checks().run([sys.executable,'-B','-c',code,str(stage)],timeout=0.2)
        self.assertEqual(caught.exception.code,124)
        self.assertFalse(stage.exists())
        self.assertIn('ready',self.output.getvalue())

    def runtime_runner(self, *, payload='pong\n', stderr='', logs='INFO: Configuration Loaded\n', failure=0):
        calls = []
        def run(argv, **options):
            calls.append((argv, options))
            output = ''
            error = ''
            if argv[:2] == ['/usr/bin/locale', '-a']: output = 'C\nC.utf8\n'
            elif argv[:2] == ['/usr/bin/locale', 'charmap']: output = 'UTF-8\n'
            elif argv[0] == '/usr/bin/qs':
                self.assertEqual(options['env']['LC_ALL'], 'C.utf8')
                output = payload if argv[1] == 'ipc' else logs
                error = stderr
                if failure: raise A.Failure('fixture failure', failure)
            return subprocess.CompletedProcess(argv, 0, output, error)
        return calls, run

    def test_utf8_ipc_stderr_warning_is_not_response_content(self):
        checks = A.Checks()
        calls, run = self.runtime_runner(stderr='WARN qt: unrelated warning\n')
        with mock.patch.object(checks, 'run', side_effect=run), mock.patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='fixture'):
            A.runtime_checks(checks)
        self.assertTrue(checks.warnings)
        self.assertEqual(checks.code, 0)
        self.assertTrue(any(argv[1] == 'log' for argv, _ in calls if argv[0] == '/usr/bin/qs'))

    def test_wrong_pong_real_qml_errors_and_nonzero_exit_fail(self):
        for changes in ({'payload':'wrong\n'}, {'logs':'ERROR: TypeError: bad component\n'}, {'failure':9}):
            checks = A.Checks()
            _, run = self.runtime_runner(**changes)
            with self.subTest(changes=changes), mock.patch.object(checks,'run',side_effect=run), \
                    mock.patch.dict(os.environ, HYPRLAND_INSTANCE_SIGNATURE='fixture'), self.assertRaises(A.Failure):
                A.runtime_checks(checks)

    def test_missing_utf8_does_not_run_qt_or_modify_locales(self):
        checks = A.Checks()
        with mock.patch.object(checks,'run',return_value=SimpleNamespace(stdout='C\nPOSIX\n')) as run:
            with self.assertRaises(A.Failure): A.utf8_environment(checks)
        self.assertEqual(run.call_count,1)

    def service_runner(self, lines):
        return lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0,
            lines if 'list-units' in argv and '--user' not in argv else '', '')

    def test_four_unrelated_tpm_failures_are_warnings_not_acceptance_failure(self):
        names = ('systemd-pcrlogin@1000.service','systemd-pcrlogin@963.service',
                 'systemd-pcrproduct.service','systemd-tpm2-setup-early.service')
        checks = A.Checks()
        policy = {'service':[{'scope':'system','name':'NetworkManager.service','default_install':True}]}
        with mock.patch.object(checks,'run',side_effect=self.service_runner('\n'.join(names))):
            failed = A.failed_services(policy,checks)
        self.assertEqual(len(failed),4)
        self.assertEqual(len(checks.warnings),4)
        self.assertEqual(checks.code,0)

    def test_required_failure_fails_even_if_preexisting_optional_failure_warns(self):
        checks = A.Checks()
        policy = {'service':[{'scope':'system','name':'NetworkManager.service','default_install':True},
                             {'scope':'system','name':'cups.service','default_install':False}]}
        with mock.patch.object(checks,'run',side_effect=self.service_runner('NetworkManager.service\ncups.service\n')):
            A.failed_services(policy,checks,{'system:NetworkManager.service':'present'})
        self.assertEqual(checks.code,1)
        self.assertEqual(len(checks.warnings),1)

    def test_plan_requires_three_authorities_exact_target_and_migrations(self):
        source = {**self.metadata,'version':'v1.0.0-rc0'}
        plan = {'source':source['version'],'target':self.metadata['version'],
                'target_sha256':self.archive_hash,'migrations':[],
                'authorities':{'system-integration':'{"blocked":false}',
                               'managed-deployment':'preserve\tmanaged', 'create-once':'preserve-existing\tuser'}}
        self.assertEqual(A.check_plan(json.dumps(plan),source,self.metadata),plan)
        for changes in ({'target_sha256':'0'*64}, {'authorities':{}}, {'migrations':[{'id':1}]}):
            with self.subTest(changes=changes), self.assertRaises(A.Failure):
                A.check_plan(json.dumps({**plan,**changes}),source,self.metadata)

    def test_graphical_gate_rejects_root_ssh_no_tty_and_wrong_host_before_capture(self):
        capture = mock.Mock()
        for patcher in (mock.patch.object(A.os,'getuid',return_value=0),
                        mock.patch.object(A.sys.stdin,'isatty',return_value=False),
                        mock.patch.dict(os.environ,SSH_CONNECTION='fixture')):
            with patcher, self.assertRaises(A.Failure):
                A.graphical_context({'vm_host':'different-host'},capture)
        capture.assert_not_called()

    def test_graphical_context_is_captured_before_sudo_without_invented_paths(self):
        uid = 1234
        env = {'XDG_SESSION_TYPE':'wayland','WAYLAND_DISPLAY':'wayland-fixture',
            'HYPRLAND_INSTANCE_SIGNATURE':'fixture', 'XDG_RUNTIME_DIR':'/run/user/1234',
            'DBUS_SESSION_BUS_ADDRESS':'unix:path=/run/user/1234/bus',
            'XDG_CONFIG_HOME':'/srv/fixture/config','XDG_DATA_HOME':'/srv/fixture/data',
            'XDG_STATE_HOME':'/srv/fixture/state','XDG_CACHE_HOME':'/srv/fixture/cache'}
        with mock.patch.dict(os.environ,env,clear=True), mock.patch.object(A.os,'getuid',return_value=uid), \
                mock.patch.object(A.sys.stdin,'isatty',return_value=True), \
                mock.patch.object(A.os,'uname',return_value=SimpleNamespace(nodename='acceptance-fixture')), \
                mock.patch.object(A.Path,'lstat',side_effect=[SimpleNamespace(st_mode=mode,st_uid=uid)
                    for mode in (0o40700,0o140600,0o140600)]), \
                mock.patch.object(A.pwd,'getpwuid',return_value=SimpleNamespace(pw_name='fixture',pw_dir='/srv/fixture')):
            context=A.graphical_context({'vm_host':'acceptance-fixture'},provider.capture_context)
            self.assertEqual(context['provider']['environment']['XDG_CONFIG_HOME'],env['XDG_CONFIG_HOME'])
            self.assertEqual(context['state'],env['XDG_STATE_HOME'])
            os.environ['DBUS_SESSION_BUS_ADDRESS']='unix:path=/wrong/bus'
            with self.assertRaises(A.Failure):
                A.graphical_context({'vm_host':'acceptance-fixture'},provider.capture_context)

    def test_native_staging_plan_cleanup_and_after_state_on_failure_or_interrupt(self):
        directory=self.prepare()
        _,record=A.load_record(directory)
        native_root=self.root/'native-root'
        (native_root/'run').mkdir(parents=True)
        store=driver.BundleStore(native_root,uid=os.getuid(),gid=os.getgid())
        user=SimpleNamespace(name='fixture',xdg_config=self.root/'config',xdg_data=self.root/'data',
            xdg_state=self.root/'state',xdg_cache=self.root/'cache',provider_context=self.context['provider'])
        api=SimpleNamespace(TargetUser=SimpleNamespace(resolve=lambda *args,**kw:user),BundleStore=lambda:store)
        before={'identity':self.metadata,'files':{'fixture':'unchanged'}}
        read=A.read_file
        glob=Path.glob
        def reads(path,**kwargs):
            return read(directory/'installed-release.json',**kwargs) if str(path)=='/usr/share/vanhyprarch/release.json' else read(path,**kwargs)
        def globs(path,pattern,**kwargs):
            return glob(native_root/'run',pattern,**kwargs) if path==Path('/run') else glob(path,pattern,**kwargs)
        plan={'source':self.metadata['version'],'target':self.metadata['version'],
              'target_sha256':self.archive_hash,'migrations':[],
              'authorities':{'system-integration':'{"blocked":false}',
                             'managed-deployment':'preserve\tmanaged','create-once':'preserve-existing\tuser'}}
        for failure,code in ((None,0),(A.Failure('native PLAN failed',8),8),(KeyboardInterrupt(),130)):
            checks=A.Checks()
            def run(argv,**kwargs):
                self.assertEqual(argv[3],'plan')
                self.assertNotIn('apply',argv)
                self.assertTrue(Path(argv[argv.index('--release-metadata')+1]).is_relative_to(native_root/'run'))
                self.assertTrue(Path(argv[argv.index('--release-artifact')+1]).is_relative_to(native_root/'run'))
                staged=Path(argv[2]).parents[1]
                self.assertEqual(staged.stat().st_mode&0o777,0o755)
                if failure: raise failure
                return subprocess.CompletedProcess(argv,0,json.dumps(plan),'')
            with self.subTest(code=code), mock.patch.object(checks,'run',side_effect=run), \
                    mock.patch.object(A,'root_snapshot',return_value=(before,None)) as snapshot, \
                    mock.patch.object(A,'read_file',side_effect=reads),mock.patch.object(Path,'glob',new=globs), \
                    A.privileged_mask(checks):
                A.root_checks(directory,record,'preflight',self.context,checks,build,api,None)
                self.assertEqual(checks.code,code,self.output.getvalue())
                self.assertEqual(snapshot.call_count,2)
                self.assertEqual(list((native_root/'run').iterdir()),[])

    def test_changed_staged_identity_never_executes_target_code(self):
        from dataclasses import replace
        directory=self.prepare()
        _,record=A.load_record(directory)
        native_root=self.root/'native-root'
        (native_root/'run').mkdir(parents=True)
        store=driver.BundleStore(native_root,uid=os.getuid(),gid=os.getgid())
        prepare=store.prepare
        def changed(*args,**kwargs):
            bundle=prepare(*args,**kwargs)
            return replace(bundle,metadata={**bundle.metadata,'commit':'0'*40})
        api=SimpleNamespace(TargetUser=SimpleNamespace(resolve=lambda *a,**kw:object()),BundleStore=lambda:store)
        read=A.read_file
        glob=Path.glob
        def reads(path,**kwargs):
            return read(directory/'installed-release.json',**kwargs) if str(path)=='/usr/share/vanhyprarch/release.json' else read(path,**kwargs)
        def globs(path,pattern,**kwargs):
            return glob(native_root/'run',pattern,**kwargs) if path==Path('/run') else glob(path,pattern,**kwargs)
        checks=A.Checks()
        with mock.patch.object(store,'prepare',side_effect=changed), \
                mock.patch.object(A,'root_snapshot',return_value=({'identity':self.metadata},None)), \
                mock.patch.object(A,'read_file',side_effect=reads),mock.patch.object(Path,'glob',new=globs), \
                mock.patch.object(checks,'run') as run,A.privileged_mask(checks):
            A.root_checks(directory,record,'preflight',self.context,checks,build,api,None)
        run.assert_not_called()
        self.assertEqual(checks.code,1)
        self.assertEqual(list((native_root/'run').iterdir()),[])

    def test_native_staging_state_mutation_is_a_real_failure(self):
        directory=self.prepare()
        _,record=A.load_record(directory)
        # Fail before staging; the finally comparison must still retain the actual change.
        before={'identity':self.metadata,'files':{'state':'before'}}
        after={'identity':self.metadata,'files':{'state':'after'}}
        api=SimpleNamespace(TargetUser=SimpleNamespace(resolve=lambda *a,**kw:object()),
            BundleStore=lambda:SimpleNamespace(prepare=mock.Mock(side_effect=AssertionError('not reached'))))
        checks=A.Checks()
        read=A.read_file
        with mock.patch.object(A,'root_snapshot',side_effect=[(before,None),(after,None)]), \
                mock.patch.object(A,'read_file',side_effect=lambda p,**kw: b'wrong' if str(p)=='/usr/share/vanhyprarch/release.json' else read(p,**kw)), \
                mock.patch.object(A.Path,'glob',return_value=iter(())):
            A.root_checks(directory,record,'preflight',self.context,checks,build,api,None)
        self.assertEqual(checks.code,1)
        self.assertIn('installed state changed during diagnostics',self.output.getvalue())

    def test_post_upgrade_runs_actual_validator_vectors_under_correct_identities(self):
        directory=self.prepare()
        _,record=A.load_record(directory)
        native_root=self.root/'native-root'
        (native_root/'run').mkdir(parents=True)
        store=driver.BundleStore(native_root,uid=os.getuid(),gid=os.getgid())
        user=SimpleNamespace(name='fixture',home=self.root,uid=os.getuid(),gid=os.getgid(),groups=(os.getgid(),),
            provider_context=self.context['provider'])
        api=SimpleNamespace(TargetUser=SimpleNamespace(resolve=lambda *a,**kw:user),BundleStore=lambda:store,
                            AuthorityRunner=SimpleNamespace(_user_environment=lambda user:{'XDG_STATE_HOME':self.context['state']}))
        before={'identity':self.metadata,'files':{'fixture':'unchanged'}}
        read=A.read_file
        glob=Path.glob
        def reads(path,**kwargs):
            return read(directory/'release.json',**kwargs) if str(path)=='/usr/share/vanhyprarch/release.json' else read(path,**kwargs)
        def globs(path,pattern,**kwargs):
            return glob(native_root/'run',pattern,**kwargs) if path==Path('/run') else glob(path,pattern,**kwargs)
        checks=A.Checks()
        calls=[]
        def run(argv,**options):
            calls.append((argv,options))
            self.assertIn('validate',argv)
            self.assertNotIn('apply',argv)
            self.assertNotIn('initialize',argv)
            return subprocess.CompletedProcess(argv,0,'valid fixture','')
        with mock.patch.object(checks,'run',side_effect=run), \
                mock.patch.object(A,'root_snapshot',return_value=(before,object())) as snapshot, \
                mock.patch.object(A,'validate_publication') as publication, \
                mock.patch.object(A,'read_file',side_effect=reads),mock.patch.object(Path,'glob',new=globs), \
                A.privileged_mask(checks):
            A.root_checks(directory,record,'post-upgrade',self.context,checks,build,api,None)
        self.assertEqual(checks.code,0,self.output.getvalue())
        self.assertEqual(snapshot.call_count,2)
        publication.assert_called_once()
        self.assertEqual(len(calls),3)
        self.assertNotIn('user',calls[0][1])
        self.assertEqual(calls[1][1]['user'],os.getuid())
        self.assertEqual(calls[2][1]['env']['XDG_STATE_HOME'],self.context['state'])
        self.assertEqual(list((native_root/'run').iterdir()),[])

    def test_installed_state_inspection_reuses_real_provenance_and_security_readers(self):
        from release import distribution as D
        from install import signed_distribution as signed
        from install.update_bootstrap_integration import provenance_bytes
        import base64
        key=self.root/'TEST-ONLY.key'
        public=self.root/'TEST-ONLY.pub'
        subprocess.run(['/usr/bin/minisign','-G','-W','-s',str(key),'-p',str(public)],capture_output=True,check=True)
        key.chmod(0o600)
        public_key=public.read_text().splitlines()[1]
        now=int(A.time.time())
        issued=A.time.strftime('%Y-%m-%dT%H:%M:%SZ',A.time.gmtime(now-60))
        root_payload=D.make_root(public_key,issued_at=issued)
        minisign=D.Minisign()
        envelope=D.envelope(root_payload,[(public_key,minisign.sign(root_payload,key,public_key))])
        anchor=D.canonical({'schema':1,'public_key':public_key,'root_sha256':D.digest(root_payload),
                            'root':base64.b64encode(envelope).decode()})
        repo=self.root/'source'
        shutil.copytree(self.base/'repo',repo)
        (repo/'release/trust.json').write_bytes(anchor)
        payload=BootstrapIntegration(repo).build()
        filesystem=self.root/'system'
        filesystem.mkdir()
        state=self.root/'user-state'
        user=SimpleNamespace(home=self.root,xdg_state=state,uid=os.getuid(),gid=os.getgid())
        def put(relative,data,mode=0o600):
            path=filesystem/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
            return path
        put('usr/share/vanhyprarch/release.json',self.metadata_path.read_bytes(),0o644)
        updater=put('usr/local/bin/vanhyprarch-update',payload,0o755)
        provenance=json.loads(provenance_bytes(payload))
        provenance['distribution_initialized']=True
        put('var/lib/vanhyprarch/update-bootstrap-v1.json',D.canonical(provenance))
        root=D.TrustedRoot.initial(envelope,pinned_public_key=public_key,pinned_root_sha256=D.digest(root_payload),minisign=minisign,clock=D.Clock(now))
        put('var/lib/vanhyprarch/distribution-security-v1.json',D.canonical(
            {'schema':1,'roots':[],'state':D.parse_state(D.initial_state(root)),'authorization':None}))
        managed, lifecycle, system = self.completed_authority_documents(self.commit)
        put('var/lib/vanhyprarch/system-integration-v1.json',D.canonical(system))
        put('var/lib/vanhyprarch/sddm-login/provenance-v1.json',b'{}')
        (filesystem/'var/lib/vanhyprarch').chmod(0o700)
        for name,value in (('managed-deployment-v1.json',managed),
                           ('create-once-lifecycle-v1.json',lifecycle)):
            path=state/'vanhyprarch'/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(D.canonical(value))
            path.chmod(0o600)
        api=SimpleNamespace(SecurityStore=lambda journal:signed.SecurityStore(journal,anchor=anchor,minisign=minisign,now=lambda:now))
        with mock.patch.object(signed.SecurityStore,'start',side_effect=AssertionError('mutation forbidden')), \
                mock.patch.object(signed.SecurityStore,'publish',side_effect=AssertionError('mutation forbidden')):
            before,_=A.root_snapshot(user,driver,api,root=filesystem,uid=os.getuid(),gid=os.getgid())
            after,_=A.root_snapshot(user,driver,api,root=filesystem,uid=os.getuid(),gid=os.getgid())
        self.assertEqual(before,after)
        self.assertEqual(before['identity'],self.metadata)
        self.assertFalse((filesystem/'var/lib/vanhyprarch/update/journal.json').exists())
        managed_path=state/'vanhyprarch/managed-deployment-v1.json'
        lifecycle_path=state/'vanhyprarch/create-once-lifecycle-v1.json'
        system_path=filesystem/'var/lib/vanhyprarch/system-integration-v1.json'
        cases = ((managed_path, {**managed, 'status': 'partial'}),
                 (managed_path, {**managed, 'transaction': {'phase': 'prepared'}}),
                 (lifecycle_path, {**lifecycle, 'pending': {'kind': 'seed', 'id': 'new-seed'}}),
                 (system_path, {**system, 'pending_system_artifact': {'id': 'terminal-fallback'}}))
        for path, pending_state in cases:
            with self.subTest(state=pending_state):
                original=path.read_bytes()
                path.write_bytes(D.canonical(pending_state))
                try:
                    with self.assertRaisesRegex(A.Failure, 'incomplete authority transaction'):
                        A.root_snapshot(user,driver,api,root=filesystem,uid=os.getuid(),gid=os.getgid())
                finally:
                    path.write_bytes(original)
        updater.chmod(0o644)
        with self.assertRaises((A.Failure,ValueError)):
            A.root_snapshot(user,driver,api,root=filesystem,uid=os.getuid(),gid=os.getgid())

    def signed_fixture(self):
        from release import distribution as D
        from install import signed_distribution as signed
        import base64
        key=self.root/'TEST-ONLY.key'
        public=self.root/'TEST-ONLY.pub'
        subprocess.run(['/usr/bin/minisign','-G','-W','-s',str(key),'-p',str(public)],capture_output=True,check=True)
        key.chmod(0o600)
        public_key=public.read_text().splitlines()[1]
        now=int(A.time.time())
        issued=A.time.strftime('%Y-%m-%dT%H:%M:%SZ',A.time.gmtime(now-60))
        root_payload=D.make_root(public_key,issued_at=issued)
        minisign=D.Minisign()
        envelope=D.envelope(root_payload,[(public_key,minisign.sign(root_payload,key,public_key))])
        anchor=D.canonical({'schema':1,'public_key':public_key,'root_sha256':D.digest(root_payload),
                            'root':base64.b64encode(envelope).decode()})
        repo=self.root/'signed-repo'
        shutil.copytree(self.base/'repo',repo)
        (repo/'release/trust.json').write_bytes(anchor)
        fixture.git(repo,'add','.')
        fixture.git(repo,'commit','-qm','TEST-ONLY acceptance trust')
        output=self.root/'signed-bundle'
        output.mkdir()
        metadata,archive=build.build(repo,fixture.git(repo,'rev-parse','HEAD'),output)
        target=build.parse_metadata(metadata.read_bytes())
        (output/'SHA256SUMS').write_text(A.digest_file(metadata)+'  release.json\n'+A.digest_file(archive)+'  '+archive.name+'\n')
        manifest=D.make_manifest(metadata,archive,root_version=1)
        signature=minisign.sign(manifest,key,public_key)
        entry=D.catalog_entry(manifest,signature)
        catalog_payload=D.make_catalog(target['channel'],1,[entry],root_version=1,issued_at=issued)
        catalog=D.envelope(catalog_payload,[(public_key,minisign.sign(catalog_payload,key,public_key))])
        publisher=self.root/'publisher'
        channel=publisher/('public/vanilla-hyprarch/channels/'+target['channel']+'.json')
        release=publisher/('public/vanilla-hyprarch/releases/'+target['version'])
        channel.parent.mkdir(parents=True)
        release.mkdir(parents=True)
        channel.write_bytes(catalog)
        (release/'manifest.json').write_bytes(manifest)
        (release/'manifest.json.sig').write_bytes(signature)
        directory=self.prepare(bundle=output,output=self.root/'signed-inputs',publisher=publisher,
            commit=target['commit'],metadata_sha256=A.digest_file(metadata),archive_sha256=A.digest_file(archive))
        _,record=A.load_record(directory)
        self.assertEqual(record['mode'],'post-upgrade')
        root=D.TrustedRoot.initial(envelope,pinned_public_key=public_key,pinned_root_sha256=D.digest(root_payload),minisign=minisign,clock=D.Clock(now))
        verified=D.verify_catalog(catalog,root,channel=target['channel'],state=D.initial_state(root),minisign=minisign,clock=D.Clock(now))
        state=D.parse_state(D.advance_state(D.initial_state(root),verified,root,clock=D.Clock(now)))
        return SimpleNamespace(directory=directory, metadata=target, source=repo,
            anchor=anchor, minisign=minisign, now=now, trust=root, ledger=state)

    def test_signed_post_upgrade_inputs_and_immutable_bindings_use_real_minisign(self):
        from release import distribution as D
        signed=self.signed_fixture()
        security=SimpleNamespace(minisign=signed.minisign,clock=lambda:D.Clock(signed.now),
            roots=lambda ledger:[signed.trust],_read=lambda:{'state':signed.ledger})
        A.validate_publication(signed.directory,signed.metadata,security)
        signed.ledger['bindings'][signed.metadata['version']]['manifest']['sha256']='0'*64
        with self.assertRaises(D.DistributionError):
            A.validate_publication(signed.directory,signed.metadata,security)

    def complete_post_upgrade(self, *, failed_authority=None, required_service=False,
                              pending=False, bad_binding=False, mutate_user=False):
        """Run main -> sudo worker -> snapshots/bindings/validators -> final report.

        Only OS/identity boundaries and the validators' machine-specific results
        are controlled. The acceptance implementation and signed verification run
        unchanged, with native staging and real canonical state/result encoders.
        """
        from release import distribution as D
        from install import signed_distribution, managed_deploy, create_once, system_integration
        from install.update_bootstrap_integration import provenance_bytes
        signed=self.signed_fixture()
        filesystem=self.root/'system'
        (filesystem/'run').mkdir(parents=True)
        user=driver.TargetUser('fixture', os.getuid(), os.getgid(), self.root,
            (os.getgid(),), self.root/'config', self.root/'data',
            self.root/'state', self.root/'cache', self.context['provider'])

        def put(relative, data, mode=0o600):
            path=filesystem/relative
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(data)
            path.chmod(mode)
            return path

        put('usr/share/vanhyprarch/release.json',(signed.directory/'release.json').read_bytes(),0o644)
        payload=BootstrapIntegration(signed.source).build()
        updater=put('usr/local/bin/vanhyprarch-update',payload,0o755)
        provenance={**json.loads(provenance_bytes(payload)), 'distribution_initialized':True}
        put('var/lib/vanhyprarch/update-bootstrap-v1.json',D.canonical(provenance))
        ledger={'schema':1,'roots':[],'state':signed.ledger,'authorization':None}
        if bad_binding:
            ledger['state']['bindings'][signed.metadata['version']]['manifest']['sha256']='0'*64
        put('var/lib/vanhyprarch/distribution-security-v1.json',D.canonical(ledger))
        managed,lifecycle,system=self.completed_authority_documents(signed.metadata['commit'])
        if pending:
            managed['transaction']={'phase':'prepared'}
        put('var/lib/vanhyprarch/system-integration-v1.json',D.canonical(system))
        put('var/lib/vanhyprarch/sddm-login/provenance-v1.json',b'{}')
        (filesystem/'var/lib/vanhyprarch').chmod(0o700)
        for name,value in (('managed-deployment-v1.json',managed),('create-once-lifecycle-v1.json',lifecycle)):
            path=user.xdg_state/'vanhyprarch'/name
            path.parent.mkdir(parents=True,exist_ok=True)
            path.write_bytes(D.canonical(value))
            path.chmod(0o600)
        preference=self.root/'config/vanhyprarch/power-idle.conf'
        preference.parent.mkdir(parents=True)
        preference.write_text('idle_timeout=600\n')
        store=driver.BundleStore(filesystem,uid=os.getuid(),gid=os.getgid())
        security_api=SimpleNamespace(SecurityStore=lambda journal: signed_distribution.SecurityStore(
            journal,anchor=signed.anchor,minisign=signed.minisign,now=lambda:signed.now))
        driver_api=SimpleNamespace(TargetUser=SimpleNamespace(resolve=lambda *a,**kw:user),
            InstalledReleaseIdentity=driver.InstalledReleaseIdentity, UpdateJournal=driver.UpdateJournal,
            BundleStore=lambda:store, AuthorityRunner=SimpleNamespace(_user_environment=lambda user:{
                **self.context['provider']['environment'], 'XDG_STATE_HOME':str(user.xdg_state)}))
        real_modules,real_read,real_snapshot=A.installed_modules,A.read_file,A.root_snapshot
        real_glob,real_popen=Path.glob,subprocess.Popen
        calls=[]
        validations=[]

        def read(path,**options):
            if str(path)=='/usr/share/vanhyprarch/release.json':
                path=filesystem/'usr/share/vanhyprarch/release.json'
            if Path(path)==updater:
                options['owner']=(os.getuid(),os.getgid())
            return real_read(path,**options)

        def modules(expected):
            # Exercise the actual pin/mode checks with a non-root fixture file.
            with mock.patch.object(A,'UPDATER',updater):
                contract,_,provider_module,_=real_modules(expected)
            return contract,driver_api,provider_module,security_api

        def globs(path,pattern,**options):
            return real_glob(filesystem/'run',pattern,**options) if path==Path('/run') else real_glob(path,pattern,**options)

        def validate(name,value):
            validations.append(name)
            if name==failed_authority:
                raise managed_deploy.ValidationError('installed artifact differs from provenance: fixture')
            return value

        def popen(argv,**options):
            argv=list(argv)
            calls.append((argv,options))
            if argv[0] in ('/usr/bin/minisign','/usr/bin/sha256sum'):
                return real_popen(argv,**options)
            out,err,code='','',0
            if argv[0]=='/usr/bin/sudo':
                self.assertIn('Graphical context captured BEFORE sudo:',self.output.getvalue())
                stdout,stderr=io.StringIO(),io.StringIO()
                worker_uid=iter((0,))
                actual_euid=os.geteuid()
                with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr), \
                        mock.patch.dict(os.environ,SUDO_USER=user.name,SUDO_UID=str(user.uid)), \
                        mock.patch.object(A.os,'geteuid',side_effect=lambda:next(worker_uid,actual_euid)):
                    code=A.main(argv[5:])
                out,err=stdout.getvalue(),stderr.getvalue()
            elif argv[0]=='/usr/bin/python3':
                name=Path(argv[2]).name
                stdout,stderr=io.StringIO(),io.StringIO()
                with contextlib.redirect_stdout(stdout),contextlib.redirect_stderr(stderr):
                    if name=='system_integration.py':
                        plan=system_integration.SystemPlan((
                            system_integration.PlanItem('package-preserve','qt5-wayland'),
                            system_integration.PlanItem('update-bootstrap-preserve','vanhyprarch-update')))
                        instance=SimpleNamespace(validate=lambda:validate(name,plan))
                        with mock.patch.object(system_integration,'SystemIntegration',return_value=instance):
                            code=system_integration.main(argv[3:])
                    elif name=='managed_deploy.py':
                        instance=SimpleNamespace(validate_installed=lambda **kw:validate(name,len(managed['artifacts'])))
                        with mock.patch.object(managed_deploy,'ManagedDeployment',return_value=instance):
                            code=managed_deploy.main(argv[3:])
                    elif name=='create_once.py':
                        results=[create_once.Result('preserve-processed','foot-config',
                            str(user.xdg_config/'foot/foot.ini'),'user-owned content is preserved')]
                        instance=SimpleNamespace(validate=lambda:validate(name,results))
                        with mock.patch.object(create_once,'CreateOnceInitializer',return_value=instance):
                            code=create_once.main(argv[3:])
                    else:
                        raise AssertionError('unexpected authority: '+repr(argv))
                out,err=stdout.getvalue(),stderr.getvalue()
            elif argv[0]=='/usr/bin/systemd-detect-virt': out='kvm\n'
            elif argv[0]=='/usr/bin/systemctl':
                if 'list-units' in argv and '--user' not in argv:
                    # Recorded by the real rehearsal; these are outside Vanilla's policy.
                    names=['systemd-pcrlogin@1000.service','systemd-pcrlogin@963.service',
                        'systemd-pcrproduct.service','systemd-tpm2-setup-early.service']
                    if required_service: names.append('NetworkManager.service')
                    out=''.join(name+' loaded failed failed TPM measurement\n' for name in names)
                elif 'show' in argv: out='Id='+argv[-1]+'\nResult=exit-code\nExecMainStatus=1\n'
            elif argv[:2]==['/usr/bin/locale','-a']: out='C\nC.utf8\nen_US.utf8\nPOSIX\n'
            elif argv[:2]==['/usr/bin/locale','charmap']: out='UTF-8\n'
            elif argv[0]=='/usr/bin/hyprctl': out=''
            elif argv[:2]==['/usr/bin/qs','ipc']:
                self.assertEqual(options['env']['LC_ALL'],'C.utf8')
                out='pong\n'
                err='WARN qt: diagnostic stream remains separate\n'
            elif argv[:2]==['/usr/bin/qs','log']:
                self.assertEqual(options['env']['LC_ALL'],'C.utf8')
                out=('INFO: Configuration Loaded\n'
                    'WARN quickshell.dbus.objectmanager: Failed to create DBusObjectManagerInterface for org.bluez\n'
                    'WARN qt.qpa.services: Failed to register with host portal\n')
                if mutate_user: preference.write_text('idle_timeout=900\n')
            else:
                raise AssertionError('unexpected real command boundary: '+repr(argv))
            return SimpleNamespace(returncode=code,communicate=lambda **kw:(out,err))

        report=self.root/'complete-report.txt'
        handler=signal.getsignal(signal.SIGTERM)
        self.addCleanup(signal.signal,signal.SIGTERM,handler)
        with mock.patch.object(A,'installed_modules',side_effect=modules), \
                mock.patch.object(A,'graphical_context',return_value=self.context), \
                mock.patch.object(A.shutil,'which',side_effect=lambda name:'/usr/bin/'+name), \
                mock.patch.object(A,'read_file',side_effect=read), \
                mock.patch.object(A,'root_snapshot',side_effect=lambda *a,**kw:real_snapshot(
                    *a,**kw,root=filesystem,uid=os.getuid(),gid=os.getgid())) as snapshots, \
                mock.patch.object(Path,'glob',new=globs), \
                mock.patch.object(subprocess,'Popen',side_effect=popen), \
                mock.patch.dict(os.environ,HYPRLAND_INSTANCE_SIGNATURE='fixture'), \
                mock.patch.object(sys,'path',list(sys.path)), \
                mock.patch.object(signed_distribution.SecurityStore,'publish',side_effect=AssertionError('mutation forbidden')):
            result=A.main(['post-upgrade',str(signed.directory),'--report',str(report)])
        self.assertEqual(list((filesystem/'run').iterdir()),[])
        self.assertFalse((filesystem/'var/lib/vanhyprarch/update/journal.json').exists())
        return result,report.read_text(),validations,calls,snapshots.call_count

    def test_complete_post_upgrade_path_reaches_warning_zero_after_all_required_checks(self):
        result,report,validations,calls,snapshots=self.complete_post_upgrade()
        self.assertEqual(result,0,report)
        self.assertEqual(validations,['system_integration.py','managed_deploy.py','create_once.py'])
        self.assertEqual(snapshots,2)
        for message in ('authenticated catalog, root chain and immutable installed release bindings',
                'all three authority validators','Installed state BEFORE:', 'Installed state AFTER:',
                'installed identity, hashes, modes, ownership and transaction state unchanged',
                'selected user-file content, ownership, permissions and identities unchanged',
                'Hyprland configuration, UTF-8 Quickshell IPC pong and runtime log checks',
                'WARNING: post-upgrade; exit status 0'):
            self.assertIn(message,report)
        self.assertEqual(report.count('outside the Vanilla service policy'),4)
        self.assertRegex(report,r'valid\t[1-9][0-9]*\tmanaged artifacts')
        self.assertNotIn('FAIL:',report)
        self.assertFalse(any('apply' in argv or 'initialize' in argv for argv,_ in calls))

    def test_complete_post_upgrade_rejects_real_authority_validation_failure(self):
        result,report,validations,_,snapshots=self.complete_post_upgrade(failed_authority='managed_deploy.py')
        self.assertEqual(result,2,report)
        self.assertEqual(validations,['system_integration.py','managed_deploy.py'])
        self.assertEqual(snapshots,2)
        self.assertIn('installed artifact differs from provenance',report)
        self.assertIn('transaction state unchanged',report)
        self.assertIn('FAIL: post-upgrade; exit status 2',report)

    def test_complete_post_upgrade_rejects_pending_transaction(self):
        result,report,validations,_,_=self.complete_post_upgrade(pending=True)
        self.assertEqual(result,1,report)
        self.assertEqual(validations,[])
        self.assertIn('incomplete authority transaction',report)

    def test_complete_post_upgrade_rejects_changed_signed_binding(self):
        result,report,validations,_,snapshots=self.complete_post_upgrade(bad_binding=True)
        self.assertNotEqual(result,0,report)
        self.assertEqual(validations,[])
        self.assertEqual(snapshots,2)
        self.assertIn('FAIL: post-upgrade;',report)

    def test_complete_post_upgrade_rejects_required_service_failure(self):
        result,report,validations,_,_=self.complete_post_upgrade(required_service=True)
        self.assertEqual(result,1,report)
        self.assertEqual(len(validations),3)
        self.assertIn('required Vanilla service failed: system:NetworkManager.service',report)

    def test_complete_post_upgrade_rejects_user_file_mutation(self):
        result,report,validations,_,_=self.complete_post_upgrade(mutate_user=True)
        self.assertEqual(result,1,report)
        self.assertEqual(len(validations),3)
        self.assertIn('selected USER_OWNED state changed during diagnostics',report)

    def vm_run(self, *, mode='preflight', missing=None, status=0, mutate=False, interrupt=False):
        directory = self.prepare()
        record_path = directory / 'approved.json'
        record = json.loads(record_path.read_text())
        record['mode'] = mode
        record_path.write_text(json.dumps(record))
        preference = self.root / 'config/vanhyprarch/power-idle.conf'
        preference.parent.mkdir(parents=True)
        preference.write_text('fixture\n')
        invocations = []
        def run(checks, argv, **kwargs):
            invocations.append(argv)
            if argv[0] == '/usr/bin/sudo':
                self.assertEqual(argv[4:6], [str(PROJECT/'release/acceptance.py'),'_root'])
                self.assertEqual(argv[6],mode)
                self.assertEqual(json.loads(argv[8]),self.context)
                self.assertNotIn('apply',argv)
                if mutate: preference.write_text('changed\n')
                if interrupt: raise KeyboardInterrupt
                return subprocess.CompletedProcess(argv,status,'worker diagnostics\n','')
            return subprocess.CompletedProcess(argv,0,'','')
        args = SimpleNamespace(command=mode,directory=directory,report=self.root/'report.txt',baseline=None)
        with mock.patch.object(A,'installed_modules',return_value=(build,driver,provider,None)), \
                mock.patch.object(A,'graphical_context',return_value=self.context), \
                mock.patch.object(A.shutil,'which',side_effect=lambda name: None if name==missing else '/usr/bin/'+name), \
                mock.patch.object(A.Checks,'run',new=run), mock.patch.object(A,'runtime_checks') as runtime:
            result = A.run_vm(args)
        return result,args.report.read_text(),invocations,runtime

    def test_whole_preflight_consolidates_report_and_preserves_user_files(self):
        result,report,calls,runtime = self.vm_run()
        self.assertEqual(result,0)
        self.assertIn('PASS: preflight; exit status 0',report)
        self.assertIn('unchanged during diagnostics',report)
        self.assertEqual(sum(argv[0]=='/usr/bin/sudo' for argv in calls),1)
        runtime.assert_not_called()

    def test_preflight_baseline_binds_target_source_host_and_user_context(self):
        result,report,_,_=self.vm_run()
        self.assertEqual(result,0)
        path=self.root/'report.txt'
        baseline=A.load_baseline(path,self.metadata,self.context,self.metadata_hash)
        self.assertTrue(baseline['user_files'])
        changed_context={**self.context,'state':'/different-state'}
        for context,digest in ((changed_context,self.metadata_hash),(self.context,'0'*64)):
            with self.subTest(context=context,digest=digest),self.assertRaises(A.Failure):
                A.load_baseline(path,self.metadata,context,digest)

    def test_whole_post_upgrade_reports_unavailable_preupgrade_evidence(self):
        result,report,calls,runtime = self.vm_run(mode='post-upgrade')
        self.assertEqual(result,0)
        self.assertIn('WARNING: no pre-upgrade hashes supplied',report)
        self.assertIn('MANUAL:',report)
        runtime.assert_called_once()

    def test_missing_dependency_is_reported_without_sudo(self):
        result,report,calls,_ = self.vm_run(missing='sudo')
        self.assertEqual(result,1)
        self.assertIn('missing required command: sudo',report)
        self.assertFalse(any(argv[0]=='/usr/bin/sudo' for argv in calls))

    def test_worker_failure_code_and_after_state_survive(self):
        result,report,_,_ = self.vm_run(status=7)
        self.assertEqual(result,7)
        self.assertIn('Selected user files AFTER:',report)
        self.assertIn('FAIL: preflight; exit status 7',report)

    def test_interruption_still_records_after_state(self):
        result,report,_,_ = self.vm_run(interrupt=True)
        self.assertEqual(result,130)
        self.assertIn('Selected user files AFTER:',report)

    def test_unexpected_user_file_change_fails(self):
        result,report,_,_ = self.vm_run(mutate=True)
        self.assertEqual(result,1)
        self.assertIn('USER_OWNED state changed during diagnostics',report)

    def test_cli_has_no_apply_repair_network_or_system_root_override(self):
        for command in ('apply','repair','resume','deploy'):
            result = subprocess.run([sys.executable,'-B',str(PROJECT/'release/acceptance.py'),command],capture_output=True)
            self.assertNotEqual(result.returncode,0)
        self.assertEqual(len(A.authority_commands(SimpleNamespace(tree=Path('/verified'),metadata=self.metadata),
            SimpleNamespace(home=self.root,uid=os.getuid(),gid=os.getgid(),groups=(os.getgid(),),name='fixture',
                            provider_context=self.context['provider']),
            SimpleNamespace(AuthorityRunner=SimpleNamespace(_user_environment=lambda user: {})))),3)
        self.assertNotIn('release/acceptance.py',FILES)

    def test_validator_vectors_parse_with_the_actual_existing_cli_interfaces(self):
        from install import system_integration,managed_deploy,create_once
        user=SimpleNamespace(home=self.root,uid=os.getuid(),gid=os.getgid(),groups=(os.getgid(),),
            name='fixture',provider_context=self.context['provider'])
        api=SimpleNamespace(AuthorityRunner=SimpleNamespace(_user_environment=lambda user:{}))
        commands=A.authority_commands(SimpleNamespace(tree=Path('/verified'),metadata=self.metadata),user,api)
        for (argv,_),module in zip(commands,(system_integration,managed_deploy,create_once)):
            parsed=module._parser().parse_args(argv[3:])
            self.assertEqual(getattr(parsed,'command',getattr(parsed,'operation',None)),'validate')


if __name__ == '__main__':
    unittest.main()
