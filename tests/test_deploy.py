"""Tests for the Dash Deployment CLI.

The full deploy flow is exercised end-to-end in dry-run mode through a real
Textual pilot session: every external command is recorded, nothing executes.

Prompt order in the flow: (1) app name -> (2) create sample app.py? -> (3) nginx server_name.
"""

import importlib
import sys

import pytest

import dash_deploy

# ---------------------------------------------------------------- fixtures


@pytest.fixture
def sandbox_home(tmp_path, monkeypatch):
    """Point the tool's base dir at a sandbox and enable dry-run mode."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("DASH_DEPLOY_HOME", str(home))
    monkeypatch.setenv("DASH_DEPLOY_DRY_RUN", "1")
    return home


# ------------------------------------------------------------ unit: naming


def test_invalid_app_names_rejected():
    for bad in ("", "1app", "MyApp", "has space", "semi;colon", "x" * 65, ".."):
        assert not dash_deploy.is_valid_app_name(bad), bad


def test_valid_app_names_accepted():
    for good in ("mydashapp", "a", "web-1", "svc_app"):
        assert dash_deploy.is_valid_app_name(good), good


# ------------------------------------------------------- unit: config render


def test_nginx_config_points_at_gunicorn(sandbox_home):
    cfg = dash_deploy.render_nginx_config("my-server.example.com", port=8050)
    assert "proxy_pass http://127.0.0.1:8050;" in cfg
    assert "server_name my-server.example.com;" in cfg
    assert "X-Forwarded-Proto" in cfg


def test_nginx_config_empty_server_name_defaults_to_wildcard(sandbox_home):
    cfg = dash_deploy.render_nginx_config("", port=8050)
    assert "server_name _;" in cfg


def test_systemd_unit_binds_tcp_not_unix_socket(sandbox_home):
    # Regression: the old template bound a unix socket with -m 007 while nginx
    # proxied to 127.0.0.1:8050 TCP - nginx proxied to nothing.
    unit = dash_deploy.render_systemd_unit("myapp", port=8050)
    assert "--bind 127.0.0.1:8050" in unit
    assert ".sock" not in unit
    assert "-m 007" not in unit
    assert f"WorkingDirectory={dash_deploy.base_dir() / 'myapp'}" in unit
    assert "Restart=on-failure" in unit


def test_sample_app_defines_gunicorn_entrypoint():
    src = dash_deploy.sample_app_source("sampleapp", port=8050)
    assert "server = app.server" in src
    assert "app.run(host=" in src
    assert "8050" in src


# --------------------------------------------------------- e2e: deploy flow


async def _drive(app, pilot, answers):
    """Feed answers to the sequential prompts, then wait for the flow."""
    for answer in answers:
        for _ in range(200):
            await pilot.pause(0.05)
            fut = app._input_future
            if fut is not None and not fut.done():
                break
        else:
            raise AssertionError("timed out waiting for a prompt")
        keys = list(answer) if answer else []
        await pilot.press(*keys, "enter")
        await pilot.pause(0.05)
    for _ in range(400):
        await pilot.pause(0.05)
        if app.finished or app.aborted:
            return
    raise AssertionError("deploy flow never settled")


async def test_full_happy_path_records_every_step(sandbox_home):
    from dash_deploy import DashDeployApp

    app = DashDeployApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        await pilot.click("#start-button")
        await _drive(app, pilot, ["mydashapp", "y", ""])

    assert app.finished is True
    assert app.aborted is False
    recorded = app.recorded
    text = "\n".join(recorded)

    # venv by absolute path (regression: the old code ran `source activate`,
    # which does nothing in a child process, leaving pip on the system python)
    assert "python3 -m venv" in text
    venv_pip = [c for c in recorded if "pip install dash gunicorn" in c]
    assert venv_pip and "venv/bin/pip" in venv_pip[0]

    # every privileged command goes through sudo -S (regression: bare sudo)
    sudo_cmds = [c for c in recorded if c.startswith("sudo")]
    assert sudo_cmds and all("sudo -S -p '' " in c for c in sudo_cmds)

    # config writes use temp file + mv (no echo|tee stdin clash)
    assert any("mv <tmp> /etc/nginx/sites-available/mydashapp" in c for c in recorded)
    assert any("mv <tmp> /etc/systemd/system/mydashapp.service" in c for c in recorded)
    assert any(c == "sudo -S -p '' nginx -t" for c in recorded)
    assert any("systemctl restart nginx" in c for c in recorded)
    assert any("systemctl daemon-reload" in c for c in recorded)
    assert any("systemctl enable --now mydashapp" in c for c in recorded)

    # both smoke tests recorded
    assert any("local smoke test" in c for c in recorded)
    assert any("curl -sf" in c for c in recorded)

    # order: apt update happens before nginx restart
    apt_idx = next(i for i, c in enumerate(recorded) if "apt-get update" in c)
    nginx_idx = next(i for i, c in enumerate(recorded) if "restart nginx" in c)
    assert apt_idx < nginx_idx

    # the sample app was written into the sandbox with the right name
    sample = sandbox_home / "mydashapp" / "app.py"
    assert sample.exists()
    assert "server = app.server" in sample.read_text()


async def test_invalid_name_is_reasked_before_any_command(sandbox_home):
    from dash_deploy import DashDeployApp

    app = DashDeployApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        await pilot.click("#start-button")
        await _drive(app, pilot, ["Bad Name!", "mydashapp", "n"])

    assert app.aborted is True  # declined sample creation -> clean abort
    # The invalid name provoked a re-ask, so the flow still deployed steps
    # would have run mkdir first; assert the mkdir used the VALID name only.
    assert all(isinstance(c, str) for c in app.recorded)
    assert not any("Bad Name" in c for c in app.recorded)


async def test_declining_sample_app_aborts_cleanly(sandbox_home):
    from dash_deploy import DashDeployApp

    app = DashDeployApp()
    async with app.run_test() as pilot:
        await pilot.pause(0.1)
        await pilot.click("#start-button")
        await _drive(app, pilot, ["mydashapp", "n"])

    assert app.aborted is True
    assert app.finished is False
    assert not (sandbox_home / "mydashapp" / "app.py").exists()


# ------------------------------------------------------ sample app import


def test_sample_app_imports_with_real_dash(tmp_path):
    """The generated app.py must import cleanly and expose a WSGI entrypoint."""
    dash_mod = pytest.importorskip("dash")

    app_py = tmp_path / "sample_app_mod.py"
    app_py.write_text(dash_deploy.sample_app_source("sampleapp"))
    sys.path.insert(0, str(tmp_path))
    try:
        mod = importlib.import_module("sample_app_mod")
    finally:
        sys.path.remove(str(tmp_path))
        sys.modules.pop("sample_app_mod", None)

    from flask import Flask

    assert isinstance(mod.server, Flask)
    assert callable(mod.app)
    assert mod.app.title == "sampleapp"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__]))
