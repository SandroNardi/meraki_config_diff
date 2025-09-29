#type: ignore
from pywebio.output import put_html, put_buttons, put_scope, use_scope, put_text, put_collapse, put_scrollable, toast, popup
from pywebio.session import download, run_js
from pywebio.exceptions import SessionNotFoundException
from pywebio.input import input_group, select, input as pywebio_input
import threading
import time
import io
import csv
import os
from typing import Dict, List, Any, Optional, Tuple, cast
from .meraki_api_utils import MerakiAPIWrapper
from .my_logging import get_logger, log_entries

class PyWebIOApp:
    """
    PyWebIO-based web application class for managing Meraki API interactions,
    UI rendering, and logging.
    """

    nav_buttons = [
        {"label": "Current Param", "value": "current_param"},
        {"label": "App Restart", "value": "app_restart"},
        {"label": "About", "value": "about"},
    ]

    def __init__(self, app_scope_name: str, app_info: Dict[str, Any]) -> None:
        """Initialize the app with scope name and app metadata."""
        self.logger = get_logger()
        self.last_displayed_log_index: int = 0
        self.log_entries_lock = threading.Lock()
        self.meraki_api_utils = MerakiAPIWrapper()
        self.app_scope_name = app_scope_name
        self.app_info = app_info

    def get_css_style(self) -> str:
        """Read and return CSS styles from 'style.css' file."""
        css_file_path = os.path.join(os.path.dirname(__file__), 'style.css')
        try:
            with open(css_file_path, 'r', encoding='utf-8') as f:
                css_content = f.read()
                self.logger.debug(f"Successfully read styles.css from {css_file_path}.")
                return css_content
        except FileNotFoundError:
            self.logger.error(f"Error: styles.css not found at {css_file_path}")
            return ""
        except Exception as e:
            self.logger.exception(f"Unexpected error reading styles.css: {e}")
            return ""

    def app_setup(
        self,
        required_app_setup_param: Dict[str, Any],
        app_setup_param: Optional[Dict[str, Any]] = None,
        enable_caching: Optional[bool] = True,
    ) -> Optional[MerakiAPIWrapper]:
        """
        Setup application parameters and Meraki API wrapper instance.

        Args:
            required_app_setup_param: Dict specifying required parameters.
            app_setup_param: Optional dict of initial parameter values.
            enable_caching: Optional flag to enable caching.

        Returns:
            MerakiAPIWrapper instance if setup successful, else None.
        """
        try:
            caching = enable_caching if enable_caching is not None else False
            initial_api_key = app_setup_param.get("api_key") if app_setup_param else None
            self.meraki_api_utils = MerakiAPIWrapper(initial_api_key=initial_api_key, enable_caching=caching)

            if not self.meraki_api_utils.setup_application_parameters(required_app_setup_param, app_setup_param=app_setup_param, enable_caching=caching):
                self.logger.error("Initial application parameter setup failed.")
                toast("Initial application parameter setup failed. Please check your configuration.", color="error", duration=0)

            with use_scope(self.app_scope_name, clear=True):
                if required_app_setup_param.get("api_key") and not self.meraki_api_utils.is_api_key_set():
                    self.logger.info("API Key required and not set. Prompting user.")
                    if self.get_valid_api_key(self.meraki_api_utils._api_key) is None:
                        return None

                organizations: Optional[List[Dict[str, Any]]] = None
                if required_app_setup_param.get("organization_id"):
                    self.logger.info("Organization ID required. Retrieving organizations.")
                    organizations = self.retrieve_organizations()
                    if organizations is None:
                        return None

                    org_id_to_validate = app_setup_param.get("organization_id") if app_setup_param else None
                    if org_id_to_validate is None and self.meraki_api_utils.is_organization_id_set():
                        org_id_to_validate = self.meraki_api_utils.get_organization_id()
                        self.logger.info(f"Organization ID already set: {org_id_to_validate}. Re-validating.")
                    elif org_id_to_validate:
                        self.logger.info(f"Organization ID provided in app_setup_param: {org_id_to_validate}.")

                    selected_org_id, _ = self.select_organization(org_id_to_validate, organizations)
                    if selected_org_id is None:
                        return None

                networks: Optional[List[Dict[str, str]]] = None
                if required_app_setup_param.get("network_id"):
                    self.logger.info("Network ID required. Retrieving networks.")
                    networks = self.retrieve_networks()
                    if networks is None:
                        return None

                    net_id_to_validate = app_setup_param.get("network_id") if app_setup_param else None
                    if net_id_to_validate is None and self.meraki_api_utils.is_network_id_set():
                        net_id_to_validate = self.meraki_api_utils.get_network_id()
                        self.logger.info(f"Network ID already set: {net_id_to_validate}. Re-validating.")
                    elif net_id_to_validate:
                        self.logger.info(f"Network ID provided in app_setup_param: {net_id_to_validate}.")

                    selected_net_id, _ = self.select_network(net_id_to_validate, networks)
                    if selected_net_id is None:
                        return None

                all_set, missing = self.meraki_api_utils.check_current_parameters_status()
                if all_set:
                    self.logger.info("All required parameters set - returning MerakiAPIWrapper instance.")
                    return self.meraki_api_utils
                else:
                    self.logger.error(f"Application setup failed: Missing parameters: {', '.join(missing)}")
                    toast(f"Application setup failed: Missing parameters: {', '.join(missing)}", color="error", duration=0)
                    return None
        except Exception as e:
            self.logger.exception(f"Unexpected error in app_setup: {e}")
            toast(f"Unexpected error during setup: {e}", color="error", duration=0)
            return None

    def show_about_popup(self) -> None:
        """Display an 'About' popup with application information."""
        info = self.app_info
        with popup("About " + info["name"], size='large'):
            put_text(f"{info['name']} (v{info['version']})").style('font-weight:bold; font-size:1.5em;')
            put_text(f"Description: {info['description']}")
            put_text(f"Author: {info['author']}")
            put_html("<hr>")
            put_text("Relevant Resources:")
            for name, link in info["links"].items():
                put_html(f'<a href="{link}" target="_blank">{name}</a><br>')
            put_html("<hr>")
            put_collapse(f"License: {info['license_name']}", [
                put_text(info['license_text']).style('white-space: pre-wrap; font-family: monospace;')
            ], open=False)
        self.logger.debug("'About' popup displayed.")

    def show_current_params_popup(self) -> None:
        """Display a popup showing current application parameters."""
        try:
            params = self.meraki_api_utils.get_current_app_params()
            with popup("Current Parameters"):
                put_text("Application Parameters").style('font-weight:bold; font-size:1.2em; margin-bottom:10px;')
                for key, details in params.items():
                    label = details.get('label', key.replace('_', ' ').title())
                    value = details.get('value', 'N/A')
                    put_text(f"{label}: {value}")
            self.logger.debug("'Current Parameters' popup displayed.")
        except Exception as e:
            self.logger.exception(f"Error displaying current parameters: {e}")

    def restart_app_client_side(self) -> None:
        """Trigger a client-side application restart by reloading the page."""
        self.logger.warning("Initiating client-side application restart (page reload).")
        run_js("location.reload()")

    def render_header(self) -> None:
        """Render the application header, navigation, and initial content."""
        try:
            put_html('<div class="top-gradient-bar"></div>')
            put_html(f'<div class="top-bar">{self.app_info.get("name")}</div>')
            put_html('<div class="main-layout-container">')
            put_scope('nav')
            put_scope('log_scope')
            with use_scope('log_scope'):
                put_collapse('Logs', [
                    put_scrollable(put_scope('log_display_content'), height=200, keep_bottom=True, scope='rolling_log_container'),
                    put_buttons([{'label': 'Download CSV', 'value': 'download'}], onclick=self.download_logs_as_csv)
                ], open=False)
            put_scope(self.app_scope_name)
            put_html('</div>')

            if self.nav_buttons:
                with use_scope('nav', clear=True):
                    def handle_nav_click(btn_value: str) -> None:
                        self.logger.info(f"Navigation button clicked: {btn_value}")
                        if btn_value == 'about':
                            self.show_about_popup()
                        elif btn_value == 'app_restart':
                            self.restart_app_client_side()
                        elif btn_value == 'current_param':
                            self.show_current_params_popup()
                        else:
                            put_text(f"Nav button clicked: {btn_value}")
                    put_buttons(self.nav_buttons, onclick=handle_nav_click)
            with use_scope(self.app_scope_name, clear=True):
                put_text(f"Welcome to {self.app_info.get("name")}").style('font-weight:bold; font-size:1.5em; margin-bottom:10px;')
                put_text("Use the navigation to manage DNS records, profiles, and networks.")
            self.logger.info("Rendered header and initial content.")
        except Exception as e:
            self.logger.exception(f"Unexpected error during header rendering: {e}")

    def download_logs_as_csv(self, btn_value: Any) -> None:
        """Download the in-memory logs as a CSV file."""
        try:
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['Timestamp - Level - Message'])
            with self.log_entries_lock:
                for entry in log_entries:
                    writer.writerow([entry])
            csv_data = output.getvalue().encode('utf-8')
            output.close()
            download('app_logs.csv', csv_data)
            self.logger.info("Triggered 'app_logs.csv' download.")
        except Exception as e:
            self.logger.exception(f"Unexpected error during CSV log download: {e}")

    def update_log_display(self) -> None:
        """Continuously update the log display area with new log entries."""
        self.logger.info("Starting log display update thread.")
        while True:
            try:
                with self.log_entries_lock:
                    current_log_count = len(log_entries)
                if current_log_count > self.last_displayed_log_index:
                    with use_scope('log_display_content', clear=False):
                        for i in range(self.last_displayed_log_index, current_log_count):
                            put_text(log_entries[i]).style(
                                'white-space: pre-wrap; font-family: monospace; background-color: #f0f0f0; padding: 4px; border-radius: 3px; margin-bottom: 2px;'
                            )
                    appended = current_log_count - self.last_displayed_log_index
                    self.last_displayed_log_index = current_log_count
                    self.logger.debug(f"Appended {appended} new log entries.")
                    run_js(
                        "document.querySelector(\"[scope='rolling_log_container'] .pywebio-scrollable-container\").scrollTop = "
                        "document.querySelector(\"[scope='rolling_log_container'] .pywebio-scrollable-container\").scrollHeight;"
                    )
            except SessionNotFoundException:
                # Session ended (e.g., browser refresh/navigation). Exit thread cleanly.
                self.logger.info("Session ended; stopping log display update thread.")
                break
            except Exception as e:
                self.logger.exception(f"Unexpected error in update_log_display thread: {e}")
            time.sleep(2)

    def get_valid_api_key(self, initial_api_key: Optional[str] = None) -> Optional[str]:
        """
        Prompt user to enter a valid API key until a valid one is set or user cancels.

        Args:
            initial_api_key: Optional initial API key to validate.

        Returns:
            Valid API key string or None if user cancels.
        """
        current_api_key = initial_api_key
        while True:
            if not current_api_key:
                api_key_data = input_group(
                    "Enter API Key",
                    [pywebio_input("API Key", name="api_key", type="password", required=True)]
                )
                if not api_key_data or not api_key_data.get("api_key"):
                    toast("API key is required to proceed. Exiting application.", color="error")
                    return None
                current_api_key = api_key_data["api_key"]

            self.meraki_api_utils.set_api_key(current_api_key)
            if self.meraki_api_utils.is_api_key_set():
                return current_api_key
            else:
                toast("Invalid API key. Please try again.", color="error")
                current_api_key = None

    def retrieve_organizations(self) -> Optional[List[Dict[str, Any]]]:
        """
        Retrieve list of organizations from Meraki API.

        Returns:
            List of organizations or None if error occurs.
        """
        organizations = self.meraki_api_utils.list_organizations()
        if isinstance(organizations, dict) and "error" in organizations:
            toast(f"Error retrieving organizations: {organizations.get('details')}", color="error")
            return None
        if not organizations:
            toast("No organizations found with the provided API key. Exiting application.", color="error")
            return None
        return organizations

    def retrieve_networks(self) -> Optional[List[Dict[str, str]]]:
        """
        Retrieve list of networks from Meraki API.

        Returns:
            List of networks or None if error occurs.
        """
        networks = self.meraki_api_utils.list_networks()
        if isinstance(networks, dict) and "error" in networks:
            toast(f"Error retrieving networks: {networks.get('details')}", color="error")
            self.logger.error(f"Failed to retrieve networks: {networks.get('details')}")
            return None
        if not networks:
            toast("No networks found. Please ensure an organization is selected and it contains networks.", color="error")
            self.logger.info("No networks found for the current context.")
            return None
        self.logger.info(f"Successfully retrieved {len(networks)} networks.")
        return cast(List[Dict[str, str]], networks)

    def select_organization(self, organization_id_param: Optional[str], organizations: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[str]]:
        """
        Select an organization by ID or prompt user to select from list.

        Args:
            organization_id_param: Optional organization ID to pre-select.
            organizations: List of available organizations.

        Returns:
            Tuple of selected organization ID and name, or (None, None) if cancelled.
        """
        valid_ids = {org["id"] for org in organizations}
        if organization_id_param in valid_ids:
            selected_id = organization_id_param
            selected_name = next(org["name"] for org in organizations if org["id"] == selected_id)
            self.meraki_api_utils.set_organization_id(selected_id, organization_name=selected_name)
            put_text(f"Organization selected: [{selected_id}] - {selected_name}").style('font-weight:bold; margin-bottom:10px;')
            return selected_id, selected_name

        if organization_id_param is not None:
            toast(f"Invalid organization id '{organization_id_param}'. Please select a valid organization.", color="error")

        options = [{"label": f"[{org['id']}] - {org['name']}", "value": org["id"]} for org in organizations]
        if not isinstance(options, list):
            self.logger.error("Options for organization selection must be a list.")
            toast("Internal error: Invalid options for organization selection.", color="error")
            return None, None

        org_selection = input_group(
            "Select an Organization",
            [select("Organization", name="organization_id", options=options, required=True)]
        )
        if not isinstance(org_selection, dict) or not org_selection.get("organization_id"):
            toast("Organization selection is required. Exiting application.", color="error")
            return None, None

        selected_id = org_selection["organization_id"]
        selected_name = next(org["name"] for org in organizations if org["id"] == selected_id)
        self.meraki_api_utils.set_organization_id(selected_id, organization_name=selected_name)
        put_text(f"Organization selected: [{selected_id}] - {selected_name}").style('font-weight:bold; margin-bottom:10px;')
        return selected_id, selected_name

    def select_network(self, network_id_param: Optional[str], networks: List[Dict[str, str]]) -> Tuple[Optional[str], Optional[str]]:
        """
        Select a network by ID or prompt user to select from list.

        Args:
            network_id_param: Optional network ID to pre-select.
            networks: List of available networks.

        Returns:
            Tuple of selected network ID and name, or (None, None) if cancelled.
        """
        valid_ids = {network["id"] for network in networks}
        if network_id_param is not None and network_id_param in valid_ids:
            selected_id = network_id_param
            selected_name = next(network["name"] for network in networks if network["id"] == selected_id)
            self.meraki_api_utils.set_network_id(selected_id, network_name=selected_name)
            put_text(f"Network selected: [{selected_id}] - {selected_name}").style('font-weight:bold; margin-bottom:10px;')
            return selected_id, selected_name

        if network_id_param is not None:
            toast(f"Invalid network id '{network_id_param}'. Please select a valid network.", color="error")

        options = [{"label": f"[{network['id']}] - {network['name']}", "value": network["id"]} for network in networks]
        if not isinstance(options, list):
            self.logger.error("Options for network selection must be a list.")
            toast("Internal error: Invalid options for network selection.", color="error")
            return None, None

        network_selection = input_group(
            "Select a Network",
            [select("Network", name="network_id", options=options, required=True)]
        )
        if not isinstance(network_selection, dict) or not network_selection.get("network_id"):
            toast("Network selection is required. Exiting application.", color="error")
            return None, None

        selected_id = network_selection["network_id"]
        selected_name = next(network["name"] for network in networks if network["id"] == selected_id)
        self.meraki_api_utils.set_network_id(selected_id, network_name=selected_name)
        put_text(f"Network selected: [{selected_id}] - {selected_name}").style('font-weight:bold; margin-bottom:10px;')
        return selected_id, selected_name