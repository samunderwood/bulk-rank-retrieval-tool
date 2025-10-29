"""
DataForSEO API Client
Reusable client for interacting with DataForSEO APIs
"""
import base64
import time
from typing import Optional, Dict, Tuple, List
import requests
from requests.auth import HTTPBasicAuth


class DataForSEOClient:
    """
    Base client for DataForSEO API interactions.
    Handles authentication, rate limiting, and common API operations.
    """
    
    API_BASE = "https://api.dataforseo.com/v3"
    
    def __init__(self, login: str = None, password: str = None, api_key: str = None):
        """
        Initialize DataForSEO client with credentials.
        
        Args:
            login: DataForSEO login (username)
            password: DataForSEO password
            api_key: Alternative to login/password, format: "login:password" or base64 encoded
        """
        self.session = requests.Session()
        self.headers = {"Content-Type": "application/json"}
        
        if login and password:
            self.session.auth = HTTPBasicAuth(login, password)
            self.auth_method = "basic"
        elif api_key:
            token = base64.b64encode(api_key.encode()).decode() if ":" in api_key else api_key
            self.headers["Authorization"] = f"Basic {token}"
            self.auth_method = "api_key"
        else:
            raise ValueError("Must provide either login/password or api_key")
    
    def _request(self, method: str, endpoint: str, data: dict = None, 
                 timeout: int = 120, retries: int = 3) -> requests.Response:
        """
        Make an API request with retry logic.
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request payload (for POST)
            timeout: Request timeout in seconds
            retries: Number of retry attempts for 50000 errors
        
        Returns:
            Response object
        """
        url = f"{self.API_BASE}/{endpoint}"
        
        for attempt in range(retries):
            try:
                if method.upper() == "GET":
                    response = self.session.get(url, headers=self.headers, timeout=timeout)
                elif method.upper() == "POST":
                    response = self.session.post(
                        url, headers=self.headers, 
                        json=data, timeout=timeout
                    )
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                response.raise_for_status()
                
                # Check for DataForSEO-specific errors
                json_data = response.json()
                tasks = json_data.get("tasks", [])
                
                if tasks:
                    for task in tasks:
                        status_code = task.get("status_code")
                        # 50000 = internal error, retry
                        if status_code == 50000 and attempt < retries - 1:
                            time.sleep(1)
                            break
                    else:
                        return response
                else:
                    return response
                    
            except requests.RequestException as e:
                if attempt < retries - 1:
                    time.sleep(1)
                    continue
                raise
        
        return response
    
    def get_languages(self, serp_type: str = "google") -> List[Dict]:
        """Get available languages for a SERP type."""
        endpoint = f"serp/{serp_type}/languages"
        response = self._request("GET", endpoint)
        tasks = response.json().get("tasks", [])
        return tasks[0].get("result", []) if tasks else []
    
    def get_locations(self, serp_type: str = "google", country_iso: str = None) -> List[Dict]:
        """Get available locations for a SERP type."""
        endpoint = f"serp/{serp_type}/locations"
        if country_iso:
            endpoint += f"/{country_iso.lower()}"
        response = self._request("GET", endpoint)
        tasks = response.json().get("tasks", [])
        return tasks[0].get("result", []) if tasks else []
    
    def test_connection(self) -> Tuple[bool, str]:
        """
        Test API credentials and connection.
        
        Returns:
            Tuple of (success: bool, message: str)
        """
        try:
            response = self._request("GET", "serp/google/languages", timeout=10, retries=1)
            if response.status_code == 200:
                return True, "Connection successful"
            elif response.status_code == 401:
                return False, "Invalid credentials"
            else:
                return False, f"API Error: {response.status_code}"
        except requests.RequestException as e:
            return False, f"Connection error: {str(e)}"


