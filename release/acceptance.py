#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only
"""Operator-side release acceptance. No update, repair, network or signing path.

Preparation runs in a trusted checkout. Transfer the resulting directory manually;
preflight/post-upgrade run as the normal graphical user on the acceptance VM.
The private worker only inspects state, runs PLAN, or invokes existing validators.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib


UPDATER = Path('/usr/local/bin/vanhyprarch-update')
SHA = re.compile(r'[0-9a-f]{64}')
AUTHORITIES = {'system-integration', 'managed-deployment', 'create-once'}


class Failure(Exception):
    def __init__(self, message, code=1):
        super().__init__(message)
        self.code = code if code > 0 else 128 - code


def require(condition, message):
    if not condition:
        raise Failure(message)


def identity(info):
    # Reads can update atime; it is not evidence of an installed-state mutation.
    return tuple(getattr(info, name) for name in ('st_dev', 'st_ino', 'st_mode',
        'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def read_file(path, *, maximum=16 * 1024 * 1024, owner=None, mode=None):
    path = Path(path)
    info = path.lstat()
    require(path.resolve() == path.absolute() and stat.S_ISREG(info.st_mode)
            and info.st_nlink == 1 and info.st_size <= maximum,
            f'unsafe or oversized regular file: {path}')
    if owner is not None:
        require((info.st_uid, info.st_gid) == owner, f'wrong ownership: {path}')
    if mode is not None:
        require(stat.S_IMODE(info.st_mode) == mode, f'wrong permissions: {path}')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(info),
                f'file changed while opening: {path}')
        data = stream.read(maximum + 1)
    require(identity(path.stat()) == identity(info) and len(data) == info.st_size,
            f'file changed while reading: {path}')
    return data


def digest_file(path):
    info = Path(path).lstat()
    require(stat.S_ISREG(info.st_mode) and Path(path).resolve() == Path(path).absolute(),
            f'unsafe input file: {path}')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as stream:
        require(identity(os.fstat(stream.fileno())) == identity(info), f'input changed: {path}')
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    require(identity(Path(path).stat()) == identity(info), f'input changed: {path}')
    return digest


def fingerprint(path, *, owner=None, mode=None):
    path = Path(path)
    if not os.path.lexists(path):
        return {'absent': True}
    data = read_file(path, owner=owner, mode=mode)
    info = path.stat()
    return {'sha256': hashlib.sha256(data).hexdigest(), 'uid': info.st_uid,
            'gid': info.st_gid, 'mode': f'{stat.S_IMODE(info.st_mode):04o}',
            'size': info.st_size, 'inode': info.st_ino, 'device': info.st_dev,
            'mtime_ns': info.st_mtime_ns, 'ctime_ns': info.st_ctime_ns}


class Checks:
    def __init__(self, stream=None):
        self.stream = stream
        self.code = 0
        self.warnings = []

    def write(self, text):
        print(text, flush=True)
        if self.stream is not None:
            print(text, file=self.stream, flush=True)

    def warning(self, text):
        self.warnings.append(text)
        self.write('WARNING: ' + text)

    def failed(self, error):
        self.code = self.code or getattr(error, 'code', 1)
        self.write('FAIL: ' + str(error))

    def run(self, argv, *, env=None, required=True, timeout=30, **kwargs):
        self.write('Command: ' + json.dumps([str(value) for value in argv]))
        try:
            process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       text=True, encoding='utf-8', errors='replace', env=env, **kwargs)
        except OSError as error:
            raise Failure(str(error), 127 if isinstance(error, FileNotFoundError) else 126) from error
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except (KeyboardInterrupt, Failure, subprocess.TimeoutExpired) as error:
            # Let Python's native PLAN finally blocks run before terminating it.
            process.send_signal(signal.SIGINT)
            try:
                stdout, stderr = process.communicate(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
            self.write('STDOUT:\n' + stdout + '\nSTDERR:\n' + stderr)
            if isinstance(error, subprocess.TimeoutExpired):
                raise Failure('command timed out: ' + str(argv[0]), 124) from error
            raise
        self.write('STDOUT:\n' + (stdout.rstrip() or '<empty>'))
        self.write('STDERR:\n' + (stderr.rstrip() or '<empty>'))
        self.write('Exit status: ' + str(process.returncode))
        if required and process.returncode:
            raise Failure('command failed: ' + str(argv[0]), process.returncode)
        return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


@contextmanager
def private_report(path):
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
        os.fchmod(stream.fileno(), 0o600)
        yield stream


@contextmanager
def privileged_mask(checks):
    original = os.umask(0o022)
    try:
        checks.write(f'Privileged umask: inherited {original:04o}; scoped effective 0022')
        yield
    finally:
        os.umask(original)


def installed_modules(expected_hash):
    require(SHA.fullmatch(expected_hash), 'missing independently approved updater hash')
    read_file(UPDATER, owner=(0, 0), mode=0o755)
    require(digest_file(UPDATER) == expected_hash, 'installed updater differs from approved hash')
    sys.path.insert(0, str(UPDATER))
    from release import build
    from install import release_update, secret_service_preflight, signed_distribution
    return build, release_update, secret_service_preflight, signed_distribution


def load_record(directory):
    directory = Path(directory).absolute()
    require(directory.is_dir() and directory.resolve() == directory, 'unsafe input directory')
    record = json.loads(read_file(directory / 'approved.json', maximum=65536))
    require(record['schema'] == 1 and record['mode'] in ('preflight', 'post-upgrade'),
            'unsupported acceptance record')
    require(re.fullmatch(r'[0-9a-f]{40}', record['commit']), 'invalid approved source commit')
    require({'release.json', 'installed-release.json', 'SHA256SUMS', 'acceptance.py'} <= set(record['files']),
            'incomplete approved input inventory')
    for value in (record['installed_updater_sha256'], record['target_updater_sha256']):
        require(SHA.fullmatch(value), 'invalid approved updater hash')
    require(set(path.name for path in directory.iterdir()) ==
            {'acceptance.py', 'approved.json', *record['files']}, 'unexpected prepared input files')
    for name, pin in record['files'].items():
        require(Path(name).name == name, 'unsafe prepared input name')
        path = directory / name
        require(path.stat().st_size == pin['size'] and digest_file(path) == pin['sha256'],
                'approved input identity mismatch: ' + name)
    require(digest_file(Path(__file__)) == record['files']['acceptance.py']['sha256'],
            'executing helper differs from the prepared, reviewed helper')
    return directory, record


def verify_inputs(directory, record, contract):
    metadata = contract.parse_metadata(read_file(directory / 'release.json', maximum=4096))
    require(metadata['commit'] == record['commit'], 'target commit differs from approval')
    archive = directory / metadata['artifact']['name']
    require(contract.verify(directory / 'release.json', archive) == metadata,
            'canonical archive verification disagrees')
    expected = ''.join(record['files'][name]['sha256'] + '  ' + name + '\n'
                       for name in ('release.json', archive.name))
    require(read_file(directory / 'SHA256SUMS').decode() == expected,
            'checksum inventory must bind exactly metadata and archive')
    return metadata, archive


def archive_text(archive, metadata, relative):
    require(not Path(relative).is_absolute() and '..' not in Path(relative).parts,
            'unsafe release payload path')
    with tarfile.open(archive, 'r:gz') as bundle:
        member = bundle.getmember('vanhyprarch-' + metadata['version'] + '/' + relative)
        require(member.isfile() and member.size <= 1024 * 1024, 'oversized manifest: ' + relative)
        stream = bundle.extractfile(member)
        require(stream is not None, 'missing release payload: ' + relative)
        return stream.read(1024 * 1024).decode('utf-8')


def prepare(args):
    # Only this development-side operation imports checkout code.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from release import build as contract
    from install.update_bootstrap_integration import BootstrapIntegration
    bundle = args.bundle.absolute()
    metadata_bytes = read_file(bundle / 'release.json', maximum=4096)
    require(hashlib.sha256(metadata_bytes).hexdigest() == args.metadata_sha256,
            'metadata differs from independent approval')
    metadata = contract.parse_metadata(metadata_bytes)
    archive = bundle / metadata['artifact']['name']
    require(metadata['commit'] == args.commit, 'source differs from independent approval')
    installed_bytes = read_file(args.installed_metadata, maximum=4096)
    contract.parse_metadata(installed_bytes)
    require(SHA.fullmatch(args.installed_updater_sha256), 'invalid approved installed-updater hash')
    files = {'release.json': metadata_bytes,
             'SHA256SUMS': read_file(bundle / 'SHA256SUMS'),
             'installed-release.json': installed_bytes}
    with tempfile.TemporaryDirectory(prefix='vanhyprarch-acceptance-prepare-') as temporary:
        copied_metadata = Path(temporary) / 'release.json'
        copied_metadata.write_bytes(metadata_bytes)
        copied_archive = Path(temporary) / archive.name
        with contract._open_regular(archive, contract.MAX_ARTIFACT, 'approved archive') as (input_stream, info):
            with copied_archive.open('xb') as output_stream:
                remaining = info.st_size
                while remaining:
                    chunk = input_stream.read(min(1024 * 1024, remaining))
                    require(chunk, 'archive was truncated while preparing inputs')
                    output_stream.write(chunk)
                    remaining -= len(chunk)
                require(not input_stream.read(1), 'archive grew while preparing inputs')
        archive = copied_archive
        require(digest_file(archive) == args.archive_sha256,
                'copied archive differs from independent approval')
        contract.verify(copied_metadata, archive)
        # The canonical verifier has already rejected links, unsafe paths and special members.
        with tarfile.open(archive, 'r:gz') as stream:
            stream.extractall(temporary, filter='data')
        source = Path(temporary) / contract.archive_root(metadata['version'])
        updater_hash = hashlib.sha256(BootstrapIntegration(source).build()).hexdigest()
        if args.publisher:
            from release import distribution as D
            anchor = D.decode((source / 'release/trust.json').read_bytes(), D.MAX_ENVELOPE)
            import base64
            root = D.TrustedRoot.initial(base64.b64decode(anchor['root'], validate=True),
                pinned_public_key=anchor['public_key'], pinned_root_sha256=anchor['root_sha256'],
                minisign=D.Minisign(), clock=D.Clock(int(time.time())))
            public = args.publisher / 'public/vanilla-hyprarch'
            files['catalog.json'] = read_file(public / ('channels/' + metadata['channel'] + '.json'))
            files['manifest.json'] = read_file(public / ('releases/' + metadata['version'] + '/manifest.json'))
            files['manifest.json.sig'] = read_file(public / ('releases/' + metadata['version'] + '/manifest.json.sig'))
            catalog = D.verify_catalog(files['catalog.json'], root, channel=metadata['channel'],
                state=D.initial_state(root), minisign=D.Minisign(), clock=D.Clock(int(time.time())))
            require(D.verify_release(files['manifest.json'], files['manifest.json.sig'],
                files['release.json'], catalog, metadata['version'], root,
                minisign=D.Minisign(), clock=D.Clock(int(time.time()))) == metadata, 'publication target mismatch')
        output = args.output.absolute()
        require(not output.is_relative_to(Path(__file__).resolve().parents[1])
                and not output.is_relative_to(bundle), 'prepare outside the checkout and original build directory')
        if args.publisher:
            require(not output.is_relative_to(args.publisher.absolute()), 'prepare outside the publisher workspace')
        output.mkdir(mode=0o700)  # Never adopt or overwrite a previous preparation.
        try:
            output.chmod(0o700)
            for name, data in files.items():
                with (output / name).open('xb') as stream:
                    os.fchmod(stream.fileno(), 0o600)
                    stream.write(data)
            shutil.copyfile(archive, output / archive.name)
            (output / archive.name).chmod(0o600)
            require(digest_file(output / archive.name) == args.archive_sha256
                    and digest_file(output / 'release.json') == args.metadata_sha256,
                    'prepared copies differ from independently approved bytes')
            shutil.copyfile(Path(__file__), output / 'acceptance.py')
            (output / 'acceptance.py').chmod(0o600)
            names = [*files, archive.name, 'acceptance.py']
            record = {'schema': 1, 'mode': 'post-upgrade' if args.publisher else 'preflight',
                'commit': args.commit, 'vm_host': args.vm_host,
                'installed_updater_sha256': args.installed_updater_sha256,
                'target_updater_sha256': updater_hash,
                'files': {name: {'size': (output / name).stat().st_size,
                                 'sha256': digest_file(output / name)} for name in names}}
            with (output / 'approved.json').open('x') as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(record, stream, indent=2)
                stream.write('\n')
            load_record(output)
            verify_inputs(output, record, contract)
        except BaseException:
            shutil.rmtree(output)  # Only the directory just created by this invocation.
            raise
        print('PASS: prepared ' + str(output))
        print('Approved record SHA-256: ' + digest_file(output / 'approved.json'))
        print('Target updater SHA-256: ' + updater_hash)


def graphical_context(record, capture):
    uid = os.getuid()
    require(uid != 0 and sys.stdin.isatty() and not os.environ.get('SSH_CONNECTION')
            and not os.environ.get('SSH_TTY'), 'run as the graphical user in VM Foot, not root/SSH')
    require(os.uname().nodename == record['vm_host'], 'this is not the approved acceptance host')
    require(os.environ.get('XDG_SESSION_TYPE') == 'wayland'
            and os.environ.get('WAYLAND_DISPLAY') and os.environ.get('HYPRLAND_INSTANCE_SIGNATURE'),
            'missing graphical Wayland/Hyprland context')
    runtime = Path('/run/user/' + str(uid))
    require(os.environ.get('XDG_RUNTIME_DIR') == str(runtime)
            and os.environ.get('DBUS_SESSION_BUS_ADDRESS') == 'unix:path=' + str(runtime) + '/bus',
            'missing or nonstandard graphical runtime/bus context')
    info = runtime.lstat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == uid
            and stat.S_IMODE(info.st_mode) == 0o700, 'unsafe graphical runtime directory')
    display = Path(os.environ['WAYLAND_DISPLAY'])
    display = display if display.is_absolute() else runtime / display
    require(display.parent == runtime, 'Wayland display is outside the graphical runtime directory')
    for socket in (runtime / 'bus', display):
        info = socket.lstat()
        require(stat.S_ISSOCK(info.st_mode) and info.st_uid == uid, 'unsafe graphical socket: ' + str(socket))
    account = pwd.getpwuid(uid)
    context = capture(os.environ, uid, Path(account.pw_dir))
    return {'name': account.pw_name, 'provider': context,
            'state': os.environ.get('XDG_STATE_HOME') or str(Path(account.pw_dir) / '.local/state'),
            'cache': os.environ.get('XDG_CACHE_HOME') or str(Path(account.pw_dir) / '.cache')}


def preference_paths(archive, metadata, target):
    manifest = tomllib.loads(archive_text(archive, metadata, 'deployment/ownership-v2.toml'))
    paths = []
    for item in manifest['artifact']:
        if (item['class'] not in {'USER_OWNED', 'CREATE_ONCE_USER', 'CREATE_ONCE_MACHINE'}
                or item['component'] == 'secret-service'):
            continue
        expression = item['target']
        if item['kind'] == 'file':
            path, _ = target.resolve(expression)
            paths.append(path)
        elif item['kind'] == 'pattern' and expression.startswith('${XDG_STATE_HOME:-$HOME/.local/state}/'):
            prefix, _pattern = expression[:expression.index('*')].rsplit('/', 1)
            base, _ = target.resolve(prefix)
            suffix = expression[len(prefix) + 1:]
            require('..' not in Path(suffix).parts and '{' not in suffix, 'unsafe preference pattern')
            paths.extend(base.glob(suffix))
    return sorted(set(paths))


def check_plan(output, source, target):
    plan = json.loads(output)
    require(plan['source'] == source['version'] and plan['target'] == target['version']
            and plan['target_sha256'] == target['artifact']['sha256'], 'PLAN identity mismatch')
    require(set(plan['authorities']) == AUTHORITIES, 'PLAN did not complete all three authorities')
    require(json.loads(plan['authorities']['system-integration'])['blocked'] is False,
            'system-integration PLAN is blocked')
    require(all(plan['authorities'].values()), 'empty authority PLAN')
    expected = list(range(source['migration_level'] + 1, target['migration_level'] + 1))
    require([item['id'] for item in plan['migrations']] == expected, 'unexpected migration PLAN')
    return plan


def root_snapshot(user, driver, signed, *, root=Path('/'), uid=0, gid=0):
    # Alternate paths/owners are an isolated Python-test seam, never CLI options.
    def system(path):
        return root / Path(path).relative_to('/')
    identity = driver.InstalledReleaseIdentity(root, uid=uid, gid=gid).validate()
    journal = driver.UpdateJournal(root, uid=uid, gid=gid)
    require(journal.inspect() is None, 'pending update journal: use exact-target recovery')
    security = signed.SecurityStore(journal)
    ledger = security._read()  # Read/authenticate only; never start/publish/acquire.
    provenance = security.api._record()
    require(provenance and provenance['schema'] == 3 and 'publication' not in provenance
            and provenance['distribution_initialized'] is True
            and provenance['sha256'] == security.api._installed()
            and provenance['distribution_anchor_sha256'] == security.anchor['root_sha256'],
            'unsafe updater provenance or incomplete publication')
    if ledger['authorization'] is not None:
        receipt = signed.D.contract.parse_metadata(signed.decoded(
            ledger['authorization']['metadata'], signed.D.contract.MAX_METADATA))
        security.authorize(receipt)
    state = user.xdg_state or user.home / '.local/state'
    files = {
        system('/usr/share/vanhyprarch/release.json'): ((uid, gid), 0o644),
        system(UPDATER): ((uid, gid), 0o755),
        security.path: ((uid, gid), 0o600),
        security.api.state: ((uid, gid), 0o600),
        system('/var/lib/vanhyprarch/system-integration-v1.json'): ((uid, gid), 0o600),
        system('/var/lib/vanhyprarch/sddm-login/provenance-v1.json'): ((uid, gid), 0o600),
        state / 'vanhyprarch/managed-deployment-v1.json': ((user.uid, user.gid), 0o600),
        state / 'vanhyprarch/create-once-lifecycle-v1.json': ((user.uid, user.gid), 0o600)}
    records = {str(path): fingerprint(path, owner=owner, mode=mode)
               for path, (owner, mode) in files.items()}
    require(not any(item.get('absent') for item in records.values()), 'required installed state is absent')
    managed = json.loads(read_file(state / 'vanhyprarch/managed-deployment-v1.json'))
    lifecycle = json.loads(read_file(state / 'vanhyprarch/create-once-lifecycle-v1.json'))
    system_state = json.loads(read_file(system('/var/lib/vanhyprarch/system-integration-v1.json')))
    require(managed['status'] == 'complete' and managed.get('transaction') is None
            and lifecycle['pending'] is None and system_state.get('pending_system_artifact') is None,
            'incomplete authority transaction')
    pending = [system('/var/lib/vanhyprarch/system-integration-transaction-v1.json'),
               system('/var/lib/vanhyprarch/sddm-login/transaction-v1.json'),
               state / 'vanhyprarch/create-once-transaction-v1']
    require(not any(os.path.lexists(path) for path in pending), 'authority recovery state requires review')
    staging = system('/var/lib/vanhyprarch-update/staging')
    require(not os.path.lexists(staging) or staging.is_dir() and not staging.is_symlink()
            and not list(staging.iterdir()), 'retained release staging requires exact-target recovery')
    return {'identity': identity, 'files': records, 'provenance': provenance,
            'security_state': ledger['state']}, security


def validate_publication(directory, metadata, security):
    from release import distribution as D
    ledger = security._read()
    roots = security.roots(ledger)
    catalog = D.verify_catalog(read_file(directory / 'catalog.json'), roots[-1],
        channel=metadata['channel'], state=D.canonical(ledger['state']),
        minisign=security.minisign, clock=security.clock())
    manifest = read_file(directory / 'manifest.json')
    signer = D.validate_object(manifest)['root_version']
    require(1 <= signer <= len(roots), 'unknown manifest signing root')
    identity = D.verify_release(manifest, read_file(directory / 'manifest.json.sig'),
        read_file(directory / 'release.json'), catalog, metadata['version'], roots[-1],
        manifest_root=roots[signer - 1], minisign=security.minisign, clock=security.clock())
    require(identity == metadata, 'authenticated target identity mismatch')
    require(ledger['state']['channels'][metadata['channel']] ==
            {'sequence': catalog.value['sequence'], 'sha256': D.digest(catalog.payload)},
            'approved catalog does not match installed channel observation; review newer evidence')
    entry = next(item for item in catalog.value['releases'] if item['version'] == metadata['version'])
    require(ledger['state']['bindings'].get(metadata['version']) == entry,
            'installed immutable release binding differs')


def authority_commands(bundle, user, driver):
    python = '/usr/bin/python3'
    root = str(bundle.tree)
    return [
        ([python, '-B', root + '/install/system_integration.py', 'validate', '--lifecycle',
          'upgrade', '--source-root', root, '--target-user', user.name,
          '--target-context-json', json.dumps(user.provider_context)], {}),
        ([python, '-B', root + '/install/managed_deploy.py', '--source-root', root,
          '--release-id', bundle.metadata['commit'], '--home', str(user.home), 'validate'],
         {'user': user.uid, 'group': user.gid, 'extra_groups': user.groups,
          'env': driver.AuthorityRunner._user_environment(user)}),
        ([python, '-B', root + '/install/create_once.py', '--source-root', root,
          '--lifecycle', 'upgrade', '--home', str(user.home), 'validate'],
         {'user': user.uid, 'group': user.gid, 'extra_groups': user.groups,
          'env': driver.AuthorityRunner._user_environment(user)})]


def root_checks(directory, record, phase, context, checks, contract, driver, signed):
    user = driver.TargetUser.resolve(context['name'], provider_context=context['provider'],
        xdg_state=Path(context['state']), xdg_cache=Path(context['cache']))
    bundle = before = None
    store = driver.BundleStore()
    try:
        before, security = root_snapshot(user, driver, signed)
        expected = directory / ('installed-release.json' if phase == 'preflight' else 'release.json')
        require(read_file('/usr/share/vanhyprarch/release.json') == read_file(expected),
                'installed identity differs from independently approved metadata')
        require(not list(Path('/run').glob('vanhyprarch-preview-*')),
                'pre-existing preview staging requires review; no directory was deleted')
        checks.write('Installed state BEFORE: ' + json.dumps(before, sort_keys=True))
        metadata, archive = verify_inputs(directory, record, contract)
        bundle = store.prepare(directory / 'release.json', archive, permanent=False)
        require(bundle.metadata == metadata
                and hashlib.sha256(bundle.metadata_bytes).hexdigest() == record['files']['release.json']['sha256'],
                'staged target changed after independent input verification')
        if phase == 'preflight':
            argv = ['/usr/bin/python3', '-B', str(bundle.tree / 'install/release_update.py'),
                'plan', '--target-user', user.name, '--target-context-json', json.dumps(user.provider_context),
                '--xdg-config-home', str(user.xdg_config), '--xdg-data-home', str(user.xdg_data),
                '--xdg-state-home', str(user.xdg_state), '--xdg-cache-home', str(user.xdg_cache),
                '--release-metadata', str(bundle.metadata_path), '--release-artifact', str(bundle.artifact_path)]
            result = checks.run(argv, timeout=None)
            check_plan(result.stdout, before['identity'], metadata)
            checks.write('PASS: target-driver PLAN, compatibility, migrations and all three authority plans')
        else:
            validate_publication(directory, metadata, security)
            checks.write('PASS: authenticated catalog, root chain and immutable installed release bindings')
            for argv, options in authority_commands(bundle, user, driver):
                checks.run(argv, timeout=None, **options)
            checks.write('PASS: all three authority validators, including manifest-derived packages and managed trees')
    except (Exception, KeyboardInterrupt) as error:
        checks.failed(Failure('interrupted', 130) if isinstance(error, KeyboardInterrupt) else error)
    finally:
        try:
            if bundle is not None:
                store.preview_cleanup(bundle)
            require(not list(Path('/run').glob('vanhyprarch-preview-*')),
                    'preview staging remains; review without deleting unrelated material')
        except Exception as error:
            checks.failed(error)
        if before is not None:
            try:
                after, _ = root_snapshot(user, driver, signed)
                checks.write('Installed state AFTER: ' + json.dumps(after, sort_keys=True))
                require(before == after, 'installed state changed during diagnostics')
                checks.write('PASS: installed identity, hashes, modes, ownership and transaction state unchanged')
            except Exception as error:
                checks.failed(error)


def utf8_environment(checks):
    env = dict(os.environ)
    locales = checks.run(['/usr/bin/locale', '-a']).stdout.splitlines()
    choices = [name for wanted in ('cutf8', 'enusutf8') for name in locales
               if re.sub(r'[-_.]', '', name).lower() == wanted]
    choices += [name for name in locales if 'utf8' in re.sub(r'[-_.]', '', name).lower()]
    require(choices, 'no available UTF-8 locale; do not modify locale configuration automatically')
    env['LC_ALL'] = choices[0]
    require(checks.run(['/usr/bin/locale', 'charmap'], env=env).stdout.strip() == 'UTF-8',
            'selected Qt locale is not UTF-8')
    return env


def qt_errors(text):
    return re.search(r'\b(?:ERROR|FATAL)(?::|\s)|\b(?:ReferenceError|TypeError|SyntaxError):|'
        r'Failed to load configuration|QQmlApplicationEngine failed|Binding loop detected', text, re.I)


def runtime_checks(checks):
    env = utf8_environment(checks)
    errors = checks.run(['/usr/bin/hyprctl', '-i', env['HYPRLAND_INSTANCE_SIGNATURE'], 'configerrors'], env=env)
    require(not errors.stdout.strip(), 'Hyprland configuration errors')
    pong = checks.run(['/usr/bin/qs', 'ipc', '-c', 'vanhyprarch', 'call', 'vanhyprarch.shell', 'ping'], env=env)
    # stderr is always diagnostic output, never part of the IPC return value.
    payload = [line.strip() for line in pong.stdout.splitlines() if line.strip()
               and not re.match(r'^\s*(?:INFO|DEBUG|WARN(?:ING)?)(?:\s|:)', line)]
    require(payload == ['pong'] and not qt_errors(pong.stdout + '\n' + pong.stderr),
            'unexpected Quickshell IPC response or error')
    logs = checks.run(['/usr/bin/qs', 'log', '-c', 'vanhyprarch', '--no-color', '--log-times'], env=env)
    require(not qt_errors(logs.stdout + '\n' + logs.stderr), 'Quickshell runtime/configuration errors')
    if pong.stderr.strip() or re.search(r'\bWARN(?:ING)?(?:\s|:)', pong.stdout + logs.stdout + logs.stderr):
        checks.warning('Quickshell warnings retained above; IPC and required error checks passed')
    checks.write('PASS: Hyprland configuration, UTF-8 Quickshell IPC pong and runtime log checks')


def failed_services(policy, checks, previous=None):
    failed = {}
    declared = {(item['scope'], item['name']): item for item in policy['service']}
    for scope in ('system', 'user'):
        flags = ['--user'] if scope == 'user' else []
        result = checks.run(['/usr/bin/systemctl', *flags, 'list-units', '--failed', '--plain',
                             '--no-legend', '--no-pager', '--full'])
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            name = line.lstrip('● ').split()[0]
            key = scope + ':' + name
            failed[key] = 'present'
            checks.run(['/usr/bin/systemctl', *flags, 'show', '--no-pager', '--property=Id',
                '--property=Result', '--property=ExecMainStatus', '--property=StateChangeTimestamp', '--', name])
            item = declared.get((scope, name))
            if item and item['default_install']:
                checks.failed(Failure('required Vanilla service failed: ' + key))
            else:
                history = ('prior status unestablished' if previous is None else
                           'also present before upgrade' if key in previous else 'not present in preflight')
                category = 'optional declared service' if item else 'outside the Vanilla service policy'
                checks.warning(f'{key}: {category}; {history}; no repair attempted')
    return failed


def load_baseline(path, metadata, context, source_digest):
    records = [json.loads(line[len('EVIDENCE_JSON '):])
               for line in read_file(path).decode().splitlines() if line.startswith('EVIDENCE_JSON ')]
    require(len(records) == 1 and records[0]['phase'] == 'preflight'
            and records[0]['exit_status'] == 0
            and records[0]['target_sha256'] == metadata['artifact']['sha256']
            and records[0]['host'] == os.uname().nodename and records[0]['context'] == context
            and records[0]['installed_metadata_sha256'] == source_digest,
            'baseline must be a successful preflight for this target, source, host and user context')
    return records[0]


def run_vm(args):
    phase = args.command
    report_path = args.report or Path.home() / 'Downloads' / (phase + '-' + args.directory.name + '.txt')
    with private_report(report_path) as stream:
        checks = Checks(stream)
        checks.write('Vanilla HyprArch ' + phase + '; host: ' + os.uname().nodename)
        checks.write('Started UTC: ' + time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()))
        before = None
        evidence = {'phase': phase}
        try:
            directory, record = load_record(args.directory)
            require(phase == record['mode'], 'prepare matching preflight/post-upgrade inputs')
            checks.write('Approved record SHA-256: ' + digest_file(directory / 'approved.json'))
            expected_hash = record['installed_updater_sha256'] if phase == 'preflight' else record['target_updater_sha256']
            contract, driver, provider, _signed = installed_modules(expected_hash)
            metadata, archive = verify_inputs(directory, record, contract)
            require(metadata['architecture'] == os.uname().machine, 'release architecture differs from this VM')
            evidence['target_sha256'] = metadata['artifact']['sha256']
            context = graphical_context(record, provider.capture_context)
            evidence.update(host=os.uname().nodename, context=context,
                            installed_metadata_sha256=record['files']['installed-release.json']['sha256'])
            checks.write('Graphical context captured BEFORE sudo: ' + json.dumps(context, sort_keys=True))
            for name in ('sudo', 'sha256sum', 'systemctl', 'systemd-detect-virt', 'minisign', 'pacman') + (
                    ('qs', 'hyprctl', 'locale') if phase == 'post-upgrade' else ()):
                require(shutil.which(name), 'missing required command: ' + name)
            checks.run(['/usr/bin/systemd-detect-virt'])
            checks.run(['/usr/bin/sha256sum', '--check', 'SHA256SUMS'], cwd=directory)
        except (Exception, KeyboardInterrupt) as error:
            checks.failed(Failure('interrupted', 130) if isinstance(error, KeyboardInterrupt) else error)
        try:
            if checks.code:
                return checks.code
            resolver = PreferenceTarget(context)
            paths = preference_paths(archive, metadata, resolver)
            before = {str(path): fingerprint(path) for path in paths}
            evidence['user_files'] = before
            checks.write('Selected user files BEFORE: ' + json.dumps(before, sort_keys=True))
            checks.write('Only manifest-selected configuration/state files are hashed; keyrings and unselected user data are not read or proven.')
            previous = load_baseline(args.baseline, metadata, context,
                record['files']['installed-release.json']['sha256']) if args.baseline else None
            result = checks.run(['/usr/bin/sudo', '/usr/bin/python3', '-I', '-B', str(Path(__file__).resolve()),
                '_root', phase, str(directory), json.dumps(context)], required=False, timeout=None)
            if result.returncode:
                checks.failed(Failure('privileged read-only checks failed', result.returncode))
            policy = tomllib.loads(archive_text(archive, metadata, 'deployment/service-policy-v1.toml'))
            evidence['failed_services'] = failed_services(policy, checks,
                previous.get('failed_services') if previous else None)
            if phase == 'post-upgrade':
                runtime_checks(checks)
                if previous:
                    changed = [name for name, value in previous['user_files'].items()
                               if before.get(name) != value]
                    if changed:
                        checks.warning('user file identities differ since preflight; review possible user changes: ' + repr(changed))
                    else:
                        checks.write('PASS: selected user-file bytes and identities match the pre-upgrade preflight evidence')
                else:
                    checks.warning('no pre-upgrade hashes supplied; byte preservation across the upgrade is not established')
                checks.write('MANUAL: verify desktop/preferences visually, then ordinary dock Update must authenticate and report already current.')
        except (Exception, KeyboardInterrupt) as error:
            checks.failed(Failure('interrupted', 130) if isinstance(error, KeyboardInterrupt) else error)
        finally:
            if before is not None:
                try:
                    after = {str(path): fingerprint(path) for path in preference_paths(archive, metadata, resolver)}
                    checks.write('Selected user files AFTER: ' + json.dumps(after, sort_keys=True))
                    require(before == after, 'selected USER_OWNED state changed during diagnostics')
                    checks.write('PASS: selected user-file content, ownership, permissions and identities unchanged during diagnostics')
                except Exception as error:
                    checks.failed(error)
            evidence['exit_status'] = checks.code
            checks.write('EVIDENCE_JSON ' + json.dumps(evidence, sort_keys=True))
            checks.write(('FAIL' if checks.code else 'WARNING' if checks.warnings else 'PASS')
                         + ': ' + phase + '; exit status ' + str(checks.code))
            checks.write('Report: ' + str(report_path))
        return checks.code


class PreferenceTarget:
    """Resolve only manifest-listed config/state file expressions; never shell-expand."""
    def __init__(self, context):
        env = context['provider']['environment']
        self.roots = {'$HOME': env['HOME'], '${XDG_CONFIG_HOME:-$HOME/.config}': env['XDG_CONFIG_HOME'],
                      '${XDG_STATE_HOME:-$HOME/.local/state}': context['state'],
                      '${XDG_CACHE_HOME:-$HOME/.cache}': context['cache'],
                      '${XDG_DATA_HOME:-$HOME/.local/share}': env['XDG_DATA_HOME']}

    def resolve(self, expression):
        for prefix, directory in self.roots.items():
            if expression.startswith(prefix + '/'):
                suffix = expression[len(prefix) + 1:]
                require(not Path(suffix).is_absolute() and '..' not in Path(suffix).parts
                        and not any(char in suffix for char in '*{}'), 'unsafe preference path')
                path = Path(directory) / suffix
                require(path.is_absolute() and path.resolve() == path, 'ambiguous preference path')
                return path, Path(directory)
        raise Failure('unsupported manifest preference prefix: ' + expression)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    preparation = commands.add_parser('prepare', help='create new private manual-transfer inputs locally')
    for name in ('bundle', 'output', 'installed-metadata', 'publisher'):
        preparation.add_argument('--' + name, type=Path, required=name != 'publisher')
    for name in ('commit', 'metadata-sha256', 'archive-sha256', 'installed-updater-sha256', 'vm-host'):
        preparation.add_argument('--' + name, required=True)
    for mode in ('preflight', 'post-upgrade'):
        command = commands.add_parser(mode)
        command.add_argument('directory', type=Path)
        command.add_argument('--report', type=Path)
        command.add_argument('--baseline', type=Path)
    worker = commands.add_parser('_root', help='internal sudo worker, not an operator entry point')
    worker.add_argument('phase', choices=('preflight', 'post-upgrade'))
    worker.add_argument('directory', type=Path)
    worker.add_argument('context')
    args = parser.parse_args(argv)
    def interrupted(signum, _frame):
        raise Failure('interrupted by signal ' + str(signum), 128 + signum)
    signal.signal(signal.SIGTERM, interrupted)
    try:
        if args.command == 'prepare':
            prepare(args)
            return 0
        if args.command != '_root':
            return run_vm(args)
        require(os.geteuid() == 0, 'private inspection worker requires sudo')
        directory, record = load_record(args.directory)
        require(record['mode'] == args.phase, 'worker phase mismatch')
        context = json.loads(args.context)
        require(os.environ.get('SUDO_USER') == context['name']
                and os.environ.get('SUDO_UID') == str(context['provider']['uid']),
                'private worker must be invoked by the captured graphical user through sudo')
        expected = record['installed_updater_sha256'] if args.phase == 'preflight' else record['target_updater_sha256']
        contract, driver, _provider, signed = installed_modules(expected)
        checks = Checks()
        with privileged_mask(checks):
            root_checks(directory, record, args.phase, context, checks, contract, driver, signed)
        return checks.code
    except (Exception, KeyboardInterrupt) as error:
        code = 130 if isinstance(error, KeyboardInterrupt) else getattr(error, 'code', 1)
        print('FAIL: ' + str(error), file=sys.stderr)
        return code


if __name__ == '__main__':
    raise SystemExit(main())
