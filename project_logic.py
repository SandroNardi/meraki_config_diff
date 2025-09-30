# project_logic.py

"""
This module provides the core business logic for the application,
handling interactions with the Meraki Dashboard API, managing data storage,
and orchestrating data comparison operations. It integrates with `use_cases.py`
to define available operations and `compare_functions.py` for comparison logic.
"""

# --- Standard Library Imports ---
import os           # For interacting with the operating system, e.g., file paths, environment variables.
import json         # For working with JSON data.
from datetime import datetime, timedelta, timezone # For generating timestamps for filenames and graph logic.
from meraki_tools.my_logging import get_logger
from meraki_tools.meraki_api_utils import MerakiAPIWrapper
from typing import Optional, List, Dict, Any, Tuple

# --- Third-Party Imports ---
import meraki       # The Meraki Dashboard API library.

# --- Local Application Imports ---
# Assuming these files exist in the same directory or are importable
import compare_functions as cf # Contains functions for comparing configuration data.
import use_cases as uc         # Defines the structure and details of various use cases (operations).


# --- Logger Setup ---
logger = get_logger()


class ProjectLogic:
    def __init__(self, api_utils:MerakiAPIWrapper):
        # Initialize instance variables that were global in core_operations.py
        self.dashboard = None    # Meraki Dashboard API object, initialized by _create_dashboard().
        self.organization_id = None # Stores the ID of the currently selected Meraki organization.
        self.organization_name = None # Stores the name of the currently selected Meraki organization.
        self.FILES_DIRECTORY =  "saved_configs"# Root directory for storing all saved configuration files.
        self.logger = get_logger()
        # Initialize Meraki Dashboard API

        # Get USE_CASE_KEYS and USE_CASES from the uc module
        self.USE_CASE_KEYS = uc.USE_CASES.keys()
        self.USE_CASES = uc.USE_CASES

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
                    results = cf.compare_network_level(self, filename, scope, operation_name, comparison_method, network_tags or None)
                elif scope == self.USE_CASE_KEYS["organization_level"]:
                    results = cf.compare_organization_level(self, filename, scope, operation_name, comparison_method, org_ids or None)
                elif scope == self.USE_CASE_KEYS["device_level"]:
                    results = cf.compare_device_level(
                        self, filename, scope, operation_name, comparison_method,
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
        logger.debug(f"Attempting to list JSON files in: {self.FILES_DIRECTORY}/{scope_folder}/{operation_folder}")
        destination_folder = os.path.join(self.FILES_DIRECTORY, scope_folder, operation_folder)

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
            organizations = self.get_organizations(True)
            for org in organizations:
                # Get devices for each organization, paginating through all pages.
                dev = self.dashboard.organizations.getOrganizationDevices(
                    org["id"], total_pages="all"
                )
                devices.extend(dev) # Add devices to the main list.
        else:
            if not self.organization_id:
                raise ValueError("Organization ID is not set. Cannot fetch devices for a specific organization.")
            logger.info(f"Fetching devices for organization ID: {self.organization_id}.")
            devices = self.dashboard.organizations.getOrganizationDevices(
                self.organization_id, total_pages="all"
            )

        if simplified:
            extracted_list = [
                {key: item[key] for key in keys_to_extract if key in item}
                for item in devices
            ]
            return extracted_list
        else:
            return devices


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
        `self.FILES_DIRECTORY`.

        Args:
            data (any): The data to be saved (e.g., list of dictionaries, dictionary).
            scope_folder (str): The top-level folder name (e.g., "organization").
            operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").
            filename (str): The name of the JSON file (including .json extension).
        """
        try:
            destination_folder = os.path.join(
                self.FILES_DIRECTORY, scope_folder, operation_folder
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
        Loads data from a JSON file located within the structured `self.FILES_DIRECTORY`.

        Args:
            scope_folder (str): The top-level folder name (e.g., "organization").
            operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").
            filename (str): The name of the JSON file to load (including .json extension).

        Returns:
            any: The loaded data (e.g., list, dictionary).
        """
        try:
            source_folder = os.path.join(self.FILES_DIRECTORY, scope_folder, operation_folder)
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


    def collect_network_data_history(self, networks_list: List[Dict[str, Any]], t0_dt: datetime, t1_dt: datetime) -> Dict[str, Any]:
        """
        Collects network client history data for the given networks and time range.
        This is a mock implementation. In a real scenario, this would call Meraki API.
        """
        logger.info(f"ProjectLogic: Collecting network data history (mock) for {len(networks_list)} networks from {t0_dt} to {t1_dt}.")
        graph_data = {}
        for network in networks_list:
            network_id = network['id']
            network_name = network['name']
            # Generate some mock history data
            history = []
            current_time = t0_dt
            while current_time < t1_dt:
                history.append({
                    "startTs": current_time.isoformat().replace('+00:00', 'Z'),
                    "clientCount": (current_time.minute % 10) + (current_time.hour % 5) + 10 # Simple varying count
                })
                current_time += timedelta(minutes=30) # Simulate 30-min resolution
            graph_data[network_id] = {"name": network_name, "history": history}
        return graph_data