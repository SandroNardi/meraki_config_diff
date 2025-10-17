import os
import meraki
from .my_logging import get_logger
from typing import Optional, Union, Any, List, Dict, Tuple,cast

logger = get_logger()


class MerakiAPIWrapper:
    """
    Wrapper class for Cisco Meraki Dashboard API with optional caching and logging.

    Attributes:
        _api_key (Optional[str]): API key for Meraki Dashboard.
        _organization_id (Optional[str]): Selected organization ID.
        _organization_name (Optional[str]): Selected organization name.
        _network_id (Optional[str]): Selected network ID.
        _network_name (Optional[str]): Selected network name.
        _enable_caching (bool): Flag to enable caching of API responses.
        _dashboard (Optional[meraki.DashboardAPI]): Meraki Dashboard API client instance.
        _organizations_cache (Optional[List[Dict[str, Any]]]): Cached organizations data.
        _networks_cache (Optional[Dict[str, List[Dict[str, Any]]]]): Cached networks data keyed by organization ID.
        _required_app_setup_param (Dict[str, bool]): Required application setup parameters.
    """

    def __init__(self, initial_api_key: Optional[str] = None, enable_caching: bool = False) -> None:
        """
        Initialize the MerakiAPIWrapper instance.

        Args:
            initial_api_key (Optional[str]): Initial API key to set.
            enable_caching (bool): Enable or disable caching of API responses.
        """
        self._api_key: Optional[str] = None
        self._organization_id: Optional[str] = None
        self._organization_name: Optional[str] = None
        self._network_id: Optional[str] = None
        self._network_name: Optional[str] = None
        self._enable_caching: bool = enable_caching
        self._dashboard: Optional[meraki.DashboardAPI] = None
        self._organizations_cache: Optional[List[Dict[str, Any]]] = None
        self._networks_cache: Optional[Dict[str, List[Dict[str, Any]]]] = None
        self._required_app_setup_param: Dict[str, bool] = {}
        self.set_api_key(initial_api_key, source="initialization")

    def _set_attr(self, attr_id: str, attr_name: str, id_value: Optional[str], name_value: Optional[str]) -> None:
        """
        Set ID and optional name attributes with logging.

        Args:
            attr_id (str): Attribute name for ID (e.g., '_organization_id').
            attr_name (str): Attribute name for name (e.g., '_organization_name').
            id_value (Optional[str]): Value to set for ID attribute.
            name_value (Optional[str]): Value to set for name attribute.
        """
        if id_value:
            setattr(self, attr_id, id_value)
            logger.info(f"{attr_id[1:].replace('_', ' ').title()} set to: {id_value}")
            if name_value:
                setattr(self, attr_name, name_value)
                logger.info(f"{attr_name[1:].replace('_', ' ').title()} set to: {name_value}")
            else:
                logger.debug(f"{attr_name[1:].replace('_', ' ').title()} not provided when setting id.")
        else:
            logger.warning(f"Attempted to set an empty or None {attr_id[1:].replace('_', ' ').title()}.")

    def _get_attr(self, attr: str) -> Optional[str]:
        """
        Get the value of an attribute.

        Args:
            attr (str): Attribute name.

        Returns:
            Optional[str]: Value of the attribute or None.
        """
        return getattr(self, attr)

    def _is_attr_set(self, attr: str) -> bool:
        """
        Check if an attribute is set (not None or empty string).

        Args:
            attr (str): Attribute name.

        Returns:
            bool: True if set, False otherwise.
        """
        val = getattr(self, attr)
        return val is not None and val != ""

    def set_api_key(self, api_key: Optional[str] = None, source: Optional[str] = None) -> None:
        """
        Set the API key from argument or environment variable and initialize Dashboard API client.

        Args:
            api_key (Optional[str]): API key to set.
            source (Optional[str]): Source description for logging.
        """
        if api_key:
            self._api_key = api_key
            logger.info(f"API key set from provided argument. Source: {source or 'direct_call'}")
        else:
            env_api_key = os.getenv("MK_CSM_KEY")
            if env_api_key:
                self._api_key = env_api_key
                logger.info("API key loaded from environment variable (MK_CSM_KEY).")
            else:
                self._api_key = None
                logger.error("Meraki API Key (MK_CSM_KEY) not found in environment variables or passed parameter.")
        if self._api_key:
            logger.debug("API_KEY updated. Initializing Meraki Dashboard API client.")
            self._dashboard = meraki.DashboardAPI(self._api_key, suppress_logging=True)
        else:
            logger.warning("API_KEY is currently not set. Dashboard API client not initialized.")
            self._dashboard = None

    def is_api_key_set(self) -> bool:
        """
        Check if API key is set.

        Returns:
            bool: True if API key is set, False otherwise.
        """
        return self._is_attr_set("_api_key")

    def get_headers(self) -> Dict[str, str]:
        """
        Get HTTP headers for API requests.

        Returns:
            Dict[str, str]: Headers including Authorization and content types.
        """
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def get_organization_id(self) -> Optional[str]:
        """
        Get the current organization ID.

        Returns:
            Optional[str]: Organization ID or None.
        """
        return self._get_attr("_organization_id")

    def set_organization_id(self, organization_id: str, organization_name: Optional[str] = None) -> None:
        """
        Set organization ID and optional name.

        Args:
            organization_id (str): Organization ID.
            organization_name (Optional[str]): Organization name.
        """
        self._set_attr("_organization_id", "_organization_name", organization_id, organization_name)

    def get_organization_name(self) -> Optional[str]:
        """
        Get the current organization name.

        Returns:
            Optional[str]: Organization name or None.
        """
        return self._get_attr("_organization_name")

    def is_organization_id_set(self) -> bool:
        """
        Check if organization ID is set.

        Returns:
            bool: True if set, False otherwise.
        """
        return self._is_attr_set("_organization_id")

    def get_network_id(self) -> Optional[str]:
        """
        Get the current network ID.

        Returns:
            Optional[str]: Network ID or None.
        """
        return self._get_attr("_network_id")

    def set_network_id(self, network_id: str, network_name: Optional[str] = None) -> None:
        """
        Set network ID and optional name.

        Args:
            network_id (str): Network ID.
            network_name (Optional[str]): Network name.
        """
        self._set_attr("_network_id", "_network_name", network_id, network_name)

    def get_network_name(self) -> Optional[str]:
        """
        Get the current network name.

        Returns:
            Optional[str]: Network name or None.
        """
        return self._get_attr("_network_name")

    def is_network_id_set(self) -> bool:
        """
        Check if network ID is set.

        Returns:
            bool: True if set, False otherwise.
        """
        return self._is_attr_set("_network_id")

    def get_dashboard(self) -> Optional[meraki.DashboardAPI]:
        """
        Get or initialize the Meraki Dashboard API client.

        Returns:
            Optional[meraki.DashboardAPI]: Dashboard API client instance or None if API key not set.
        """
        if self._dashboard is None:
            if not self._api_key:
                logger.error("Cannot initialize Meraki Dashboard API: API Key is not set.")
                return None
            logger.info("Initializing Meraki Dashboard API instance.")
            try:
                self._dashboard = meraki.DashboardAPI(self._api_key, suppress_logging=True)
                logger.debug("Meraki Dashboard API instance created successfully.")
            except Exception as e:
                logger.exception(f"Failed to initialize Meraki Dashboard API: {e}")
                raise
        else:
            logger.debug("Using existing Meraki Dashboard API instance.")
        return self._dashboard

    def _fetch_data(
        self,
        fetch_func,
        cache_attr: str,
        cache_key: Optional[str] = None,
        use_cache: bool = False,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Internal method to fetch data with optional caching and error handling.

        Args:
            fetch_func: Callable to fetch data from API.
            cache_attr (str): Attribute name for cache storage.
            cache_key (Optional[str]): Key for cache dictionary if applicable.
            use_cache (bool): Whether to use cached data if available.

        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any]]: Fetched data or error dictionary.
        """
        cache = getattr(self, cache_attr)
        if use_cache and self._enable_caching:
            if cache_key is None and cache is not None:
                logger.info(f"Using cached data from {cache_attr}.")
                return cache
            elif cache_key is not None and cache is not None and cache_key in cache:
                logger.info(f"Using cached data for key {cache_key} from {cache_attr}.")
                return cache[cache_key]
        dashboard = self.get_dashboard()
        if not dashboard:
            return {"error": "DashboardAPIError", "details": "Meraki Dashboard API not initialized."}
        try:
            data = fetch_func()
            if self._enable_caching:
                if cache_key is None:
                    setattr(self, cache_attr, data)
                else:
                    if getattr(self, cache_attr) is None:
                        setattr(self, cache_attr, {})
                    getattr(self, cache_attr)[cache_key] = data
                logger.info(f"Fetched and cached {len(data)} items for {cache_attr} {cache_key or ''}.")
            else:
                logger.info(f"Fetched {len(data)} items for {cache_attr} {cache_key or ''} (not cached).")
            return data
        except meraki.APIError as e:
            logger.error(f"Meraki API error fetching data: {e.status} - {e.message}")
            if self._enable_caching:
                if cache_key is None:
                    setattr(self, cache_attr, [])
                else:
                    if getattr(self, cache_attr) is None:
                        setattr(self, cache_attr, {})
                    getattr(self, cache_attr)[cache_key] = []
            return {"error": "MerakiAPIError", "details": e.message, "status_code": e.status}
        except Exception as e:
            logger.exception(f"Unexpected error fetching data: {e}")
            if self._enable_caching:
                if cache_key is None:
                    setattr(self, cache_attr, [])
                else:
                    if getattr(self, cache_attr) is None:
                        setattr(self, cache_attr, {})
                    getattr(self, cache_attr)[cache_key] = []
            return {"error": "UnexpectedError", "details": str(e)}



    def _get_organizations(self, use_cache: bool = False) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Retrieve organizations list with optional caching.

        Args:
            use_cache (bool): Use cached data if available.

        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any]]: Organizations data or error dictionary.
        """
        if self._dashboard is None:
            logger.error("Meraki Dashboard API client is not initialized.")
            return {"error": "DashboardAPIError", "details": "Meraki Dashboard API client is not initialized."}
        return self._fetch_data(
            lambda: cast(meraki.DashboardAPI, self._dashboard).organizations.getOrganizations(),
            "_organizations_cache",
            use_cache=use_cache,
        )

    def _get_networks(self, organization_id: Optional[str] = None, use_cache: bool = False) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Retrieve networks list for an organization with optional caching.

        Args:
            organization_id (Optional[str]): Organization ID to fetch networks for.
            use_cache (bool): Use cached data if available.

        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any]]: Networks data or error dictionary.
        """
        if self._dashboard is None:
            logger.error("Meraki Dashboard API client is not initialized.")
            return {"error": "DashboardAPIError", "details": "Meraki Dashboard API client is not initialized."}
        org_id = organization_id or self.get_organization_id()
        if not org_id:
            logger.warning("No organization id provided or set.")
            return {"error": "NoOrganizationSelected", "details": "Please select an organization first."}
        return self._fetch_data(
            lambda: cast(meraki.DashboardAPI, self._dashboard).organizations.getOrganizationNetworks(org_id),
            "_networks_cache",
            cache_key=org_id,
            use_cache=use_cache,
        )

    def list_organizations(self, use_cache: bool = False) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        List organizations with formatted output.

        Args:
            use_cache (bool): Use cached data if available.

        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any]]: List of organizations or error dictionary.
        """
        logger.info("Listing organizations.")
        raw_response = self._get_organizations(use_cache=use_cache)
        if isinstance(raw_response, dict) and "error" in raw_response:
            logger.error(f"Error listing organizations: {raw_response.get('details')}")
            return raw_response
        if isinstance(raw_response, list):
            if not raw_response:
                logger.info("No organizations found.")
                return []
            return [
                {
                    "id": org.get("id"),
                    "name": org.get("name"),
                    "url": org.get("url"),
                    "api enabled": org.get("api", {}).get("enabled", False),
                    "licensing model": org.get("licensing", {}).get("model"),
                }
                for org in raw_response
            ]
        logger.error(f"Unexpected response type from _get_organizations: {type(raw_response)}")
        return {"error": "UnexpectedReturnType", "details": "Internal function returned an unexpected type."}

    def list_networks(
        self,
        organization_id: Optional[str] = None,
        use_cache: bool = False,
        filter_tags: Optional[List[str]] = None,
        filter_product_type: Optional[List[str]] = None,
    ) -> Union[List[Dict[str, Any]], Dict[str, Any]]:
        """
        List networks for an organization with formatted output,
        supporting filtering by tags and product types.

        Args:
            organization_id (Optional[str]): Organization ID to list networks for.
            use_cache (bool): Use cached data if available.
            filter_tags (Optional[List[str]]): List of tags to filter networks by.
                                                A network must have at least one of these tags.
                                                If an empty list or None, no tag filtering is applied.
            filter_product_type (Optional[List[str]]): List of product types to filter networks by.
                                                        A network must support at least one of these product types.
                                                        If an empty list or None, no product type filtering is applied.

        Returns:
            Union[List[Dict[str, Any]], Dict[str, Any]]: List of networks or error dictionary.
        """
        org_id = organization_id or self.get_organization_id()
        if not org_id:
            return {"error": "ConfigurationError", "details": "Organization ID is not provided and cannot be determined."}

        logger.info(f"Listing networks for organization id: {org_id}")
        response = self._get_networks(organization_id=organization_id, use_cache=use_cache)

        if isinstance(response, dict) and "error" in response:
            logger.error(f"Error listing networks: {response.get('details')}")
            return response

        if isinstance(response, list):
            if not response:
                logger.info("No networks found for the selected organization.")
                return []

            filtered_networks = []
            for net in response:
                # Apply tag filtering
                tags_match = True
                # If filter_tags is None or an empty list, this 'if' condition is false,
                # and tags_match remains True, effectively not filtering by tags.
                if filter_tags:
                    network_tags = set(net.get("tags", []))
                    if not any(tag in network_tags for tag in filter_tags):
                        tags_match = False

                # Apply product type filtering
                product_type_match = True
                # If filter_product_type is None or an empty list, this 'if' condition is false,
                # and product_type_match remains True, effectively not filtering by product types.
                if filter_product_type:
                    network_product_types = set(net.get("productTypes", []))
                    if not any(ptype in network_product_types for ptype in filter_product_type):
                        product_type_match = False

                if tags_match and product_type_match:
                    filtered_networks.append(net)

            if not filtered_networks:
                logger.info("No networks found matching the specified filters.")
                return []

            return [
                {
                    "id": net.get("id"),
                    "name": net.get("name"),
                    "type": net.get("type"),
                    "time zone": net.get("timeZone"),
                    "tags": net.get("tags", []),  # Changed to return as a list
                    "productTypes": net.get("productTypes", []),  # Changed to return as a list
                }
                for net in filtered_networks
            ]
        logger.error(f"Unexpected response type from _get_networks: {type(response)}")
        return []

    def _check_required_parameter_order(self, required_params: Dict[str, bool]) -> bool:
        """
        Validate the logical order of required parameters.

        Args:
            required_params (Dict[str, bool]): Dictionary of required parameters.

        Returns:
            bool: True if order is valid, False otherwise.
        """
        api_key_req = required_params.get("api_key", False)
        org_id_req = required_params.get("organization_id", False)
        net_id_req = required_params.get("network_id", False)
        if org_id_req and not api_key_req:
            logger.error("'organization_id' cannot be required if 'api_key' is not.")
            return False
        if net_id_req and (not api_key_req or not org_id_req):
            logger.error("'network_id' cannot be required if 'api_key' or 'organization_id' is not.")
            return False
        return True

    def setup_application_parameters(
        self,
        required_app_setup_parm: Dict[str, bool],
        app_setup_param: Optional[Dict[str, str]] = None,
        enable_caching: Optional[bool] = None,
    ) -> bool:
        """
        Setup application parameters including API key, organization, and network IDs.

        Args:
            required_app_setup_parm (Dict[str, bool]): Required parameters with flags.
            app_setup_param (Optional[Dict[str, str]]): Parameter values to set.
            enable_caching (Optional[bool]): Enable or disable caching.

        Returns:
            bool: True if setup successful, False otherwise.
        """
        logger.info("Setting up application parameters.")
        if enable_caching is not None:
            self._enable_caching = enable_caching
        logger.info(f"Caching enabled: {self._enable_caching}")
        if not self._check_required_parameter_order(required_app_setup_parm):
            return False
        self._required_app_setup_param = required_app_setup_parm
        params = app_setup_param or {}

        if required_app_setup_parm.get("api_key"):
            self.set_api_key(params.get("api_key"), source="setup_application_parameters")
            if not self.is_api_key_set():
                logger.error("API Key is required but not set.")
                return False

        if required_app_setup_parm.get("organization_id"):
            if not self.is_api_key_set():
                logger.error("API Key must be set before setting Organization ID.")
                return False
            org_id = params.get("organization_id")
            org_name = params.get("org_name")
            if org_id:
                self.set_organization_id(org_id, org_name)
            else:
                logger.error("Organization ID is required but not provided.")
                return False
            if not self.is_organization_id_set():
                logger.error("Failed to set required Organization ID.")
                return False

        if required_app_setup_parm.get("network_id"):
            if not self.is_api_key_set() or not self.is_organization_id_set():
                logger.error("API Key and Organization ID must be set before setting Network ID.")
                return False
            net_id = params.get("network_id")
            net_name = params.get("net_name")
            if net_id:
                self.set_network_id(net_id, net_name)
            else:
                logger.error("Network ID is required but not provided.")
                return False
            if not self.is_network_id_set():
                logger.error("Failed to set required Network ID.")
                return False

        logger.info("Application parameters setup complete.")
        return True

    def check_current_parameters_status(self) -> Tuple[bool, List[str]]:
        """
        Check if all required parameters are set.

        Returns:
            Tuple[bool, List[str]]: (True, []) if all set; otherwise (False, list of missing).
        """
        if not self._required_app_setup_param:
            logger.warning("No required parameters defined. Call setup_application_parameters first.")
            return False, ["No required parameters defined"]
        if not self._check_required_parameter_order(self._required_app_setup_param):
            return False, ["Invalid required_app_setup_parm configuration stored in instance"]
        missing = []
        if self._required_app_setup_param.get("api_key") and not self.is_api_key_set():
            missing.append("API_KEY")
        if self._required_app_setup_param.get("organization_id") and not self.is_organization_id_set():
            missing.append("ORGANIZATION_ID")
        if self._required_app_setup_param.get("network_id") and not self.is_network_id_set():
            missing.append("NETWORK_ID")
        if missing:
            logger.error(f"Missing required parameters: {', '.join(missing)}")
            return False, missing
        logger.info("All required parameters are set.")
        return True, []

    def get_current_app_params(self) -> Dict[str, Dict[str, str]]:
        """
        Get current application parameters with masked API key for display.

        Returns:
            Dict[str, Dict[str, str]]: Dictionary of parameters with values and labels.
        """
        params: Dict[str, Dict[str, str]] = {}
        req = self._required_app_setup_param

        if req.get("api_key", False):
            api_key = self._api_key or ""
            masked = "*" * max(len(api_key) - 4, 0) + api_key[-4:] if api_key else "N/A"
            params["api_key"] = {"value": masked, "label": "API Key"}

        if req.get("organization_id", False):
            params["organization_id"] = {"value": self.get_organization_id() or "N/A", "label": "Organization ID"}
            params["organization_name"] = {"value": self.get_organization_name() or "N/A", "label": "Organization Name"}

        if req.get("network_id", False):
            params["network_id"] = {"value": self.get_network_id() or "N/A", "label": "Network ID"}
            params["network_name"] = {"value": self.get_network_name() or "N/A", "label": "Network Name"}

        return params