# project_logic.py

"""
This module provides the core business logic for the application,
handling interactions with the Meraki Dashboard API, managing data storage,
and orchestrating data comparison operations. It integrates with `use_cases.py`
to define available operations and `compare_functions.py` for comparison logic.
"""

# --- Standard Library Imports ---
import json         # For working with JSON data.
import os           # For interacting with the operating system, e.g., file paths, environment variables.
import re           # For regular expressions, used in path parsing.
from collections import OrderedDict # For maintaining order in dictionaries, used in flattening.
from datetime import datetime, timedelta, timezone # For generating timestamps for filenames and graph logic.
from typing import Any, Callable, Dict, List, Optional, Self, Tuple # For type hinting.

# --- Third-Party Imports ---
import meraki       # The Meraki Dashboard API library.
from deepdiff import DeepDiff # The main library for deep comparison of data structures.

# --- Local Application Imports ---
# Assuming these files exist in the same directory or are importable
from meraki_tools.meraki_api_utils import MerakiAPIWrapper
from meraki_tools.my_logging import get_logger

# --- Module-Level Constants ---
FILES_DIRECTORY = "saved_configs" # Root directory for storing all saved configuration files.
# This 'folders' variable was found at the end of the original file, outside the class.
# If it's intended to be a module-level constant, it belongs here.
# If it's meant to be an instance variable, it should be defined in __init__.
# For now, assuming it's a module-level constant if it's used globally.
# If not used, it should be removed.
FOLDERS_MAPPING = {"network": "network", "organization": "organization", "device": "device"}

# --- Logger Setup ---
logger = get_logger()


