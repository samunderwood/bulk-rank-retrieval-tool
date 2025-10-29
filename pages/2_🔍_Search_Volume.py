"""
Search Volume Tool
Get clickstream-based search volume data for keywords with 12-month historical trends.
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO

from ui_components import setup_page_config, render_credentials_sidebar
from dataforseo_client import KeywordsDataClient

# Configure page
setup_page_config(title="Search Volume - DataForSEO Tools", layout="wide")

st.title("🔍 Search Volume Tool")
st.markdown("Get clickstream-based search volume data for up to 1000 keywords with 12-month historical trends.")

# Initialize session state for results
if "sv_results_df" not in st.session_state:
    st.session_state.sv_results_df = None
if "sv_location_code" not in st.session_state:
    st.session_state.sv_location_code = None
if "sv_selected_location" not in st.session_state:
    st.session_state.sv_selected_location = None

# Sidebar credentials
client = render_credentials_sidebar(KeywordsDataClient)

if not client:
    st.warning("👈 Please enter your DataForSEO credentials in the sidebar to get started.")
    st.info("""
        **Getting Started:**
        1. Enter your DataForSEO login and password in the sidebar
        2. Your credentials will automatically persist across all pages
        3. Start getting search volume data!
        
        Don't have credentials? Get them at [DataForSEO API Access](https://app.dataforseo.com/api-access)
    """)
    st.stop()

# Get available locations
@st.cache_data(ttl=3600)
def get_locations(_login: str, _password: str):
    """Fetch available locations for clickstream data."""
    try:
        temp_client = KeywordsDataClient(login=_login, password=_password)
        response = temp_client.get_locations_and_languages()
        if response.get("status_code") == 20000:
            tasks = response.get("tasks", [])
            if tasks and tasks[0].get("result"):
                return tasks[0]["result"]
    except Exception as e:
        st.error(f"Error fetching locations: {e}")
    return []

# Main configuration
st.subheader("Configuration")

col1, col2 = st.columns([2, 1])

with col1:
    keywords_input = st.text_area(
        "Keywords (one per line)",
        height=200,
        placeholder="youtube\nbeat maker\nmusic production\n...",
        help="Enter keywords, one per line. Each keyword must be at least 3 characters. Large lists will be automatically processed in batches of 1,000."
    )

with col2:
    # Location selector
    locations = get_locations(st.session_state.user_login, st.session_state.user_password)
    
    if locations:
        location_names = {f"{loc.get('location_name')} ({loc.get('location_code')})": loc.get('location_code') 
                         for loc in locations}
        
        selected_location = st.selectbox(
            "Location",
            options=list(location_names.keys()),
            index=list(location_names.keys()).index("United States (2840)") if "United States (2840)" in location_names else 0,
            help="Select the geographic location for search volume data"
        )
        
        location_code = location_names[selected_location]
    else:
        st.error("Could not load locations. Please check your credentials.")
        st.stop()
    
    st.info(f"""
        **About Clickstream Data:**
        
        Real search behavior data based on actual user clicks, not estimates.
        
        - Process unlimited keywords (auto-batched)
        - 12 months of historical data
        - Location-specific volumes
    """)

st.divider()

# Run button
run = st.button("▶️ Get Search Volume", type="primary", use_container_width=True)

if run:
    # Validation
    kws = [k.strip() for k in keywords_input.splitlines() if k.strip()]
    
    if not kws:
        st.error("⚠️ Please enter at least one keyword.")
        st.stop()
    
    # Check keyword length
    short_keywords = [kw for kw in kws if len(kw) < 3]
    if short_keywords:
        st.error(f"⚠️ Keywords must be at least 3 characters. Too short: {', '.join(short_keywords[:5])}")
        st.stop()
    
    # Calculate batches
    BATCH_SIZE = 1000
    total_keywords = len(kws)
    num_batches = (total_keywords + BATCH_SIZE - 1) // BATCH_SIZE  # Ceiling division
    
    # Display execution summary
    if num_batches > 1:
        st.info(f"""
            **Execution Summary:**
            - Total Keywords: {total_keywords:,}
            - Batches: {num_batches} (up to {BATCH_SIZE} keywords per batch)
            - Location: {selected_location}
            - API: Clickstream Bulk Search Volume (Live)
            
            💡 Processing multiple batches sequentially...
        """)
    else:
        st.info(f"""
            **Execution Summary:**
            - Keywords: {total_keywords}
            - Location: {selected_location}
            - API: Clickstream Bulk Search Volume (Live)
        """)
    
    # Execute batched requests
    try:
        all_rows = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for batch_idx in range(num_batches):
            # Get batch of keywords
            start_idx = batch_idx * BATCH_SIZE
            end_idx = min(start_idx + BATCH_SIZE, total_keywords)
            batch_keywords = kws[start_idx:end_idx]
            
            # Update progress
            progress = (batch_idx + 1) / num_batches
            progress_bar.progress(progress)
            status_text.text(f"Processing batch {batch_idx + 1} of {num_batches} ({len(batch_keywords)} keywords)...")
            
            # Make API request
            with st.spinner(f"Fetching batch {batch_idx + 1}/{num_batches}..."):
                response = client.bulk_search_volume(
                    keywords=batch_keywords,
                    location_code=location_code,
                    tag=f"batch_{batch_idx + 1}"
                )
            
            # Parse results
            if response.get("status_code") != 20000:
                st.error(f"API Error in batch {batch_idx + 1}: {response.get('status_message')}")
                st.stop()
            
            tasks = response.get("tasks", [])
            if not tasks:
                st.warning(f"No data returned for batch {batch_idx + 1}")
                continue
            
            task = tasks[0]
            if task.get("status_code") != 20000:
                st.warning(f"Batch {batch_idx + 1} returned status {task.get('status_code')}: {task.get('status_message')}")
                continue
            
            results = task.get("result", [])
            if not results or not results[0].get("items"):
                st.warning(f"No search volume data in batch {batch_idx + 1}")
                continue
            
            items = results[0]["items"]
            
            # Process items from this batch
            for item in items:
                row = {
                    "keyword": item.get("keyword"),
                    "search_volume": item.get("search_volume", 0),
                    "location_code": location_code,
                    "batch": batch_idx + 1
                }
                
                # Add monthly data
                monthly = item.get("monthly_searches", [])
                for i, month_data in enumerate(monthly[:12]):  # Last 12 months
                    row[f"month_{i+1}"] = month_data.get("search_volume", 0)
                    row[f"month_{i+1}_label"] = f"{month_data.get('year')}-{month_data.get('month'):02d}"
                
                all_rows.append(row)
        
        # Complete progress
        progress_bar.progress(1.0)
        status_text.empty()
        
        # Create combined dataframe
        if not all_rows:
            st.error("No search volume data retrieved from any batch.")
            st.stop()
        
        df = pd.DataFrame(all_rows)
        
        # Store in session state
        st.session_state.sv_results_df = df
        st.session_state.sv_location_code = location_code
        st.session_state.sv_selected_location = selected_location
        
        # Show completion
        if num_batches > 1:
            st.success(f"✅ **Complete!** Retrieved search volume for {len(df):,} keywords across {num_batches} batches")
        else:
            st.success(f"✅ **Complete!** Retrieved search volume for {len(df)} keywords")
    
    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())

# Display results from session state if available
if st.session_state.sv_results_df is not None:
    df = st.session_state.sv_results_df
    location_code = st.session_state.sv_location_code
    selected_location = st.session_state.sv_selected_location
    
    # Display results in tabs
    st.divider()
    
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("📊 Results")
    with col2:
        if st.button("🗑️ Clear Results", use_container_width=True):
            st.session_state.sv_results_df = None
            st.session_state.sv_location_code = None
            st.session_state.sv_selected_location = None
            st.rerun()
    
    tab1, tab2, tab3 = st.tabs(["📋 Table View", "📈 Charts & Trends", "💾 Export"])
    
    with tab1:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Keywords", len(df))
        col2.metric("Total Volume", f"{df['search_volume'].sum():,}")
        col3.metric("Avg Volume", f"{df['search_volume'].mean():,.0f}")
        col4.metric("Max Volume", f"{df['search_volume'].max():,}")
        
        # Table
        display_df = df[["keyword", "search_volume"]].sort_values("search_volume", ascending=False)
        st.dataframe(display_df, width="stretch", height=400)
        
        # Top keywords
        with st.expander("🏆 Top 20 Keywords by Volume"):
            top_20 = df.nlargest(20, "search_volume")[["keyword", "search_volume"]]
            fig = px.bar(
                top_20,
                x="search_volume",
                y="keyword",
                orientation="h",
                title="Top 20 Keywords",
                labels={"search_volume": "Search Volume", "keyword": "Keyword"}
            )
            fig.update_layout(yaxis={'categoryorder':'total ascending'})
            st.plotly_chart(fig, use_container_width=True)
    
    with tab2:
        st.subheader("📈 Search Volume Trends")
        
        # Select keyword for trend analysis
        selected_kw = st.selectbox(
            "Select keyword to view monthly trend:",
            options=df["keyword"].tolist(),
            index=0
        )
        
        if selected_kw:
            kw_data = df[df["keyword"] == selected_kw].iloc[0]
            
            # Extract monthly data
            monthly_data = []
            for i in range(1, 13):
                if f"month_{i}" in kw_data and pd.notna(kw_data[f"month_{i}"]):
                    monthly_data.append({
                        "month": kw_data[f"month_{i}_label"],
                        "volume": kw_data[f"month_{i}"]
                    })
            
            if monthly_data:
                monthly_df = pd.DataFrame(monthly_data)
                
                # Line chart
                fig = px.line(
                    monthly_df,
                    x="month",
                    y="volume",
                    title=f"12-Month Trend: {selected_kw}",
                    labels={"month": "Month", "volume": "Search Volume"},
                    markers=True
                )
                fig.update_layout(hovermode="x unified")
                st.plotly_chart(fig, use_container_width=True)
                
                # Stats
                col1, col2, col3 = st.columns(3)
                col1.metric("Current Volume", f"{monthly_data[0]['volume']:,}")
                col2.metric("12-Month Avg", f"{sum(m['volume'] for m in monthly_data) / len(monthly_data):,.0f}")
                
                # Trend direction
                if len(monthly_data) >= 2:
                    change = ((monthly_data[0]['volume'] - monthly_data[-1]['volume']) / monthly_data[-1]['volume']) * 100
                    col3.metric("12-Month Change", f"{change:+.1f}%")
            else:
                st.info("No monthly data available for this keyword.")
        
        st.divider()
        
        # Volume distribution
        st.subheader("📊 Volume Distribution")
        
        fig = px.histogram(
            df,
            x="search_volume",
            nbins=50,
            title="Search Volume Distribution",
            labels={"search_volume": "Search Volume", "count": "Number of Keywords"}
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with tab3:
        st.subheader("💾 Download Results")
        
        # Prepare export dataframe
        export_df = df.copy()
        
        # CSV download
        csv = export_df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"search_volume_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # Excel download
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            # Results sheet
            export_df.to_excel(writer, sheet_name='Results', index=False)
            
            # Summary sheet
            summary_data = {
                'Metric': ['Total Keywords', 'Total Volume', 'Average Volume', 'Median Volume', 'Max Volume', 'Min Volume'],
                'Value': [
                    len(df),
                    f"{df['search_volume'].sum():,}",
                    f"{df['search_volume'].mean():,.0f}",
                    f"{df['search_volume'].median():,.0f}",
                    f"{df['search_volume'].max():,}",
                    f"{df['search_volume'].min():,}"
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
        
        st.download_button(
            label="📥 Download Excel (with Summary)",
            data=buffer.getvalue(),
            file_name=f"search_volume_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )

