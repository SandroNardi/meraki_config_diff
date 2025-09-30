# compare_functions.py

"""
This module provides functions for comparing configuration data using DeepDiff.
It supports comparisons at the organization, network, and device levels,
processing DeepDiff's output into a more human-readable and categorized format.
"""

# --- Standard Library Imports ---
import logging  # For logging events and errors.
import re       # For regular expression operations, used in parsing DeepDiff paths.
from collections import OrderedDict # To preserve order of keys when flattening JSON.
from tkinter import Entry
from typing import Optional, Callable, List, Dict, Any

# --- Third-Party Imports ---
from deepdiff import DeepDiff # The main library for deep comparison of data structures.

# --- Local Application Imports ---
import core_operations as core # Provides functions for loading data and retrieving operation metadata.
import use_cases as uc         # Defines the structure and details of various use cases/operations.


# --- Logger Setup ---
logger = logging.getLogger(__name__)

# logger = logging.getLogger(__name__) # Ensure your logger is initialized appropriately

def _compare_level_general(
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

    baseline = core.load_from_json(
        core.get_scope_folder_name(scope),
        core.get_operation_folder_name(scope, operation_name),
        json_file_name,
    )
    if not baseline:
        logger.error(f"Baseline data not found: {json_file_name} for {scope}/{operation_name}")
        return []

    fetch_function = core.get_operation_fetch_function(scope, operation_name)
    if not fetch_function:
        logger.error(f"No fetch function for {scope}/{operation_name}")
        return []

    operations_list = uc.USE_CASES.get(scope, {}).get("operations", [])
    found_op = next((op for op in operations_list if op["name"] == operation_name), None)
    group_by_key = found_op.get("group_by") if found_op else None

    entities = get_entities_func(True)
    results = []

    compare_func = _COMPARISON_METHODS.get(comparison_method)
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

def _organization_filter(entity: Dict[str, Any], scope: str, operation_name: str, filter_args: Dict[str, Any]) -> bool:
    """
    Filter logic specific to organization-level comparisons.
    Checks if the organization ID is in the provided list.
    """
    organization_ids_filter = filter_args.get("organization_ids")
    if organization_ids_filter and entity.get("id") not in organization_ids_filter:
        logger.debug(f"Skipping organization '{entity.get('name', 'N/A')}' (ID: {entity.get('id', 'N/A')}) as it's not in the filter list.")
        return False
    return True

def _network_filter(entity: dict, scope: str, operation_name: str, filter_args: dict) -> bool:
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
    product_type = core.get_operation_product_type(scope, operation_name)
    if product_type:
        if product_type not in entity.get("productTypes", []):
            logger.debug(f"Skipping network '{entity.get('name', 'N/A')}' due product type not present.")
            return False

    return True


def _device_filter(entity: dict, scope: str, operation_name: str, filter_args: dict) -> bool:
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

def compare_organization_level(json_file_name: str, scope: str, operation_name: str,comparison_method:str ="deepdiff", organization_ids: list = None) -> list:
    """
    Compares the current organization-level configuration data against a saved baseline.
    """
    return _compare_level_general(
        json_file_name=json_file_name,
        scope=scope,
        operation_name=operation_name,
        get_entities_func=core.get_organizations,
        entity_id_key="id",
        entity_name_key="name",
        entity_filter_func=_organization_filter,
        filter_args={"organization_ids": organization_ids} if organization_ids else None,
        comparison_method= comparison_method,
    )

def compare_network_level(json_file_name: str, scope: str, operation_name: str, comparison_method:str ="deepdiff", network_tags: list = None) -> list:
    """
    Compares the current network-level configuration data against a saved baseline.
    """
    return _compare_level_general(
        json_file_name=json_file_name,
        scope=scope,
        operation_name=operation_name,
        get_entities_func=core.get_networks,
        entity_id_key="id",
        entity_name_key="name",
        entity_filter_func=_network_filter,
        filter_args={"network_tags": network_tags} if network_tags else None,
        comparison_method= comparison_method,
    )

def compare_device_level(json_file_name: str, scope: str, operation_name: str, comparison_method: str = "deepdiff",
                         network_tags: list = None, device_models: list = None, device_tags: list = None, product_types: list = None) -> list:
    """
    Compares the current device-level configuration data against a saved baseline,
    with filtering options for tags, device models, network tags, and product types.
    """
    return _compare_level_general(
        json_file_name=json_file_name,
        scope=scope,
        operation_name=operation_name,
        get_entities_func=core.get_devices,
        entity_id_key="serial",
        entity_name_key="name",
        entity_filter_func=_device_filter,
        filter_args={
            "network_tags": network_tags,
            "device_models": device_models,
            "device_tags": device_tags,
            "product_types": product_types,
        },
        comparison_method=comparison_method,
    )


# --- Core Difference Comparison Function ---

def compare_differences(json1, json2, group_by_key_name=None):
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

    #logger.debug(f"Raw DeepDiff output: {diff_output}")

    # Temporary structure to group changes by item_id
    # { item_id: { "status": "added"|"removed"|"changed", "changes": [], "full_item_ref": None, "full_item_curr": None } }
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
                    item_id, field, is_root_item_only = _extract_path_components(path)
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
                item_id, field, is_root_item = _extract_path_components(item_path)
                if item_id is not None:
                    if is_root_item:
                        # Entire item added at root level (e.g., root['new_item_id'] for dict, or root[new_index] for list if group_by used)
                        current_value = _get_value_from_original_json(json2, item_id, None) # Get full item data
                        if item_id not in grouped_item_changes:
                            grouped_item_changes[item_id] = {"status": "added", "changes": [], "full_item_ref": None, "full_item_curr": None}
                        grouped_item_changes[item_id]["status"] = "added"
                        grouped_item_changes[item_id]["full_item_curr"] = current_value
                        logger.debug(f"Item added (dict/group_by): {item_id}")
                    else:
                        # Nested attribute/item added (e.g., root['id']['new_field'] or root[0]['new_field'])
                        current_value = _get_value_from_original_json(json2, item_id, field)
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
                item_id, field, is_root_item = _extract_path_components(item_path)
                if item_id is not None:
                    if is_root_item:
                        # Entire item removed at root level (e.g., root['old_item_id'] for dict, or root[old_index] for list if group_by used)
                        reference_value = _get_value_from_original_json(json1, item_id, None) # Get full item data
                        if item_id not in grouped_item_changes:
                            grouped_item_changes[item_id] = {"status": "removed", "changes": [], "full_item_ref": None, "full_item_curr": None}
                        grouped_item_changes[item_id]["status"] = "removed"
                        grouped_item_changes[item_id]["full_item_ref"] = reference_value
                        logger.debug(f"Item removed (dict/group_by): {item_id}")
                    else:
                        # Nested attribute/item removed (e.g., root['id']['old_field'] or root[0]['old_field'])
                        reference_value = _get_value_from_original_json(json1, item_id, field)
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
                item_id, field, is_root_item = _extract_path_components(path)
                if item_id is not None and is_root_item: # Should always be root item for iterable_item_added
                    # Get the full item data from json2
                    current_value = _get_value_from_original_json(json2, item_id, None)
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
                item_id, field, is_root_item = _extract_path_components(path)
                if item_id is not None and is_root_item: # Should always be root item for iterable_item_removed
                    # Get the full item data from json1
                    reference_value = _get_value_from_original_json(json1, item_id, None)
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
                item_id, field, _ = _extract_path_components(path)
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
def _summarize_diff_results(formatted_diff_res: list, raw_deepdiff_output: dict) -> dict:
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

def _extract_path_components(path_str: str) -> tuple[str | int | None, str | None, bool]:
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


def _get_value_from_nested_data(data: dict | list, path_parts: list) -> any:
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


def _get_value_from_original_json(json_data: dict | list, item_id: str | int, field_path: str = None) -> any:
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
        return _get_value_from_nested_data(current_item, path_parts)
    else:
        # If no field_path, return the entire item identified by item_id.
        return current_item

# --- Data Comparison Utility Functions ---
def flatten_json(data: any, parent_key: str = "", separator: str = ".") -> OrderedDict:
    """
    Recursively flattens a nested JSON object (dictionary or list) into a single-level
    OrderedDict where keys represent the path to the original value.

    Args:
        data (any): The JSON data (dict or list) to flatten.
        parent_key (str): Used internally for recursion to build the path.
        separator (str): The character used to separate keys in the flattened path.

    Returns:
        OrderedDict: A flattened dictionary with path-like keys.
    """
    items = []
    if isinstance(data, dict):
        for key, value in data.items():
            new_key = f"{parent_key}{separator}{key}" if parent_key else key
            items.extend(flatten_json(value, new_key, separator).items())
    elif isinstance(data, list):
        for index, value in enumerate(data):
            # Ensure index is treated as string for key consistency
            new_key = f"{parent_key}{separator}{index}" if parent_key else str(index)
            items.extend(flatten_json(value, new_key, separator).items())
    else:
        items.append((parent_key, data))
    return OrderedDict(items)


def flat_compare_differences_enhanced(json1: dict | list, json2: dict | list) -> dict:
    """
    Compares two JSON objects (or lists) by first flattening them and then identifying
    changes, additions, and removals based on the flattened keys.

    Args:
        json1 (dict | list): The reference JSON object or list.
        json2 (dict | list): The current JSON object or list to compare against the reference.

    Returns:
        dict: A dictionary containing:
              - "has_changes" (bool): True if any differences (changed, added, removed) were found.
              - "detailed_changes" (list): A list of dictionaries detailing each change.
                                           Each dict will have "key", "status", "reference_value", "current_value".
    """
    if not isinstance(json1, (dict, list)) or not isinstance(json2, (dict, list)):
        logger.error("Input JSON structures must be dictionaries or lists for flat comparison.")
        return {"has_changes": False, "detailed_changes": []}

    flat_json1 = flatten_json(json1)
    flat_json2 = flatten_json(json2)

    # Get all unique keys from both flattened structures
    all_keys = sorted(list(set(flat_json1.keys()).union(flat_json2.keys())))
    

    detailed_changes = []
    has_changes = False

    for key in all_keys:
        ref_val = flat_json1.get(key)
        curr_val = flat_json2.get(key)

        # Compare values. Since flatten_json breaks down nested structures,
        # ref_val and curr_val should be primitive types or None.
        if ref_val == curr_val:
            continue # No change for this key

        has_changes = True
        change_entry = {
            "key": key,
            "reference_value": ref_val,
            "current_value": curr_val
        }

        if ref_val is None: # Key exists in json2 but not json1 (added)
            change_entry["status"] = "added"
        elif curr_val is None: # Key exists in json1 but not json2 (removed)
            change_entry["status"] = "removed"
        else: # Key exists in both, but values differ (changed)
            change_entry["status"] = "changed"
        
        detailed_changes.append(change_entry)

    return {"has_changes": has_changes, "detailed_changes": detailed_changes}


# 3. Modified _summarize_flat_results function
def _summarize_flat_results(
    flat_comparison_output: dict,
    was_list_transformed: bool = False,
    top_level_item_ids: Optional[List[str]] = None,
    processed_baseline_data: Optional[Dict[str, Any]] = None, # New parameter
    processed_current_data: Optional[Dict[str, Any]] = None # New parameter
) -> dict:
    """
    Processes the output from flat_compare_differences_enhanced to categorize and count changes,
    preparing them for display in a format consistent with the DeepDiff summary structure.

    Args:
        flat_comparison_output (dict): The output from flat_compare_differences_enhanced,
                                       e.g., {"has_changes": bool, "detailed_changes": list}.
        was_list_transformed (bool): True if the original input data was a list of dicts
                                     and was transformed into a dict keyed by group_by_key_name
                                     before flattening. This affects how flattened keys are parsed.
        top_level_item_ids (Optional[List[str]]): A list of the actual item IDs that were used
                                                  as top-level keys when transforming a list
                                                  of dicts. Used for robust item_id extraction.
        processed_baseline_data (Optional[Dict[str, Any]]): The baseline data after potential
                                                             transformation (keyed by group_by).
        processed_current_data (Optional[Dict[str, Any]]): The current data after potential
                                                            transformation (keyed by group_by).

    Returns:
        dict: A structured dictionary containing:
            - 'relevant_changes': List of dictionaries for 'changed', 'added', 'removed' items.
            - 'other_changes': List of dictionaries for 'other' changes (will be empty for flat compare).
            - 'raw_deepdiff_output': Placeholder (empty dict).
            - 'summary_counts': Dictionary with counts for 'changed', 'added', 'removed', 'other' changes.
            - 'has_diffs': Boolean indicating if any differences were found.
    """
    detailed_changes = flat_comparison_output.get("detailed_changes", [])
    has_diffs = flat_comparison_output.get("has_changes", False)

    # Use a dictionary to group changes by item_id
    grouped_relevant_changes = OrderedDict() # Use OrderedDict to maintain insertion order for item_ids

    for change_item in detailed_changes:
        full_key = change_item["key"]
        status = change_item["status"]
        ref_val = change_item["reference_value"]
        curr_val = change_item["current_value"]

        item_id_for_grouping = None
        field_for_display = None

        if was_list_transformed and top_level_item_ids:
            # Find the correct item_id by checking for the longest prefix match
            best_match_id = None

            sorted_item_ids = sorted(top_level_item_ids, key=len, reverse=True)

            for item_id_val in sorted_item_ids:
                if full_key.startswith(item_id_val) and \
                   (len(full_key) == len(item_id_val) or full_key[len(item_id_val)] == '.'):
                    best_match_id = item_id_val
                    break

            if best_match_id:
                item_id_for_grouping = best_match_id
                # The field is whatever comes after the item_id and the separator
                if len(full_key) > len(best_match_id) + 1 and full_key[len(best_match_id)] == '.':
                    field_for_display = full_key[len(best_match_id) + 1:]
                elif len(full_key) == len(best_match_id):
                    field_for_display = None # The item_id itself is the changed "field" (e.g., if it's a primitive value)
                else:
                    logger.warning(f"Unexpected key format for transformed list: '{full_key}' with matched ID '{best_match_id}'. Falling back to full key as field.")
                    field_for_display = full_key
            else:
                logger.warning(f"Could not determine item_id for key '{full_key}' in transformed list comparison. Treating as global.")
                item_id_for_grouping = "Global Configuration"
                field_for_display = full_key

        else:
            item_id_for_grouping = "Global Configuration"
            field_for_display = full_key

        # Initialize the item_id entry if it doesn't exist
        if item_id_for_grouping not in grouped_relevant_changes:
            grouped_relevant_changes[item_id_for_grouping] = {
                "item_id": item_id_for_grouping,
                "changes": [],
                "status": status # Set initial status to the first encountered status for this item
            }
        else:
            # Update overall item status based on precedence: removed > added > changed
            current_item_overall_status = grouped_relevant_changes[item_id_for_grouping]["status"]
            if status == "removed":
                grouped_relevant_changes[item_id_for_grouping]["status"] = "removed"
            elif status == "added" and current_item_overall_status != "removed":
                grouped_relevant_changes[item_id_for_grouping]["status"] = "added"
            elif status == "changed" and current_item_overall_status not in ["removed", "added"]:
                grouped_relevant_changes[item_id_for_grouping]["status"] = "changed"

        # Add the specific field change to the item_id's changes list
        # This part will be modified after the loop for 'added'/'removed' full objects
        grouped_relevant_changes[item_id_for_grouping]["changes"].append({
            "field": field_for_display,
            "reference_value": ref_val,
            "current_value": curr_val
        })

    # --- Post-processing for full 'added'/'removed' objects when list was transformed ---
    if was_list_transformed:
        for item_id, item_details in grouped_relevant_changes.items():
            if item_details["status"] == "added":
                # Get the full added object from processed_current_data
                full_added_object = processed_current_data.get(item_id)
                if full_added_object is not None:
                    item_details["changes"] = [{
                        "field": None, # Indicates full item
                        "reference_value": "N/A",
                        "current_value": full_added_object
                    }]
                else:
                    logger.warning(f"Could not retrieve full added object for item_id: {item_id}")
            elif item_details["status"] == "removed":
                # Get the full removed object from processed_baseline_data
                full_removed_object = processed_baseline_data.get(item_id)
                if full_removed_object is not None:
                    item_details["changes"] = [{
                        "field": None, # Indicates full item
                        "reference_value": full_removed_object,
                        "current_value": "N/A"
                    }]
                else:
                    logger.warning(f"Could not retrieve full removed object for item_id: {item_id}")

    relevant_changes = list(grouped_relevant_changes.values())

    # Re-calculate summary counts based on the grouped items
    final_changed_count = 0
    final_added_count = 0
    final_removed_count = 0
    for item in relevant_changes:
        if item["status"] == "changed":
            final_changed_count += 1
        elif item["status"] == "added":
            final_added_count += 1
        elif item["status"] == "removed":
            final_removed_count += 1

    return {
        "relevant_changes": relevant_changes,
        "other_changes": [], # This list will be empty for flat comparison
        "raw_deepdiff_output": {}, # This will be an empty dict as it's not DeepDiff output
        "summary_counts": {
            "changed": final_changed_count,
            "added": final_added_count,
            "removed": final_removed_count,
            "other": 0, # This will be 0
        },
        "has_diffs": has_diffs # This should still reflect if *any* detailed change was found
    }

def _handle_deepdiff_comparison(
    baseline: Any,
    current_data: Any,
    group_by_key: Optional[str] = None
) -> dict:
   
    formatted = compare_differences(baseline, current_data, group_by_key_name=group_by_key)
    summary = _summarize_diff_results(formatted.get("res", []), formatted.get("dif", {}))
    return summary


def _transform_list_to_dict_by_key(
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


def _handle_flat_comparison(
    baseline: Any,
    current_data: Any,
    group_by_key: Optional[str],
    entity_name: str
) -> dict:
    """
    Perform flat comparison with optional list-to-dict transformation.
    """
    was_transformed = False
    top_level_ids = set()

    processed_baseline = baseline
    processed_current = current_data

    # Transform lists to dicts keyed by group_by_key if applicable
    if group_by_key:
        if isinstance(baseline, list) and all(isinstance(i, dict) for i in baseline):
            processed_baseline = _transform_list_to_dict_by_key(baseline, group_by_key, f"{entity_name} baseline")
            top_level_ids.update(str(k) for k in processed_baseline.keys())
            was_transformed = True

        if isinstance(current_data, list) and all(isinstance(i, dict) for i in current_data):
            processed_current = _transform_list_to_dict_by_key(current_data, group_by_key, f"{entity_name} current")
            top_level_ids.update(str(k) for k in processed_current.keys())
            was_transformed = True

    flat_output = flat_compare_differences_enhanced(processed_baseline, processed_current)

    summary = _summarize_flat_results(
        flat_output,
        was_list_transformed=was_transformed,
        top_level_item_ids=list(top_level_ids),
        processed_baseline_data=processed_baseline if was_transformed else None,
        processed_current_data=processed_current if was_transformed else None,
    )
    return summary


# Registry of comparison methods for easy extensibility
_COMPARISON_METHODS = {
    "deepdiff": _handle_deepdiff_comparison,
    "flat": _handle_flat_comparison,
    # Future methods can be added here
}