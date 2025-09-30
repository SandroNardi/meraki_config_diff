# core_operations.py

"""
This module provides the core business logic for the application,
handling interactions with the Meraki Dashboard API, managing data storage,
and orchestrating data comparison operations. It integrates with `use_cases.py`
to define available operations and `compare_functions.py` for comparison logic.
"""

# --- Standard Library Imports ---
import os           # For interacting with the operating system, e.g., file paths, environment variables.
import json         # For working with JSON data.
from datetime import datetime # For generating timestamps for filenames.
import logging      # For logging events and errors.

# --- Third-Party Imports ---
import meraki       # The Meraki Dashboard API library.

# --- Local Application Imports ---
import compare_functions as cf # Contains functions for comparing configuration data.
import use_cases as uc         # Defines the structure and details of various use cases (operations).


# --- Global Configuration and State Variables ---
# Meraki Dashboard API key, loaded from environment variable or defaults.
API_KEY = os.getenv("MK_CSM_KEY", "default_api_key")
dashboard = None    # Meraki Dashboard API object, initialized by create_dashboard().
organization_id = None # Stores the ID of the currently selected Meraki organization.
orgnaization_name = None # Stores the name of the currently selected Meraki organization.

# Defines logical folder names for organizing saved configuration files.
folders = {"network": "network", "organization": "organization", "device": "device"} # Added "device" for consistency.
FILES_DIRECTORY = "saved_configs" # Root directory for storing all saved configuration files.


# --- Logger Setup ---
# Get a named logger for this module.
logger = logging.getLogger(__name__)


