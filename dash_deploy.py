"""Dash Deployment CLI - deploy a Python Dash app to an Ubuntu server.

Interactive Textual app that walks through the full deployment:

1. apt dependencies (nginx, python3-venv)
2. Python virtual environment for the app
3. dash + gunicorn installed into that venv
4. app.py (created from a working sample if absent)
5. local smoke test of app.py behind the venv
6. nginx reverse proxy (proxy -> 127.0.0.1:8050)
7. systemd service running the venv's gunicorn
8. live smoke test of the deployed service

Real run:   python3 dash_deploy.py
Dry run:    python3 dash_deploy.py --dry-run
            (every external command is recorded, nothing is executed)
"""

import asyncio
import getpass
import os
import re
import shlex
import socket
import subprocess  # nosec B404 - fixed argv (no shell) for the local smoke test only
import sys
import tempfile
from pathlib import Path
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Header, Input, Label, RichLog, Static

GUNICORN_PORT = int(os.environ.get("DASH_DEPLOY_PORT", "8050"))

SAMPLE_APP_PY = '''\
"""Minimal Dash app served by gunicorn in production (app:server)."""

from dash import Dash, dcc, html

app = Dash(__name__)
app.title = "{app_name}"

app.layout = html.Div(
    children=[
        html.H1("{app_name} is live!"),
        html.P("Edit ~/{app_name}/app.py and restart the service after changes."),
        dcc.Graph(id="example-graph"),
    ]
)

# gunicorn entrypoint: app:server
server = app.server

if __name__ == "__main__":
    app.run(host="127.0.0.1", port={port}, debug=False)
'''

NGINX_CONFIG_TEMPLATE = """\
server {{
    listen 80;
    server_name {server_name};

    location / {{
        proxy_pass http://127.0.0.1:{port};
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }}
}}
"""

SYSTEMD_UNIT_TEMPLATE = """\
[Unit]
Description=Gunicorn instance to serve {app_name}
After=network.target

[Service]
User={user}
Group={group}
WorkingDirectory={workdir}
Environment=PYTHONUNBUFFERED=1
ExecStart={workdir}/venv/bin/gunicorn --workers 3 --bind 127.0.0.1:{port} app:server
Restart=on-failure

[Install]
WantedBy=multi-user.target
"""


def is_valid_app_name(name: str) -> bool:
    """App names become directories, nginx files and unit names: keep them strict."""
    return bool(re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name)) and len(name) <= 64


def base_dir() -> Path:
    """Home directory of the deploying user (overridable for tests)."""
    return Path(os.environ.get("DASH_DEPLOY_HOME", Path.home())).expanduser()


def dry_run_enabled() -> bool:
    return os.environ.get("DASH_DEPLOY_DRY_RUN", "") == "1"


def render_nginx_config(server_name: str, port: int = GUNICORN_PORT) -> str:
    """Render the nginx server block for the app."""
    return NGINX_CONFIG_TEMPLATE.format(server_name=server_name or "_", port=port)


def render_systemd_unit(
    app_name: str,
    port: int = GUNICORN_PORT,
    user: Optional[str] = None,
) -> str:
    """Render the systemd unit for the app's gunicorn service."""
    user = user or getpass.getuser()
    workdir = base_dir() / app_name
    return SYSTEMD_UNIT_TEMPLATE.format(
        app_name=app_name,
        user=user,
        group=user,
        workdir=workdir,
        port=port,
    )


def sample_app_source(app_name: str, port: int = GUNICORN_PORT) -> str:
    return SAMPLE_APP_PY.format(app_name=app_name, port=port)


def _default_server_name() -> str:
    return "_"


class PasswordDialog(ModalScreen):
    """Modal dialog asking for the invoking user's sudo password."""

    def compose(self) -> ComposeResult:
        with Container(id="password-box"):
            yield Label("Enter your sudo password (kept in memory only, never stored):")
            yield Input(password=True, placeholder="sudo password", id="sudo-password-input")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        self.dismiss(event.value)

    def on_mount(self) -> None:
        self.query_one("#sudo-password-input", Input).focus()


