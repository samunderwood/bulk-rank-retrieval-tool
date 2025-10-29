import time, json, base64, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Tuple, List

import streamlit as st
import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

API_BASE = "https://api.dataforseo.com/v3"
st.set_page_config(page_title="DataForSEO Rank Tool", layout="wide")

# -------- Auth --------
def make_headers() -> Optional[Tuple[Dict[str, str], Tuple[str, Optional[Tuple[str,str]]]]]:
    headers = {"Content-Type": "application/json"}
    try:
        login = st.secrets.get("DATAFORSEO_LOGIN")
        password = st.secrets.get("DATAFORSEO_PASSWORD")
        api_key = st.secrets.get("DATAFORSEO_API_KEY") or st.secrets.get("dataforseo-api-key")
        if login and password:
            return headers, ("basic", (login, password))
        elif api_key:
            token = base64.b64encode(api_key.encode()).decode() if ":" in api_key else api_key
            headers["Authorization"] = f"Basic {token}"
            return headers, ("header", None)
    except:
        pass
    return None

def make_session(auth_mode, creds):
    s = requests.Session()
    if auth_mode == "basic":
        s.auth = HTTPBasicAuth(*creds)
    return s

# -------- API helpers --------
def get_languages(sess, headers) -> pd.DataFrame:
    r = sess.get(f"{API_BASE}/serp/google/languages", headers=headers, timeout=60)
    r.raise_for_status()
    tasks = r.json().get("tasks", [])
    df = pd.DataFrame(tasks[0].get("result", [])) if tasks else pd.DataFrame()
    cols = ["language_name","language_code"]
    return df[cols].drop_duplicates().sort_values("language_name").reset_index(drop=True) if not df.empty else pd.DataFrame(columns=cols)

def get_locations(sess, headers, iso: Optional[str]=None) -> pd.DataFrame:
    path = "serp/google/locations" + (f"/{iso.lower()}" if iso else "")
    r = sess.get(f"{API_BASE}/{path}", headers=headers, timeout=120)
    r.raise_for_status()
    tasks = r.json().get("tasks", [])
    df = pd.DataFrame(tasks[0].get("result", [])) if tasks else pd.DataFrame()
    cols = ["location_name","location_code","country_iso_code","location_type"]
    return df[cols].sort_values(["country_iso_code","location_type","location_name"]).reset_index(drop=True) if not df.empty else pd.DataFrame(columns=cols)

def pick_country_code(df: pd.DataFrame, iso: str) -> Optional[int]:
    if df.empty: return None
    iso = iso.upper()
    hit = df[(df["country_iso_code"].str.upper()==iso) & (df["location_type"]=="Country")]
    return int(hit.iloc[0]["location_code"]) if not hit.empty else None

@st.cache_data(ttl=3600)
def get_all_countries(_sess, _headers) -> pd.DataFrame:
    """Get all available countries from DataForSEO"""
    try:
        r = _sess.get(f"{API_BASE}/serp/google/locations", headers=_headers, timeout=120)
        r.raise_for_status()
        tasks = r.json().get("tasks", [])
        df = pd.DataFrame(tasks[0].get("result", [])) if tasks else pd.DataFrame()
        if not df.empty:
            countries = df[df["location_type"] == "Country"].copy()
            countries = countries[["location_name", "location_code", "country_iso_code"]].drop_duplicates()
            countries = countries.sort_values("location_name").reset_index(drop=True)
            return countries
    except Exception as e:
        st.error(f"Failed to fetch countries: {e}")
    return pd.DataFrame(columns=["location_name", "location_code", "country_iso_code"])

def parse_record(res, kw, lang, device, os_name, depth):
    record = {
        "keyword": kw, "found": False,
        "organic_rank": None, "absolute_rank": None, "type": None,
        "url": None, "title": None,
        "se_domain": res.get("se_domain"),
        "location_name": res.get("location_name"),
        "language_code": lang, "device": device, "os": os_name, "depth": depth,
        "note": None
    }
    items = [i for i in (res.get("items") or []) if i.get("type")=="organic"]
    if not items:
        record["note"] = f"Target not found within depth={depth}"
        return record
    best = sorted(items, key=lambda i: (i.get("rank_group") or 10**9, i.get("rank_absolute") or 10**9))[0]
    record.update({
        "found": True,
        "organic_rank": best.get("rank_group"),
        "absolute_rank": best.get("rank_absolute"),
        "type": best.get("type"),
        "url": best.get("url"),
        "title": best.get("title"),
    })
    return record