# --- Common Utility Functions ---
def get_app_log_content() -> str:
    """
    Reads the content of the 'app.log' file.

    This function is used to display the application's log directly within the GUI,
    aiding in debugging and monitoring.

    Returns:
        str: The content of the 'app.log' file, or an error message if the file
             cannot be read or is not found.
    """
    # Construct the path to app.log assuming it's in the same directory as this module.
    log_file_path = os.path.join(os.path.dirname(__file__), 'app.log')
    try:
        with open(log_file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return content
    except FileNotFoundError:
        return "Error: app.log file not found. Please ensure it exists in the same directory as core_operations.py."
    except Exception as e:
        return f"Error reading app.log: {e}"


def create_dashboard():
    """
    Initializes the global Meraki Dashboard API object.

    This function should be called once at the application's start to set up
    the API client for all subsequent Meraki API interactions.
    """
    global dashboard
    dashboard = meraki.DashboardAPI(API_KEY, suppress_logging=True)
    # Pass the initialized dashboard object to the use_cases module for API calls.
    uc.set_dashboard(dashboard)


def core_data_operation(scope: str, operation_name: str, task: str, identifier: str = None, filename: str = None,
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
        tags (list, optional): A list of tags to filter by (for "compare" tasks, e.g., network tags).
                               Defaults to None.
        org_ids (list, optional): A list of organization IDs to filter by (for "compare" tasks).
                                  Defaults to None.

    Returns:
        dict: A dictionary containing the results of the operation, particularly for "compare" tasks.
              Returns an empty dictionary for "store" tasks upon success.
    """
    results = {}
    try:
        if task == "store":
            logger.debug(f"Attempting to store: {scope} {operation_name} {identifier if identifier else 'N/A'}")
            # The 'store' function will now raise exceptions on failure.
            store(scope, operation_name, identifier)
            results = {"success": True} # Indicate success for store operation
        elif task == "compare":
            logger.debug(f"Attempting to compare: {scope} {operation_name} {filename if filename else 'N/A'}")
            # Comparison functions already return a dict, which might contain an error.
            if scope == "network_level":
                results = cf.compare_network_level(filename, scope, operation_name,comparison_method, network_tags or None)
            elif scope == "organization_level":
                results = cf.compare_organization_level(filename, scope, operation_name, comparison_method,org_ids or None)
            elif scope == "device_level":
                results = cf.compare_device_level(
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
# These functions abstract access to the `uc.USE_CASES` dictionary,
# providing a clean interface for retrieving operation-specific metadata.

def get_operation(scope: str, operation_name: str) -> dict:
    """
    Retrieves the dictionary containing details for a specific operation within a given scope.

    Args:
        scope (str): The level of the operation (e.g., "organization_level").
        operation_name (str): The name of the specific operation (e.g., "admins").

    Returns:
        dict: A dictionary of operation details, or None if not found.
    """
    operations = uc.USE_CASES.get(scope, {}).get("operations", [])
    for operation in operations:
        if operation["name"] == operation_name:
            return operation
    return None

def get_operations(scope: str) -> list:
    """
    Retrieves a list of all operations defined for a given scope.

    Args:
        scope (str): The level of operations to retrieve (e.g., "network_level").

    Returns:
        list: A list of dictionaries, each representing an operation.
    """
    return uc.USE_CASES.get(scope, {}).get("operations", [])

def get_use_cases_items() -> list:
    """
    Retrieves all top-level use cases and their details from the `use_cases` module.

    Returns:
        list: A list of (key, value) pairs for each use case.
    """
    return uc.USE_CASES.items()

def get_scope_folder_name(scope: str) -> str:
    """
    Retrieves the designated folder name for a given scope (e.g., "organization", "network").

    Args:
        scope (str): The level (e.g., "organization_level").

    Returns:
        str: The folder name associated with the scope.
    """
    return uc.USE_CASES.get(scope, {}).get("folder", "")

def get_operation_folder_name(scope: str, operation_name: str) -> str:
    """
    Retrieves the designated sub-folder name for a specific operation within a scope.

    Args:
        scope (str): The level (e.g., "network_level").
        operation_name (str): The name of the operation (e.g., "ssids").

    Returns:
        str: The sub-folder name for the operation, or None if not found.
    """
    operations = uc.USE_CASES.get(scope, {}).get("operations", [])
    for operation in operations:
        if operation["name"] == operation_name:
            return operation["folder"]
    return None

# Note: The following `get_operation_folder_name` function is a duplicate of the one above.
# It does not introduce new functionality and can be removed for code cleanliness if modifications were allowed.
def get_operation_folder_name(scope: str, operation_name: str) -> str:
    """
    Retrieves the designated sub-folder name for a specific operation within a scope.
    (This is a duplicate function definition).

    Args:
        scope (str): The level (e.g., "network_level").
        operation_name (str): The name of the operation (e.g., "ssids").

    Returns:
        str: The sub-folder name for the operation, or None if not found.
    """
    operations = uc.USE_CASES.get(scope, {}).get("operations", [])
    for operation in operations:
        if operation["name"] == operation_name:
            return operation["folder"]
    return None


def get_operation_fetch_function(scope: str, operation_name: str) -> callable:
    """
    Retrieves the Python function responsible for fetching data for a given operation.

    Args:
        scope (str): The level (e.g., "organization_level").
        operation_name (str): The name of the operation (e.g., "admins").

    Returns:
        callable: The fetch function, or None if not found.
    """
    operations = uc.USE_CASES.get(scope, {}).get("operations", [])
    for operation in operations:
        if operation["name"] == operation_name:
            return operation["fetch_function"]
    return None

def get_operation_file_name(scope: str, operation_name: str) -> str:
    """
    Retrieves the base filename for data associated with a given operation.

    Args:
        scope (str): The level (e.g., "network_level").
        operation_name (str): The name of the operation (e.g., "ssids").

    Returns:
        str: The base filename, or None if not found.
    """
    operations = uc.USE_CASES.get(scope, {}).get("operations", [])
    for operation in operations:
        if operation["name"] == operation_name:
            return operation["file_name"]
    return None

def get_operation_product_type(scope: str, operation_name: str) -> str:
    """
    Retrieves the associated Meraki product type for a given operation, if specified.

    Args:
        scope (str): The level (e.g., "device_level").
        operation_name (str): The name of the operation (e.g., "device_status").

    Returns:
        str: The product type (e.g., "wireless", "appliance"), or None if not specified.
    """
    operations = uc.USE_CASES.get(scope, {}).get("operations", [])
    for operation in operations:
        if operation["name"] == operation_name:
            return operation.get("product_type", None)
    return None


def list_json_files(scope_folder: str, operation_folder: str) -> list:
    """
    Lists all JSON files within a specific operation's saved configuration folder.

    Args:
        scope_folder (str): The top-level folder name (e.g., "organization").
        operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").

    Returns:
        list: A list of JSON filenames found in the directory, or an empty list if
              the directory does not exist or is inaccessible.
    """
    logger.debug(f"Attempting to list JSON files in: {FILES_DIRECTORY}/{scope_folder}/{operation_folder}")
    destination_folder = os.path.join(FILES_DIRECTORY, scope_folder, operation_folder)

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


# --- Organization Management Functions ---
def set_organization(org_id):
    global organization_id
    global orgnaization_name
    try:
        org_details = dashboard.organizations.getOrganization(org_id)
        orgnaization_name = org_details["name"]
        organization_id = org_id
        logger.info(f"Current organization set to: {orgnaization_name} (ID: {organization_id}).")
    except meraki.APIError as e:
        logger.error(f"Meraki API error setting organization {org_id}: {e}", exc_info=True)
        organization_id = None
        orgnaization_name = None
        raise # Re-raise to notify caller (gui.py)
    except Exception as e:
        logger.error(f"An unexpected error occurred while setting organization {org_id}: {e}", exc_info=True)
        organization_id = None
        orgnaization_name = None
        raise # Re-raise to notify caller (gui.py)


def get_organization() -> tuple:
    """
    Retrieves the ID and name of the currently selected organization.

    Returns:
        tuple: A tuple containing (organization_id, organization_name).
               Returns (None, None) if no organization is set.
    """
    return organization_id, orgnaization_name


def get_organizations(simplified: bool = False) -> list:
    """
    Fetches all Meraki organizations accessible by the configured API key.

    Args:
        simplified (bool): If True, returns a list of dictionaries with only 'id' and 'name'.
                           If False, returns the full Meraki API response for each organization.

    Returns:
        list: A list of organization dictionaries.
    """
    keys_to_extract = ["id", "name"]
    logger.info("Fetching all accessible organizations.")
    organizations = dashboard.organizations.getOrganizations()

    if simplified:
        extracted_list = [
            {key: item[key] for key in keys_to_extract if key in item}
            for item in organizations
        ]
        return extracted_list
    else:
        return organizations


def get_networks(simplified: bool = False, global_networks: bool = False) -> list:
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
        organizations = get_organizations(True) # Get simplified list of organizations.
        for org in organizations:
            # Get networks for each organization, paginating through all pages.
            net = dashboard.organizations.getOrganizationNetworks(
                org["id"], total_pages="all"
            )
            networks.extend(net) # Add networks to the main list.
    else:
        if not organization_id:
            raise ValueError("Organization ID is not set. Cannot fetch networks for a specific organization.")
        logger.info(f"Fetching networks for organization ID: {organization_id}.")
        networks = dashboard.organizations.getOrganizationNetworks(
            organization_id, total_pages="all"
        )

    if simplified:
        extracted_list = [
            {key: item[key] for key in keys_to_extract if key in item}
            for item in networks
        ]
        return extracted_list
    else:
        return networks


def get_devices(simplified: bool = False, global_devices: bool = False) -> list:
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
        organizations = get_organizations(True) # Get simplified list of organizations.
        for org in organizations:
            # Get devices for each organization, paginating through all pages.
            dev = dashboard.organizations.getOrganizationDevices(
                org["id"], total_pages="all"
            )
            devices.extend(dev) # Add devices to the main list.
    else:
        if not organization_id:
            raise ValueError("Organization ID is not set. Cannot fetch devices for a specific organization.")
        logger.info(f"Fetching devices for organization ID: {organization_id}.")
        devices = dashboard.organizations.getOrganizationDevices(
            organization_id, total_pages="all"
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
def store(scope: str, operation_name: str, identifier: str = None):
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
    fetch_function = get_operation_fetch_function(scope, operation_name)
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
        # Catch specific exceptions from fetch_function if needed, otherwise re-raise
        logger.error(f"Error fetching data for {scope}/{operation_name}: {e}", exc_info=True)
        raise # Re-raise the exception

    filename = create_file_name_with_timestamp(
        get_operation_file_name(scope, operation_name)
    )
    # save_to_json will now raise an exception on failure
    save_to_json(
        data_to_store,
        get_scope_folder_name(scope),
        get_operation_folder_name(scope, operation_name),
        filename,
    )
    logger.info(f"Data for {scope}/{operation_name} saved to {filename}.")


def create_file_name_with_timestamp(base_filename: str) -> str:
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


def save_to_json(data: any, scope_folder: str, operation_folder: str, filename: str):
    """
    Saves Python data (list or dictionary) to a JSON file within the structured
    `FILES_DIRECTORY`.

    Args:
        data (any): The data to be saved (e.g., list of dictionaries, dictionary).
        scope_folder (str): The top-level folder name (e.g., "organization").
        operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").
        filename (str): The name of the JSON file (including .json extension).
    """
    try:
        destination_folder = os.path.join(
            FILES_DIRECTORY, scope_folder, operation_folder
        )
        os.makedirs(destination_folder, exist_ok=True)
        destination = os.path.join(destination_folder, filename)
        with open(destination, "w") as file:
            json.dump(data, file, indent=4)
    except Exception as e:
        logger.error(f"Error saving to JSON: {e}", exc_info=True)
        raise # Re-raise the exception


def load_from_json(scope_folder: str, operation_folder: str, filename: str) -> any:
    """
    Loads data from a JSON file located within the structured `FILES_DIRECTORY`.

    Args:
        scope_folder (str): The top-level folder name (e.g., "organization").
        operation_folder (str): The sub-folder name for the specific operation (e.g., "admins").
        filename (str): The name of the JSON file to load (including .json extension).

    Returns:
        any: The loaded data (e.g., list, dictionary), or None if an error occurs.
    """
    try:
        source_folder = os.path.join(FILES_DIRECTORY, scope_folder, operation_folder)
        source = os.path.join(source_folder, filename)
        with open(source, "r") as file:
            return json.load(file)
    except FileNotFoundError as e:
        logger.error(f"JSON file not found: {source}. {e}", exc_info=True)
        raise # Re-raise FileNotFoundError
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from file: {source}. File might be corrupted or malformed. {e}", exc_info=True)
        raise # Re-raise JSONDecodeError
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading JSON file {source}: {e}", exc_info=True)
        raise # Re-raise other exceptions


