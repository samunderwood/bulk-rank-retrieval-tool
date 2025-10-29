"""
Rank Retrieval Logic
Handles the core rank checking functionality for both Live and Standard modes
"""
import time
import pandas as pd
import streamlit as st
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict
from dataforseo_client import SERPClient


def parse_serp_record(result: dict, keyword: str, lang: str, device: str, 
                     os_name: str, depth: int, target_domain: str = None) -> dict:
    """
    Parse a SERP result and extract rank information.
    
    Args:
        result: SERP result from DataForSEO
        keyword: Search keyword
        lang: Language code
        device: Device type
        os_name: Operating system
        depth: Search depth
    
    Returns:
        Dictionary with parsed rank data
    """
    record = {
        "keyword": keyword,
        "found": False,
        "organic_rank": None,
        "absolute_rank": None,
        "type": None,
        "url": None,
        "title": None,
        "se_domain": result.get("se_domain"),
        "location_name": result.get("location_name"),
        "language_code": lang,
        "device": device,
        "os": os_name,
        "depth": depth,
        "note": None
    }
    
    # Filter for organic results only
    all_items = result.get("items") or []
    items = [i for i in all_items if i.get("type") == "organic"]
    
    st.write(f"🔍 **DEBUG parse_serp_record:**")
    st.write(f"   - Total items: {len(all_items)}")
    st.write(f"   - Item types: {set(i.get('type') for i in all_items) if all_items else 'None'}")
    st.write(f"   - Organic items: {len(items)}")
    st.write(f"   - target_domain param: {target_domain}")
    
    if not items:
        record["note"] = f"No organic results found"
        st.warning(f"   ⚠️ No organic items to process")
        return record
    
    # If target_domain is specified, filter by domain (for Standard mode)
    if target_domain:
        from urllib.parse import urlparse
        
        # Normalize target domain
        target_clean = target_domain.lower().replace('www.', '').replace('http://', '').replace('https://', '').strip('/')
        
        matching_items = []
        for item in items:
            url = item.get("url", "")
            if url:
                try:
                    parsed = urlparse(url if url.startswith('http') else f'http://{url}')
                    item_domain = parsed.netloc.lower().replace('www.', '')
                    
                    # Check if domain matches (exact or subdomain)
                    if item_domain == target_clean or item_domain.endswith('.' + target_clean):
                        matching_items.append(item)
                except:
                    continue
        
        if not matching_items:
            record["note"] = f"Domain not found in top {depth} results"
            return record
        
        items = matching_items
    
    # Get the best (lowest) rank from matching items
    best = sorted(
        items, 
        key=lambda i: (i.get("rank_group") or 10**9, i.get("rank_absolute") or 10**9)
    )[0]
    
    record.update({
        "found": True,
        "organic_rank": best.get("rank_group"),
        "absolute_rank": best.get("rank_absolute"),
        "type": best.get("type"),
        "url": best.get("url"),
        "title": best.get("title"),
    })
    
    return record


