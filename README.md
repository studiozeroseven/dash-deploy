# Dash Deployment CLI

An interactive Textual CLI that deploys a Python Dash app to an Ubuntu server:
apt dependencies, a real Python venv, dash + gunicorn inside that venv, an
nginx reverse proxy, and a systemd service - with smoke tests before and
after the switch.

## What it does

```
Step 1  apt-get update; install python3-venv + nginx          (sudo)
Step 2  mkdir ~/yourapp; python3 -m venv ~/yourapp/venv
Step 3  venv/bin/pip install dash gunicorn
Step 4  app.py - uses yours, or bootstraps a working sample
Step 5  local smoke test: venv python app.py, probe :8050
Step 6  nginx server block -> proxy 127.0.0.1:8050 (sudo)
Step 7  systemd unit: venv gunicorn binds 127.0.0.1:8050 (sudo)
Step 8  live smoke test against the running service
```

Prompts: (1) app name (validated, becomes every file/dir name), (2) create the
sample app.py if none exists, (3) nginx `server_name` (enter for the wildcard
default), plus the sudo password once, up front.

## Run it

```bash
git clone https://github.com/studiozeroseven/dash-deploy.git
cd dash-deploy
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# real deployment (Ubuntu server, you will be prompted)
python3 dash_deploy.py

# dry run - records every command, executes nothing
python3 dash_deploy.py --dry-run
```

Quit with `q` or `Ctrl+C` at any point.

## Why the old version could not deploy anything

For the record (v0.1.0 behavior, all fixed in v0.2.0 and covered by tests):

- `source venv/bin/activate` ran in a child process: it changed nothing, so
  pip/gunicorn used the system Python and the systemd unit pointed at an
  empty venv.
- nginx proxied to `127.0.0.1:8050` (TCP) while the systemd unit bound a
  unix socket with `-m 007`: the proxy pointed at nothing.
- Textual's `Input.wait_for_input()` does not exist - the very first prompt
  could never complete.
- All subprocess calls blocked the Textual event loop; the `python app.py`
  step never returned (Dash runs forever), so the flow could not proceed.
- `sudo` was called without `-S`, so the piped password was ignored; pipes
  (`echo | sudo tee`) collided with the password on stdin.
- Unvalidated app names allowed shell injection into every constructed command.

## Design notes

- Every privileged command runs as `sudo -S -p '' <cmd>` with the password
  piped once; config files are written to a 0600 temp file and moved into
  place with `sudo mv` (no stdin collisions, password never lands in files).
- The sudo password lives in app memory only; the process list never shows it.
- The generated systemd unit binds `127.0.0.1:8050` with
  `Restart=on-failure`; nginx adds `X-Forwarded-Proto` so Dash generates
  correct absolute URLs behind the proxy.
- App names are validated `^[a-z][a-z0-9_-]{0,63}$` before any string joins
  them.

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest tests/
```

The e2e tests drive the full flow through a real Textual pilot in dry-run
mode: every command is recorded and asserted (sudo prefix, venv-by-path,
socket-vs-TCP binding, ordering), nothing is executed against your system.
A final test imports the generated sample app with the real dash package and
verifies the `app:server` gunicorn entrypoint.

## Deployment notes

- The target app's `app.py` must expose the Dash instance as `app` (the
  generated sample does). The service runs its own venv's gunicorn via
  `app:server`.
- Dash websockets (rare in plain apps) would need additional nginx
  upgrade headers; default Dash callbacks use XHR and work with this config.
- The nginx default site: on stock Ubuntu it claims port 80 with
  `server_name _` and would shadow the deployment, so step 6 removes
  `/etc/nginx/sites-enabled/default` (the stock symlink). If YOU have a
  real default site, back it up before deploying.

## License

GPL-3.0 - see [LICENSE](LICENSE). (The README previously said MIT; the
repository ships GPL v3.)

## Contact

Ian Schwartz - [ian@theapk.com](mailto:ian@theapk.com) -
[studiozeroseven](https://github.com/studiozeroseven)