class DashDeployApp(App):
    """A Textual CLI app to deploy a Dash app to an Ubuntu server."""

    CSS_PATH = "style.css"
    TITLE = "Dash Deployment CLI"
    BINDINGS = [("q", "quit", "Quit"), ("ctrl+c", "quit", "Quit")]

    def __init__(self) -> None:
        super().__init__()
        self.password: Optional[str] = None
        self._input_future: Optional[asyncio.Future] = None
        self.recorded: list[str] = []  # dry-run: recorded commands in execution order
        self.aborted = False
        self.finished = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main"):
            yield Static("Welcome to the Dash App Deployment CLI!", id="title")
            yield Static(
                "Deploys a Dash app (venv + gunicorn + nginx + systemd) on this Ubuntu server.",
                id="subtitle",
            )
            yield Button("Start Deployment", id="start-button")
            yield VerticalScroll(id="steps")
        yield Footer()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses; the deploy runs as an exclusive worker."""
        if event.button.id == "start-button" and not self.finished:
            event.button.disabled = True
            self.run_worker(self.deploy_dash_app(), name="deploy", exclusive=True)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Resolve the pending ask-user future when an Input is submitted."""
        if (
            event.input.id == "ask-input"
            and self._input_future is not None
            and not self._input_future.done()
        ):
            self._input_future.set_result(event.value)

    # ------------------------------------------------------------------ flow

    async def deploy_dash_app(self) -> None:
        """Guide the user through the deployment process."""
        try:
            app_name = await self._ask_app_name()
            if app_name is None:
                self.aborted = True
                return

            self._mark(f"Deploying {app_name!r} (port {GUNICORN_PORT})", None)

            if not await self._ensure_password():
                self.aborted = True
                return

            # ---- step 1: system dependencies
            self._mark("Step 1: Install system dependencies (nginx, python3-venv)", None)
            if not await self._run_cmd(
                "DEBIAN_FRONTEND=noninteractive apt-get update", sudo=True, timeout=900
            ):
                self.aborted = True
                return
            if not await self._run_cmd(
                "DEBIAN_FRONTEND=noninteractive apt-get -y install python3-venv nginx",
                sudo=True,
                timeout=900,
            ):
                self.aborted = True
                return

            # ---- step 2: virtual environment
            self._mark("Step 2: Set up the Python virtual environment", None)
            app_dir = base_dir() / app_name
            venv_bin = app_dir / "venv" / "bin"
            if not await self._run_cmd(f"mkdir -p {app_dir}"):
                self.aborted = True
                return
            if (venv_bin / "python").exists():
                self._mark("venv already exists - skipping creation.", "success")
            elif not await self._run_cmd(f"python3 -m venv {app_dir}/venv", timeout=600):
                self.aborted = True
                return

            # ---- step 3: dash + gunicorn into the app's venv
            self._mark("Step 3: Install dash and gunicorn (inside the app venv)", None)
            if not await self._run_cmd(f"{venv_bin}/pip install --upgrade pip", timeout=600):
                self.aborted = True
                return
            if not await self._run_cmd(f"{venv_bin}/pip install dash gunicorn", timeout=600):
                self.aborted = True
                return

            # ---- step 4: app.py
            self._mark("Step 4: Prepare your Dash app", None)
            app_py = app_dir / "app.py"
            if app_py.exists():
                self._mark(f"{app_py} already exists - using it.", "success")
            else:
                self._mark(
                    f"No app.py found at {app_py}. A working sample can bootstrap the deploy.",
                    None,
                )
                create = await self._ask_user("Create the sample app.py now? [y/N]:")
                if not create or create.lower() != "y":
                    self._mark("Aborted: no app.py to deploy.", "error")
                    self.aborted = True
                    return
                if self.dry_run:
                    # mkdir was only recorded above; materialize it locally so
                    # the flow can continue to be driven (and tested) to the end.
                    app_py.parent.mkdir(parents=True, exist_ok=True)
                app_py.write_text(sample_app_source(app_name), encoding="utf-8")
                os.chmod(app_py, 0o644)
                self._mark(f"Wrote {app_py}", "success")

            # ---- step 5: local smoke test (real run only)
            self._mark("Step 5: Local smoke test (venv python app.py)", None)
            if not await self._smoke_local(app_name, venv_bin, app_py):
                self.aborted = True
                return

            # ---- step 6: nginx
            self._mark("Step 6: Configure nginx as a reverse proxy", None)
            server_name = await self._ask_user(
                f"Public domain or server IP for nginx server_name"
                f" (enter for {_default_server_name()}):"
            )
            if not await self._write_sudo_file(
                f"/etc/nginx/sites-available/{app_name}",
                render_nginx_config(server_name or _default_server_name()),
            ):
                self.aborted = True
                return
            if not await self._run_cmd(
                f"ln -sf /etc/nginx/sites-available/{app_name} /etc/nginx/sites-enabled/{app_name}",
                sudo=True,
            ):
                self.aborted = True
                return
            # The stock Ubuntu default site claims `server_name _` on port 80
            # and would shadow (or collide with) this deployment - retire it.
            # Idempotent and only removes the stock symlink, nothing else.
            self._mark("Step 6b: Retire the stock nginx default site (port 80)", None)
            if not await self._run_cmd("rm -f /etc/nginx/sites-enabled/default", sudo=True):
                self.aborted = True
                return
            if not await self._run_cmd("nginx -t", sudo=True):
                self.aborted = True
                return
            if not await self._run_cmd("systemctl restart nginx", sudo=True):
                self.aborted = True
                return

            # ---- step 7: systemd service
            self._mark("Step 7: Install the systemd service", None)
            if not await self._write_sudo_file(
                f"/etc/systemd/system/{app_name}.service",
                render_systemd_unit(app_name),
            ):
                self.aborted = True
                return
            if not await self._run_cmd("systemctl daemon-reload", sudo=True):
                self.aborted = True
                return
            if not await self._run_cmd(f"systemctl enable --now {app_name}", sudo=True):
                self.aborted = True
                return

            # ---- step 8: live smoke test (real run only)
            self._mark(f"Step 8: Live smoke test (127.0.0.1:{GUNICORN_PORT})", None)
            if not await self._smoke_live():
                self._mark(
                    f"The service did not answer on port {GUNICORN_PORT}. Check:\n"
                    f"  systemctl status {app_name}\n"
                    f"  journalctl -u {app_name} -n 50",
                    "error",
                )
                self.aborted = True
                return

            self._mark(
                "Deployment complete! Your Dash app is served via nginx on port 80.\n"
                f"Manage it with: systemctl restart/stop/start {app_name}",
                "success",
            )
            self.finished = True
        except Exception as exc:  # workers swallow exceptions; surface them
            self._mark(f"Unexpected error: {exc}", "error")
            self.aborted = True

    # ----------------------------------------------------------- interaction

    async def _ask_app_name(self) -> Optional[str]:
        """Ask (and re-ask) until a valid app directory name is entered."""
        while True:
            self._mark(
                "Enter a name for your Dash app (lowercase letters, digits, '-', '_';"
                " must start with a letter).",
                None,
            )
            name = await self._ask_user("App name (e.g. mydashapp):")
            if is_valid_app_name(name):
                return name
            self._mark(f"Invalid app name: {name!r}", "error")

    async def _ask_user(self, prompt: str) -> str:
        """Mount an Input for the prompt and await its submission."""
        steps = self.query_one("#steps", VerticalScroll)
        await steps.mount(Label(prompt))
        fut: asyncio.Future = asyncio.get_running_loop().create_future()
        self._input_future = fut
        await steps.mount(Input(placeholder=prompt, id="ask-input"))
        self.query_one("#ask-input", Input).focus()
        value = await fut
        self._input_future = None
        try:
            await self.query_one("#ask-input", Input).remove()
        except Exception as exc:  # nosec B110 - the widget may already be gone
            await self._log_line("(cleanup) ask-input already removed: " + type(exc).__name__)
        return value.strip()

    async def _ensure_password(self) -> bool:
        """Show the password dialog once, up-front, then reuse it."""
        if self.dry_run:
            return True
        if self.password:
            return True
        self._mark("You will now be asked for your sudo password (first sudo step).", None)
        result_holder: dict = {}

        def _store(value: Optional[str]) -> None:
            result_holder["value"] = value

        self.push_screen(PasswordDialog(), callback=_store)
        while "value" not in result_holder:  # dismissed via Enter in the dialog
            await asyncio.sleep(0.05)
        password = result_holder["value"]
        if not password:
            self._mark("No sudo password provided - cannot continue.", "error")
            return False
        self.password = password
        return True

    def _mark(self, message: str, kind: Optional[str]) -> None:
        """Append a status line to the steps container."""
        steps = self.query_one("#steps", VerticalScroll)
        label = Label(message)
        if kind in ("error", "success"):
            label.add_class(kind)
        steps.mount(label)
        steps.scroll_end(animate=False)

    async def _log_line(self, text: str) -> None:
        steps = self.query_one("#steps", VerticalScroll)
        log = self._console(steps)
        log.write(text)
        steps.scroll_end(animate=False)

    def _console(self, steps: VerticalScroll) -> RichLog:
        try:
            return steps.query_one("#console", RichLog)
        except Exception:
            log = RichLog(id="console", highlight=False, markup=False, wrap=True)
            steps.mount(log)
            return log

    # ------------------------------------------------------------ execution

    async def _run_cmd(
        self,
        command: str,
        sudo: bool = False,
        timeout: float = 300.0,
    ) -> bool:
        """Run one command asynchronously; non-zero exits abort the flow.

        Dry runs record the exact command (including the sudo -S prefix)
        instead of executing it.
        """
        if sudo:
            command = f"sudo -S -p '' {command}"
        displayed = command.replace("-S -p '' ", "-S ")
        await self._log_line(f"$ {displayed}")
        if self.dry_run:
            self.recorded.append(command)
            await self._log_line("(dry-run) recorded, not executed")
            return True

        if sudo:
            if not self.password:
                self._mark("Internal error: missing sudo password.", "error")
                return False
            stdin_data = f"{self.password}\n"
        else:
            stdin_data = ""

        try:
            proc = await asyncio.create_subprocess_exec(
                *shlex.split(command),
                stdin=asyncio.subprocess.PIPE if stdin_data else None,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            out_bytes, err_bytes = await asyncio.wait_for(
                proc.communicate(stdin_data.encode()), timeout
            )
        except asyncio.TimeoutError:
            self._mark(f"Command timed out after {timeout:.0f}s: {displayed}", "error")
            return False
        except FileNotFoundError as exc:
            self._mark(f"Command not found: {shlex.split(command)[0]} ({exc})", "error")
            return False

        out = (out_bytes or b"").decode(errors="replace")
        err = (err_bytes or b"").decode(errors="replace")
        tail = "\n".join(out.splitlines()[-30:])
        if tail:
            await self._log_line(tail)

        if proc.returncode != 0:
            err_tail = "\n".join(err.splitlines()[-15:])
            self._mark(
                f"Command failed (exit {proc.returncode}): {displayed}\n{err_tail}",
                "error",
            )
            return False
        return True

    async def _write_sudo_file(self, dest: str, content: str) -> bool:
        """Write a privileged config file via a temp file + sudo mv.

        Piping the content into `sudo tee` would collide with the sudo
        password on stdin and could leak the password line into the file.
        """
        await self._log_line(f"$ write {dest}")
        if self.dry_run:
            self.recorded.append(f"sudo -S -p '' mv <tmp> {dest}")
            self.recorded.append(f"<contents for {dest}>")
            await self._log_line("(dry-run) content recorded: " + content.split("\n", 1)[0])
            return True
        tmp_path: Optional[str] = None
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".tmp", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            os.chmod(tmp_path, 0o644)
            return await self._run_cmd(f"mv {tmp_path} {dest}", sudo=True)
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

    async def _smoke_local(self, app_name: str, venv_bin: Path, app_py: Path) -> bool:
        """Start app.py behind the venv and probe port GUNICORN_PORT."""
        if self.dry_run:
            self.recorded.append(f"{venv_bin}/python {app_py}  # local smoke test")
            await self._log_line("(dry-run) local smoke test recorded, not executed")
            return True
        if not app_py.exists():
            self._mark(f"{app_py} is missing - cannot run the local smoke test.", "error")
            return False
        await self._log_line(
            f"{venv_bin}/python {app_py} (backgrounded, probing port {GUNICORN_PORT})"
        )
        proc = subprocess.Popen(  # nosec B603 - fixed argv, no shell
            [str(venv_bin / "python"), str(app_py)],
            cwd=str(base_dir() / app_name),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        try:
            ok = False
            for _ in range(30):
                await asyncio.sleep(0.3)
                if proc.poll() is not None:
                    self._mark("app.py exited immediately - fix it before deploying.", "error")
                    return False
                try:
                    with socket.create_connection(("127.0.0.1", GUNICORN_PORT), timeout=0.4):
                        ok = True
                        break
                except OSError:
                    continue
            if not ok:
                self._mark(
                    f"Nothing answered on port {GUNICORN_PORT} within 9s -"
                    " check that app.py serves that port.",
                    "error",
                )
                return False
            self._mark(f"app.py answered on port {GUNICORN_PORT}.", "success")
            return True
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()

    async def _smoke_live(self) -> bool:
        """Probe the deployed gunicorn service on GUNICORN_PORT."""
        if self.dry_run:
            self.recorded.append(f"curl -sf -o /dev/null http://127.0.0.1:{GUNICORN_PORT}")
            await self._log_line("(dry-run) live smoke test recorded, not executed")
            return True
        for _ in range(15):
            await asyncio.sleep(1)
            if await self._run_cmd(f"curl -sf -o /dev/null http://127.0.0.1:{GUNICORN_PORT}"):
                self._mark(f"Service answered on port {GUNICORN_PORT}.", "success")
                return True
        return False

    @property
    def dry_run(self) -> bool:
        return dry_run_enabled()


def main() -> None:
    """Entry point."""
    if "--dry-run" in sys.argv:
        os.environ["DASH_DEPLOY_DRY_RUN"] = "1"
    DashDeployApp().run()


if __name__ == "__main__":
    main()
