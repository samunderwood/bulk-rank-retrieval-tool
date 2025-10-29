"""
DataForSEO Rank Retrieval Tool
Main Streamlit application using modular architecture
"""
import threading
import streamlit as st
import pandas as pd

from dataforseo_client import SERPClient
from ui_components import (
    setup_page_config,
    render_credentials_sidebar,
    verify_credentials,
    render_location_selector,
    render_language_selector,
    render_results_table
)
from rank_retrieval import (
    live_mode_rank_check,
    standard_mode_rank_check
)

# Configure page
setup_page_config(title="DataForSEO Rank Tool", layout="wide")

# -------- UI --------
st.title("DataForSEO Rank Retrieval")

# Get authenticated client
client = render_credentials_sidebar(client_class=SERPClient)

# Verify credentials
if client:
    verify_credentials(client)
else:
    st.stop()

# Mode selection
mode = st.radio("Mode", ["Live (immediate)", "Standard (batched)"], horizontal=True)

# Main configuration
st.subheader("Target Configuration")
colA, colB = st.columns([1, 1])

with colA:
    domain = st.text_input(
        "Target domain",
        placeholder="example.com (no https)",
        help="Enter domain without https://"
    )
    
    # Location selector
    location_code, country_iso = render_location_selector(
        client, serp_type="google", default_country="GB"
    )

with colB:
    device = st.radio("Device", ["desktop", "mobile"], horizontal=True)
    # OS is set automatically: windows for desktop, android for mobile
    # (Users rarely need to change this, and it clutters the UI)
    os_name = "windows" if device == "desktop" else "android"

# Language selector
language_code = render_language_selector(
    client, serp_type="google", default_language="en"
)

# Search parameters
st.subheader("Search Parameters")
col1, col2 = st.columns([1, 1])

with col1:
    depth = st.slider(
        "Depth", 10, 200, 100, 10,
        help="Number of search results to check"
    )

with col2:
    include_sub = st.checkbox(
        "Include subdomains", True,
        help="Check all subdomains of target domain"
    )

# Performance parameters (hidden from user, optimized defaults)
if mode.startswith("Live"):
    parallel = 10
    rpm = 600
    launch_delay = 0.0
else:
    tasks_per = 100
    max_inflight = 1000
    poll_iv = 2.0
    fetch_parallel = 12

# Keywords input
st.subheader("Keywords")
keywords = st.text_area(
    "Enter keywords (one per line)",
    height=200,
    placeholder="Enter your keywords here, one per line\nExample:\nseo tools\nkeyword research\nrank tracker"
)

# Initialize stop event
if "stop_evt" not in st.session_state:
    st.session_state.stop_evt = threading.Event()

# Run buttons
st.divider()
c1, c2 = st.columns([1, 1])
run = c1.button("🚀 Run Rank Retrieval", type="primary", use_container_width=True)
stop = c2.button("⏹️ Stop", type="secondary", use_container_width=True)

if stop:
    st.session_state.stop_evt.set()
    st.info("Stop requested.")

if run:
    st.session_state.stop_evt.clear()
    
    # Validation
    if not domain or " " in domain:
        st.error("⚠️ Enter a valid target domain (no spaces, no protocol).")
        st.stop()
    
    kws = [k.strip() for k in keywords.splitlines() if k.strip()]
    if not kws:
        st.error("⚠️ Please enter at least one keyword.")
        st.stop()
    
    if not location_code:
        st.error("❌ Could not resolve location code. Please try selecting a different country.")
        st.stop()
    
    # Display execution summary
    st.info(f"""
    **Execution Summary:**
    - 🎯 Target: `{domain}`
    - 🌍 Location Code: `{location_code}`
    - 🗣️ Language: `{language_code}`
    - 📱 Device: `{device}` ({os_name})
    - 🔍 Depth: `{depth}`
    - 📊 Keywords: `{len(kws)}`
    - ⚡ Mode: `{mode}`
    """)
    
    # Execute rank checking
    try:
        if mode.startswith("Live"):
            rows = live_mode_rank_check(
                client=client,
                keywords=kws,
                domain=domain,
                location_code=location_code,
                language_code=language_code,
                device=device,
                os_name=os_name,
                depth=depth,
                include_subdomains=include_sub,
                parallel=parallel,
                rpm=rpm,
                stop_event=st.session_state.stop_evt
            )
        else:
            rows = standard_mode_rank_check(
                client=client,
                keywords=kws,
                domain=domain,
                location_code=location_code,
                language_code=language_code,
                device=device,
                os_name=os_name,
                depth=depth,
                include_subdomains=include_sub,
                tasks_per_batch=tasks_per,
                fetch_parallel=fetch_parallel,
                poll_interval=poll_iv,
                stop_event=st.session_state.stop_evt
            )
        
        # Prepare results dataframe
        df = pd.DataFrame(rows)
        cols = [
            "keyword", "found", "organic_rank", "absolute_rank", "type",
            "url", "title", "language_code", "se_domain", "location_name",
            "device", "os", "depth", "note"
        ]
        df = df.reindex(columns=cols)
        
        # Render results
        render_results_table(df, domain=domain)
        
    except Exception as e:
        st.error(f"❌ **Error during execution**: {str(e)}")
        import traceback
        with st.expander("Show error details"):
            st.code(traceback.format_exc())

