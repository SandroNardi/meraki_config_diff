# app.py
"""
This module initializes and runs the PyWebIO application.
It sets up logging, configures the UI, and orchestrates the main application flow
by integrating Meraki API utilities and project-specific logic and UI components.
"""
from pywebio.output import toast
from pywebio import start_server, config
from meraki_tools.my_logging import setup_logger  # Setup logger and log storage
from pywebio.session import register_thread
import threading
import meraki_tools.meraki_ui as meraki_ui
import os
import about

# Import the new class-based modules
from project_ui import ProjectUI # type: ignore
from meraki_tools.meraki_api_utils import MerakiAPIWrapper # type: ignore


# Initialize logger with console output enabled for debugging and monitoring.
logger = setup_logger(enable_logging=True, console_logging=True, file_logging=True)

# Define required application setup parameters and their necessity.
required_app_setup_param: dict[str, bool] = {"api_key": True, "organization_id": True, "network_id": False}

# Application setup parameters, potentially from environment variables or defaults.
app_setup_param: dict[str, str | None] = {"api_key": os.getenv("MK_CSM_KEY"), "organization_id": os.getenv("MK_MAIN_ORG")}

# Define the scope name for the application's UI.
app_scope_name: str = "app"

# Initialize the PyWebIO UI instance with the application scope and information.
UI: meraki_ui.PyWebIOApp = meraki_ui.PyWebIOApp(app_scope_name, about.APP_INFO)

def app() -> None:
    """
    The main PyWebIO application function.

    Initializes the UI, sets up background tasks, and orchestrates the application flow.
    It handles API utility setup, error handling, and delegates control to the ProjectUI.
    """
    logger.info("Starting PyWebIO application.")
    try:
        # Create and register a background thread to update the log display in the UI.
        # This thread runs UI.update_log_display to continuously refresh the log output.
        t: threading.Thread = threading.Thread(target=UI.update_log_display, daemon=True)
        register_thread(t)

        # Render the application header using the UI instance.
        UI.render_header()
        # Start the log update thread to display real-time logs.
        t.start()

        # Call app_setup to configure API utilities and retrieve the MerakiAPI_Utils object.
        api_utils: MerakiAPIWrapper | None = UI.app_setup(required_app_setup_param, app_setup_param=app_setup_param)

        if api_utils is None:
            # Handle setup failure (e.g., API key missing, organization not found).
            logger.error("Application setup failed. Exiting.")
            toast("Application setup failed. Please check configurations.", color="error", duration=0)
            return # Use return instead of exit(1) in PyWebIO app context

        # Instantiate the ProjectUI class, injecting both api_utils and the application scope name.
        project_ui_instance: ProjectUI = ProjectUI(api_utils, app_scope_name)

        # Start the application by calling the main menu method on the ProjectUI instance.
        project_ui_instance.app_main_menu()

    except Exception as e:
        # Log and show error toast if any unexpected error occurs during application startup.
        logger.exception(f"An unexpected error occurred during application startup: {e}")
        toast(f"An unexpected error occurred during startup: {e}", color="error", duration=0)

if __name__ == "__main__":
    """
    Entry point of the script.

    Configures PyWebIO and starts the server.
    It applies custom CSS and launches the PyWebIO application on a specified port.
    """
    logger.info("Application script started.")
    # Apply custom CSS styles from the wrapper module for UI customization.
    config(css_style=UI.get_css_style())
    # Start PyWebIO server on port 8080 with debug enabled for development.
    start_server(app, port=8080, debug=True)