class SERPClient(DataForSEOClient):
    """
    Client for SERP API operations (rank tracking, organic results, etc.)
    """
    
    def __init__(self, login: str = None, password: str = None, api_key: str = None, 
                 serp_type: str = "google"):
        """
        Initialize SERP client.
        
        Args:
            login: DataForSEO login
            password: DataForSEO password
            api_key: Alternative API key
            serp_type: SERP type (google, bing, yahoo, etc.)
        """
        super().__init__(login, password, api_key)
        self.serp_type = serp_type
    
    def post_live(self, tasks: List[Dict]) -> Dict:
        """
        Post live SERP requests (immediate results).
        
        Args:
            tasks: List of task dictionaries
        
        Returns:
            API response as dictionary
        """
        endpoint = f"serp/{self.serp_type}/organic/live/advanced"
        response = self._request("POST", endpoint, data=tasks)
        return response.json()
    
    def post_tasks(self, tasks: List[Dict]) -> Dict:
        """
        Post standard SERP tasks (queued, retrieve later).
        
        Args:
            tasks: List of task dictionaries
        
        Returns:
            API response with task IDs
        """
        endpoint = f"serp/{self.serp_type}/organic/task_post"
        response = self._request("POST", endpoint, data=tasks)
        return response.json()
    
    def get_tasks_ready(self) -> Dict:
        """Get list of completed tasks ready for retrieval."""
        endpoint = f"serp/{self.serp_type}/organic/tasks_ready"
        response = self._request("GET", endpoint, timeout=60)
        return response.json()
    
    def get_task_result(self, task_id: str) -> Dict:
        """
        Get results for a specific task.
        
        Args:
            task_id: Task ID from post_tasks
        
        Returns:
            Task results
        """
        endpoint = f"serp/{self.serp_type}/organic/task_get/advanced/{task_id}"
        response = self._request("GET", endpoint)
        return response.json()


class BacklinksClient(DataForSEOClient):
    """
    Client for Backlinks API.
    Future expansion placeholder.
    """
    
    def __init__(self, login: str = None, password: str = None, api_key: str = None):
        super().__init__(login, password, api_key)
    
    # Add backlinks methods here as needed


class OnPageClient(DataForSEOClient):
    """
    Client for OnPage API (technical SEO, site audits).
    Future expansion placeholder.
    """
    
    def __init__(self, login: str = None, password: str = None, api_key: str = None):
        super().__init__(login, password, api_key)
    
    # Add on-page methods here as needed


