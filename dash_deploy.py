import os
import subprocess
from textual.app import App, ComposeResult
from textual.containers import Container
from textual.widgets import Header, Footer, Button, Input, Static, Label

class PasswordDialog(Container):
    """A custom dialog for entering the sudo password."""

    def compose(self) -> ComposeResult:
        """Compose the password dialog."""
        yield Label("Enter sudo password:")
        yield Input(placeholder="Password", password=True, id="password-input")
        yield Button("Submit", id="submit-button")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle the submit button press."""
        if event.button.id == "submit-button":
            password = self.query_one("#password-input", Input).value
            self.app.password = password  # Store the password in the app
            self.remove()  # Close the dialog

class DashDeployApp(App):
    """A Textual CLI app to deploy a Dash app to an Ubuntu server."""

    CSS_PATH = "style.css"
    BINDINGS = [("q", "quit", "Quit")]

    def __init__(self):
        super().__init__()
        self.password = None  # Store the sudo password

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header()
        yield Container(
            Label("Welcome to the Dash App Deployment CLI!", id="title"),
            Label("This tool will guide you through deploying your Dash app to an Ubuntu server.", id="subtitle"),
            Button("Start Deployment", id="start-button"),
            id="main-container"
        )
        yield Footer()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "start-button":
            await self.deploy_dash_app()

    async def deploy_dash_app(self) -> None:
        """Guide the user through the deployment process."""
        self.clear_screen()
        await self.add_step("Step 1: Update and Install Dependencies")
        await self.run_command("sudo apt update && sudo apt upgrade -y")
        await self.run_command("sudo apt install -y python3-pip python3-venv nginx")

        await self.add_step("Step 2: Set Up a Python Virtual Environment")
        app_name = await self.ask_user("Enter a name for your Dash app (e.g., mydashapp):")
        await self.run_command(f"mkdir ~/{app_name}")
        await self.run_command(f"python3 -m venv ~/{app_name}/venv")
        await self.run_command(f"source ~/{app_name}/venv/bin/activate")

        await self.add_step("Step 3: Install Dash and Required Packages")
        await self.run_command("pip install dash gunicorn")

        await self.add_step("Step 4: Prepare Your Dash App")
        await self.ask_user("Place your Dash app code in ~/{app_name}/app.py. Press Enter to continue.")

        await self.add_step("Step 5: Test Your Dash App Locally")
        await self.run_command(f"python ~/{app_name}/app.py")
        await self.ask_user("Ensure your app is running locally. Press Enter to continue.")

        await self.add_step("Step 6: Set Up Gunicorn")
        await self.run_command(f"gunicorn --workers 3 --bind 0.0.0.0:8050 app:server")

        await self.add_step("Step 7: Configure Nginx")
        nginx_config = f"""
        server {{
            listen 80;
            server_name your_server_ip;

            location / {{
                proxy_pass http://127.0.0.1:8050;
                proxy_set_header Host $host;
                proxy_set_header X-Real-IP $remote_addr;
                proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            }}
        }}
        """
        await self.run_command(f"echo '{nginx_config}' | sudo tee /etc/nginx/sites-available/{app_name}")
        await self.run_command(f"sudo ln -s /etc/nginx/sites-available/{app_name} /etc/nginx/sites-enabled/")
        await self.run_command("sudo nginx -t")
        await self.run_command("sudo systemctl restart nginx")

        await self.add_step("Step 8: Set Up a Systemd Service")
        service_config = f"""
        [Unit]
        Description=Gunicorn instance to serve {app_name}
        After=network.target

        [Service]
        User={os.getlogin()}
        Group=www-data
        WorkingDirectory=/home/{os.getlogin()}/{app_name}
        ExecStart=/home/{os.getlogin()}/{app_name}/venv/bin/gunicorn --workers 3 --bind unix:{app_name}.sock -m 007 app:server

        [Install]
        WantedBy=multi-user.target
        """
        await self.run_command(f"echo '{service_config}' | sudo tee /etc/systemd/system/{app_name}.service")
        await self.run_command(f"sudo systemctl start {app_name}")
        await self.run_command(f"sudo systemctl enable {app_name}")

        await self.add_step("Deployment Complete!")
        await self.ask_user(f"Your Dash app is now deployed! Visit http://your_server_ip to access it. Press Enter to exit.")

    def clear_screen(self) -> None:
        """Clear the terminal screen."""
        os.system("clear")

    async def add_step(self, message: str) -> None:
        """Display a step in the deployment process."""
        self.mount(Label(f"\n{message}\n"))
        self.refresh()  # Refresh the UI

    async def ask_user(self, prompt: str) -> str:
        """Ask the user for input."""
        self.mount(Label(prompt))
        self.refresh()  # Refresh the UI
        return await self.get_input()

    async def get_input(self) -> str:
        """Get input from the user."""
        input_widget = Input()
        self.mount(input_widget)
        self.refresh()
        return await input_widget.wait_for_input()

    async def run_command(self, command: str) -> None:
        """Run a shell command and handle sudo password prompts."""
        self.mount(Label(f"Running: {command}"))
        self.refresh()  # Refresh the UI

        if command.startswith("sudo"):
            # Show the password dialog
            await self.show_password_dialog()
            if not self.password:
                self.mount(Label("Error: No password provided."))
                return

            # Run the sudo command with the password
            process = subprocess.Popen(
                command,
                shell=True,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate(input=f"{self.password}\n")
        else:
            # Run the non-sudo command
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )
            stdout, stderr = process.communicate()

        if process.returncode != 0:
            self.mount(Label(f"Error: {stderr}"))
        else:
            self.mount(Label(stdout))
        self.refresh()  # Refresh the UI

    async def show_password_dialog(self) -> None:
        """Show the password input dialog."""
        dialog = PasswordDialog()
        self.mount(dialog)
        self.refresh()
        await dialog.wait_for_remove()  # Wait for the dialog to close

if __name__ == "__main__":
    app = DashDeployApp()
    app.run()
