"""
Google Trends Tool
Extract keyword popularity trends, regional interest, and related topics/queries for multiple keywords.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
from io import BytesIO
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

from ui_components import setup_page_config, render_credentials_sidebar
from dataforseo_client import KeywordsDataClient

# Configure page
setup_page_config(title="Google Trends - DataForSEO Tools", layout="wide")

st.title("📈 Google Trends Tool")
st.markdown("Extract keyword popularity trends, regional interest, and discover related topics and queries for multiple keywords.")

# Initialize session state for results
if "gt_results_df" not in st.session_state:
    st.session_state.gt_results_df = None
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
    help="Live: Results in ~5-10 seconds per keyword (250/min limit). Standard: Post tasks then retrieve results, better for bulk (2000/min limit)."
)

col1, col2 = st.columns([2, 1])

with col1:
    # Keywords input (unlimited)
    keywords_input = st.text_area(
        "Keywords (one per line)",
        height=200,
        placeholder="seo api\nrank tracker\nkeyword research\ncontent marketing\n...",
        help="Enter keywords, one per line. Each keyword will be processed individually. Large lists will be batched automatically."
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
    
    st.info("""
        **About Bulk Extraction:**
        
        Each keyword processed individually with its own trend data, regional interest, and related topics/queries.
        
        - Unlimited keywords (auto-batched)
        - Individual trend analysis per keyword
        - Export to CSV/Excel with all metrics
    """)

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
        st.write("Data to retrieve (per keyword):")
        get_graph = st.checkbox("Interest over time", value=True)
        get_map = st.checkbox("Regional interest", value=True)
        get_topics = st.checkbox("Related topics", value=True)
        get_queries = st.checkbox("Related queries", value=True)
        
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
    
    # Display execution summary
    st.info(f"""
        **Execution Summary:**
        - Mode: {mode}
        - Keywords: {len(kws):,} keywords (processed individually)
        - Type: {trends_type}
        - Location: {selected_location}
        - Time Range: {'Custom' if use_date_range else time_range}
    """)
    
    # Execute parallel requests
    try:
        all_results = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        completed = 0
        lock = threading.Lock()
        
        def process_keyword(idx, keyword):
            """Process a single keyword."""
            try:
                if mode == "Live":
                    # Live mode - immediate results
                    response = client.trends_explore_live(
                        keywords=[keyword],
                        location_code=location_code,
                        location_name=location_name,
                        language_code=language_code,
                        type=trends_type,
                        date_from=date_from.strftime("%Y-%m-%d") if use_date_range and date_from else None,
                        date_to=date_to.strftime("%Y-%m-%d") if use_date_range and date_to else None,
                        time_range=time_range,
                        item_types=item_types if item_types else None,
                        tag=f"bulk_{idx}"
                    )
                else:
                    # Standard mode - post task
                    response = client.trends_explore_post(
                        keywords=[keyword],
                        location_code=location_code,
                        location_name=location_name,
                        language_code=language_code,
                        type=trends_type,
                        date_from=date_from.strftime("%Y-%m-%d") if use_date_range and date_from else None,
                        date_to=date_to.strftime("%Y-%m-%d") if use_date_range and date_to else None,
                        time_range=time_range,
                        item_types=item_types if item_types else None,
                        tag=f"bulk_{idx}"
                    )
                
                # Parse response
                if response.get("status_code") != 20000:
                    return None
                
                tasks = response.get("tasks", [])
                if not tasks:
                    return None
                
                task = tasks[0]
                
                if mode == "Live":
                    # Live mode - results are immediate
                    if task.get("status_code") != 20000:
                        return None
                    
                    results = task.get("result", [])
                    if results:
                        return {
                            "keyword": keyword,
                            "data": results[0],
                            "task_id": task.get("id")
                        }
                else:
                    # Standard mode - store task ID for later retrieval
                    if task.get("status_code") != 20100:
                        return None
                    
                    task_id = task.get("id")
                    if task_id:
                        return {
                            "keyword": keyword,
                            "task_id": task_id,
                            "status": "pending"
                        }
            except Exception as e:
                return None
            
            return None
        
        # Process keywords in parallel
        # Live mode: 10 threads (rate limit: 250/min)
        # Standard mode: 30 threads (rate limit: 2000/min)
        max_workers = 10 if mode == "Live" else 30
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_keyword = {
                executor.submit(process_keyword, idx, kw): kw 
                for idx, kw in enumerate(kws)
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_keyword):
                keyword = future_to_keyword[future]
                
                try:
                    result = future.result()
                    if result:
                        with lock:
                            all_results.append(result)
                except Exception as e:
                    pass
                
                # Update progress
                with lock:
                    completed += 1
                    progress = completed / len(kws)
                    progress_bar.progress(progress)
                    status_text.text(f"Processed {completed} of {len(kws)} keywords...")
        
        # Complete progress
        progress_bar.progress(1.0)
        status_text.empty()
        
        if not all_results:
            st.error("No data retrieved for any keyword.")
            st.stop()
        
        # For Standard mode, poll for results
        if mode == "Standard":
            st.info(f"✅ Posted {len(all_results)} tasks. Now retrieving results...")
            
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            max_wait = 180  # 3 minutes
            poll_interval = 5
            start_time = time.time()
            completed = 0
            
            while completed < len(all_results) and (time.time() - start_time) < max_wait:
                for result in all_results:
                    if result.get("status") == "pending":
                        try:
                            task_response = client.trends_explore_get_result(result["task_id"])
                            
                            if task_response.get("status_code") == 20000:
                                result_tasks = task_response.get("tasks", [])
                                if result_tasks:
                                    result_task = result_tasks[0]
                                    if result_task.get("status_code") == 20000:
                                        task_results = result_task.get("result", [])
                                        if task_results:
                                            result["data"] = task_results[0]
                                            result["status"] = "completed"
                                            completed += 1
                        except:
                            pass
                
                progress_bar.progress(min(completed / len(all_results), 0.95))
                status_text.text(f"Retrieved {completed} of {len(all_results)} results...")
                
                if completed < len(all_results):
                    time.sleep(poll_interval)
            
            progress_bar.progress(1.0)
            status_text.empty()
            
            # Filter to completed only
            all_results = [r for r in all_results if r.get("status") == "completed"]
            
            if not all_results:
                st.error("No tasks completed within timeout period.")
                st.stop()
        
        # Process results into dataframe
        rows = []
        
        for result in all_results:
            keyword = result["keyword"]
            data = result.get("data", {})
            items = data.get("items", [])
            
            row = {
                "keyword": keyword,
                "location": selected_location,
                "type": trends_type,
                "check_url": data.get("check_url", "")
            }
            
            # Extract graph data (interest over time)
            for item in items:
                if item.get("type") == "google_trends_graph":
                    graph_data = item.get("data", [])
                    if graph_data:
                        # Calculate averages
                        all_values = []
                        for point in graph_data:
                            values = point.get("values", [])
                            if values and values[0] is not None:
                                all_values.append(values[0])
                        
                        if all_values:
                            row["avg_interest"] = sum(all_values) / len(all_values)
                            row["max_interest"] = max(all_values)
                            row["min_interest"] = min(all_values)
                            row["data_points"] = len(all_values)
            
            # Extract map data (regional interest)
            for item in items:
                if item.get("type") == "google_trends_map":
                    map_data = item.get("data", [])
                    if map_data:
                        # Get top region - safely handle None values
                        def get_region_value(region):
                            values = region.get("values", [])
                            if values and len(values) > 0 and values[0] is not None:
                                return values[0]
                            return 0
                        
                        sorted_regions = sorted(map_data, key=get_region_value, reverse=True)
                        if sorted_regions:
                            top_region = sorted_regions[0]
                            row["top_region"] = top_region.get("geo_name")
                            row["top_region_interest"] = get_region_value(top_region)
                            row["num_regions"] = len([r for r in map_data if get_region_value(r) > 0])
            
            # Extract topics data
            for item in items:
                if item.get("type") == "google_trends_topics_list":
                    topics_data = item.get("data", {})
                    top_topics = topics_data.get("top", [])
                    rising_topics = topics_data.get("rising", [])
                    
                    row["num_top_topics"] = len(top_topics)
                    row["num_rising_topics"] = len(rising_topics)
                    
                    if top_topics:
                        row["top_topic"] = top_topics[0].get("topic_title")
                    if rising_topics:
                        row["top_rising_topic"] = rising_topics[0].get("topic_title")
            
            # Extract queries data
            for item in items:
                if item.get("type") == "google_trends_queries_list":
                    queries_data = item.get("data", {})
                    top_queries = queries_data.get("top", [])
                    rising_queries = queries_data.get("rising", [])
                    
                    row["num_top_queries"] = len(top_queries)
                    row["num_rising_queries"] = len(rising_queries)
                    
                    if top_queries:
                        row["top_query"] = top_queries[0].get("query")
                    if rising_queries:
                        row["top_rising_query"] = rising_queries[0].get("query")
            
            rows.append(row)
        
        # Create dataframe
        df = pd.DataFrame(rows)
        
        # Store in session state
        st.session_state.gt_results_df = df
        st.session_state.gt_config = {
            "mode": mode,
            "type": trends_type,
            "location": selected_location,
            "keywords_count": len(kws)
        }
        
        st.success(f"✅ **Complete!** Retrieved trends data for {len(df):,} keywords")
    
    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())

# Display results from session state if available
if st.session_state.gt_results_df is not None:
    df = st.session_state.gt_results_df
    config = st.session_state.gt_config
    
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("📊 Results")
    with col2:
        if st.button("🗑️ Clear Results", use_container_width=True):
            st.session_state.gt_results_df = None
            st.session_state.gt_config = {}
            st.rerun()
    
    st.caption(f"Mode: {config.get('mode')} | Type: {config.get('type')} | Location: {config.get('location')} | Keywords: {config.get('keywords_count'):,}")
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["📋 Table View", "📈 Charts & Analytics", "💾 Export"])
    
    with tab1:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Keywords", len(df))
        
        if "avg_interest" in df.columns:
            col2.metric("Avg Interest", f"{df['avg_interest'].mean():.1f}")
            col3.metric("Highest Interest", f"{df['avg_interest'].max():.1f}")
            col4.metric("Lowest Interest", f"{df['avg_interest'].min():.1f}")
        
        # Table
        st.dataframe(df, width="stretch", height=400)
    
    with tab2:
        st.subheader("📈 Keyword Analysis")
        
        if "avg_interest" in df.columns:
            # Top keywords by interest
            top_keywords = df.nlargest(20, "avg_interest")
            
            fig = px.bar(
                top_keywords,
                x="avg_interest",
                y="keyword",
                orientation="h",
                title="Top 20 Keywords by Average Interest",
                labels={"avg_interest": "Average Interest (0-100)", "keyword": "Keyword"}
            )
            fig.update_layout(yaxis={'categoryorder':'total ascending'}, height=600)
            st.plotly_chart(fig, use_container_width=True)
            
            # Interest distribution
            fig2 = px.histogram(
                df,
                x="avg_interest",
                nbins=30,
                title="Interest Distribution",
                labels={"avg_interest": "Average Interest", "count": "Number of Keywords"}
            )
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No interest data available for visualization.")
    
    with tab3:
        st.subheader("💾 Download Results")
        
        # CSV download
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"google_trends_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # Excel download
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Results sheet
            df.to_excel(writer, sheet_name='Trends Data', index=False)
            
            # Summary sheet
            if "avg_interest" in df.columns:
                summary_data = {
                    'Metric': ['Total Keywords', 'Avg Interest', 'Max Interest', 'Min Interest'],
                    'Value': [
                        len(df),
                        f"{df['avg_interest'].mean():.2f}",
                        f"{df['avg_interest'].max():.2f}",
                        f"{df['avg_interest'].min():.2f}"
                    ]
                }
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
        
        st.download_button(
            label="📥 Download Excel (with Summary)",
            data=buffer.getvalue(),
            file_name=f"google_trends_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