class ProjectLogic:
    def __init__(self, api_utils: MerakiAPIWrapper):
        # Initialize instance variables
        self._api_utils = api_utils
        self.logger = logger # Use the module-level logger
        self.files_directory = FILES_DIRECTORY # Use the module-level constant for the default

        # Comparison methods registry
        self._COMPARISON_METHODS = {
            "deepdiff": self._handle_deepdiff_comparison,
            # Future methods can be added here
        }

        # Use case keys for consistent referencing
        self.USE_CASE_KEYS = {
            "organization_level": "organization_level",
            "network_level": "network_level",
            "device_level": "device_level",
            "store_prefix": "store_",
            "compare_prefix": "compare_",
            "display_name": "display_name",
            "name": "name",
        }

        # Define all available use cases and their operations
        self.USE_CASES = {
            "organization_level": {
                "folder": "Organization_config", # Base folder name for organization-level configs.
                "display_name": "Organization",   # Display name for this level in the GUI.
                "operations": [
                    {
                        "name": "organization_admins",      # Unique internal name for the operation.
                        "display_name": "Organization Administrators", # User-friendly name for the GUI.
                        "fetch_function": self.fetch_organization_admins, # Reference to the function that fetches this data.
                        "folder": "organization_admins",    # Sub-folder within "Organization_config" for this operation's files.
                        "file_name": "getOrganizationAdmins", # Base filename for saved data.
                        "group_by": "email"                 # Key to use for grouping items in DeepDiff comparison (e.g., for list of admins).
                    },
                    {
                        "name": "organization_settings",
                        "display_name": "Organization Settings",
                        "fetch_function": self.fetch_organization_settings,
                        "folder": "organization_settings",
                        "file_name": "getOrganizationSettings",
                        # No "group_by" needed as it's typically a single dictionary, not a list of items.
                    },
                    # Add more organization-level use cases here following the same structure.
                ],
            },
            "network_level": {
                "folder": "Network_config", # Base folder name for network-level configs.
                "display_name": "Network",    # Display name for this level in the GUI.
                "operations": [
                    {
                        "name": "network_ssids",
                        "display_name": "Wireless Network SSIDs",
                        "fetch_function": self.fetch_network_ssids,
                        "folder": "network_ssids",
                        "file_name": "getNetworkWirelessSsids",
                        "product_type": "wireless", # Optional: Filter networks by product type.
                        "group_by": "name"          # Group SSIDs by their name for comparison.
                    },
                    {
                        "name": "network_settings",
                        "display_name": "Network Settings",
                        "fetch_function": self.fetch_network_settings,
                        "folder": "network_settings",
                        "file_name": "getNetworkSettings",
                    },
                    # Add more network-level use cases here.
                ],
            },
            "device_level": {
                "folder": "Device_config", # Base folder name for device-level configs.
                "display_name": "Device",   # Display name for this level in the GUI.
                "operations": [
                    {
                        "name": "switchport_on_switch",
                        "display_name": "Switchport on a switch",
                        "fetch_function": self.fetch_switch_switchport, # Using the more appropriately named function.
                        "folder": "switchport_on_switch",
                        "file_name": "getDeviceSwitchPorts",
                        "product_type": "switch", # Assuming MX devices are 'appliance' product type.
                        "group_by":"portId"
                        # No "group_by" typically needed for a single device's interface settings.
                    },
                    # Add more device-level use cases here.
                ],
            },
        }

        logger.info("ProjectLogic initialized with Meraki Dashboard API and configuration.")


    def core_data_operation(self, scope: str, operation_name: str, task: str, identifier: str = None, filename: str = None,
                            comparison_method: str = "deepdiff", device_tags: list = None, device_models: list = None,
                            network_tags: list = None, product_types: list = None, org_ids: list = None) -> dict:
        """
        Orchestrates data operations (store or compare) based on the specified scope,
        operation, and task.

        Args:
            scope (str): The level of the operation (e.g., "network_level", "organization_level", "device_level").
            operation_name (str): The specific operation to perform (e.g., "admins", "ssids").
            task (str): The type of operation ("store" or "compare").
            identifier (str, optional): An ID for the specific entity (e.g., network ID, device serial)
                                        when the operation is not organization-wide. Defaults to None.
            filename (str, optional): The name of the file to compare against (for "compare" tasks).
                                      Defaults to None.
            comparison_method (str): The method to use for comparison ("deepdiff" or "flat").
            device_tags (list, optional): A list of device tags to filter by.
            device_models (list, optional): A list of device models to filter by.
            network_tags (list, optional): A list of network tags to filter by.
            product_types (list, optional): A list of product types to filter by.
            org_ids (list, optional): A list of organization IDs to filter by.

        Returns:
            dict: A dictionary containing the results of the operation, particularly for "compare" tasks.
                  Returns {"success": True} for "store" tasks upon success.
        """
        results = {}
        try:
            if task == "store":
                logger.debug(f"Attempting to store: {scope} {operation_name} {identifier if identifier else 'N/A'}")
                self._store(scope, operation_name, identifier) # Call instance method
                results = {"success": True}
            elif task == "compare":
                logger.debug(f"Attempting to compare: {scope} {operation_name} {filename if filename else 'N/A'}")
                # Pass 'self' (the ProjectLogic instance) to comparison functions
                if scope == self.USE_CASE_KEYS["network_level"]:
                    results = self.compare_network_level(filename, scope, operation_name, comparison_method, network_tags or None)
                elif scope == self.USE_CASE_KEYS["organization_level"]:
                    results = self.compare_organization_level(filename, scope, operation_name, comparison_method, org_ids or None)
                elif scope == self.USE_CASE_KEYS["device_level"]:
                    results = self.compare_device_level(
                        filename, scope, operation_name, comparison_method,
                        network_tags=network_tags or None,
                        device_models=device_models or None,
                        device_tags=device_tags or None,
                        product_types=product_types or None,
                    )
                else:
                    raise ValueError(f"Compare function not found for scope: {scope}")

        except meraki.APIError as e:
            error_message = f"Meraki API Error during {task} for {operation_name}: {e}"
            logger.error(error_message, exc_info=True)
            results["error"] = error_message
        except FileNotFoundError as e:
            error_message = f"File not found during {task} for {operation_name}: {e}"
            logger.error(error_message, exc_info=True)
            results["error"] = error_message
        except Exception as e:
            error_message = f"Unexpected Error during {task} for {operation_name}: {e}"
            logger.error(error_message, exc_info=True)
            results["error"] = error_message

        return results


    # --- Use Case and Operation Metadata Retrieval Functions ---
    def get_operation(self, scope: str, operation_name: str) -> dict:
        """
        Retrieves the dictionary containing details for a specific operation within a given scope.

        Args:
            scope (str): The level of the operation (e.g., "organization_level").
            operation_name (str): The name of the specific operation (e.g., "admins").

        Returns:
            dict: A dictionary of operation details, or None if not found.
        """
        operations = self.USE_CASES.get(scope, {}).get("operations", [])
        for operation in operations:
            if operation["name"] == operation_name:
                return operation
        return None

    def get_operations(self, scope: str) -> list:
        """
        Retrieves a list of all operations defined for a given scope.

        Args:
            scope (str): The level of operations to retrieve (e.g., "network_level").

        Returns:
            list: A list of dictionaries, each representing an operation.
        """
        return self.USE_CASES.get(scope, {}).get("operations", [])

    def get_use_cases_items(self) -> list:
        """
        Retrieves all top-level use cases and their details from the `use_cases` module.

        Returns:
            list: A list of (key, value) pairs for each use case.
        """
        return self.USE_CASES.items()

    def get_scope_folder_name(self, scope: str) -> str:
        """
        Retrieves the designated folder name for a given scope (e.g., "organization").

        Args:
            scope (str): The level (e.g., "organization_level").

        Returns:
            str: The folder name associated with the scope.
        """
        return self.USE_CASES.get(scope, {}).get("folder", "")

    def get_operation_folder_name(self, scope: str, operation_name: str) -> str:
        """
        Retrieves the designated sub-folder name for a specific operation within a scope.

        Args:
            scope (str): The level (e.g., "network_level").
            operation_name (str): The name of the operation (e.g., "ssids").

        Returns:
            str: The sub-folder name for the operation, or None if not found.
        """
        operations = self.USE_CASES.get(scope, {}).get("operations", [])
        for operation in operations:
            if operation["name"] == operation_name:
                return operation["folder"]
        return None

    def get_operation_fetch_function(self, scope: str, operation_name: str) -> callable:
        """
        Retrieves the Python function responsible for fetching data for a given operation.

        Args:
            scope (str): The level (e.g., "organization_level").
            operation_name (str): The name of the operation (e.g., "admins").

        Returns:
            callable: The fetch function, or None if not found.
        """
        operations = self.USE_CASES.get(scope, {}).get("operations", [])
        for operation in operations:
            if operation["name"] == operation_name:
                return operation["fetch_function"]
        return None

    def get_operation_file_name(self, scope: str, operation_name: str) -> str:
        """
        Retrieves the base filename for data associated with a given operation.

        Args:
            scope (str): The level (e.g., "network_level").
            operation_name (str): The name of the operation (e.g., "ssids").

        Returns:
            str: The base filename, or None if not found.
        """
        operations = self.USE_CASES.get(scope, {}).get("operations", [])
        for operation in operations:
            if operation["name"] == operation_name:
                return operation["file_name"]
        return None

    def get_operation_product_type(self, scope: str, operation_name: str) -> str:
        """
        Retrieves the associated Meraki product type for a given operation, if specified.

        Args:
            scope (str): The level (e.g., "device_level").
            operation_name (str): The name of the operation (e.g., "device_status").

        Returns:
            str: The product type (e.g., "wireless", "appliance"), or None if not specified.
        """
        operations = self.USE_CASES.get(scope, {}).get("operations", [])
        for operation in operations:
            if operation["name"] == operation_name:
                return operation.get("product_type", None)
        return None


    def list_json_files(self, scope_folder: str, operation_folder: str) -> list:
        """
        Lists all JSON files within a specific operation's saved configuration folder.

        Args:
            scope_folder (str): The top-level folder name (e.g., "organization").
            operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").

        Returns:
            list: A list of JSON filenames found in the directory, or an empty list if
                  the directory does not exist or is inaccessible.
        """
        logger.debug(f"Attempting to list JSON files in: {self.files_directory}/{scope_folder}/{operation_folder}")
        destination_folder = os.path.join(self.files_directory, scope_folder, operation_folder)

        if not os.path.exists(destination_folder):
            logger.warning(f"Path does not exist: {destination_folder}. No JSON files to list.")
            return []

        if not os.access(destination_folder, os.R_OK):
            logger.error(f"No read access to: {destination_folder}.")
            return []

        files = os.listdir(destination_folder)
        json_files = [f for f in files if f.endswith(".json")]
        logger.debug(f"Found {len(json_files)} JSON files in {destination_folder}.")
        return json_files


    def get_devices(self, simplified: bool = False, global_devices: bool = False) -> list:
        """
        Fetches devices. Can fetch all devices across all accessible organizations
        or only devices under the currently selected organization.

        Args:
            simplified (bool): If True, returns a list of dictionaries with only
                               'serial', 'name', 'tags', and 'productTypes'.
            global_devices (bool): If True, fetches devices from all organizations.
                                   If False, fetches devices only from the currently
                                   set `organization_id`.

        Returns:
            list: A list of device dictionaries.

        Raises:
            ValueError: If `global_devices` is False and no organization ID is set.
        """
        keys_to_extract = ["serial", "name", "tags", "productType","model"]
        devices = []

        if global_devices:
            logger.info("Fetching all devices across all accessible organizations.")
            organizations = self._api_utils.list_organizations(True)
            for org in organizations:
                # Get devices for each organization, paginating through all pages.
                dev = self._api_utils.get_dashboard().organizations.getOrganizationDevices(
                    org["id"], total_pages="all"
                )
                devices.extend(dev) # Add devices to the main list.
        else:
            if not self._api_utils.get_organization_id():
                raise ValueError("Organization ID is not set. Cannot fetch devices for a specific organization.")
            logger.info(f"Fetching devices for organization ID: {self._api_utils.get_organization_id()}.")
            devices = self._api_utils.get_dashboard().organizations.getOrganizationDevices(
                self._api_utils.get_organization_id(), total_pages="all"
            )

        if simplified:
            extracted_list = [
                {key: item[key] for key in keys_to_extract if key in item}
                for item in devices
            ]
            return extracted_list
        else:
            return devices

    def get_networks(self, simplified: bool = False, global_networks: bool = False) -> list:
        """
        Fetches networks. Can fetch all networks across all accessible organizations
        or only networks under the currently selected organization.

        Args:
            simplified (bool): If True, returns a list of dictionaries with only
                               'id', 'name', 'tags', and 'productTypes'.
            global_networks (bool): If True, fetches networks from all organizations.
                                    If False, fetches networks only from the currently
                                    set `organization_id`.

        Returns:
            list: A list of network dictionaries.

        Raises:
            ValueError: If `global_networks` is False and no organization ID is set.
        """
        keys_to_extract = ["id", "name", "tags", "productTypes"]
        networks = []

        if global_networks:
            logger.info("Fetching all networks across all accessible organizations.")
            organizations = self._api_utils.list_organizations(True)
            for org in organizations:
                # Get networks for each organization, paginating through all pages.
                net = self._api_utils.get_dashboard().organizations.getOrganizationNetworks(
                    org["id"], total_pages="all"
                )
                networks.extend(net) # Add networks to the main list.
        else:
            if not self._api_utils.get_organization_id():
                raise ValueError("Organization ID is not set. Cannot fetch networks for a specific organization.")
            logger.info(f"Fetching networks for organization ID: {self._api_utils.get_organization_id()}.")
            networks = self._api_utils.get_dashboard().organizations.getOrganizationNetworks(
                self._api_utils.get_organization_id(), total_pages="all"
            )

        if simplified:
            extracted_list = [
                {key: item[key] for key in keys_to_extract if key in item}
                for item in networks
            ]
            return extracted_list
        else:
            return networks


    # --- Data Storage Functions ---
    def _store(self, scope: str, operation_name: str, identifier: str = None):
        """
        Fetches data for a specific operation and saves it to a JSON file.

        The fetch function is determined by the `use_cases` configuration.
        The file is saved in a structured directory based on scope and operation.

        Args:
            scope (str): The level of the operation (e.g., "network_level").
            operation_name (str): The name of the specific operation (e.g., "ssids").
            identifier (str, optional): An ID for the specific entity (e.g., network ID)
                                        if the fetch function requires it. Defaults to None.
        """
        fetch_function = self.get_operation_fetch_function(scope, operation_name)
        if not fetch_function:
            raise ValueError(f"No fetch function found for {scope}/{operation_name}. Data cannot be stored.")

        data_to_store = None
        try:
            if identifier:
                data_to_store = fetch_function(identifier)
            else:
                data_to_store = fetch_function()
            logger.info(f"Successfully fetched data for {scope}/{operation_name}.")
        except Exception as e:
            logger.error(f"Error fetching data for {scope}/{operation_name}: {e}", exc_info=True)
            raise

        filename = self._create_file_name_with_timestamp(
            self.get_operation_file_name(scope, operation_name)
        )
        self._save_to_json(
            data_to_store,
            self.get_scope_folder_name(scope),
            self.get_operation_folder_name(scope, operation_name),
            filename,
        )
        logger.info(f"Data for {scope}/{operation_name} saved to {filename}.")


    def _create_file_name_with_timestamp(self, base_filename: str) -> str:
        """
        Generates a unique filename by appending a timestamp to a base filename.

        Args:
            base_filename (str): The original filename without extension (e.g., "admins").

        Returns:
            str: The new filename including a timestamp and .json extension
                 (e.g., "admins-2023-10-27_14-30-00.json").
        """
        now = datetime.now()
        return f"{base_filename}-{now.strftime('%Y-%m-%d_%H-%M-%S')}.json"


    def _save_to_json(self, data: Any, scope_folder: str, operation_folder: str, filename: str):
        """
        Saves Python data (list or dictionary) to a JSON file within the structured
        `self.files_directory`.

        Args:
            data (any): The data to be saved (e.g., list of dictionaries, dictionary).
            scope_folder (str): The top-level folder name (e.g., "organization").
            operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").
            filename (str): The name of the JSON file (including .json extension).
        """
        try:
            destination_folder = os.path.join(
                self.files_directory, scope_folder, operation_folder
            )
            os.makedirs(destination_folder, exist_ok=True)
            destination = os.path.join(destination_folder, filename)
            with open(destination, "w") as file:
                json.dump(data, file, indent=4)
        except Exception as e:
            logger.error(f"Error saving to JSON: {e}", exc_info=True)
            raise


    def load_from_json(self, scope_folder: str, operation_folder: str, filename: str) -> Any:
        """
        Loads data from a JSON file located within the structured `self.files_directory`.

        Args:
            scope_folder (str): The top-level folder name (e.g., "organization").
            operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").
            filename (str): The name of the JSON file to load (including .json extension).

        Returns:
            any: The loaded data (e.g., list, dictionary).
        """
        try:
            source_folder = os.path.join(self.files_directory, scope_folder, operation_folder)
            source = os.path.join(source_folder, filename)
            with open(source, "r") as file:
                return json.load(file)
        except FileNotFoundError as e:
            logger.error(f"JSON file not found: {source}. {e}", exc_info=True)
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON from file: {source}. File might be corrupted or malformed. {e}", exc_info=True)
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred while loading JSON file {source}: {e}", exc_info=True)
            raise

    def fetch_device_MX_interfaces(self,dev_id: str) -> dict:
        """
        Fetches the management interface settings for a specific Meraki MX device.

        Args:
            dev_id (str): The serial number of the Meraki MX device.

        Returns:
            dict: A dictionary containing the management interface configuration.
        """
        logger.debug(f"Fetching MX management interface for device ID: {dev_id}")
        return self._api_utils.get_dashboard().getDeviceManagementInterface(dev_id)


    def fetch_network_settings(self,net_id: str) -> dict:
        """
        Fetches the general settings for a specific Meraki network.

        Args:
            net_id (str): The ID of the Meraki network.

        Returns:
            dict: A dictionary containing the network's general settings.
        """
        logger.debug(f"Fetching network settings for network ID: {net_id}")
        return self._api_utils.get_dashboard().networks.getNetworkSettings(net_id)


    def fetch_organization_settings(self,org_id: str = None) -> dict:
        """
        Fetches the general settings for a Meraki organization.
        If `org_id` is not provided, it defaults to the globally selected organization
        from `core_operations`.

        Args:
            org_id (str, optional): The ID of the Meraki organization. Defaults to None.

        Returns:
            dict: A dictionary containing the organization's settings, with 'id', 'name',
                and 'url' keys removed for comparison purposes.
        """
        # Use the provided org_id or retrieve it from core_operations if not provided.
        org_id_to_fetch = org_id if org_id is not None else self._api_utils.get_organization_id()
        if not org_id_to_fetch:
            logger.error("No organization ID available to fetch organization settings.")
            return {}

        logger.debug(f"Fetching organization settings for organization ID: {org_id_to_fetch}")
        setting = self._api_utils.get_dashboard().organizations.getOrganization(org_id_to_fetch)
        # Remove dynamic or irrelevant keys before comparison/storage.
        setting.pop("id", None)
        setting.pop("name", None)
        setting.pop("url", None)
        return setting


    def fetch_network_ssids(self,net_id: str) -> list:
        """
        Fetches the SSID configurations for a specific Meraki wireless network.
        Includes error handling for non-wireless networks.

        Args:
            net_id (str): The ID of the Meraki network.

        Returns:
            list: A list of dictionaries, each representing an SSID configuration.
                Returns None if the network does not support wireless features.
        Raises:
            meraki.exceptions.APIError: Re-raises API errors not related to unsupported wireless networks.
        """
        logger.debug(f"Fetching wireless SSIDs for network ID: {net_id}")
        try:
            return self._api_utils.get_dashboard().wireless.getNetworkWirelessSsids(net_id)
        except meraki.exceptions.APIError as e:
            logger.error(f"API Error fetching SSIDs for network {net_id}: {e}", exc_info=True)
            raise

    def fetch_switch_switchport(self,dev_id: str) -> dict :
        logger.debug(f"Fetching switchport configuration for device ID: {dev_id} (duplicate function).")
        try:
            return self._api_utils.get_dashboard().switch.getDeviceSwitchPorts(dev_id)
        except meraki.exceptions.APIError as e:
            logger.error(f"API Error fetching switchport for device {dev_id}: {e}", exc_info=True)
            raise


    def fetch_organization_admins(self,org_id: str = None) -> list:
        """
        Fetches the administrators for a Meraki organization.
        If `org_id` is not provided, it defaults to the globally selected organization.
        Removes the 'lastActive' field from each admin for consistent comparison.

        Args:
            org_id (str, optional): The ID of the Meraki organization. Defaults to None.

        Returns:
            list: A list of dictionaries, each representing an organization administrator.
        """
        org_id_to_fetch =  self._api_utils.get_organization_id()
        if not org_id_to_fetch:
            logger.error("No organization ID available to fetch organization admins.")
            return []

        logger.debug(f"Fetching organization administrators for organization ID: {org_id_to_fetch}")
        admins = self._api_utils.get_dashboard().organizations.getOrganizationAdmins(org_id_to_fetch)
        # Remove dynamic fields that are not relevant for configuration comparison.
        for admin in admins:
            admin.pop("lastActive", None) # 'lastActive' changes frequently and is not a config setting.
        return admins

    def _compare_level_general(self,
    json_file_name: str,
    scope: str,
    operation_name: str,
    get_entities_func: Callable[[bool], List[Dict[str, Any]]],
    entity_id_key: str,
    entity_name_key: str,
    entity_filter_func: Optional[Callable[[Dict[str, Any], str, str, Dict[str, Any]], bool]] = None,
    filter_args: Optional[Dict[str, Any]] = None,
    comparison_method: str = "deepdiff",
    ) -> List[Dict[str, Any]]:
        """
        General comparison function for any scope and operation.
        """
        logger.info(f"Starting comparison: scope={scope}, operation={operation_name}, method={comparison_method}")

        baseline = self.load_from_json(
            self.get_scope_folder_name(scope),
            self.get_operation_folder_name(scope, operation_name),
            json_file_name,
        )
        if not baseline:
            logger.error(f"Baseline data not found: {json_file_name} for {scope}/{operation_name}")
            return []

        fetch_function = self.get_operation_fetch_function(scope, operation_name)
        if not fetch_function:
            logger.error(f"No fetch function for {scope}/{operation_name}")
            return []

        operations_list = self.USE_CASES.get(scope, {}).get("operations", [])
        found_op = next((op for op in operations_list if op["name"] == operation_name), None)
        group_by_key = found_op.get("group_by") if found_op else None

        entities = get_entities_func(True)
        results = []

        compare_func = self._COMPARISON_METHODS.get(comparison_method)
        if not compare_func:
            logger.error(f"Unsupported comparison method: {comparison_method}")
            return []
        if group_by_key:
            logger.info(f"Comparing entity using using group_by: {group_by_key}")
        else:
            logger.info(f"Comparing entity without group_by")
        for entity in entities:
            entity_id = entity.get(entity_id_key)
            entity_name = entity.get(entity_name_key, "Unknown")

            if entity_id is None:
                logger.warning(f"Skipping entity with missing ID '{entity_id_key}': {entity_name}")
                continue


            if entity_filter_func and not entity_filter_func(entity, scope, operation_name, filter_args or {}):
                continue


            logger.debug(f"Comparing entity: {entity_name} (ID: {entity_id})")

            current_data = fetch_function(entity_id)
            if current_data is None:
                logger.warning(f"No current data for entity: {entity_name} (ID: {entity_id})")
                continue

            summary = compare_func(
                baseline=baseline,
                current_data=current_data,
                group_by_key=group_by_key,
                entity_name=entity_name
            ) if comparison_method == "flat" else compare_func(
                baseline=baseline,
                current_data=current_data,
                group_by_key=group_by_key
            )

            results.append({
                "name": entity_name,
                "summary": summary,
            })

        logger.info(f"Completed comparison for {scope}/{operation_name}, total entities compared: {len(results)}")
        return results