def live_mode_rank_check(
    client: SERPClient,
    keywords: List[str],
    domain: str,
    location_code: int,
    language_code: str,
    device: str,
    os_name: str,
    depth: int,
    include_subdomains: bool,
    parallel: int = 10,
    rpm: int = 600,
    stop_event = None
) -> List[Dict]:
    """
    Execute rank checking in Live mode (immediate results).
    
    Args:
        client: SERPClient instance
        keywords: List of keywords to check
        domain: Target domain
        location_code: DataForSEO location code
        language_code: Language code
        device: Device type (desktop/mobile)
        os_name: Operating system
        depth: Search depth
        include_subdomains: Include subdomains flag
        parallel: Number of parallel workers
        rpm: Requests per minute limit
        stop_event: Threading event for stopping
    
    Returns:
        List of result dictionaries
    """
    spacing = 60.0 / max(1, rpm)
    rows = []
    bar = st.progress(0.0, text="Submitting…")
    
    def live_worker(keyword: str):
        """Worker function for single live request."""
        if stop_event and stop_event.is_set():
            return {"keyword": keyword, "found": False, "note": "Stopped"}
        
        payload = [{
            "keyword": keyword,
            "language_code": language_code,
            "location_code": int(location_code),
            "target": domain,
            "include_subdomains": bool(include_subdomains),
            "device": device,
            "depth": int(depth),
            "os": os_name or ("windows" if device == "desktop" else "android"),
        }]
        
        try:
            response = client.post_live(payload)
            
            # DEBUG: Show full response structure
            st.write(f"🔍 **DEBUG Live Mode - '{keyword}':**")
            st.write(f"   - Response status: {response.get('status_code')} - {response.get('status_message')}")
            st.write(f"   - Tasks count: {len(response.get('tasks', []))}")
            
            task = response.get("tasks", [{}])[0]
            st.write(f"   - Task status: {task.get('status_code')} - {task.get('status_message')}")
            st.write(f"   - Task result_count: {task.get('result_count')}")
            
            if task.get("status_code") != 20000:
                return {
                    "keyword": keyword,
                    "found": False,
                    "note": f"API error: {task.get('status_message')}"
                }
            
            result_list = task.get("result", [])
            st.write(f"   - Result array length: {len(result_list)}")
            
            if not result_list:
                st.error(f"   ❌ No result array returned")
                return {"keyword": keyword, "found": False, "note": "No result array"}
            
            result_obj = result_list[0]
            st.write(f"   - Result object keys: {list(result_obj.keys())}")
            st.write(f"   - Result keyword: {result_obj.get('keyword')}")
            st.write(f"   - Result type: {result_obj.get('type')}")
            st.write(f"   - Result se_results_count: {result_obj.get('se_results_count')}")
            st.write(f"   - Result items_count: {result_obj.get('items_count')}")
            st.write(f"   - Result items length: {len(result_obj.get('items', []))}")
            
            items = result_obj.get('items', [])
            if items:
                st.write(f"   - Item types found: {set(i.get('type') for i in items)}")
                organic_items = [i for i in items if i.get('type') == 'organic']
                st.write(f"   - Organic items count: {len(organic_items)}")
                
                if organic_items:
                    st.write(f"   - First 3 organic URLs:")
                    for idx, item in enumerate(organic_items[:3], 1):
                        st.write(f"      {idx}. Rank {item.get('rank_absolute')}: {item.get('url')}")
            else:
                st.error(f"   ❌ No items in result object")
            
            return parse_serp_record(
                result_list[0], keyword, language_code, device,
                payload[0]["os"], depth, target_domain=None  # Live mode: target already filtered by API
            )
            
        except Exception as e:
            import traceback
            st.error(f"❌ Exception in live_worker for '{keyword}': {e}")
            st.code(traceback.format_exc())
            return {"keyword": keyword, "found": False, "note": f"Error: {e}"}
    
    # Execute with rate limiting
    with ThreadPoolExecutor(max_workers=parallel) as executor:
        futures = []
        last = 0.0
        
        for kw in keywords:
            if stop_event and stop_event.is_set():
                break
            
            # Rate limiting
            now = time.time()
            wait = max(0.0, (last + spacing) - now)
            if wait:
                time.sleep(wait)
            
            futures.append(executor.submit(live_worker, kw))
            last = time.time()
        
        # Collect results
        for i, future in enumerate(as_completed(futures), 1):
            if stop_event and stop_event.is_set():
                break
            rows.append(future.result())
            bar.progress(i / len(futures), text=f"{i}/{len(futures)} done")
    
    # Handle stopped keywords
    if stop_event and stop_event.is_set():
        done_keywords = {r.get("keyword") for r in rows if r.get("keyword")}
        for kw in keywords:
            if kw not in done_keywords:
                rows.append({"keyword": kw, "found": False, "note": "Stopped before start"})
    
    return rows


