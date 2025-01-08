# Dash Deployment CLI

The **Dash Deployment CLI** is a fully interactive command-line application built using the **Textual** framework. It guides users through the process of deploying a Python Dash app to an Ubuntu server. The app automates the deployment steps, making it easy for developers to deploy their Dash apps without manually running commands or configuring services.

---

## Features

- **Step-by-Step Guidance**: Walks users through the entire deployment process.
- **Automated Commands**: Runs shell commands automatically to set up the server, install dependencies, and configure services.
- **User-Friendly Interface**: Uses an interactive CLI interface with buttons, labels, and input prompts.
- **Customizable**: Easily modify the app to suit specific deployment needs.
- **Supports**:
  - Python virtual environments.
  - Dash and Gunicorn installation.
  - Nginx configuration.
  - Systemd service setup.

---

## Prerequisites

Before using the Dash Deployment CLI, ensure you have the following:

1. **Ubuntu Server**: A running Ubuntu server (20.04 or later recommended).
2. **Python 3.8+**: Installed on the server.
3. **SSH Access**: Ability to connect to the server via SSH.
4. **Dash App Code**: Your Dash app code ready for deployment.

---

## Installation

1. **Clone the Repository**:
   ```bash
   git clone https://github.com/studiozeroseven/dash_deploy.git
   cd dash-deployment-cli
   ```

2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Run the CLI App**:
   ```bash
   python dash_deploy.py
   ```

## Usage

1. **Start the App**:
   Run the app using the command:
   ```bash
   python dash_deploy.py
   ```

2. **Follow the Prompts**:
   - The app will guide you through each step of the deployment process.
   - Provide inputs when prompted (e.g., app name).
   - The app will automatically run commands and display output.

3. **Deployment Steps**:
   The app will perform the following steps:
   - Update and install server dependencies.
   - Set up a Python virtual environment.
   - Install Dash and Gunicorn.
   - Configure Nginx as a reverse proxy.
   - Set up a systemd service to manage the Dash app.

4. **Access Your Dash App**:
   Once the deployment is complete, visit `http://your_server_ip` in your browser to access your Dash app.

---

## Customization

You can customize the app to suit your specific needs:

1. **Nginx Configuration**:
   Modify the Nginx configuration template in the `deploy_dash_app` method to add SSL, custom domains, or other settings.

2. **Systemd Service**:
   Adjust the systemd service configuration in the `deploy_dash_app` method to change user permissions, working directories, or other parameters.

3. **Styling**:
   Add custom CSS in the `style.css` file to change the appearance of the CLI interface.

---

## Example Deployment

Here’s an example of how the app works:

1. **Start the App**:
   ```bash
   python dash_deploy.py
   ```

2. **Welcome Screen**:
   ```
   Welcome to the Dash App Deployment CLI!
   This tool will guide you through deploying your Dash app to an Ubuntu server.
   [Start Deployment]
   ```

3. **Enter App Name**:
   ```
   Enter a name for your Dash app (e.g., mydashapp): mydashapp
   ```

4. **Follow the Steps**:
   The app will automatically:
   - Update the server.
   - Install dependencies.
   - Set up a virtual environment.
   - Install Dash and Gunicorn.
   - Configure Nginx and systemd.

5. **Deployment Complete**:
   ```
   Deployment Complete!
   Your Dash app is now deployed! Visit http://your_server_ip to access it.
   ```

---

## Troubleshooting

1. **Command Errors**:
   - If a command fails, the app will display the error message. Check the error and ensure all prerequisites are met.

2. **Nginx Issues**:
   - If Nginx fails to restart, check the configuration file at `/etc/nginx/sites-available/your_app_name`.

3. **Systemd Service Issues**:
   - If the systemd service fails to start, check the logs using:
     ```bash
     sudo journalctl -u your_app_name.service
     ```

---

## Contributing

Contributions are welcome! If you’d like to contribute to this project, please follow these steps:

1. Fork the repository.
2. Create a new branch for your feature or bug fix.
3. Commit your changes.
4. Submit a pull request.

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

- **Textual Framework**: For providing an excellent Python CLI framework.
- **Dash Framework**: For making it easy to build web applications in Python.
- **Codearmo Tutorial**: For the detailed deployment guide.

---

## Contact

For questions or feedback, please open an issue on GitHub or contact the maintainer:

- **Your Name**
- **Email**: your.email@example.com
- **GitHub**: [yourusername](https://github.com/yourusername)

---

Enjoy deploying your Dash apps with ease! 🚀
```