# --- Helper Filter Functions for Specific Levels ---

    def _organization_filter(self,entity: Dict[str, Any], scope: str, operation_name: str, filter_args: Dict[str, Any]) -> bool:
        """
        Filter logic specific to organization-level comparisons.
        Checks if the organization ID is in the provided list.
        """
        organization_ids_filter = filter_args.get("organization_ids")
        if organization_ids_filter and entity.get("id") not in organization_ids_filter:
            logger.debug(f"Skipping organization '{entity.get('name', 'N/A')}' (ID: {entity.get('id', 'N/A')}) as it's not in the filter list.")
            return False
        return True

    def _network_filter(self,entity: dict, scope: str, operation_name: str, filter_args: dict) -> bool:
        """
        Filter logic specific to network-level entities.
        Checks for network tags and product types.
        """
        # Filter by network tags

        network_tags_filter = filter_args.get("network_tags")
        if network_tags_filter:
            if not any(tag in entity.get("tags", []) for tag in network_tags_filter):
                logger.debug(f"Skipping network '{entity.get('name', 'N/A')}' due to network tag filter.")
                return False

        # Filter by product types at network level
        product_type = self.get_operation_product_type(scope, operation_name)
        if product_type:
            if product_type not in entity.get("productTypes", []):
                logger.debug(f"Skipping network '{entity.get('name', 'N/A')}' due product type not present.")
                return False

        return True


    def _device_filter(self,entity: dict, scope: str, operation_name: str, filter_args: dict) -> bool:
        """
        Filter logic specific to device-level entities.
        Checks device tags, device models, device product types,
        and verifies if device's network ID belongs to networks filtered by network tags.
        """
        # Filter by device tags
        tags_filter = filter_args.get("device_tags")
        if tags_filter:
            if not any(tag in entity.get("device_tags", []) for tag in tags_filter):
                logger.debug(f"Skipping device '{entity.get('name', 'N/A')}' due to device tag filter.")
                return False

        # Filter by device models
        models_filter = filter_args.get("device_models")
        if models_filter:
            if entity.get("model") not in models_filter:
                logger.debug(f"Skipping device '{entity.get('name', 'N/A')}' due to device model filter.")
                return False

        # Filter by device product types
        product_type_filter = filter_args.get("product_types")
        if product_type_filter:
            if not any(pt in entity.get("productTypes", []) for pt in product_type_filter):
                logger.debug(f"Skipping device '{entity.get('name', 'N/A')}' due to device product type filter.")
                return False

        # Filter by network tags via device's network ID
        network_tags_filter = filter_args.get("network_tags")
        if network_tags_filter:
            # You need a way to map device.networkId to network entity's tags
            # This requires fetching network data or having a precomputed mapping
            # For example, assume filter_args contains a dict: network_id_to_tags
            network_id = entity.get("networkId")
            network_id_to_tags = filter_args.get("network_id_to_tags", {})

            network_tags = network_id_to_tags.get(network_id, [])
            if not any(tag in network_tags for tag in network_tags_filter):
                logger.debug(f"Skipping device '{entity.get('name', 'N/A')}' due to network tag filter on network ID {network_id}.")
                return False

        return True

    # --- Refactored Original Functions (now wrappers) ---

    def compare_organization_level(self,json_file_name: str, scope: str, operation_name: str,comparison_method:str ="deepdiff", organization_ids: list = None) -> list:
        """
        Compares the current organization-level configuration data against a saved baseline.
        """
        return self._compare_level_general(
            json_file_name=json_file_name,
            scope=scope,
            operation_name=operation_name,
            get_entities_func=self._api_utils.list_organizations,
            entity_id_key="id",
            entity_name_key="name",
            entity_filter_func=self._organization_filter,
            filter_args={"organization_ids": organization_ids} if organization_ids else None,
            comparison_method= comparison_method,
        )

    def compare_network_level(self,json_file_name: str, scope: str, operation_name: str, comparison_method:str ="deepdiff", network_tags: list = None) -> list:
        """
        Compares the current network-level configuration data against a saved baseline.
        """
        return self._compare_level_general(
            json_file_name=json_file_name,
            scope=scope,
            operation_name=operation_name,
            get_entities_func=self.get_networks,
            entity_id_key="id",
            entity_name_key="name",
            entity_filter_func=self._network_filter,
            filter_args={"network_tags": network_tags} if network_tags else None,
            comparison_method= comparison_method,
        )

    def compare_device_level(self,json_file_name: str, scope: str, operation_name: str, comparison_method: str = "deepdiff",
                            network_tags: list = None, device_models: list = None, device_tags: list = None, product_types: list = None) -> list:
        """
        Compares the current device-level configuration data against a saved baseline,
        with filtering options for tags, device models, network tags, and product types.
        """
        return self._compare_level_general(
            json_file_name=json_file_name,
            scope=scope,
            operation_name=operation_name,
            get_entities_func=self.get_devices,
            entity_id_key="serial",
            entity_name_key="name",
            entity_filter_func=self._device_filter,
            filter_args={
                "network_tags": network_tags,
                "device_models": device_models,
                "device_tags": device_tags,
                "product_types": product_types,
            },
            comparison_method=comparison_method,
        )


    # --- Core Difference Comparison Function ---

    def compare_differences(self,json1, json2, group_by_key_name=None):
        """
        Compares two JSON structures using DeepDiff and processes the output
        to categorize and format changes according to specified rules.

        Args:
            json1 (dict or list): The first JSON structure (e.g., old data).
            json2 (dict or list): The second JSON structure (e.g., new data).
            group_by_key_name (str, optional): The key name to use for grouping items
                                            in DeepDiff (e.g., "email", "id").
                                            If None or an empty string, DeepDiff
                                            will not use 'group_by', and list/set
                                            changes will be reported differently.
                                            Defaults to None.

        Returns:
            dict: A structured dictionary containing:
                - 'res': List of dictionaries, each detailing a change (item_id, field, values, status).
                - 'dif': The raw DeepDiff output.
        """

        # Modified type check to allow lists
        if not isinstance(json1, (dict, list)) or not isinstance(json2, (dict, list)):
            logger.error("Input JSON structures must be dictionaries or lists.")
            return {"res": [], "dif": {}}

        deepdiff_args = {
            "ignore_order": True,
            "verbose_level": 2
        }
        if group_by_key_name:
            deepdiff_args["group_by"] = group_by_key_name

        try:
            diff_output = DeepDiff(json1, json2, **deepdiff_args)
        except Exception as e:
            logger.error(f"Error during DeepDiff comparison: {e}")
            return {"res": [], "dif": {}}

        grouped_item_changes = {}
        other_changes_list = []

        for diff_type, changes in diff_output.items():
            if diff_type == 'values_changed':
                for path, change_details in changes.items():
                    if path == 'root':
                        # This case applies when the entire root object (if it's a dict) is replaced.
                        # If json1/json2 are lists, this 'root' change is less common for values_changed.
                        old_root_value = change_details.get('old_value', {})
                        new_root_value = change_details.get('new_value', {})

                        # Handle items removed from the root (if root was a dict)
                        if isinstance(old_root_value, dict):
                            for item_id, item_data in old_root_value.items():
                                if item_id not in grouped_item_changes:
                                    grouped_item_changes[item_id] = {"status": "removed", "changes": [], "full_item_ref": None, "full_item_curr": None}
                                grouped_item_changes[item_id]["status"] = "removed"
                                grouped_item_changes[item_id]["full_item_ref"] = item_data
                                logger.debug(f"Root removed item (dict): {item_id}")

                        # Handle items added to the root (if root was a dict)
                        if isinstance(new_root_value, dict):
                            for item_id, item_data in new_root_value.items():
                                if item_id not in grouped_item_changes:
                                    grouped_item_changes[item_id] = {"status": "added", "changes": [], "full_item_ref": None, "full_item_curr": None}
                                grouped_item_changes[item_id]["status"] = "added"
                                grouped_item_changes[item_id]["full_item_curr"] = item_data
                                logger.debug(f"Root added item (dict): {item_id}")

                        # If root was a list and it was completely replaced, DeepDiff might report it here.
                        # This is less granular, so we'll just log it as an 'other' change if not a dict.
                        if not isinstance(old_root_value, dict) and not isinstance(new_root_value, dict):
                            other_changes_list.append({
                                "item_id": "root", "field": "type_or_full_value_change",
                                "reference_value": old_root_value,
                                "current_value": new_root_value,
                                "status": "other"
                            })

                    else:
                        # Attribute value changed (e.g., root['id']['field'] or root[0]['field'])
                        item_id, field, is_root_item_only = self._extract_path_components(path)
                        if item_id is not None:
                            if item_id not in grouped_item_changes:
                                grouped_item_changes[item_id] = {"status": "changed", "changes": [], "full_item_ref": None, "full_item_curr": None}

                            # If an item was previously marked as added/removed, and now has attribute changes,
                            # it's a complex case. For this implementation, 'changed' takes precedence for attributes
                            # unless the item was fully added/removed.
                            if grouped_item_changes[item_id]["status"] not in ["added", "removed"]:
                                grouped_item_changes[item_id]["status"] = "changed"

                            # If it's a root-level item change (e.g., root[0] changed from 1 to 2),
                            # treat it as a full item change at that index.
                            if is_root_item_only:
                                grouped_item_changes[item_id]["changes"].append({
                                    "field": "full_item_at_index", # Special field name to indicate the whole item changed
                                    "reference_value": change_details.get('old_value'),
                                    "current_value": change_details.get('new_value')
                                })
                                logger.debug(f"Root-level item value changed at index: {item_id}")
                            else:
                                grouped_item_changes[item_id]["changes"].append({
                                    "field": field,
                                    "reference_value": change_details.get('old_value'),
                                    "current_value": change_details.get('new_value')
                                })
                                logger.debug(f"Attribute changed: {item_id}.{field}")
                        else:
                            logger.warning(f"Could not process values_changed path: {path}")
                            other_changes_list.append({
                                "item_id": None, "field": path,
                                "reference_value": change_details.get('old_value'),
                                "current_value": change_details.get('new_value'),
                                "status": "other"
                            })

            elif diff_type == 'dictionary_item_added':
                for item_path in changes:
                    item_id, field, is_root_item = self._extract_path_components(item_path)
                    if item_id is not None:
                        if is_root_item:
                            # Entire item added at root level (e.g., root['new_item_id'] for dict, or root[new_index] for list if group_by used)
                            current_value = self._get_value_from_original_json(json2, item_id, None) # Get full item data
                            if item_id not in grouped_item_changes:
                                grouped_item_changes[item_id] = {"status": "added", "changes": [], "full_item_ref": None, "full_item_curr": None}
                            grouped_item_changes[item_id]["status"] = "added"
                            grouped_item_changes[item_id]["full_item_curr"] = current_value
                            logger.debug(f"Item added (dict/group_by): {item_id}")
                        else:
                            # Nested attribute/item added (e.g., root['id']['new_field'] or root[0]['new_field'])
                            current_value = self._get_value_from_original_json(json2, item_id, field)
                            if item_id not in grouped_item_changes:
                                grouped_item_changes[item_id] = {"status": "changed", "changes": [], "full_item_ref": None, "full_item_curr": None}

                            if grouped_item_changes[item_id]["status"] not in ["added", "removed"]:
                                grouped_item_changes[item_id]["status"] = "changed"

                            grouped_item_changes[item_id]["changes"].append({
                                "field": field,
                                "reference_value": "N/A",
                                "current_value": current_value
                            })
                            logger.debug(f"Nested item/attribute added: {item_id}.{field}")
                    else:
                        logger.warning(f"Could not process dictionary_item_added path: {item_path}")
                        other_changes_list.append({
                            "item_id": None, "field": item_path,
                            "reference_value": "N/A",
                            "current_value": changes.get(item_path, "Value not in diff"),
                            "status": "other"
                        })

            elif diff_type == 'dictionary_item_removed':
                for item_path in changes:
                    item_id, field, is_root_item = self._extract_path_components(item_path)
                    if item_id is not None:
                        if is_root_item:
                            # Entire item removed at root level (e.g., root['old_item_id'] for dict, or root[old_index] for list if group_by used)
                            reference_value = self._get_value_from_original_json(json1, item_id, None) # Get full item data
                            if item_id not in grouped_item_changes:
                                grouped_item_changes[item_id] = {"status": "removed", "changes": [], "full_item_ref": None, "full_item_curr": None}
                            grouped_item_changes[item_id]["status"] = "removed"
                            grouped_item_changes[item_id]["full_item_ref"] = reference_value
                            logger.debug(f"Item removed (dict/group_by): {item_id}")
                        else:
                            # Nested attribute/item removed (e.g., root['id']['old_field'] or root[0]['old_field'])
                            reference_value = self._get_value_from_original_json(json1, item_id, field)
                            if item_id not in grouped_item_changes:
                                grouped_item_changes[item_id] = {"status": "changed", "changes": [], "full_item_ref": None, "full_item_curr": None}

                            if grouped_item_changes[item_id]["status"] not in ["added", "removed"]:
                                grouped_item_changes[item_id]["status"] = "changed"

                            grouped_item_changes[item_id]["changes"].append({
                                "field": field,
                                "reference_value": reference_value,
                                "current_value": "N/A"
                            })
                            logger.debug(f"Nested item/attribute removed: {item_id}.{field}")
                    else:
                        logger.warning(f"Could not process dictionary_item_removed path: {item_path}")
                        other_changes_list.append({
                            "item_id": None, "field": item_path,
                            "reference_value": changes.get(item_path, "Value not in diff"),
                            "current_value": "N/A",
                            "status": "other"
                        })

            elif diff_type == 'iterable_item_added': # Correct DeepDiff type for list/set additions
                for path, new_value in changes.items(): # 'changes' is a dict of path:new_value
                    item_id, field, is_root_item = self._extract_path_components(path)
                    if item_id is not None and is_root_item: # Should always be root item for iterable_item_added
                        # Get the full item data from json2
                        current_value = self._get_value_from_original_json(json2, item_id, None)
                        if item_id not in grouped_item_changes:
                            grouped_item_changes[item_id] = {"status": "added", "changes": [], "full_item_ref": None, "full_item_curr": None}
                        grouped_item_changes[item_id]["status"] = "added"
                        grouped_item_changes[item_id]["full_item_curr"] = current_value
                        logger.debug(f"Iterable item added at index/key: {item_id}")
                    else:
                        logger.warning(f"Could not process iterable_item_added path: {path}")
                        other_changes_list.append({
                            "item_id": item_id, "field": path,
                            "reference_value": "N/A",
                            "current_value": new_value,
                            "status": "other"
                        })

            elif diff_type == 'iterable_item_removed': # Correct DeepDiff type for list/set removals
                for path, old_value in changes.items(): # 'changes' is a dict of path:old_value
                    item_id, field, is_root_item = self._extract_path_components(path)
                    if item_id is not None and is_root_item: # Should always be root item for iterable_item_removed
                        # Get the full item data from json1
                        reference_value = self._get_value_from_original_json(json1, item_id, None)
                        if item_id not in grouped_item_changes:
                            grouped_item_changes[item_id] = {"status": "removed", "changes": [], "full_item_ref": None, "full_item_curr": None}
                        grouped_item_changes[item_id]["status"] = "removed"
                        grouped_item_changes[item_id]["full_item_ref"] = reference_value
                        logger.debug(f"Iterable item removed at index/key: {item_id}")
                    else:
                        logger.warning(f"Could not process iterable_item_removed path: {path}")
                        other_changes_list.append({
                            "item_id": item_id, "field": path,
                            "reference_value": old_value,
                            "current_value": "N/A",
                            "status": "other"
                        })

            else:
                # Capture other DeepDiff change types directly (e.g., type_changed, set_item_added/removed)
                logger.info(f"Processing 'other' diff type: {diff_type}")
                for path, details in changes.items():
                    item_id, field, _ = self._extract_path_components(path)
                    # Attempt to extract old/new values if available, otherwise use the 'details'
                    ref_val = details.get('old_value', details) if isinstance(details, dict) else details
                    curr_val = details.get('new_value', "N/A") if isinstance(details, dict) else "N/A"

                    other_changes_list.append({
                        "item_id": item_id,
                        "field": field if field else path, # Use field if extracted, else the full path
                        "reference_value": ref_val,
                        "current_value": curr_val,
                        "status": "other"
                    })

        # Consolidate grouped changes into the final desired format
        final_formatted_output = []
        for item_id, details in grouped_item_changes.items():
            if details["status"] == "added":
                final_formatted_output.append({
                    "item_id": item_id,
                    "changes": [{"field": None, "reference_value": "N/A", "current_value": details["full_item_curr"]}] if details["full_item_curr"] is not None else [],
                    "status": "added"
                })
            elif details["status"] == "removed":
                final_formatted_output.append({
                    "item_id": item_id,
                    "changes": [{"field": None, "reference_value": details["full_item_ref"], "current_value": "N/A"}] if details["full_item_ref"] is not None else [],
                    "status": "removed"
                })
            elif details["status"] == "changed":
                # Only include if there are actual attribute changes or full item changes reported
                if details["changes"]:
                    final_formatted_output.append({
                        "item_id": item_id,
                        "changes": details["changes"],
                        "status": "changed"
                    })
            # Note: If an item was marked "added" or "removed" but also had "changed" attributes,
            # the "added"/"removed" status takes precedence for the item as a whole.
            # Current logic prioritizes "added"/"removed" for full items, and "changed" for attribute diffs.

        # Add any 'other' changes that couldn't be grouped by item_id
        final_formatted_output.extend(other_changes_list)

        return {"res": final_formatted_output, "dif": diff_output}


    # --- NEW Helper Function for Summarizing Diff Results ---
    def _summarize_diff_results(self,formatted_diff_res: list, raw_deepdiff_output: dict) -> dict:
        """
        Processes the formatted DeepDiff results to categorize and count changes,
        preparing them for display.

        Args:
            formatted_diff_res (list): The 'res' output from compare_differences.
            raw_deepdiff_output (dict): The 'dif' output from compare_differences.

        Returns:
            dict: A structured dictionary containing:
                - 'relevant_changes': List of dictionaries for 'changed', 'added', 'removed' items.
                - 'other_changes': List of dictionaries for 'other' changes.
                - 'raw_deepdiff_output': The original raw DeepDiff output.
                - 'summary_counts': Dictionary with counts for 'changed', 'added', 'removed', 'other' changes.
                - 'has_diffs': Boolean indicating if any differences were found.
        """
        relevant_changes = []
        other_changes = []
        changed_count = 0
        added_count = 0
        removed_count = 0
        other_count = 0

        for diff_item in formatted_diff_res:
            status = diff_item.get('status')
            if status == 'changed':
                changed_count += 1
                relevant_changes.append(diff_item)
            elif status == 'added':
                added_count += 1
                relevant_changes.append(diff_item)
            elif status == 'removed':
                removed_count += 1
                relevant_changes.append(diff_item)
            elif status == 'other':
                other_count += 1
                other_changes.append(diff_item)
            else:
                logger.warning(f"Unknown diff status encountered: {status} for item {diff_item.get('item_id')}")
                other_count += 1 # Treat unknown as 'other'
                other_changes.append(diff_item)

        has_diffs = (changed_count + added_count + removed_count + other_count) > 0

        return {
            "relevant_changes": relevant_changes,
            "other_changes": other_changes,
            "raw_deepdiff_output": raw_deepdiff_output,
            "summary_counts": {
                "changed": changed_count,
                "added": added_count,
                "removed": removed_count,
                "other": other_count,
            },
            "has_diffs": has_diffs
        }



    # --- Helper Functions for DeepDiff Output Processing ---

    def _extract_path_components(self,path_str: str) -> tuple[str | int | None, str | None, bool]:
        """
        Parses a DeepDiff path string (e.g., "root['item_id']['attribute']" or "root[0]['attribute']")
        to extract the primary item identifier, the nested field path, and whether it's a root-level item change.

        Args:
            path_str (str): The path string provided by DeepDiff.

        Returns:
            tuple: (item_id, field_path_dot_notation, is_root_item_only)
                - item_id (str or int or None): The identifier of the primary item (e.g., 'item_id', 0).
                - field_path_dot_notation (str or None): The path to the changed field within the item
                                                            (e.g., "nested_dict.some_key.0").
                - is_root_item_only (bool): True if the change applies to the root item itself (no nested field).
        """
        if not isinstance(path_str, str) or not path_str.startswith("root["):
            logger.warning(f"Unexpected DeepDiff path format (not starting with 'root['): {path_str}")
            return None, None, False

        # Regex to capture the first key (string in single quotes) or index (digits)
        # and the rest of the path.
        # Group 1: string key (e.g., 'my_id')
        # Group 2: integer index (e.g., 0)
        # Group 3: remaining path (e.g., "['nested_dict']['some_key']")
        match = re.match(r"root\[(?:'([^']+)'|(\d+))\](.*)", path_str)
        if not match:
            logger.warning(f"Could not parse item_id/index from DeepDiff path: {path_str}")
            return None, None, False

        # Determine item_id: string if group(1) exists, int if group(2) exists.
        item_id = match.group(1) if match.group(1) else int(match.group(2))
        raw_field_path = match.group(3) # This is the part like "['nested_dict']['some_key']" or "[0]['attr']"

        if not raw_field_path:
            # If there's no remaining path, it means the change is directly on the root-level item.
            return item_id, None, True

        # Convert the raw_field_path to a more readable dot-notation format.
        processed_field = raw_field_path
        processed_field = re.sub(r"\[\'([^\']+)\'\]", r'.\1', processed_field) # Replace ['key'] with .key
        processed_field = re.sub(r'\[(\d+)\]', r'.\1', processed_field)       # Replace [index] with .index

        # Clean up any redundant dots (e.g., '..') or leading/trailing dots.
        processed_field = re.sub(r'\.{2,}', '.', processed_field)
        processed_field = processed_field.strip('.')

        return item_id, processed_field, False # Not a root-level item, it has a nested field path.


    def _get_value_from_nested_data(self,data: dict | list, path_parts: list) -> any:
        """
        Safely retrieves a value from a nested dictionary or list using a list of path parts.
        Handles both dictionary keys and list indices.

        Args:
            data (dict or list): The nested data structure.
            path_parts (list): A list of keys/indices representing the path to the desired value.

        Returns:
            any: The value at the specified path, or None if the path is invalid or not found.
        """
        current_data = data
        for part in path_parts:
            try:
                if isinstance(current_data, dict):
                    current_data = current_data[part]
                elif isinstance(current_data, list):
                    current_data = current_data[int(part)] # Convert part to int for list indexing.
                else:
                    return None # Path leads to a non-dict/list intermediate, so cannot proceed.
            except (KeyError, IndexError, TypeError):
                return None # Path not found or invalid part (e.g., non-integer index for list).
        return current_data


    def _get_value_from_original_json(self,json_data: dict | list, item_id: str | int, field_path: str = None) -> any:
        """
        Retrieves a specific value from the original JSON data structure given an item_id
        and an optional nested field_path.

        This is used to reconstruct the original values (reference or current) that DeepDiff
        might not provide in their entirety for complex changes.

        Args:
            json_data (dict or list): The original JSON data (either baseline or current).
            item_id (str or int): The identifier of the primary item (e.g., a dictionary key, or list index).
            field_path (str, optional): The dot-notation path to a nested field within the item.
                                        If None, the entire item identified by item_id is returned.

        Returns:
            any: The value at the specified item_id and field_path, or None if not found.
        """
        if item_id is None or not isinstance(json_data, (dict, list)):
            return None

        # First, retrieve the item identified by item_id from the root of json_data.
        try:
            if isinstance(json_data, dict):
                if item_id not in json_data:
                    return None
                current_item = json_data[item_id]
            elif isinstance(json_data, list):
                # For lists, item_id is expected to be an integer index.
                if not isinstance(item_id, int) or item_id >= len(json_data) or item_id < 0:
                    return None
                current_item = json_data[item_id]
            else:
                return None
        except (KeyError, IndexError, TypeError):
            # Handle cases where item_id is not found or is of an incompatible type.
            return None

        if field_path:
            # If a field_path is provided, navigate into the current_item.
            path_parts = field_path.split('.') # Split the dot-notation path into individual parts.
            return self._get_value_from_nested_data(current_item, path_parts)
        else:
            # If no field_path, return the entire item identified by item_id.
            return current_item


    def _handle_deepdiff_comparison(self,
        baseline: Any,
        current_data: Any,
        group_by_key: Optional[str] = None,
        **kwargs # Accept extra kwargs like entity_name for consistency, but don't use them here
    ) -> dict:

        formatted = self.compare_differences(baseline, current_data, group_by_key_name=group_by_key)
        summary = self._summarize_diff_results(formatted.get("res", []), formatted.get("dif", {}))
        return summary


    def _transform_list_to_dict_by_key(self,
        data_list: List[Dict[str, Any]],
        key: str,
        entity_name: str,
    ) -> Dict[str, Dict[str, Any]]:
        """
        Transform a list of dicts into a dict keyed by `key`.
        Logs warnings on duplicates or missing keys.
        """
        transformed = {}
        for item in data_list:
            item_id = item.get(key)
            if item_id is None:
                logger.warning(f"Item missing group_by key '{key}' in {entity_name}: {item}")
                continue
            if item_id in transformed:
                logger.warning(f"Duplicate group_by key '{item_id}' in {entity_name}, overwriting previous entry.")
            transformed[item_id] = item
        return transformed
