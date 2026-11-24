# Changelog

## [0.2.1] - 2026-11-23

### Fixed
- The stock Ubuntu nginx default site claims `server_name _` on port 80 and
  silently shadows the deployed app (you get "Welcome to nginx!" instead of
  your Dash app). Step 6 now retires `/etc/nginx/sites-enabled/default`
  (idempotent, only the stock symlink). Found by a live end-to-end run on a
  fresh Ubuntu 24.04 systemd container.

## [0.2.0] - 2026-11-23

### Fixed
- `source venv/bin/activate` in a child process did nothing - dash/gunicorn
  were installed into the system Python while the systemd unit used the empty
  venv. Everything now uses the venv by absolute path.
- nginx (TCP 127.0.0.1:8050) vs systemd (unix socket, `-m 007`) mismatch -
  the proxy pointed at nothing. The unit now binds 127.0.0.1:8050 and adds
  `Restart=on-failure`.
- Nonexistent `Input.wait_for_input()` replaced with a proper async
  input mechanism (mounted Input + submit event + future) - the first
  prompt could never complete before.
- Blocking `subprocess` calls froze the whole TUI and `python app.py`
  never returned - commands now run via asyncio subprocesses with timeouts,
  and the local smoke test launches app.py in the background, probes the
  port, then stops it.
- sudo without `-S` ignored the piped password; piping configs through
  `sudo tee` collided with the password on stdin. All sudo commands now use
  `sudo -S -p ''` and files are staged via temp file + `sudo mv`.
- The password dialog mounted again (and never removed itself) on every
  sudo command - it is now one up-front modal, reused for the session.
- Unvalidated app names (shell injection) - names are validated and re-asked.
- `os.getlogin()` replaced with `getpass.getuser()`.
- installer.sh cloned a nonexistent repo name and cd'd into the wrong
  directory; README claimed MIT while the repo ships GPL v3.

### Added
- `--dry-run` mode: the exact command list is recorded (and asserted by
  tests), nothing executes.
- Working sample app.py bootstrap (compatible with dash 2.x-4.x:
  `server = app.server`, verified with real dash 4.5).
- Real test suite (10 tests) driving the whole flow headlessly through
  Textual's pilot, plus pyproject/dev requirements/CI workflow.
- Live smoke test of the deployed service and clearer failure hints
  (`systemctl status`, `journalctl`).

## [0.1.0]

Initial attempt. Could not complete a single prompt or deploy anything.