class KeywordsDataClient(DataForSEOClient):
    """
    Client for Keywords Data API (search volume, clickstream data, keyword suggestions).
    
    Reference: https://docs.dataforseo.com/v3/keywords_data/overview/
    """
    
    def __init__(self, login: str = None, password: str = None, api_key: str = None):
        super().__init__(login, password, api_key)
    
    def get_locations_and_languages(self):
        """
        Get available locations and languages for clickstream data.
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/clickstream_data/locations_and_languages/
        
        Returns:
            dict: Response with available locations and languages
        """
        response = self._request(
            "GET",
            "keywords_data/clickstream_data/locations_and_languages"
        )
        return response.json()
    
    def bulk_search_volume(self, keywords: list, location_code: int, tag: str = None):
        """
        Get clickstream-based search volume for up to 1000 keywords.
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/clickstream_data/bulk_search_volume/live/
        
        Args:
            keywords: List of keywords (up to 1000, min 3 chars each)
            location_code: Location code from locations_and_languages endpoint
            tag: Optional task identifier
        
        Returns:
            dict: Response with search volume data and 12-month history
        """
        payload = [{
            "keywords": keywords,
            "location_code": location_code
        }]
        
        if tag:
            payload[0]["tag"] = tag
        
        response = self._request(
            "POST",
            "keywords_data/clickstream_data/bulk_search_volume/live",
            data=payload
        )
        return response.json()
    
    # Google Trends Methods
    
    def get_trends_locations(self, country: str = None):
        """
        Get available locations for Google Trends.
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/google_trends/locations/
        
        Args:
            country: Optional country ISO code to filter locations (e.g., 'us')
        
        Returns:
            dict: Response with available locations
        """
        endpoint = "keywords_data/google_trends/locations"
        if country:
            endpoint += f"/{country.lower()}"
        
        response = self._request("GET", endpoint)
        return response.json()
    
    def get_trends_languages(self):
        """
        Get available languages for Google Trends.
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/google_trends/languages/
        
        Returns:
            dict: Response with available languages
        """
        response = self._request("GET", "keywords_data/google_trends/languages")
        return response.json()
    
    def trends_explore_live(self, keywords: list, location_name: str = None, location_code: int = None,
                           language_code: str = "en", type: str = "web", category_code: int = 0,
                           date_from: str = None, date_to: str = None, time_range: str = None,
                           item_types: list = None, tag: str = None):
        """
        Get Google Trends data (Live mode - immediate results).
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/google_trends/explore/live/
        
        Args:
            keywords: List of keywords (max 5, max 100 chars each)
            location_name: Full location name (e.g., "United States")
            location_code: Location code (e.g., 2840)
            language_code: Language code (default: "en")
            type: Trends type - web, news, youtube, images, froogle (default: "web")
            category_code: Category code (default: 0 for all categories)
            date_from: Start date "yyyy-mm-dd" format
            date_to: End date "yyyy-mm-dd" format
            time_range: Preset range (past_hour, past_day, past_7_days, past_30_days, etc.)
            item_types: Types to return (google_trends_graph, google_trends_map, etc.)
            tag: Optional task identifier
        
        Returns:
            dict: Response with trends data
        """
        payload = [{
            "keywords": keywords,
            "language_code": language_code,
            "type": type,
            "category_code": category_code
        }]
        
        if location_name:
            payload[0]["location_name"] = location_name
        if location_code:
            payload[0]["location_code"] = location_code
        if date_from:
            payload[0]["date_from"] = date_from
        if date_to:
            payload[0]["date_to"] = date_to
        if time_range:
            payload[0]["time_range"] = time_range
        if item_types:
            payload[0]["item_types"] = item_types
        if tag:
            payload[0]["tag"] = tag
        
        response = self._request(
            "POST",
            "keywords_data/google_trends/explore/live",
            data=payload
        )
        return response.json()
    
    def trends_explore_post(self, keywords: list, location_name: str = None, location_code: int = None,
                           language_code: str = "en", type: str = "web", category_code: int = 0,
                           date_from: str = None, date_to: str = None, time_range: str = None,
                           item_types: list = None, tag: str = None):
        """
        Post Google Trends task (Standard mode - retrieve later).
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/google_trends/explore/task_post/
        
        Args: Same as trends_explore_live()
        
        Returns:
            dict: Response with task ID
        """
        payload = [{
            "keywords": keywords,
            "language_code": language_code,
            "type": type,
            "category_code": category_code
        }]
        
        if location_name:
            payload[0]["location_name"] = location_name
        if location_code:
            payload[0]["location_code"] = location_code
        if date_from:
            payload[0]["date_from"] = date_from
        if date_to:
            payload[0]["date_to"] = date_to
        if time_range:
            payload[0]["time_range"] = time_range
        if item_types:
            payload[0]["item_types"] = item_types
        if tag:
            payload[0]["tag"] = tag
        
        response = self._request(
            "POST",
            "keywords_data/google_trends/explore/task_post",
            data=payload
        )
        return response.json()
    
    def trends_explore_tasks_ready(self):
        """
        Get list of completed Google Trends tasks.
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/google_trends/explore/tasks_ready/
        
        Returns:
            dict: Response with completed task IDs
        """
        response = self._request("GET", "keywords_data/google_trends/explore/tasks_ready")
        return response.json()
    
    def trends_explore_get_result(self, task_id: str):
        """
        Get results for a specific Google Trends task.
        
        Reference: https://docs.dataforseo.com/v3/keywords_data/google_trends/explore/task_get/
        
        Args:
            task_id: Task ID from task_post
        
        Returns:
            dict: Task results with trends data
        """
        response = self._request(
            "GET",
            f"keywords_data/google_trends/explore/task_get/{task_id}"
        )
        return response.json()

