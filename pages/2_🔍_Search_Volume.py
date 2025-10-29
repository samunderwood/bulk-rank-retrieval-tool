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

# Sidebar credentials
client = render_credentials_sidebar(KeywordsDataClient)

if not client:
    st.warning("👈 Please enter your DataForSEO credentials in the sidebar to get started.")
    st.info("""
        **Getting Started:**
        1. Enter your DataForSEO login and password in the sidebar
        2. Check 'Remember credentials' to keep them for your session
        3. Start getting search volume data!
        
        Don't have credentials? Get them at [DataForSEO API Access](https://app.dataforseo.com/api-access)
    """)
    st.stop()

# Get available locations
@st.cache_data(ttl=3600)
def get_locations():
    """Fetch available locations for clickstream data."""
    try:
        response = client.get_locations_and_languages()
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
        help="Enter up to 1000 keywords, one per line. Each keyword must be at least 3 characters."
    )

with col2:
    # Location selector
    locations = get_locations()
    
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
        
        - Up to 1000 keywords per request
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
    
    if len(kws) > 1000:
        st.error(f"⚠️ Maximum 1000 keywords allowed. You entered {len(kws)}.")
        st.stop()
    
    # Check keyword length
    short_keywords = [kw for kw in kws if len(kw) < 3]
    if short_keywords:
        st.error(f"⚠️ Keywords must be at least 3 characters. Too short: {', '.join(short_keywords[:5])}")
        st.stop()
    
    # Display execution summary
    st.info(f"""
        **Execution Summary:**
        - Keywords: {len(kws)}
        - Location: {selected_location}
        - API: Clickstream Bulk Search Volume (Live)
    """)
    
    # Execute request
    try:
        with st.spinner("Fetching search volume data..."):
            response = client.bulk_search_volume(
                keywords=kws,
                location_code=location_code
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
            st.error(f"Task Error: {task.get('status_message')}")
            st.stop()
        
        results = task.get("result", [])
        if not results or not results[0].get("items"):
            st.error("No search volume data found.")
            st.stop()
        
        items = results[0]["items"]
        
        # Create dataframe
        rows = []
        for item in items:
            row = {
                "keyword": item.get("keyword"),
                "search_volume": item.get("search_volume", 0),
                "location_code": location_code
            }
            
            # Add monthly data
            monthly = item.get("monthly_searches", [])
            for i, month_data in enumerate(monthly[:12]):  # Last 12 months
                row[f"month_{i+1}"] = month_data.get("search_volume", 0)
                row[f"month_{i+1}_label"] = f"{month_data.get('year')}-{month_data.get('month'):02d}"
            
            rows.append(row)
        
        df = pd.DataFrame(rows)
        
        # Show completion
        st.success(f"✅ **Complete!** Retrieved search volume for {len(df)} keywords")
        
        # Display results in tabs
        st.divider()
        st.subheader("📊 Results")
        
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
    
    except Exception as e:
        st.error(f"Error: {e}")
        import traceback
        st.code(traceback.format_exc())

