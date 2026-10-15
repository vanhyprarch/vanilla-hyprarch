# Persistent Secret Service

Vanilla requires official Arch `gnome-keyring` for standard application
credentials. GNOME Keyring alone owns credential storage, persistence, and
unlocking. KeePassXC is not part of Vanilla: it is a personally installed,
optional manual password manager. Vanilla never enables its Secret Service
integration, starts it automatically, or changes its settings.

## Session boundary

The supported sequence is SDDM password authentication and upstream PAM login
keyring initialization/unlock, user session, graphical environment publication,
`gnome-keyring-daemon --start --components=secrets`, then dex and applications.
The existing Lua startup callback runs this ordered command once per graphical
session. Configuration reload does not repeat it. No project session helper,
configuration scanner, custom credential store, or security daemon is deployed.

Missing required environment or failed publication still prevents dex. The
upstream handoff is synchronous, uses the PAM daemon/control socket/singleton,
and discards its output without evaluation. A failed handoff logs a fixed,
non-sensitive diagnostic and still starts dex. This isolates unrelated autostart
apps from keyring availability. It adds no plaintext fallback and never uses
`--replace`. Command success or bus ownership alone does not prove unlocking.

Arch owns `/etc/pam.d/sddm`, the PAM module, registrations, daemon service,
socket, and desktop entries. The official package enables its control socket;
Vanilla adds no redundant enablement. User keyrings remain outside deployment
and create-once initialization. Matching SDDM/login-keyring passwords are
required for automatic unlocking; autologin is not the acceptance path.

## Provisioning boundary and target context

`install/secret_service_preflight.py` is installer-only read-only compatibility
code. It never runs on graphical startup. The system integration stage runs it
as the selected target user before package mutation, using explicitly captured
provider discovery context rather than root's inherited environment.

The capture operation uses only UID, account HOME, `XDG_CONFIG_HOME`,
`XDG_DATA_HOME`, `XDG_DATA_DIRS`, and an optional `KPXC_CONFIG` path for a known
third-party provider. It never captures the whole environment. Standard defaults
are resolved in the target user's normal invocation only when those variables
are absent. Explicit custom paths survive sudo unchanged. Identity, required
keys, and absolute paths are checked; missing or ambiguous context blocks rather
than silently falling back to `~/.config`. The supplied payload is an explicit
administrator-reviewed declaration, not an authentication token. Do not capture
it as root or substitute another user's environment.

Fresh installation and the user-launched updater forward the payload through
existing arguments. No context file or preference is persisted. Root-only calls
require an explicit capture. Older updater code without forwarding fails closed
against the new target. The approved one-time preparation and normal signed
discovery have now passed on the existing v1.0.0 VM, resolving that handoff;
the genuine v1.0.1 target preflight and upgrade remain pending.

The probe checks registrations, activation availability, and current bus owner
using standard D-Bus interfaces, plus known optional provider-enable settings.
No provider or existing official GNOME Keyring is compatible. Installed password
manager package metadata alone is never a conflict. A genuinely enabled
alternative provider, competing registration/owner, or uninspectable state
blocks provisioning; nothing is uninstalled or overwritten. A known
KeePassXC `FdoSecrets/Enabled=true` setting is one such installer-only detection
case, not a Vanilla dependency or a special runtime integration. Malformed
unrelated regular registration contents are ignored; uninspectable discovery
inputs require conservative review. Unsupported wrappers, portable managers,
private buses, or separate application contexts need manual review.

## Native Nextcloud backend

