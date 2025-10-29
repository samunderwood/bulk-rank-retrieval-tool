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
    
    if not items:
        record["note"] = f"No organic results found"
        return record
    
    # If target_domain is specified, filter by domain (for Standard mode)
    if target_domain:
        from urllib.parse import urlparse
        
        # Normalize target domain (remove protocol, www, trailing slash, path)
        target_clean = target_domain.lower().replace('www.', '').replace('http://', '').replace('https://', '').strip('/').split('/')[0]
        
        matching_items = []
        for item in items:
            url = item.get("url", "")
            if url:
                try:
                    parsed = urlparse(url if url.startswith('http') else f'http://{url}')
                    item_domain = parsed.netloc.lower().replace('www.', '')
                    
                    # Check if domain matches (exact match or item_domain is subdomain of target)
                    # Examples:
                    # - soundtrap.com == soundtrap.com ✓
                    # - app.soundtrap.com contains .soundtrap.com ✓
                    # - soundtrap.com.otherdomain.com contains .soundtrap.com but wrong ✗
                    if item_domain == target_clean or item_domain.endswith('.' + target_clean):
                        matching_items.append(item)
                except:
                    continue
        
        if not matching_items:
            record["note"] = f"Not found in top {depth}"
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
        
        # Format target parameter according to DataForSEO docs:
        # - "example.com" = exact home page match only
        # - "example.com*" = domain and all its pages
        # - "*example.com*" = domain, all pages, and all subdomains
        if include_subdomains:
            target_param = f"*{domain}*"  # Match domain, pages, and subdomains
        else:
            target_param = f"{domain}*"   # Match domain and all its pages
        
        payload = [{
            "keyword": keyword,
            "language_code": language_code,
            "location_code": int(location_code),
            "target": target_param,
            "device": device,
            "depth": int(depth),
            "os": os_name or ("windows" if device == "desktop" else "android"),
        }]
        
        try:
            response = client.post_live(payload)
            task = response.get("tasks", [{}])[0]
            
            if task.get("status_code") != 20000:
                return {
                    "keyword": keyword,
                    "found": False,
                    "note": f"Not found in top {payload[0]['depth']}"
                }
            
            result_list = task.get("result", [])
            if not result_list:
                return {"keyword": keyword, "found": False, "note": "No result array"}
            
            return parse_serp_record(
                result_list[0], keyword, language_code, device,
                payload[0]["os"], depth, target_domain=None  # Live mode: target already filtered by API
            )
            
        except Exception as e:
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
        batch_num = (idx // tasks_per_batch) + (1 if idx % tasks_per_batch else 0)
        total_batches = (len(keywords) + tasks_per_batch - 1) // tasks_per_batch
        post_bar.progress(min(1.0, idx / len(keywords)), text=f"Batch {batch_num}/{total_batches}: {idx}/{len(keywords)} tasks")
        time.sleep(0.3)
    
    # Note: In DataForSEO, 1 keyword = 1 task. Multiple tasks go in 1 API request (batch).
    # We can send up to 100 tasks per API request.
    total_batches = (len(keywords) + tasks_per_batch - 1) // tasks_per_batch
    if total_batches == 1:
        post_bar.progress(1.0, text=f"✅ Submitted {len(task_ids)} tasks in 1 batch")
    else:
        post_bar.progress(1.0, text=f"✅ Submitted {len(task_ids)} tasks in {total_batches} batches")
    
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
            status_code = task.get("status_code")
            
            # Status codes:
            # 20000 = OK (success)
            # 5701 = Task In Queue (still processing - should continue polling)
            # Other = actual error
            if status_code == 5701:
                # Task still processing, return None to indicate "not ready yet"
                return None
            elif status_code != 20000:
                return {
                    "keyword": None,
                    "found": False,
                    "note": f"API error: {task.get('status_message')}"
                }
            
            result_list = task.get("result", [])
            if not result_list:
                return {"keyword": None, "found": False, "note": f"No result returned"}
            
            result = result_list[0]
            keyword = result.get("keyword") or (result.get("keyword_info") or {}).get("keyword")
            
            return parse_serp_record(result, keyword, language_code, device, os_name, depth, target_domain=domain)
            
        except Exception as e:
            return {"keyword": None, "found": False, "note": f"Fetch error: {e}"}
    
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
        completed_task_ids = []
        
        with ThreadPoolExecutor(max_workers=fetch_parallel) as executor:
            futures = {executor.submit(fetch_one, tid): tid for tid in take}
            for future in as_completed(futures):
                task_id = futures[future]
                result = future.result()
                
                if result is not None:  # None means "not ready yet" (status 5701)
                    results.append(result)
                    completed_task_ids.append(task_id)
                    done += 1
                    pbar.progress(min(1.0, done / max(1, total)), text=f"Fetched {done}/{total}")
                # If None, task stays in pending and will be retried next poll
        
        # Only remove tasks that actually completed
        pending -= set(completed_task_ids)
    
    # Handle stopped tasks
    if stop_event and stop_event.is_set():
        for _ in pending:
            results.append({"keyword": None, "found": False, "note": "Stopped before fetch"})
    
    pbar.progress(1.0, text=f"Fetched {done}/{total}")
    return results

