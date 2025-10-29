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
def make_headers() -> Tuple[Dict[str, str], Tuple[str, Optional[Tuple[str,str]]]]:
    headers = {"Content-Type": "application/json"}
    login = st.secrets.get("DATAFORSEO_LOGIN")
    password = st.secrets.get("DATAFORSEO_PASSWORD")
    api_key = st.secrets.get("DATAFORSEO_API_KEY") or st.secrets.get("dataforseo-api-key")
    if login and password:
        return headers, ("basic", (login, password))
    elif api_key:
        token = base64.b64encode(api_key.encode()).decode() if ":" in api_key else api_key
        headers["Authorization"] = f"Basic {token}"
        return headers, ("header", None)
    else:
        st.stop()

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
mode = st.radio("Mode", ["Live (immediate)", "Standard (batched)"], horizontal=True)

colA, colB = st.columns([1,1])
with colA:
    domain = st.text_input("Target domain", placeholder="example.com (no https)")
with colB:
    device = st.radio("Device", ["desktop", "mobile"], horizontal=True)
    os_name = st.selectbox("OS", ["windows","macos"] if device=="desktop" else ["android","ios"])

headers, auth = make_headers()
sess = make_session(*auth)

# Fetch all locations to build country list
all_loc_df = get_locations(sess, headers, None)
lang_df = get_languages(sess, headers)

# Build searchable country list
if not all_loc_df.empty:
    countries = all_loc_df[all_loc_df["location_type"] == "Country"].copy()
    countries = countries.sort_values("location_name").drop_duplicates(subset=["country_iso_code"])
    country_options = [f"{row.location_name} [{row.country_iso_code}]" for row in countries.itertuples()]
    # Find default (United Kingdom)
    default_idx = next((i for i, opt in enumerate(country_options) if "[GB]" in opt.upper()), 0)
    country_selection = st.selectbox("Country", country_options, index=default_idx)
    # Extract ISO code from selection
    country_iso = country_selection.split("[")[-1].split("]")[0] if "[" in country_selection else "gb"
else:
    country_iso = st.text_input("Country ISO", value="gb")

# Fetch locations for selected country
loc_df = get_locations(sess, headers, country_iso or None)
lang_options = [f"{r.language_name} [{r.language_code}]" for r in lang_df.itertuples()] or ["English [en]"]
language = st.selectbox("Language", lang_options, index=(lang_options.index("English [en]") if "English [en]" in lang_options else 0))

# Single search+select for Location (optional override)
def fmt_opt(row): return f'{row.location_name} [{row.location_code}] — {row.location_type} / {row.country_iso_code}'
opts = [fmt_opt(r) for r in loc_df.itertuples()]
loc_pick = st.selectbox("Location (optional; overrides country)", [""] + opts)

depth = st.slider("Depth", 10, 200, 100, 10)
include_sub = st.checkbox("Include subdomains", True)
organic_only = st.checkbox("Organic only", True)  # kept for future logic parity

# Performance controls
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

keywords = st.text_area("Keywords (one per line)", height=200)

if "stop_evt" not in st.session_state:
    st.session_state.stop_evt = threading.Event()

c1, c2 = st.columns([1,1])
run = c1.button("Run")
stop = c2.button("Stop", type="secondary")

if stop:
    st.session_state.stop_evt.set()
    st.info("Stop requested.")

if run:
    st.session_state.stop_evt.clear()
    if not domain or " " in domain:
        st.error("Enter a valid target domain (no spaces, no protocol)."); st.stop()
    kws = [k.strip() for k in keywords.splitlines() if k.strip()]
    if not kws:
        st.error("Paste at least one keyword."); st.stop()

    # Resolve location
    def parse_code(s: str) -> Optional[int]:
        if "[" in s and "]" in s:
            try: return int(s.split("[")[-1].split("]")[0])
            except: return None
        return None
    loc_code = parse_code(loc_pick)
    if not loc_code:
        loc_code = pick_country_code(loc_df, country_iso) if country_iso else None
    if not loc_code:
        st.error("No location resolved. Provide Country ISO or pick a Location."); st.stop()

    lang_code = language.split("[")[-1].split("]")[0] if "[" in language else "en"

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

    df = pd.DataFrame(rows)
    cols = ["keyword","found","organic_rank","absolute_rank","type","url","title",
            "language_code","se_domain","location_name","device","os","depth","note"]
    df = df.reindex(columns=cols)
    st.dataframe(df, use_container_width=True)
    st.download_button("Download CSV", df.to_csv(index=False).encode("utf-8"), "dataforseo_ranks.csv", "text/csv")