# -------- Workers --------
def post_live(sess, headers, payload): 
    return sess.post(f"{API_BASE}/serp/google/organic/live/advanced", headers=headers, data=json.dumps(payload), timeout=120)

def live_worker(kw, domain, loc_code, lang, device, os_name, depth, headers, auth, include_sub, stop_evt):
    if stop_evt.is_set(): return {"keyword": kw, "found": False, "note": "Stopped"}
    sess = make_session(*auth)
    payload = [{
        "keyword": kw, "language_code": lang, "location_code": int(loc_code),
        "target": domain, "include_subdomains": bool(include_sub),
        "device": device, "depth": int(depth),
        "os": os_name or ("windows" if device=="desktop" else "android"),
    }]
    try:
        resp = post_live(sess, headers, payload); resp.raise_for_status()
        data = resp.json(); t = data.get("tasks", [{}])[0]
        if t.get("status_code") != 20000:
            return {"keyword": kw, "found": False, "note": f"API error: {t.get('status_message')}"}
        res_list = t.get("result", [])
        if not res_list: return {"keyword": kw, "found": False, "note": "No result array"}
        return parse_record(res_list[0], kw, lang, device, payload[0]["os"], depth)
    except requests.HTTPError as e:
        return {"keyword": kw, "found": False, "note": f"HTTP {e.response.status_code}"}
    except Exception as e:
        return {"keyword": kw, "found": False, "note": f"Error: {e}"}

def std_post_tasks(sess, headers, tasks_payload):
    return sess.post(f"{API_BASE}/serp/google/organic/task_post", headers=headers, data=json.dumps(tasks_payload), timeout=120)

def std_tasks_ready(sess, headers):
    r = sess.get(f"{API_BASE}/serp/google/organic/tasks_ready", headers=headers, timeout=60)
    r.raise_for_status(); return r.json()

def std_task_get(sess, headers, tid):
    r = sess.get(f"{API_BASE}/serp/google/organic/task_get/advanced/{tid}", headers=headers, timeout=120)
    r.raise_for_status(); return r.json()

def std_post_batched(keywords: List[str], batch_size: int, domain: str, loc_code: int,
                     lang: str, device: str, os_name: str, depth: int, include_sub: bool,
                     headers, auth, stop_evt) -> List[str]:
    sess = make_session(*auth); ids=[]
    for i in range(0, len(keywords), batch_size):
        if stop_evt.is_set(): break
        chunk = keywords[i:i+batch_size]
        payload = [{
            "keyword": kw, "language_code": lang, "location_code": int(loc_code),
            "target": domain, "include_subdomains": bool(include_sub),
            "device": device, "depth": int(depth),
            "os": os_name or ("windows" if device=="desktop" else "android"),
        } for kw in chunk]
        data = std_post_tasks(sess, headers, payload).json()
        for t in data.get("tasks", []):
            if t.get("status_code")==20100 and t.get("result"):
                ids.append(t["result"][0]["id"])
        time.sleep(0.2)
    return ids

def std_fetch(task_ids: List[str], headers, auth, poll_s: float, fetch_parallel: int, lang, device, os_name, depth, stop_evt):
    results = []
    posted = set(task_ids)
    poll_sess = make_session(*auth)
    pbar = st.progress(0.0, text="Fetching results…")
    total = len(task_ids); done = 0

    def fetch_one(tid):
        s = make_session(*auth)
        try:
            data = std_task_get(s, headers, tid)
            t = data.get("tasks", [{}])[0]
            if t.get("status_code") != 20000:
                return {"keyword": None, "found": False, "note": f"GET error {tid}: {t.get('status_message')}"}
            res_list = t.get("result", [])
            if not res_list:
                return {"keyword": None, "found": False, "note": f"No result {tid}"}
            res = res_list[0]
            kw = res.get("keyword") or (res.get("keyword_info") or {}).get("keyword")
            return parse_record(res, kw, lang, device, os_name, depth)
        except Exception as e:
            return {"keyword": None, "found": False, "note": f"Fetch error {tid}: {e}"}

    while posted and not stop_evt.is_set():
        try:
            ready = std_tasks_ready(poll_sess, headers)
            ready_ids = {rr["id"] for t in ready.get("tasks", []) for rr in t.get("result", []) if rr.get("id") in posted}
        except Exception:
            ready_ids = set(list(posted)[:min(len(posted), fetch_parallel*2)])

        if not ready_ids:
            time.sleep(max(0.5, poll_s)); continue

        take = list(ready_ids)[:fetch_parallel]
        with ThreadPoolExecutor(max_workers=fetch_parallel) as ex:
            for fut in as_completed([ex.submit(fetch_one, tid) for tid in take]):
                results.append(fut.result())
                done += 1
                pbar.progress(min(1.0, done/max(1,total)), text=f"Fetched {done}/{total}")
        posted -= set(take)

    if stop_evt.is_set():
        for _ in posted:
            results.append({"keyword": None, "found": False, "note": "Stopped before fetch"})
    pbar.progress(1.0, text=f"Fetched {done}/{total}")
    return results

# -------- UI --------
st.title("DataForSEO Rank Retrieval")

# Info banner
st.info("👈 **Enter your DataForSEO credentials in the sidebar to get started.** Your credentials are only used for this session and are never stored.")

# Check if admin credentials exist in secrets (for private deployment)
admin_auth = make_headers()

# Credentials input section
st.sidebar.header("🔐 DataForSEO Credentials")
st.sidebar.info("Don't have an account? [Sign up here](https://dataforseo.com/)")

# Check if admin credentials exist in secrets
if admin_auth:
    use_admin = st.sidebar.checkbox("Use configured credentials", value=False, 
                                     help="Use credentials from Streamlit secrets (for private deployments)")
    if use_admin:
        headers, auth = admin_auth
        st.sidebar.success("✅ Using configured credentials")
    else:
        user_login = st.sidebar.text_input("Login", type="default", placeholder="your_login")
        user_password = st.sidebar.text_input("Password", type="password", placeholder="your_password")
        
        if user_login and user_password:
            headers = {"Content-Type": "application/json"}
            auth = ("basic", (user_login, user_password))
        else:
            st.warning("⚠️ Please enter your DataForSEO login and password in the sidebar to continue.")
            st.stop()
else:
    # No admin credentials - user must provide their own
    user_login = st.sidebar.text_input("Login", type="default", placeholder="your_login")
    user_password = st.sidebar.text_input("Password", type="password", placeholder="your_password")
    
    if user_login and user_password:
        headers = {"Content-Type": "application/json"}
        auth = ("basic", (user_login, user_password))
    else:
        st.warning("⚠️ Please enter your DataForSEO login and password in the sidebar to continue.")
        st.stop()

sess = make_session(*auth)

# Test credentials with a simple API call
try:
    with st.spinner("Verifying credentials..."):
        test_response = sess.get(f"{API_BASE}/serp/google/languages", headers=headers, timeout=10)
        if test_response.status_code == 401:
            st.error("❌ **Invalid credentials**. Please check your DataForSEO login/password or API key.")
            st.stop()
        elif test_response.status_code != 200:
            st.error(f"❌ **API Error**: {test_response.status_code} - {test_response.text}")
            st.stop()
except requests.exceptions.RequestException as e:
    st.error(f"❌ **Connection Error**: Unable to connect to DataForSEO API. {str(e)}")
    st.stop()

# Initialize session state for caching
if "countries_df" not in st.session_state:
    with st.spinner("Loading countries..."):
        st.session_state.countries_df = get_all_countries(sess, headers)

if "lang_df" not in st.session_state:
    with st.spinner("Loading languages..."):
        st.session_state.lang_df = get_languages(sess, headers)

countries_df = st.session_state.countries_df
lang_df = st.session_state.lang_df

# Mode selection
mode = st.radio("Mode", ["Live (immediate)", "Standard (batched)"], horizontal=True)

# Main inputs
st.subheader("Target Configuration")
colA, colB = st.columns([1,1])

with colA:
    domain = st.text_input("Target domain", placeholder="example.com (no https)", help="Enter domain without https://")
    
    # Country selection with searchable dropdown
    if not countries_df.empty:
        country_options = [f"{row.location_name} ({row.country_iso_code}) [{row.location_code}]" 
                          for row in countries_df.itertuples()]
        # Default to United Kingdom
        default_idx = 0
        for idx, row in enumerate(countries_df.itertuples()):
            if row.country_iso_code.upper() == "GB":
                default_idx = idx
                break
        
        country_selection = st.selectbox(
            "Country", 
            country_options,
            index=default_idx,
            help="Select the country for search rankings"
        )
    else:
        st.error("Unable to load countries from DataForSEO API")
        st.stop()

with colB:
    device = st.radio("Device", ["desktop", "mobile"], horizontal=True)
    os_name = st.selectbox("OS", ["windows","macos"] if device=="desktop" else ["android","ios"])

# Language selection
lang_options = [f"{r.language_name} [{r.language_code}]" for r in lang_df.itertuples()] or ["English [en]"]
language = st.selectbox("Language", lang_options, 
                        index=(lang_options.index("English [en]") if "English [en]" in lang_options else 0))

# Optional: More specific location override
with st.expander("🔍 Advanced: Override with specific location (city/region)"):
    st.info("By default, we use country-level location. Expand to select a specific city or region.")
    
    # Extract selected country ISO
    selected_country_iso = country_selection.split("(")[1].split(")")[0] if "(" in country_selection else "GB"
    
    if st.checkbox("Use specific location instead of country"):
        with st.spinner(f"Loading locations for {selected_country_iso}..."):
            loc_df = get_locations(sess, headers, selected_country_iso.lower())
        
        if not loc_df.empty:
            def fmt_opt(row): 
                return f'{row.location_name} [{row.location_code}] — {row.location_type}'
            opts = [fmt_opt(r) for r in loc_df.itertuples() if r.location_type != "Country"]
            if opts:
                specific_location = st.selectbox("Specific Location", opts)
            else:
                st.warning("No specific locations available for this country")
                specific_location = None
        else:
            specific_location = None
    else:
        specific_location = None

# Search parameters
st.subheader("Search Parameters")
col1, col2 = st.columns([1,1])
with col1:
    depth = st.slider("Depth", 10, 200, 100, 10, help="Number of search results to check")
with col2:
    include_sub = st.checkbox("Include subdomains", True, help="Check all subdomains of target domain")

# Performance controls
with st.expander("⚙️ Performance Settings"):
    if mode.startswith("Live"):
        colL1, colL2, colL3 = st.columns([1,1,1])
        with colL1: parallel = st.slider("Live: parallel", 1, 24, 8, 1)
        with colL2: rpm = st.slider("Live: RPM", 30, 1200, 240, 30)
        with colL3: launch_delay = st.slider("Live: launch delay (s)", 0.0, 0.5, 0.0, 0.05)
    else:
        colS1, colS2, colS3, colS4 = st.columns([1,1,1,1])
        with colS1: tasks_per = st.slider("Std: tasks per POST", 10, 1000, 100, 10)
        with colS2: max_inflight = st.slider("Std: max in-flight", 100, 5000, 500, 100)
        with colS3: poll_iv = st.slider("Std: poll interval (s)", 0.2, 5.0, 1.0, 0.2)
        with colS4: fetch_parallel = st.slider("Std: fetch parallel", 2, 48, 12, 2)

# Keywords input
st.subheader("Keywords")
keywords = st.text_area("Enter keywords (one per line)", height=200, 
                        placeholder="Enter your keywords here, one per line\nExample:\nseo tools\nkeyword research\nrank tracker")

if "stop_evt" not in st.session_state:
    st.session_state.stop_evt = threading.Event()

st.divider()
c1, c2 = st.columns([1,1])
run = c1.button("🚀 Run Rank Retrieval", type="primary", use_container_width=True)
stop = c2.button("⏹️ Stop", type="secondary", use_container_width=True)

if stop:
    st.session_state.stop_evt.set()
    st.info("Stop requested.")

if run:
    st.session_state.stop_evt.clear()
    
    # Validation
    if not domain or " " in domain:
        st.error("⚠️ Enter a valid target domain (no spaces, no protocol)."); st.stop()
    kws = [k.strip() for k in keywords.splitlines() if k.strip()]
    if not kws:
        st.error("⚠️ Please enter at least one keyword."); st.stop()

    # Resolve location code
    def parse_code(s: str) -> Optional[int]:
        if "[" in s and "]" in s:
            try: return int(s.split("[")[-1].split("]")[0])
            except: return None
        return None
    
    # Check if using specific location override
    if 'specific_location' in locals() and specific_location:
        loc_code = parse_code(specific_location)
    else:
        # Use country-level location from country selection
        loc_code = parse_code(country_selection)
    
    if not loc_code:
        st.error("❌ Could not resolve location code. Please try selecting a different country."); st.stop()

    lang_code = language.split("[")[-1].split("]")[0] if "[" in language else "en"
    
    # Display execution summary
    st.info(f"""
    **Execution Summary:**
    - 🎯 Target: `{domain}`
    - 🌍 Location Code: `{loc_code}`
    - 🗣️ Language: `{lang_code}`
    - 📱 Device: `{device}` ({os_name})
    - 🔍 Depth: `{depth}`
    - 📊 Keywords: `{len(kws)}`
    - ⚡ Mode: `{mode}`
    """)

    if mode.startswith("Live"):
        spacing = 60.0 / max(1, rpm)
        rows = []
        bar = st.progress(0.0, text="Submitting…")
        with ThreadPoolExecutor(max_workers=parallel) as ex:
            futs = []
            last = 0.0
            for kw in kws:
                if st.session_state.stop_evt.is_set(): break
                now = time.time(); wait = max(0.0, (last + spacing) - now)
                if wait: time.sleep(wait)
                futs.append(ex.submit(live_worker, kw, domain, loc_code, lang_code, device, os_name, depth, headers, auth, include_sub, st.session_state.stop_evt))
                last = time.time()
                if launch_delay: time.sleep(launch_delay)
            for i, fu in enumerate(as_completed(futs), 1):
                if st.session_state.stop_evt.is_set(): break
                rows.append(fu.result())
                bar.progress(i/len(futs), text=f"{i}/{len(futs)} done")
        if st.session_state.stop_evt.is_set():
            done = {r.get("keyword") for r in rows if r.get("keyword")}
            for kw in kws:
                if kw not in done:
                    rows.append({"keyword": kw, "found": False, "note": "Stopped before start"})
    else:
        # Standard queue
        posted = []
        # Post in waves, respecting max_inflight
        idx = 0
        while idx < len(kws) and not st.session_state.stop_evt.is_set():
            capacity = max_inflight - len(posted)
            if capacity <= 0: break
            size = min(tasks_per, len(kws)-idx, capacity)
            ids = std_post_batched(kws[idx:idx+size], tasks_per, domain, loc_code, lang_code, device, os_name, depth, include_sub, headers, auth, st.session_state.stop_evt)
            posted.extend(ids); idx += size
            time.sleep(0.2)
        while idx < len(kws) and not st.session_state.stop_evt.is_set():
            time.sleep(0.8)
            capacity = max_inflight - len(posted)
            if capacity <= 0: continue
            size = min(tasks_per, len(kws)-idx, capacity)
            ids = std_post_batched(kws[idx:idx+size], tasks_per, domain, loc_code, lang_code, device, os_name, depth, include_sub, headers, auth, st.session_state.stop_evt)
            posted.extend(ids); idx += size
        rows = std_fetch(posted, headers, auth, poll_iv, fetch_parallel, lang_code, device, os_name, depth, st.session_state.stop_evt)

    # Display results
    df = pd.DataFrame(rows)
    cols = ["keyword","found","organic_rank","absolute_rank","type","url","title",
            "language_code","se_domain","location_name","device","os","depth","note"]
    df = df.reindex(columns=cols)
    
    st.divider()
    st.subheader("📊 Results")
    
    # Summary metrics
    found_count = df["found"].sum()
    total_count = len(df)
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Keywords", total_count)
    col2.metric("Found", found_count)
    col3.metric("Not Found", total_count - found_count)
    
    # Display table
    st.dataframe(df, use_container_width=True, height=400)
    
    # Download button
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="📥 Download Results as CSV",
        data=csv,
        file_name=f"dataforseo_ranks_{domain}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv",
        use_container_width=True
    )
    
    # Show sample of found results
    if found_count > 0:
        with st.expander("🎯 Found Rankings Preview"):
            found_df = df[df["found"] == True][["keyword", "organic_rank", "absolute_rank", "url", "title"]].head(10)
            st.dataframe(found_df, use_container_width=True)