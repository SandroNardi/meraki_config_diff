# use_cases.py

"""
This module defines the various use cases and operations that the application supports
for interacting with the Meraki Dashboard API. It acts as a central registry,
mapping human-readable display names to specific Meraki API calls, file storage
locations, and comparison grouping keys.

It also provides helper functions for fetching data from the Meraki Dashboard API.
"""

import meraki # The Meraki Dashboard API library.
import core_operations as core # Imports core utility functions, especially for organization context.
import logging # For logging events and errors.


# --- Logger Setup ---
# Get a named logger for this module.
logger = logging.getLogger(__name__)

# --- Global Meraki Dashboard API Object ---
# This variable will hold the initialized Meraki Dashboard API object.
# It is set by the `set_dashboard` function, which is called from `core_operations`.
dashboard = None


# --- Dashboard API Initialization ---
def set_dashboard(created_dashboard: meraki.DashboardAPI):
    """
    Sets the global Meraki Dashboard API object for use within this module.
    This function is crucial for enabling API calls from the fetch functions defined here.

    Args:
        created_dashboard (meraki.DashboardAPI): An initialized Meraki Dashboard API instance.
    """
    global dashboard
    dashboard = created_dashboard
    logger.info("Meraki Dashboard API object set in use_cases module.")


# --- Meraki API Data Fetch Functions ---
# These functions encapsulate specific Meraki Dashboard API calls.
# They are designed to be used by the `core_operations` module for data retrieval.

def fetch_device_MX_interfaces(dev_id: str) -> dict:
    """
    Fetches the management interface settings for a specific Meraki MX device.

    Args:
        dev_id (str): The serial number of the Meraki MX device.

    Returns:
        dict: A dictionary containing the management interface configuration.
    """
    logger.debug(f"Fetching MX management interface for device ID: {dev_id}")
    return dashboard.devices.getDeviceManagementInterface(dev_id)


def fetch_network_settings(net_id: str) -> dict:
    """
    Fetches the general settings for a specific Meraki network.

    Args:
        net_id (str): The ID of the Meraki network.

    Returns:
        dict: A dictionary containing the network's general settings.
    """
    logger.debug(f"Fetching network settings for network ID: {net_id}")
    return dashboard.networks.getNetworkSettings(net_id)


def fetch_organization_settings(org_id: str = None) -> dict:
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
    org_id_to_fetch = org_id if org_id is not None else core.get_organization()[0]
    if not org_id_to_fetch:
        logger.error("No organization ID available to fetch organization settings.")
        return {}

    logger.debug(f"Fetching organization settings for organization ID: {org_id_to_fetch}")
    setting = dashboard.organizations.getOrganization(org_id_to_fetch)
    # Remove dynamic or irrelevant keys before comparison/storage.
    setting.pop("id", None)
    setting.pop("name", None)
    setting.pop("url", None)
    return setting


def fetch_network_ssids(net_id: str) -> list:
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
        return dashboard.wireless.getNetworkWirelessSsids(net_id)
    except meraki.exceptions.APIError as e:
        logger.error(f"API Error fetching SSIDs for network {net_id}: {e}", exc_info=True)
        raise

def fetch_switch_switchport(dev_id: str) -> dict :
    logger.debug(f"Fetching switchport configuration for device ID: {dev_id} (duplicate function).")
    try:
        return dashboard.switch.getDeviceSwitchPorts(dev_id)
    except meraki.exceptions.APIError as e:
        logger.error(f"API Error fetching switchport for device {dev_id}: {e}", exc_info=True)
        raise


def fetch_organization_admins(org_id: str = None) -> list:
    """
    Fetches the administrators for a Meraki organization.
    If `org_id` is not provided, it defaults to the globally selected organization.
    Removes the 'lastActive' field from each admin for consistent comparison.

    Args:
        org_id (str, optional): The ID of the Meraki organization. Defaults to None.

    Returns:
        list: A list of dictionaries, each representing an organization administrator.
    """
    org_id_to_fetch = org_id if org_id is not None else core.get_organization()[0]
    if not org_id_to_fetch:
        logger.error("No organization ID available to fetch organization admins.")
        return []

    logger.debug(f"Fetching organization administrators for organization ID: {org_id_to_fetch}")
    admins = dashboard.organizations.getOrganizationAdmins(org_id_to_fetch)
    # Remove dynamic fields that are not relevant for configuration comparison.
    for admin in admins:
        admin.pop("lastActive", None) # 'lastActive' changes frequently and is not a config setting.
    return admins


# --- USE CASE DEFINITIONS ---
# This dictionary structures all supported operations, categorized by level
# (organization, network, device). Each operation includes metadata
# necessary for fetching, storing, and comparing data.

USE_CASES = {
    "organization_level": {
        "folder": "Organization_config", # Base folder name for organization-level configs.
        "display_name": "Organization",   # Display name for this level in the GUI.
        "operations": [
            {
                "name": "organization_admins",      # Unique internal name for the operation.
                "display_name": "Organization Administrators", # User-friendly name for the GUI.
                "fetch_function": fetch_organization_admins, # Reference to the function that fetches this data.
                "folder": "organization_admins",    # Sub-folder within "Organization_config" for this operation's files.
                "file_name": "getOrganizationAdmins", # Base filename for saved data.
                "group_by": "email"                 # Key to use for grouping items in DeepDiff comparison (e.g., for list of admins).
            },
            {
                "name": "organization_settings",
                "display_name": "Organization Settings",
                "fetch_function": fetch_organization_settings,
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
                "fetch_function": fetch_network_ssids,
                "folder": "network_ssids",
                "file_name": "getNetworkWirelessSsids",
                "product_type": "wireless", # Optional: Filter networks by product type.
                "group_by": "name"          # Group SSIDs by their name for comparison.
            },
            {
                "name": "network_settings",
                "display_name": "Network Settings",
                "fetch_function": fetch_network_settings,
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
                "fetch_function": fetch_switch_switchport, # Using the more appropriately named function.
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