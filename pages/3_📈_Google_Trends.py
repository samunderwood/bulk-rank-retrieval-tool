"""
Google Trends Tool
Get keyword popularity trends over time with related topics and queries.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import BytesIO
import time

from ui_components import setup_page_config, render_credentials_sidebar
from dataforseo_client import KeywordsDataClient

# Configure page
setup_page_config(title="Google Trends - DataForSEO Tools", layout="wide")

st.title("📈 Google Trends Tool")
st.markdown("Analyze keyword popularity trends, regional interest, and discover related topics and queries.")

# Initialize session state for results
if "gt_results" not in st.session_state:
    st.session_state.gt_results = None
if "gt_mode" not in st.session_state:
    st.session_state.gt_mode = None
if "gt_config" not in st.session_state:
    st.session_state.gt_config = {}

# Sidebar credentials
client = render_credentials_sidebar(KeywordsDataClient)

if not client:
    st.warning("👈 Please enter your DataForSEO credentials in the sidebar to get started.")
    st.info("""
        **Getting Started:**
        1. Enter your DataForSEO login and password in the sidebar
        2. Your credentials will automatically persist across all pages
        3. Start exploring Google Trends data!
        
        Don't have credentials? Get them at [DataForSEO API Access](https://app.dataforseo.com/api-access)
    """)
    st.stop()

# Get available locations (cached)
@st.cache_data(ttl=3600)
def get_locations(_login: str, _password: str):
    """Fetch available locations for Google Trends."""
    try:
        temp_client = KeywordsDataClient(login=_login, password=_password)
        response = temp_client.get_trends_locations()
        if response.get("status_code") == 20000:
            tasks = response.get("tasks", [])
            if tasks and tasks[0].get("result"):
                return tasks[0]["result"]
    except Exception as e:
        st.error(f"Error fetching locations: {e}")
    return []

# Get available languages (cached)
@st.cache_data(ttl=3600)
def get_languages(_login: str, _password: str):
    """Fetch available languages for Google Trends."""
    try:
        temp_client = KeywordsDataClient(login=_login, password=_password)
        response = temp_client.get_trends_languages()
        if response.get("status_code") == 20000:
            tasks = response.get("tasks", [])
            if tasks and tasks[0].get("result"):
                return tasks[0]["result"]
    except Exception as e:
        st.error(f"Error fetching languages: {e}")
    return []

# Main configuration
st.subheader("Configuration")

# Mode selection
mode = st.radio(
    "Mode",
    options=["Live", "Standard"],
    horizontal=True,
    help="Live: Immediate results (slower, limited to 250 tasks/min). Standard: Queued processing (faster for bulk, up to 2000 tasks/min)."
)

col1, col2 = st.columns([2, 1])

with col1:
    # Keywords input (max 5)
    keywords_input = st.text_area(
        "Keywords (one per line, max 5)",
        height=150,
        placeholder="seo api\nrank tracker\nkeyword research\n...",
        help="Enter up to 5 keywords to compare. For topics/queries lists, use only 1 keyword."
    )

with col2:
    # Trends type
    trends_type = st.selectbox(
        "Trends Type",
        options=["web", "news", "youtube", "images", "froogle"],
        help="Google Trends data source"
    )
    
    # Location selector
    locations = get_locations(st.session_state.user_login, st.session_state.user_password)
    
    if locations:
        # Filter to countries only for simplicity
        countries = [loc for loc in locations if loc.get("location_type") == "Country"]
        location_names = {f"{loc.get('location_name')} ({loc.get('location_code')})": loc.get('location_code') 
                         for loc in countries}
        
        selected_location = st.selectbox(
            "Location (optional)",
            options=["Global"] + list(location_names.keys()),
            help="Select a location or leave as Global for worldwide data"
        )
        
        location_code = None if selected_location == "Global" else location_names[selected_location]
        location_name = None if selected_location == "Global" else selected_location.split(" (")[0]
    else:
        st.error("Could not load locations. Please check your credentials.")
        st.stop()
    
    # Language selector
    languages = get_languages(st.session_state.user_login, st.session_state.user_password)
    
    if languages:
        lang_options = {f"{lang.get('language_name')} ({lang.get('language_code')})": lang.get('language_code')
                       for lang in languages}
        
        # Default to English
        default_idx = list(lang_options.values()).index("en") if "en" in lang_options.values() else 0
        
        selected_language = st.selectbox(
            "Language",
            options=list(lang_options.keys()),
            index=default_idx,
            help="Interface language for Google Trends"
        )
        
        language_code = lang_options[selected_language]
    else:
        language_code = "en"

# Advanced settings expander
with st.expander("⚙️ Advanced Settings"):
    col_a, col_b = st.columns(2)
    
    with col_a:
        # Date range
        use_date_range = st.checkbox("Use custom date range", value=False)
        
        if use_date_range:
            date_from = st.date_input(
                "From",
                value=datetime.now() - timedelta(days=365),
                max_value=datetime.now()
            )
            date_to = st.date_input(
                "To",
                value=datetime.now(),
                max_value=datetime.now()
            )
            time_range = None
        else:
            time_range = st.selectbox(
                "Time Range",
                options=[
                    "past_7_days", "past_30_days", "past_90_days", 
                    "past_12_months", "past_5_years", 
                    "2004_present" if trends_type == "web" else "2008_present"
                ],
                index=1
            )
            date_from = None
            date_to = None
    
    with col_b:
        # Item types
        st.write("Data to retrieve:")
        get_graph = st.checkbox("Interest over time (graph)", value=True)
        get_map = st.checkbox("Regional interest (map)", value=True)
        get_topics = st.checkbox("Related topics", value=False, help="Only works with 1 keyword")
        get_queries = st.checkbox("Related queries", value=False, help="Only works with 1 keyword")
        
        item_types = []
        if get_graph:
            item_types.append("google_trends_graph")
        if get_map:
            item_types.append("google_trends_map")
        if get_topics:
            item_types.append("google_trends_topics_list")
        if get_queries:
            item_types.append("google_trends_queries_list")

st.divider()

# Run button
run = st.button("▶️ Get Trends Data", type="primary", use_container_width=True)

if run:
    # Validation
    kws = [k.strip() for k in keywords_input.splitlines() if k.strip()]
    
    if not kws:
        st.error("⚠️ Please enter at least one keyword.")
        st.stop()
    
    if len(kws) > 5:
        st.error(f"⚠️ Maximum 5 keywords allowed. You entered {len(kws)}.")
        st.stop()
    
    # Check if requesting topics/queries with multiple keywords
    if (get_topics or get_queries) and len(kws) > 1:
        st.warning("⚠️ Related topics and queries only work with 1 keyword. Using first keyword only for these items.")
    
    # Display execution summary
    st.info(f"""
        **Execution Summary:**
        - Mode: {mode}
        - Keywords: {', '.join(kws)}
        - Type: {trends_type}
        - Location: {selected_location}
        - Time Range: {'Custom' if use_date_range else time_range}
    """)
    
    # Execute request
    try:
        if mode == "Live":
            # Live mode - immediate results
            with st.spinner("Fetching trends data... (this may take 5-10 seconds)"):
                response = client.trends_explore_live(
                    keywords=kws,
                    location_code=location_code,
                    location_name=location_name,
                    language_code=language_code,
                    type=trends_type,
                    date_from=date_from.strftime("%Y-%m-%d") if use_date_range and date_from else None,
                    date_to=date_to.strftime("%Y-%m-%d") if use_date_range and date_to else None,
                    time_range=time_range,
                    item_types=item_types if item_types else None
                )
            
            # Parse results
            if response.get("status_code") != 20000:
                st.error(f"API Error: {response.get('status_message')}")
                st.stop()
            
            tasks = response.get("tasks", [])
            if not tasks:
                st.error("No data returned from API.")
                st.stop()
            
            task = tasks[0]
            if task.get("status_code") != 20000:
                st.error(f"Task Error ({task.get('status_code')}): {task.get('status_message')}")
                st.stop()
            
            results = task.get("result", [])
            if not results:
                st.error("No trends data found.")
                st.stop()
            
            # Store results
            st.session_state.gt_results = results[0]
            st.session_state.gt_mode = mode
            st.session_state.gt_config = {
                "keywords": kws,
                "type": trends_type,
                "location": selected_location
            }
            
            st.success(f"✅ **Complete!** Retrieved trends data for {len(kws)} keyword(s)")
        
        else:
            # Standard mode - post and poll
            with st.spinner("Posting trends task..."):
                response = client.trends_explore_post(
                    keywords=kws,
                    location_code=location_code,
                    location_name=location_name,
                    language_code=language_code,
                    type=trends_type,
                    date_from=date_from.strftime("%Y-%m-%d") if use_date_range and date_from else None,
                    date_to=date_to.strftime("%Y-%m-%d") if use_date_range and date_to else None,
                    time_range=time_range,
                    item_types=item_types if item_types else None,
                    tag=f"trends_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                )
            
            # Check task posted successfully
            if response.get("status_code") != 20000:
                st.error(f"API Error: {response.get('status_message')}")
                st.stop()
            
            tasks = response.get("tasks", [])
            if not tasks:
                st.error("Failed to post task.")
                st.stop()
            
            task = tasks[0]
            if task.get("status_code") != 20100:
                st.error(f"Task Error ({task.get('status_code')}): {task.get('status_message')}")
                st.stop()
            
            task_id = task.get("id")
            if not task_id:
                st.error("No task ID returned.")
                st.stop()
            
            st.info(f"✅ Task posted successfully (ID: {task_id})")
            
            # Poll for results
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            max_wait = 120  # 2 minutes
            poll_interval = 5  # 5 seconds
            elapsed = 0
            
            while elapsed < max_wait:
                status_text.text(f"Waiting for results... ({elapsed}s / {max_wait}s)")
                
                # Check if task is ready
                result_response = client.trends_explore_get_result(task_id)
                
                if result_response.get("status_code") == 20000:
                    result_tasks = result_response.get("tasks", [])
                    if result_tasks:
                        result_task = result_tasks[0]
                        if result_task.get("status_code") == 20000:
                            # Task complete
                            results = result_task.get("result", [])
                            if results:
                                st.session_state.gt_results = results[0]
                                st.session_state.gt_mode = mode
                                st.session_state.gt_config = {
                                    "keywords": kws,
                                    "type": trends_type,
                                    "location": selected_location
                                }
                                
                                progress_bar.progress(1.0)
                                status_text.empty()
                                st.success(f"✅ **Complete!** Retrieved trends data for {len(kws)} keyword(s)")
                                break
                
                # Wait before next poll
                time.sleep(poll_interval)
                elapsed += poll_interval
                progress_bar.progress(min(elapsed / max_wait, 0.95))
            else:
                st.warning(f"⏱️ Task did not complete within {max_wait} seconds. Task ID: {task_id}")
                st.info("You can check the task status later using the Task ID above.")
    
    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())

# Display results from session state if available
if st.session_state.gt_results is not None:
    results = st.session_state.gt_results
    config = st.session_state.gt_config
    
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("📊 Results")
    with col2:
        if st.button("🗑️ Clear Results", use_container_width=True):
            st.session_state.gt_results = None
            st.session_state.gt_mode = None
            st.session_state.gt_config = {}
            st.rerun()
    
    # Display check URL
    if results.get("check_url"):
        st.markdown(f"🔗 [View on Google Trends]({results.get('check_url')})")
    
    st.caption(f"Keywords: {', '.join(config.get('keywords', []))} | Type: {config.get('type')} | Location: {config.get('location')}")
    
    # Process items
    items = results.get("items", [])
    
    if not items:
        st.warning("No items returned in results.")
    else:
        # Create tabs for different visualizations
        tab_labels = []
        tab_contents = []
        
        # Check what items we have
        has_graph = any(item.get("type") == "google_trends_graph" for item in items)
        has_map = any(item.get("type") == "google_trends_map" for item in items)
        has_topics = any(item.get("type") == "google_trends_topics_list" for item in items)
        has_queries = any(item.get("type") == "google_trends_queries_list" for item in items)
        
        if has_graph:
            tab_labels.append("📈 Interest Over Time")
        if has_map:
            tab_labels.append("🗺️ Regional Interest")
        if has_topics:
            tab_labels.append("💡 Related Topics")
        if has_queries:
            tab_labels.append("🔍 Related Queries")
        tab_labels.append("💾 Export")
        
        tabs = st.tabs(tab_labels)
        tab_idx = 0
        
        # Interest Over Time tab
        if has_graph:
            with tabs[tab_idx]:
                for item in items:
                    if item.get("type") == "google_trends_graph":
                        st.subheader(item.get("title", "Interest Over Time"))
                        
                        data = item.get("data", [])
                        keywords = item.get("keywords", [])
                        
                        if data:
                            # Create dataframe for plotting
                            rows = []
                            for point in data:
                                date = point.get("date_from")
                                values = point.get("values", [])
                                
                                for idx, value in enumerate(values):
                                    if value is not None:
                                        rows.append({
                                            "date": date,
                                            "keyword": keywords[idx] if idx < len(keywords) else f"Keyword {idx+1}",
                                            "interest": value
                                        })
                            
                            if rows:
                                df = pd.DataFrame(rows)
                                df["date"] = pd.to_datetime(df["date"])
                                
                                # Line chart
                                fig = px.line(
                                    df,
                                    x="date",
                                    y="interest",
                                    color="keyword",
                                    title="Keyword Popularity Over Time",
                                    labels={"interest": "Interest (0-100)", "date": "Date", "keyword": "Keyword"}
                                )
                                fig.update_layout(hovermode="x unified", height=500)
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Summary stats
                                st.subheader("Summary Statistics")
                                summary_df = df.groupby("keyword")["interest"].agg(["mean", "max", "min", "std"]).round(1)
                                summary_df.columns = ["Average", "Peak", "Lowest", "Std Dev"]
                                st.dataframe(summary_df, width="stretch")
            tab_idx += 1
        
        # Regional Interest tab
        if has_map:
            with tabs[tab_idx]:
                for item in items:
                    if item.get("type") == "google_trends_map":
                        st.subheader(item.get("title", "Regional Interest"))
                        
                        data = item.get("data", [])
                        keywords = item.get("keywords", [])
                        
                        if data:
                            # Create dataframe
                            rows = []
                            for region in data:
                                geo_name = region.get("geo_name")
                                values = region.get("values", [])
                                
                                for idx, value in enumerate(values):
                                    if value is not None:
                                        rows.append({
                                            "region": geo_name,
                                            "keyword": keywords[idx] if idx < len(keywords) else f"Keyword {idx+1}",
                                            "interest": value
                                        })
                            
                            if rows:
                                df = pd.DataFrame(rows)
                                
                                # Top regions bar chart
                                top_regions = df.nlargest(20, "interest")
                                
                                fig = px.bar(
                                    top_regions,
                                    x="interest",
                                    y="region",
                                    color="keyword",
                                    orientation="h",
                                    title="Top 20 Regions by Interest",
                                    labels={"interest": "Interest (0-100)", "region": "Region", "keyword": "Keyword"}
                                )
                                fig.update_layout(yaxis={'categoryorder':'total ascending'}, height=600)
                                st.plotly_chart(fig, use_container_width=True)
                                
                                # Full data table
                                with st.expander("📊 View All Regions"):
                                    st.dataframe(df.sort_values("interest", ascending=False), width="stretch", height=400)
            tab_idx += 1
        
        # Related Topics tab
        if has_topics:
            with tabs[tab_idx]:
                for item in items:
                    if item.get("type") == "google_trends_topics_list":
                        st.subheader(item.get("title", "Related Topics"))
                        
                        data = item.get("data", {})
                        
                        col_t1, col_t2 = st.columns(2)
                        
                        with col_t1:
                            st.markdown("### 🔥 Top Topics")
                            top_topics = data.get("top", [])
                            
                            if top_topics:
                                topics_df = pd.DataFrame([{
                                    "Topic": t.get("topic_title"),
                                    "Type": t.get("topic_type"),
                                    "Value": t.get("value")
                                } for t in top_topics[:25]])
                                st.dataframe(topics_df, width="stretch", height=400)
                            else:
                                st.info("No top topics data available.")
                        
                        with col_t2:
                            st.markdown("### 📈 Rising Topics")
                            rising_topics = data.get("rising", [])
                            
                            if rising_topics:
                                rising_df = pd.DataFrame([{
                                    "Topic": t.get("topic_title"),
                                    "Type": t.get("topic_type"),
                                    "Growth": f"{t.get('value')}%"
                                } for t in rising_topics[:25]])
                                st.dataframe(rising_df, width="stretch", height=400)
                            else:
                                st.info("No rising topics data available.")
            tab_idx += 1
        
        # Related Queries tab
        if has_queries:
            with tabs[tab_idx]:
                for item in items:
                    if item.get("type") == "google_trends_queries_list":
                        st.subheader(item.get("title", "Related Queries"))
                        
                        data = item.get("data", {})
                        
                        col_q1, col_q2 = st.columns(2)
                        
                        with col_q1:
                            st.markdown("### 🔥 Top Queries")
                            top_queries = data.get("top", [])
                            
                            if top_queries:
                                queries_df = pd.DataFrame([{
                                    "Query": q.get("query"),
                                    "Value": q.get("value")
                                } for q in top_queries[:25]])
                                st.dataframe(queries_df, width="stretch", height=400)
                            else:
                                st.info("No top queries data available.")
                        
                        with col_q2:
                            st.markdown("### 📈 Rising Queries")
                            rising_queries = data.get("rising", [])
                            
                            if rising_queries:
                                rising_df = pd.DataFrame([{
                                    "Query": q.get("query"),
                                    "Growth": f"{q.get('value')}%" if isinstance(q.get('value'), (int, float)) else q.get('value')
                                } for q in rising_queries[:25]])
                                st.dataframe(rising_df, width="stretch", height=400)
                            else:
                                st.info("No rising queries data available.")
            tab_idx += 1
        
        # Export tab
        with tabs[tab_idx]:
            st.subheader("💾 Download Results")
            
            # Prepare export data
            export_data = {
                "config": config,
                "results": results
            }
            
            # JSON download
            import json
            json_str = json.dumps(export_data, indent=2, default=str)
            st.download_button(
                label="📥 Download JSON",
                data=json_str,
                file_name=f"google_trends_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
                mime="application/json",
                use_container_width=True
            )
            
            st.caption("Full API response including all data points and metadata")

