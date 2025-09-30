# project_ui.py
"""
This module handles the Graphical User Interface (GUI) for the application using PyWebIO.
It defines the layout, user interaction flows for saving and comparing configurations,
and displays results. It integrates with `project_logic` for backend logic
and `gui_components` for styling.
"""

# --- Standard Library Imports ---
import logging
from multiprocessing import Value
from os import name
from typing import Optional, List, Dict, Any, Tuple
import json
from datetime import datetime, timedelta, timezone
import io
import csv

# --- Third-Party Imports ---
from pywebio.input import *
from pywebio.output import *

from pyecharts.charts import Line
from pyecharts import options as opts

# --- Local Application Imports ---
from meraki_tools.my_logging import get_logger
from project_logic import ProjectLogic
from meraki_tools.meraki_api_utils import MerakiAPIWrapper
# --- Logger Setup ---
logger = logging.getLogger()


class ProjectUI:
    def __init__(self, api_utils: MerakiAPIWrapper,app_scope_name):
        self._project_logic = ProjectLogic(api_utils)
        self._api_utils = api_utils
        self.logger = get_logger()
        self.app_scope_name = app_scope_name
        self.logger.info("ProjectUI initialized with ProjectLogic instance.")

    # --- Dropdown Data Preparation Functions ---
    def list_organizations_for_dropdown(self) -> List[Dict[str, Any]]:
        """Fetches organizations and formats them for a dropdown menu."""
        orgs = self._project_logic.get_organizations(True)
        return [{"label": f"[{org['id']}] - {org['name']}", "value": org["id"]} for org in orgs]


    def list_devices_for_dropdown(self) -> List[Dict[str, Any]]:
        """Fetches devices and formats them for a dropdown menu."""
        devices = self._project_logic.get_devices(True)
        return [{"label": f"[{device['serial']}] - {device['name']}", "value": device["serial"]} for device in devices]

    # --- User Interaction and Configuration Management Functions ---
    def select_organization(self):
        """
        Prompts the user to select an organization from a dropdown.
        The selected organization is then set in the `_project_logic` module.
        """
        self.logger.info("Starting organization selection process")
        org_options = self.list_organizations_for_dropdown()
        if not org_options:
            popup("Error", "No organizations found. Please check your API key and permissions.")
            self.logger.error("No organizations available for selection.")
            return

        org_selection = input_group(
            "Select an Organization",
            [
                select("Choose an Organization", name="org_id", options=org_options),
                actions(
                    name="actions",
                    buttons=[{"label": "Set", "value": "set", "color": "primary"}],
                ),
            ],
        )
        if org_selection["actions"] == "set":
            try:
                self._project_logic.set_organization(org_selection["org_id"])
                self.logger.info(f"Organization selected: {org_selection['org_id']}")
                toast("Organization set successfully!", color="success")
            except Exception as e:
                self.logger.error(f"Failed to set organization: {e}", exc_info=True)
                popup("Error Setting Organization", f"Failed to set organization: {e}\nPlease try again.")
                toast("Error setting organization.", color="error")

    def save_reference_config_level(
        self,
        scope_key: str,
        input_group_title: str,
        checkbox_name: str,
        checkbox_label: str,
        entity_type_name: str,
        select_label: Optional[str] = None,
        select_name: Optional[str] = None,
        select_options_func: Optional[callable] = None,
    ):
        """
        Guides the user through saving configurations for a selected entity (network or device)
        or for the organization level.
        It presents a dynamic list of operations and an entity selector if applicable.
        """
        self.logger.info(f"Starting process to save {entity_type_name}-level reference configurations.")
        with use_scope(self.app_scope_name, clear=True):
            level_operations = self._project_logic.get_operations(scope_key)
            checkbox_options = []
            for operation in level_operations:
                label = f"Save {operation['display_name']}"
                value = f"{self._project_logic.USE_CASE_KEYS['store_prefix']}{operation['name']}"
                checkbox_options.append({"label": label, "value": value})

            input_elements = []
            print(select_label,select_name)
            if select_label and select_name and select_options_func:
                input_elements.append(
                    select(
                        select_label,
                        name=select_name,
                        options=select_options_func(), # Call the function passed as argument
                    )
                )

            input_elements.append(
                checkbox(
                    name=checkbox_name,
                    label=checkbox_label,
                    options=checkbox_options,
                )
            )
            input_elements.append(
                actions(
                    name="actions",
                    buttons=[
                        {"label": "Set", "value": "set", "color": "primary"},
                        {"label": "Cancel", "value": "cancel", "color": "secondary"},
                    ],
                ),
            )

            user_input = input_group(input_group_title, input_elements)

            if user_input["actions"] == "cancel":
                self.app_main_menu()
                return

            identifier = None
            if select_name:
                identifier = user_input.get(select_name)

            selected_actions = user_input.get(checkbox_name, [])

            if select_name and not identifier:
                self.logger.warning(f"No {entity_type_name} selected for saving.")
                toast(f"No {entity_type_name} selected.", color="warn")
                clear(self.app_scope_name)
                self.app_main_menu()
                return

            if not selected_actions:
                self.logger.warning("No operations selected for saving.")
                toast("No operations selected.", color="warn")
                clear(self.app_scope_name)
                self.app_main_menu()
                return

            all_successful = True
            for operation in level_operations:
                action_key = f"{self._project_logic.USE_CASE_KEYS['store_prefix']}{operation['name']}"
                if action_key in selected_actions:
                    operation_kwargs = {}
                    if identifier:
                        operation_kwargs["identifier"] = identifier

                    result = self._project_logic.core_data_operation(
                        scope_key, operation["name"], "store", **operation_kwargs
                    )
                    if result.get("success"):
                        if identifier:
                            self.logger.info(f"{operation['display_name']} saved for {entity_type_name}: {identifier}.")
                            toast(f"Saved {operation['display_name']} for {identifier}", color="success")
                        else:
                            self.logger.info(f"{operation['display_name']} saved for {entity_type_name}.")
                            toast(f"Saved {operation['display_name']}", color="success")
                    else:
                        all_successful = False
                        error_msg = result.get("error", "Unknown error occurred.")
                        if identifier:
                            self.logger.error(f"Failed to save {operation['display_name']} for {entity_type_name} {identifier}: {error_msg}")
                            popup(f"Error Saving {operation['display_name']}", f"Failed to save for {entity_type_name} {identifier}: {error_msg}")
                        else:
                            self.logger.error(f"Failed to save {operation['display_name']} for {entity_type_name}: {error_msg}")
                            popup(f"Error Saving {operation['display_name']}", f"Failed to save: {error_msg}")
                        toast(f"Error saving {operation['display_name']}", color="error")

            if all_successful:
                if identifier:
                    toast(f"All selected configurations for {entity_type_name} {identifier} saved successfully!", color="success", duration=3)
                else:
                    toast(f"All selected configurations for {entity_type_name} saved successfully!", color="success", duration=3)
            else:
                if identifier:
                    toast(f"Some configurations for {entity_type_name} {identifier} failed to save. Check pop-ups and logs.", color="error", duration=5)
                else:
                    toast(f"Some configurations for {entity_type_name} failed to save. Check pop-ups and logs for details.", color="error", duration=5)


            self.app_main_menu()

    def save_reference_config_network_level(self):
        """
        Guides the user through saving network-level configurations for a selected network.
        It presents a dynamic list of operations (e.g., saving SSIDs) and a network selector.
        """
        self.save_reference_config_level(
            scope_key=self._project_logic.USE_CASE_KEYS.get("network_level"),
            input_group_title="Network-Level Configuration",
            select_label="Select a Network",
            select_name="network_id",
            select_options_func=self.list_networks_for_dropdown,
            checkbox_name="network_actions",
            checkbox_label="Actions for Selected Network",
            entity_type_name="network"
        )
    # Inside the ProjectUI class
    def list_networks_for_dropdown(self) -> List[Dict[str, Any]]:
        """Fetches networks and formats them for a dropdown menu."""
        networks = self._api_utils.list_networks(use_cache=True) # Assuming list_networks takes use_cache
        return [{"label": f"[{net['id']}] - {net['name']}", "value": net["id"]} for net in networks]

    def save_reference_config_device_level(self):
        """
        Guides the user through saving device-level configurations for a selected device.
        It presents a dynamic list of operations and a device selector.
        """
        self.save_reference_config_level(
            scope_key=self._project_logic.USE_CASE_KEYS["device_level"],
            input_group_title="Device-Level Configuration",
            select_label="Select a Device",
            select_name="device_id",
            select_options_func=self.list_devices_for_dropdown,
            checkbox_name="device_actions",
            checkbox_label="Actions for Selected Devices",
            entity_type_name="device"
        )

    def save_reference_config_organization_level(self):
        """
        Guides the user through saving organization-level configurations.
        It presents a dynamic list of operations (e.g., saving admins) based on `core.USE_CASES`.
        """
        self.save_reference_config_level(
            scope_key=self._project_logic.USE_CASE_KEYS["organization_level"],
            input_group_title="Organization-Level Configuration",
            checkbox_name="org_actions",
            checkbox_label="Actions for Organization",
            entity_type_name="the organization"
        )

    # --- GUI Layout and Navigation Functions ---


    def app_main_menu(self):
        """
        The main function for the GUI, responsible for displaying the primary navigation
        options (Store reference config, Compare with reference config) in the sidenav.
        """
        with use_scope(self.app_scope_name, clear=True):
            # Generate "Store reference config" buttons dynamically based on use cases.
            store_buttons = []
            store_onclicks = []

            for use_case_key, use_case in self._project_logic.get_use_cases_items():
                label = use_case[self._project_logic.USE_CASE_KEYS["display_name"]]
                store_buttons.append({"label": label, "value": use_case_key})
                func_name = f"save_reference_config_{use_case_key}"
                func = getattr(self, func_name, None)
                store_onclicks.append(func if func else (lambda: None))

            put_markdown("**Store reference config**")
            put_buttons(store_buttons, onclick=store_onclicks)
            put_markdown("---")

            # Generate "Compare with reference config" buttons dynamically.
            compare_buttons = []
            compare_onclicks = []
            for use_case_key, use_case in self._project_logic.get_use_cases_items():
                label = f"{use_case[self._project_logic.USE_CASE_KEYS['display_name']]}"
                compare_buttons.append({"label": label, "value": f"{self._project_logic.USE_CASE_KEYS['compare_prefix']}{use_case_key}"})
                func_name = f"compare_{use_case_key}"
                func = getattr(self, func_name, None)
                compare_onclicks.append(func if func else (lambda: None))

            put_markdown("**Compare with reference config**")
            put_buttons(compare_buttons, onclick=compare_onclicks)



    def perform_comparison(self, scope: str, additional_input_elements: List[Any] = None):
        """
        Handles the common logic for performing configuration comparisons (organization/network/device level).
        It prompts the user to select files for comparison and displays a progress bar.
        """

        use_case_inputs = []
        operations = self._project_logic.get_operations(scope)

        for operation in operations:
            operation_name = operation["name"]
            operation_display_name = operation["display_name"]

            relevant_json_files = self._project_logic.list_json_files(
                self._project_logic.get_scope_folder_name(scope), operation_name
            )
            options = [""] + relevant_json_files if relevant_json_files else ["No JSON files found"]
            if not relevant_json_files:
                 self.logger.warning(f"No JSON files found for {operation_display_name} in {scope}.")

            use_case_inputs.append(
                select(
                    f"Select operation for {operation_display_name}",
                    lablel=options,
                    value=operation_name,
                )
            )

        input_group_elements = []
        if additional_input_elements:
            input_group_elements.extend(additional_input_elements)
        input_group_elements.extend(use_case_inputs)
        input_group_elements.append(
            checkbox(
                "Comparison Options",
                options=[{"label": "Perform Deep Comparison (using DeepDiff)", "value": "deep"}],
                name="deep_comparison_checkbox",
            )
        )
        input_group_elements.append(actions(name="submit", buttons=["Submit", "Cancel"]))

        operation_selections = input_group(
            "Choose files for each use case",
            input_group_elements,
        )

        if operation_selections["submit"] == "Cancel":
            clear(self.app_scope_name)
            self.app_main_menu()
            return

        perform_deep_comparison = "deep" in operation_selections.get("deep_comparison_checkbox", [])
        comparison_method = "deepdiff" if perform_deep_comparison else "flat"

        results = {}
        with use_scope(self.app_scope_name, clear=True):
            put_progressbar("bar")

            total_operations = len(operations)
            for idx, operation in enumerate(operations, start=1):
                operation_name = operation["name"]
                selected_file = operation_selections.get(operation_name)
                if not selected_file or selected_file == "No JSON files found":
                    results[operation_name] = {"error": f"No baseline file selected or found for {operation['display_name']}."}
                    self.logger.warning(f"No baseline file selected or found for {operation['display_name']}.")
                else:
                    kwargs = {"filename": selected_file}
                    if scope == self._project_logic.USE_CASE_KEYS["network_level"]:
                        selected_network_tags = operation_selections.get("selected_network_tags", [])
                        if selected_network_tags:
                            kwargs["network_tags"] = selected_network_tags
                    elif scope == self._project_logic.USE_CASE_KEYS["device_level"]:
                        selected_device_tags = operation_selections.get("selected_device_tags", [])
                        selected_network_tags_for_devices = operation_selections.get("selected_network_tags", [])
                        selected_device_models=operation_selections.get("selected_device_models",[])
                        selected_product_types=operation_selections.get("selected_product_types",[])
                        if selected_device_tags:
                            kwargs["device_tags"] = selected_device_tags
                        if selected_network_tags_for_devices:
                            kwargs["network_tags"] = selected_network_tags_for_devices
                        if selected_device_models:
                            kwargs["device_models"] = selected_device_models
                        if selected_product_types:
                            kwargs["product_types"] = selected_product_types

                    kwargs["comparison_method"] = comparison_method

                    op_results = self._project_logic.core_data_operation(
                        scope,
                        operation["name"],
                        "compare",
                        **kwargs,
                    )
                    results[operation["name"]] = op_results

                    if op_results and isinstance(op_results, dict) and "error" in op_results:
                        self.logger.error(f"Error during comparison for {operation['name']}: {op_results['error']}")
                        toast(f"Error comparing {operation['name']}: {op_results['error']}", color="error", duration=5)

                set_progressbar("bar", idx / total_operations)
        with use_scope(self.app_scope_name, clear=True):
            self.display_comparison_results(results, operation_selections, scope=scope)


    def compare_network_level(self):
        """
        Initiates a network-level configuration comparison, including an option
        to filter networks by tags.
        """
        with use_scope(self.app_scope_name, clear=True):
            with put_loading():
                networks = self._api_utils.list_networks(use_cache=True)
                unique_tags = sorted(list(set(tag for network in networks for tag in network.get("tags", []))))

                tag_checkboxes = None
                if not unique_tags:
                    self.logger.warning("No network tags are available for selection.")
                else:
                    tag_checkboxes = checkbox(
                        "Select network tags",
                        options=[{"label": tag, "value": tag} for tag in unique_tags],
                        name="selected_network_tags",
                        inline=True
                    )
                additional_inputs = [tag_checkboxes] if tag_checkboxes else []
            self.perform_comparison(self._project_logic.USE_CASE_KEYS["network_level"], additional_inputs)


    def compare_organization_level(self):
        """
        Initiates an organization-level configuration comparison.
        No additional filters (like tags) are applied at this level.
        """
        self.perform_comparison(self._project_logic.USE_CASE_KEYS["organization_level"])


    def compare_device_level(self):
        """
        Initiates a device-level configuration comparison, including options
        to filter devices by tags, device models, network tags, and product types.
        """
        with use_scope(self.app_scope_name, clear=True):
            with put_loading():
                devices = self._project_logic.get_devices(True, True)
                networks =self._project_logic.get_networks(True,True)

                unique_device_tags = sorted(list(set(tag for device in devices for tag in device.get("tags", []))))
                unique_device_models = sorted(list(set(device.get("model", "Unknown") for device in devices)))
                unique_network_tags = sorted(list(set(tag for network in networks for tag in network.get("tags", []))))
                unique_product_types = sorted(list(set(device.get("productType", "Unknown") for device in devices)))

                network_tag_checkboxes = None
                if unique_network_tags:
                    network_tag_checkboxes = checkbox(
                        "Select network tags",
                        options=[{"label": tag, "value": tag} for tag in unique_network_tags],
                        name="selected_network_tags",
                        inline=True,
                    )
                else:
                    self.logger.warning("No network tags are available for selection.")

                device_tag_checkboxes = None
                if unique_device_tags:
                    device_tag_checkboxes = checkbox(
                        "Select device tags",
                        options=[{"label": tag, "value": tag} for tag in unique_device_tags],
                        name="selected_device_tags",
                        inline=True,
                    )
                else:
                    self.logger.warning("No device tags are available for selection.")

                product_type_checkboxes = None
                if unique_product_types:
                    product_type_checkboxes = checkbox(
                        "Select product types",
                        options=[{"label": pt, "value": pt} for pt in unique_product_types],
                        name="selected_product_types",
                        inline=True,
                    )
                else:
                    self.logger.warning("No product types are available for selection.")

                device_model_checkboxes = None
                if unique_device_models:
                    device_model_checkboxes = checkbox(
                        "Select device models",
                        options=[{"label": model, "value": model} for model in unique_device_models],
                        name="selected_device_models",
                        inline=True,
                    )
                else:
                    self.logger.warning("No device models are available for selection.")

                additional_inputs = [
                    cb for cb in [
                        network_tag_checkboxes,
                        product_type_checkboxes,
                        device_tag_checkboxes,
                        device_model_checkboxes,
                    ] if cb is not None
                ]
            self.perform_comparison(self._project_logic.USE_CASE_KEYS["device_level"], additional_inputs)


    def format_value_for_html(self, value):
        """Helper to format complex values (dicts/lists) for HTML display with expand/collapse."""
        if isinstance(value, (dict, list)):
            json_str = json.dumps(value, indent=2)
            summary_text = json_str[:25].replace('\n', '').replace('\r', '') + ("..." if len(json_str) > 25 else "")
            return f"""
            <details>
                <summary style="cursor: pointer; white-space: pre;">{summary_text}</summary>
                <pre style="margin: 0; padding: 5px; background-color: #f8f8f8; border: 1px solid #ddd; overflow-x: auto;"><code>{json_str}</code></pre>
            </details>
            """
        else:
            return str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;').replace("'", '&#039;')

    def show_changes_popup(self, diff_results_list: List[Dict[str, Any]], item_name: str):
        """
        Displays a popup showing 'changed', 'added', and 'removed' items from
        DeepDiff results in a formatted table.
        """
        popup_title = f"Differences for {item_name}"
        table_html_parts = []
        has_content = False

        relevant_changes = diff_results_list

        if relevant_changes:
            has_content = True
            table_html_parts.append("""
            <table border="1" style="border-collapse: collapse; width: 100%;">
                <thead>
                    <tr>
                        <th style="padding: 8px; text-align: left;">Status</th>
                        <th style="padding: 8px; text-align: left;">Item ID</th>
                        <th style="padding: 8px; text-align: left;">Field</th>
                        <th style="padding: 8px; text-align: left;">Reference Value</th>
                        <th style="padding: 8px; text-align: left;">Current Value</th>
                    </tr>
                </thead>
                <tbody>
            """)

            relevant_changes.sort(key=lambda x: (x.get('status'), x.get('item_id')))

            for item_change in relevant_changes:
                item_id = item_change.get('item_id', 'N/A')
                status = item_change.get('status', 'unknown')
                changes_list = item_change.get('changes', [])

                row_style = ""
                if status == 'added':
                    row_style = "background-color: #d4edda;"
                elif status == 'removed':
                    row_style = "background-color: #f8d7da;"
                elif status == 'changed':
                    row_style = "background-color: #fff3cd;"

                if changes_list:
                    rowspan_count = len(changes_list) if changes_list else 1

                    for i, change_detail in enumerate(changes_list):
                        field_to_display = change_detail.get('field')
                        if field_to_display is None:
                            field_to_display = "(Full Item)"
                        elif field_to_display == "":
                            field_to_display = "(Root Value)"

                        reference_value = change_detail.get('reference_value')
                        current_value = change_detail.get('current_value')

                        formatted_reference_value = self.format_value_for_html(reference_value)
                        formatted_current_value = self.format_value_for_html(current_value)

                        table_html_parts.append(f"<tr style='{row_style}'>")
                        if i == 0:
                            table_html_parts.append(f'<td style="padding: 8px;" rowspan="{rowspan_count}">{status.capitalize()}</td>')
                            table_html_parts.append(f'<td style="padding: 8px;" rowspan="{rowspan_count}">{item_id}</td>')

                        table_html_parts.append(f"""
                            <td style="padding: 8px;">{field_to_display}</td>
                            <td style="padding: 8px;">{formatted_reference_value}</td>
                            <td style="padding: 8px;">{formatted_current_value}</td>
                        </tr>
                        """)
                else:
                    table_html_parts.append(f"<tr style='{row_style}'>")
                    table_html_parts.append(f'<td style="padding: 8px;">{status.capitalize()}</td>')
                    table_html_parts.append(f'<td style="padding: 8px;">{item_id}</td>')
                    table_html_parts.append(f'<td style="padding: 8px;">N/A</td>')
                    table_html_parts.append(f'<td style="padding: 8px;">N/A</td>')
                    table_html_parts.append(f'<td style="padding: 8px;">N/A</td>')
                    table_html_parts.append(f"</tr>")

            table_html_parts.append("</tbody></table><br>")

        if not has_content:
            popup(popup_title, content="No changed, added, or removed items found.")
        else:
            popup_content = put_html("".join(table_html_parts))
            popup(popup_title, content=popup_content, size="large")


    def show_other_changes_popup(self, other_changes_list: List[Dict[str, Any]], raw_diff_output: Dict[str, Any], item_name: str):
        """
        Displays a separate popup for 'other' differences (uncategorized changes)
        and the raw DeepDiff output for debugging.
        """
        popup_title = f"Other Differences for {item_name}"
        content_parts = []

        if other_changes_list:
            content_parts.append("<h3>Uncategorized Changes</h3>")
            content_parts.append("""
            <table border="1" style="border-collapse: collapse; width: 100%;">
                <thead>
                    <tr>
                        <th style="padding: 8px; text-align: left;">Item ID</th>
                        <th style="padding: 8px; text-align: left;">Field/Path</th>
                        <th style="padding: 8px; text-align: left;">Reference Value</th>
                        <th style="padding: 8px; text-align: left;">Current Value</th>
                    </tr>
                </thead>
                <tbody>
            """)
            for change_detail in other_changes_list:
                item_id = change_detail.get('item_id', 'N/A')
                field = change_detail.get('field', 'N/A')
                ref_val = change_detail.get('reference_value', 'N/A')
                curr_val = change_detail.get('current_value', 'N/A')
                content_parts.append(f"""
                <tr style="background-color: #f0f0f0;">
                    <td style="padding: 8px;">{item_id}</td>
                    <td style="padding: 8px;">{field}</td>
                    <td style="padding: 8px;">{json.dumps(ref_val, indent=2) if isinstance(ref_val, (dict, list)) else ref_val}</td>
                    <td style="padding: 8px;">{json.dumps(curr_val, indent=2) if isinstance(curr_val, (dict, list)) else curr_val}</td>
                </tr>
                """)
            content_parts.append("</tbody></table><br>")
        else:
            content_parts.append("<p>No uncategorized ('other') changes found.</p>")

        content_parts.append("<h3>Raw DeepDiff Output</h3>")
        content_parts.append(f"<pre style='background-color: #f8f8f8; padding: 10px; border: 1px solid #ddd;'>{json.dumps(raw_diff_output, indent=2)}</pre>")

        popup_content = put_html("".join(content_parts))
        popup(popup_title, content=popup_content, size="large")


    def display_comparison_results(self, results_data: Dict[str, Any], use_case_selections: Dict[str, Any], scope: str):
        """
        Displays the aggregated comparison results in a table format.
        Each cell in the table provides buttons to view detailed differences.
        """
        active_use_cases = [
            uc["name"]
            for uc in self._project_logic.get_operations(scope)
            if use_case_selections.get(uc["name"]) and use_case_selections.get(uc["name"]) != "No JSON files found"
        ]

        table_headers = [scope.capitalize()] + [
            next(
                uc["display_name"]
                for uc in self._project_logic.get_operations(scope)
                if uc["name"] == uc_name
            )
            for uc_name in active_use_cases
        ]
        table_data = []

        all_entity_names = set()
        for use_case_name in active_use_cases:
            use_case_results_list = results_data.get(use_case_name)
            if isinstance(use_case_results_list, list):
                for entity_result_entry in use_case_results_list:
                    if isinstance(entity_result_entry, dict) and "name" in entity_result_entry:
                        all_entity_names.add(entity_result_entry["name"])
            elif isinstance(use_case_results_list, dict) and "error" in use_case_results_list:
                all_entity_names.add(f"Error in {use_case_name}")


        for entity_name_key in sorted(list(all_entity_names)):
            row = [entity_name_key]
            for use_case_name in active_use_cases:
                current_entity_result_for_use_case = None
                use_case_results_list = results_data.get(use_case_name)

                if isinstance(use_case_results_list, dict) and "error" in use_case_results_list:
                    if entity_name_key == f"Error in {use_case_name}":
                        row.append(
                            put_text("❌ Error").style("color: red; text-decoration: underline; cursor: pointer;")
                            .onclick(lambda msg=use_case_results_list['error']: popup("Comparison Error", msg))
                        )
                    else:
                        row.append("")
                    continue

                if isinstance(use_case_results_list, list):
                    for entry in use_case_results_list:
                        if isinstance(entry, dict) and entry.get("name") == entity_name_key:
                            current_entity_result_for_use_case = entry
                            break

                if current_entity_result_for_use_case:
                    if "error" in current_entity_result_for_use_case:
                        error_msg = current_entity_result_for_use_case["error"]
                        row.append(
                            put_text("❌ Error").style("color: red; text-decoration: underline; cursor: pointer;")
                            .onclick(lambda msg=error_msg: popup("Comparison Error", msg))
                        )
                    else:
                        summary = current_entity_result_for_use_case.get('summary', {})
                        summary_counts = summary.get('summary_counts', {})
                        relevant_changes_for_popup = summary.get('relevant_changes', [])
                        other_changes_for_popup = summary.get('other_changes', [])
                        raw_diff_for_entity = summary.get('raw_deepdiff_output', {})

                        changed_count = summary_counts.get('changed', 0)
                        added_count = summary_counts.get('added', 0)
                        removed_count = summary_counts.get('removed', 0)
                        other_count = summary_counts.get('other', 0)

                        buttons_list = []

                        if changed_count == 0 and added_count == 0 and removed_count == 0 and other_count == 0:
                            row.append("✅")
                        else:
                            if changed_count > 0 or added_count > 0 or removed_count > 0:
                                buttons_list.append(
                                    put_text(f"Changes (C:{changed_count}, A:{added_count}, R:{removed_count})")
                                    .style("color: #1d69cc; text-decoration: underline; cursor: pointer;")
                                    .onclick(lambda d=relevant_changes_for_popup, n=entity_name_key: self.show_changes_popup(d, n))
                                )

                            if other_count > 0:
                                buttons_list.append(
                                    put_text(f"Other ({other_count})")
                                    .style("color: #ffc107; text-decoration: underline; cursor: pointer;")
                                    .onclick(lambda o=other_changes_for_popup, r=raw_diff_for_entity, n=entity_name_key: self.show_other_changes_popup(o, r, n))
                                )

                            if buttons_list:
                                row.append(put_row(buttons_list))
                            else:
                                row.append("")
                else:
                    row.append("")

            table_data.append(row)

        with use_scope(self.app_scope_name, clear=True):
            put_table(
                header=table_headers,
                tdata=table_data,
            )

            put_buttons(
                [{"label": "Back to Main Menu", "value": "back"}],
                onclick=lambda _: self.app_main_menu(),
            )


    # --- Application Setup and Header Functions ---
    def setup(self, value=None):
        """
        Initializes the PyWebIO application by clearing scopes, displaying the header,
        prompting for organization selection, and then launching the main navigation.
        """
        

        with use_scope(self.app_scope_name, clear=True):
            self.header("My app")
            self.select_organization()
        org_id, _ = self._project_logic.get_organization()
        if org_id:
            self.app_main_menu()
        else:
            with use_scope(self.app_scope_name, clear=True):
                self.header("My app")
                put_text("Please select an organization to proceed.").style("color: red; font-weight: bold;")
                put_buttons([{"label": "Try Again", "value": "retry"}], onclick=lambda _: self.setup())


    def show_app_log_popup(self):
        """Displays the content of the application log file in a scrollable popup."""
        log_content = self._project_logic.get_app_log_content()
        styled_log_content = put_code(log_content).style('overflow-y: auto; max-height: 400px; text-align: left;')
        popup("Application Log", styled_log_content, size='large')

    def header(self, app_name: str, current_org_id: str = None, current_org_name: str = None, on_change_org_callback: callable = None):
        """
        Displays the application header, including the app name, selected organization info (if any),
        and buttons for changing organization or viewing the application log.
        """
        put_html(f'<div class="top-gradient-bar"></div>')

        header_elements = []
        header_elements.append(
            put_text(app_name).style("font-size: 1.5em; font-weight: bold; margin-right: auto;")
        )

        if current_org_id and current_org_name:
            header_elements.append(
                put_text(f"Selected Org: {current_org_name} [{current_org_id}]").style(
                    "font-size: 1.5em; font-weight: bold; margin-right: 20px;"
                )
            )

        if on_change_org_callback:
            change_org_button = put_buttons(
                [{"label": "Change Organization", "value": "change_org", "color": "warning"}],
                onclick=lambda val: on_change_org_callback(),
            )
            header_elements.append(change_org_button)

        show_log_button = put_buttons(
            [{"label": "Show App Log", "value": "show_log", "color": "warning"}],
            onclick=lambda val: self.show_app_log_popup(),
        )
        header_elements.append(show_log_button)

        put_row(
            header_elements,
        ).style(
            "display: flex; justify-content: space-between; align-items: center; padding: 10px 20px; background: linear-gradient(0.25turn, #143052, #07172B); color: white;"
        )

