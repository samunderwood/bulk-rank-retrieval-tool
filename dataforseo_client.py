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
        
        Documentation:
        https://docs.dataforseo.com/v3/serp-google-organic-live-advanced/
        
        Response Structure:
        {
          "tasks": [{
            "status_code": 20000,  // Success
            "result": [{
              "keyword": "...",
              "items": [...]
            }]
          }]
        }
        
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
        
        Documentation:
        https://docs.dataforseo.com/v3/serp-google-organic-task_post/
        
        Response Structure:
        {
          "tasks": [{
            "id": "string",           // Task ID - directly in task object
            "status_code": 20100,     // 20100 = successfully created
            "result": null            // Result is NULL for task_post
          }]
        }
        
        Args:
            tasks: List of task dictionaries
        
        Returns:
            API response with task IDs
        """
        endpoint = f"serp/{self.serp_type}/organic/task_post"
        response = self._request("POST", endpoint, data=tasks)
        return response.json()
    
    def get_tasks_ready(self) -> Dict:
        """
        Get list of completed tasks ready for retrieval.
        
        Documentation:
        https://docs.dataforseo.com/v3/serp-google-organic-tasks-ready/
        
        Response Structure:
        {
          "tasks": [{
            "result": [{
              "id": "string",      // Task IDs that are ready
              "date_posted": "...",
              "endpoint_regular": "...",
              "endpoint_advanced": "...",
              "endpoint_html": "..."
            }]
          }]
        }
        """
        endpoint = f"serp/{self.serp_type}/organic/tasks_ready"
        response = self._request("GET", endpoint, timeout=60)
        return response.json()
    
    def get_task_result(self, task_id: str) -> Dict:
        """
        Get results for a specific task.
        
        Documentation:
        https://docs.dataforseo.com/v3/serp-google-organic-task-get-advanced/
        
        Response Structure:
        {
          "tasks": [{
            "status_code": 20000,  // 20000 = task completed successfully
            "result": [{
              "keyword": "...",
              "type": "organic",
              "se_domain": "google.com",
              "location_code": 2826,
              "language_code": "en",
              "items": [        // Array of SERP items
                {
                  "type": "organic",
                  "rank_group": 1,
                  "rank_absolute": 1,
                  "url": "...",
                  "title": "..."
                }
              ]
            }]
          }]
        }
        
        Args:
            task_id: Task ID from post_tasks
        
        Returns:
            Task results
        """
        endpoint = f"serp/{self.serp_type}/organic/task_get/advanced/{task_id}"
        response = self._request("GET", endpoint)
        return response.json()


class KeywordsDataClient(DataForSEOClient):
    """
    Client for Keywords Data API (search volume, suggestions, etc.)
    Future expansion placeholder.
    """
    
    def __init__(self, login: str = None, password: str = None, api_key: str = None):
        super().__init__(login, password, api_key)
    
    def get_search_volume(self, keywords: List[str], location_code: int, 
                          language_code: str) -> Dict:
        """Get search volume data for keywords."""
        endpoint = "keywords_data/google_ads/search_volume/live"
        tasks = [{
            "keywords": keywords,
            "location_code": location_code,
            "language_code": language_code
        }]
        response = self._request("POST", endpoint, data=tasks)
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