The supported test client is official Extra `nextcloud-client` (audited
2:34.0.5-1), not a Flatpak or AppImage. It depends on `qtkeychain-qt6` 0.17.0-1.
The official QtKeychain binary contains the libsecret lookup/store backend.
Upstream [backend selection](https://github.com/frankosterfeld/qtkeychain/blob/0.17.0/qtkeychain/keychain_unix.cpp)
prefers libsecret for an unrecognized desktop such as Hyprland when libsecret
is available. The GVfs baseline already supplies `libsecret`; no desktop identity
spoofing or `QTKEYCHAIN_BACKEND` override is added. Existing user overrides must
be reviewed if the client chooses a different backend.

Nextcloud's [HTTP credentials implementation](https://github.com/nextcloud/desktop/blob/v34.0.5/src/libsync/creds/httpcredentials.cpp)
reads/writes credentials through QtKeychain with insecure fallback disabled.
QtKeychain's [libsecret implementation](https://github.com/frankosterfeld/qtkeychain/blob/0.17.0/qtkeychain/libsecret.cpp)
stores in the default Secret Service collection using `org.qt.keychain` metadata
and the `server` application identifier. Correct ownership, an unlocked persistent
login/default collection, and actual Nextcloud logout/login/reboot success are
all required. Installing GNOME Keyring alone does not prove authentication
persistence, nor migrate credentials from another backend.

## Development acceptance — passed

The corrected managed configuration is deployed on the development host with
official GNOME Keyring 51.1 and gcr. The user confirmed SDDM password login
unlocked the persistent login keyring and native Nextcloud authenticated and
synchronized. Its normal autostart option created `Nextcloud.desktop`.
After a full reboot, Nextcloud launched automatically, requested neither browser
login nor a password, and displayed green synchronized status. The original
repeated-authentication problem is resolved on this host.

The post-reboot live metadata probe confirmed GNOME Keyring ownership, exactly
one daemon, the unlocked login/default collection, a private persistent login
file, two accessible Nextcloud credential items, and zero locked items. It did
not retrieve any secret values. All 23 deployed managed artifacts validated.

The procedure below remains the acceptance path for future integration changes.

From the checkout in the target user's normal session, capture context before
sudo and review the read-only full plan:

```bash
(
  target_context=$(python -B install/secret_service_preflight.py context) || exit 1
  target_user=$(id -un) || exit 1
  sudo python -B install/system_integration.py plan --source-root "$PWD" \
    --target-user "$target_user" --target-context-json "$target_context"
)
```

Do not run the full system apply on the development host. For an authorized
deployment, review the managed plan; this integration changes only the Hyprland
core and installs no session helper. Preserve exact rollback material and
validate all managed files.
Then perform these manual checks:

1. Log out and sign in through SDDM using the account password. Run
   `python tests/secret-service-live.py`. Require GNOME ownership, an unlocked
   login/default collection, a private persistent login file, and one daemon.
   The probe prints only booleans and counts; it never retrieves secrets.
2. Use the official native `nextcloud-client` for acceptance. Enable its normal
   autostart option, authenticate once through the normal browser flow, and
   wait for successful synchronization. Re-run the metadata probe and require
   an unlocked Nextcloud item in the persistent login collection. No Nextcloud
   command or desktop entry is hardcoded by Vanilla.
3. Count this boot's `Starting XDG Autostart after GNOME Keyring handoff attempt`
   messages with `journalctl -b -t vanhyprarch-autostart --no-pager`.
   Run `hyprctl reload`; require no additional startup message or Nextcloud
   launch. A new graphical session should add exactly one message.
4. Log out and password-login again. Confirm automatic client launch, retained
   authentication, resumed synchronization, and unlocked persistent collection.
5. Reboot manually and repeat those checks. Only this actual reboot test
   completes end-to-end acceptance. Report each result separately.

If authentication recurs, distinguish absent/locked login collection, wrong
default collection, client/backend override, failed credential write, and
server-side token revocation. Review sanitized errors locally. Never share
passwords, keyring contents, full client configuration, or credential attributes.
Do not delete/reset keyrings or add insecure fallback as a workaround.

The previous isolated upstream 51.1 daemon probe produced an unlocked persistent
login collection and one daemon with stable owner/PID across repeated starts.
That disposable private-bus test does not establish real SDDM or Nextcloud
acceptance. The corrected regression suite separately covers availability,
explicit context forwarding, provider conflicts, and reload isolation.

The final automated run passed 456 tests across the manifest, system
integration, managed deployment, contained Lua ownership, XDG Autostart,
provider/context, bootstrap, release-driver/bootstrap/artifact, create-once,
and SDDM suites. The updater also reports invalid target-user context with a
fixed diagnostic and exits before sudo, without a traceback or context disclosure.
Shell syntax and `git diff --check` passed. The later libalpm correction resolved
the `man-db`/`man` source defect, and the existing v1.0.0 VM passed approved
updater preparation and authenticated discovery. Those completed phases are not
new release gates. The next genuine v1.0.1 target preflight must validate provider
and package compatibility before the separately authorized real upgrade.