def standard_mode_rank_check(
    client: SERPClient,
    keywords: List[str],
    domain: str,
    location_code: int,
    language_code: str,
    device: str,
    os_name: str,
    depth: int,
    include_subdomains: bool,
    tasks_per_batch: int = 100,
    fetch_parallel: int = 12,
    poll_interval: float = 2.0,
    stop_event = None
) -> List[Dict]:
    """
    Execute rank checking in Standard mode (post tasks, then fetch results).
    
    Args:
        client: SERPClient instance
        keywords: List of keywords to check
        domain: Target domain
        location_code: DataForSEO location code
        language_code: Language code
        device: Device type (desktop/mobile)
        os_name: Operating system
        depth: Search depth
        include_subdomains: Include subdomains flag
        tasks_per_batch: Tasks per batch POST
        fetch_parallel: Parallel fetch workers
        poll_interval: Polling interval in seconds
        stop_event: Threading event for stopping
    
    Returns:
        List of result dictionaries
    """
    # Phase 1: Post all tasks
    st.write("**Phase 1:** Posting tasks to DataForSEO...")
    post_bar = st.progress(0.0, text="Submitting batches...")
    
    task_ids = []
    idx = 0
    
    while idx < len(keywords) and not (stop_event and stop_event.is_set()):
        size = min(tasks_per_batch, len(keywords) - idx)
        chunk = keywords[idx:idx + size]
        
        # Build payload
        # Note: Standard mode does NOT use 'target' parameter
        # Per DataForSEO docs: target only works in Live mode
        # We get all results and filter client-side in parse_serp_record()
        payload = [{
            "keyword": kw,
            "language_code": language_code,
            "location_code": int(location_code),
            "device": device,
            "depth": int(depth),
            "os": os_name or ("windows" if device == "desktop" else "android"),
        } for kw in chunk]
        
        try:
            response = client.post_tasks(payload)
            
            for task in response.get("tasks", []):
                status_code = task.get("status_code")
                # 20100 = successfully created task
                if status_code == 20100:
                    # According to DataForSEO docs, for task_post the ID is directly in the task object
                    # https://docs.dataforseo.com/v3/serp-google-type-task_post/
                    task_id = task.get("id")
                    if task_id:
                        task_ids.append(task_id)
                    else:
                        st.warning(f"⚠️ Task succeeded but no ID found in task object")
                elif status_code != 20100:
                    # Log non-success status codes for debugging
                    st.warning(f"Task failed with status {status_code}: {task.get('status_message', 'Unknown error')}")
        except Exception as e:
            st.error(f"Error posting batch: {e}")
            import traceback
            st.code(traceback.format_exc())
        
        idx += size
        post_bar.progress(min(1.0, idx / len(keywords)), text=f"Posted {idx}/{len(keywords)} keywords")
        time.sleep(0.3)
    
    post_bar.progress(1.0, text=f"✅ Posted {len(task_ids)} tasks successfully")
    
    if not task_ids:
        st.error("No tasks were successfully posted.")
        return []
    
    # Phase 2: Fetch results
    st.write(f"**Phase 2:** Waiting for results (this may take 1-3 minutes)...")
    return fetch_task_results(
        client, task_ids, domain, language_code, device, os_name, depth,
        fetch_parallel, poll_interval, stop_event
    )


def fetch_task_results(
    client: SERPClient,
    task_ids: List[str],
    domain: str,
    language_code: str,
    device: str,
    os_name: str,
    depth: int,
    fetch_parallel: int,
    poll_interval: float,
    stop_event
) -> List[Dict]:
    """
    Fetch results for posted tasks.
    
    Args:
        client: SERPClient instance
        task_ids: List of task IDs to fetch
        language_code: Language code
        device: Device type
        os_name: Operating system
        depth: Search depth
        fetch_parallel: Number of parallel fetches
        poll_interval: Seconds between polls
        stop_event: Threading event for stopping
    
    Returns:
        List of result dictionaries
    """
    results = []
    pending = set(task_ids)
    pbar = st.progress(0.0, text="Fetching results…")
    total = len(task_ids)
    done = 0
    
    def fetch_one(task_id: str):
        """Fetch single task result."""
        try:
            response = client.get_task_result(task_id)
            task = response.get("tasks", [{}])[0]
            
            if task.get("status_code") != 20000:
                return {
                    "keyword": None,
                    "found": False,
                    "note": f"GET error {task_id}: {task.get('status_message')}"
                }
            
            result_list = task.get("result", [])
            if not result_list:
                return {"keyword": None, "found": False, "note": f"No result {task_id}"}
            
            result = result_list[0]
            keyword = result.get("keyword") or (result.get("keyword_info") or {}).get("keyword")
            
            return parse_serp_record(result, keyword, language_code, device, os_name, depth, target_domain=domain)
            
        except Exception as e:
            return {"keyword": None, "found": False, "note": f"Fetch error {task_id}: {e}"}
    
    # Poll and fetch ready tasks
    while pending and not (stop_event and stop_event.is_set()):
        try:
            # Check which tasks are ready
            ready_response = client.get_tasks_ready()
            ready_ids = {
                rr["id"]
                for t in ready_response.get("tasks", [])
                for rr in t.get("result", [])
                if rr.get("id") in pending
            }
        except Exception:
            # If tasks_ready fails, try fetching some anyway
            ready_ids = set(list(pending)[:min(len(pending), fetch_parallel * 2)])
        
        if not ready_ids:
            time.sleep(max(0.5, poll_interval))
            continue
        
        # Fetch ready tasks in parallel
        take = list(ready_ids)[:fetch_parallel]
        with ThreadPoolExecutor(max_workers=fetch_parallel) as executor:
            for future in as_completed([executor.submit(fetch_one, tid) for tid in take]):
                results.append(future.result())
                done += 1
                pbar.progress(min(1.0, done / max(1, total)), text=f"Fetched {done}/{total}")
        
        pending -= set(take)
    
    # Handle stopped tasks
    if stop_event and stop_event.is_set():
        for _ in pending:
            results.append({"keyword": None, "found": False, "note": "Stopped before fetch"})
    
    pbar.progress(1.0, text=f"Fetched {done}/{total}")
    return results

