"""
DataForSEO Rank Retrieval Tool
Main Streamlit application using modular architecture
"""
import threading
from datetime import datetime
from io import BytesIO
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

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

# Initialize results history in session state
if "results_history" not in st.session_state:
    st.session_state.results_history = []
if "loaded_result" not in st.session_state:
    st.session_state.loaded_result = None

# Show results history in sidebar
if st.session_state.results_history:
    with st.sidebar.expander(f"📜 Results History ({len(st.session_state.results_history)})", expanded=False):
        for i, run in enumerate(reversed(st.session_state.results_history[-5:])):  # Show last 5
            idx = len(st.session_state.results_history) - i - 1
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"**Run {idx + 1}**")
                    st.text(f"🎯 {run['domain']}")
                    st.text(f"📊 {run['total']} keywords")
                    st.text(f"✅ {run['found']} found")
                    st.text(f"🕐 {run['timestamp'].strftime('%H:%M:%S')}")
                with col2:
                    if st.button("📂", key=f"load_{idx}", help="Load this result"):
                        st.session_state.loaded_result = run
                        st.rerun()
                st.divider()

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

# Display loaded result if available
if st.session_state.loaded_result is not None:
    result = st.session_state.loaded_result
    df = result['df']
    
    st.info(f"📂 **Loaded Result from {result['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}** - Domain: {result['domain']}")
    
    # Add a "Clear" button
    if st.button("🗑️ Clear Loaded Result", use_container_width=True):
        st.session_state.loaded_result = None
        st.rerun()
    
    # Reuse the results display logic (same as after a run)
    found_count = result['found']
    total_count = result['total']
    
    st.divider()
    st.subheader("📊 Loaded Results")
    
    # Display results in tabs (reusing existing display code structure)
    tab1, tab2, tab3 = st.tabs(["📋 Table View", "📈 Charts & Analytics", "💾 Export"])
    
    with tab1:
        # Summary metrics
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Keywords", total_count)
        col2.metric("Found", found_count)
        col3.metric("Not Found", total_count - found_count)
        if found_count > 0:
            avg_rank = df[df["found"] == True]["organic_rank"].mean()
            col4.metric("Avg Rank", f"{avg_rank:.1f}" if pd.notna(avg_rank) else "N/A")
        
        # Table
        st.dataframe(df, width="stretch", height=400)
        
        # Top rankings preview
        if found_count > 0:
            with st.expander("🏆 Top 10 Rankings Preview"):
                top_10 = df[df["found"] == True].nsmallest(10, "organic_rank")[
                    ["keyword", "organic_rank", "url", "title"]
                ]
                st.dataframe(top_10, width="stretch")
    
    with tab2:
        if found_count > 0:
            import plotly.express as px
            import plotly.graph_objects as go
            
            found_df = df[df["found"] == True].copy()
            
            # Rank distribution bar chart
            st.subheader("📊 Rank Distribution")
            rank_counts = found_df["organic_rank"].value_counts().sort_index()
            fig = px.bar(
                x=rank_counts.index,
                y=rank_counts.values,
                labels={"x": "Rank Position", "y": "Number of Keywords"},
                title="Keywords by Rank Position"
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # Rank range breakdown
            st.subheader("🎯 Rank Range Breakdown")
            
            def rank_range(rank):
                if rank <= 3: return "Top 3"
                elif rank <= 10: return "Top 10"
                elif rank <= 20: return "Top 20"
                elif rank <= 50: return "Top 50"
                else: return "Beyond 50"
            
            found_df["rank_range"] = found_df["organic_rank"].apply(rank_range)
            range_counts = found_df["rank_range"].value_counts()
            
            fig = go.Figure(data=[go.Pie(
                labels=range_counts.index,
                values=range_counts.values,
                hole=0.3
            )])
            fig.update_layout(title="Keywords by Rank Range")
            st.plotly_chart(fig, use_container_width=True)
            
            # Stats
            col1, col2 = st.columns(2)
            with col1:
                st.metric("📈 Top 3 Performance", f"{(found_df['organic_rank'] <= 3).sum() / len(found_df) * 100:.1f}%")
                st.metric("📈 Top 10 Performance", f"{(found_df['organic_rank'] <= 10).sum() / len(found_df) * 100:.1f}%")
            with col2:
                st.metric("🏆 Best Rank", int(found_df["organic_rank"].min()))
                st.metric("📊 Median Rank", int(found_df["organic_rank"].median()))
        else:
            st.info("No ranking data found to visualize.")
    
    with tab3:
        st.subheader("💾 Download Results")
        
        # CSV download
        csv = df.to_csv(index=False)
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"rank_results_{result['domain']}_{result['timestamp'].strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True
        )
        
        # Excel download with summary
        from io import BytesIO
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name='Results', index=False)
            
            # Create summary sheet
            summary_data = {
                'Metric': ['Total Keywords', 'Found', 'Not Found', 'Average Rank', 'Best Rank', 'Worst Rank'],
                'Value': [
                    total_count,
                    found_count,
                    total_count - found_count,
                    f"{df[df['found'] == True]['organic_rank'].mean():.1f}" if found_count > 0 else "N/A",
                    int(df[df['found'] == True]['organic_rank'].min()) if found_count > 0 else "N/A",
                    int(df[df['found'] == True]['organic_rank'].max()) if found_count > 0 else "N/A"
                ]
            }
            pd.DataFrame(summary_data).to_excel(writer, sheet_name='Summary', index=False)
        
        st.download_button(
            label="📥 Download Excel (with Summary)",
            data=buffer.getvalue(),
            file_name=f"rank_results_{result['domain']}_{result['timestamp'].strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    
    st.stop()  # Don't show the run form when viewing loaded results

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
        
        # Calculate metrics
        found_count = df["found"].sum() if "found" in df.columns else 0
        total_count = len(df)
        
        # Add to history
        st.session_state.results_history.append({
            "timestamp": datetime.now(),
            "domain": domain,
            "total": total_count,
            "found": found_count,
            "df": df.copy()
        })
        
        # Show completion status
        status_container = st.empty()
        with status_container:
            st.success(f"✅ **Complete!** Found {found_count}/{total_count} keywords ranking")
        
        # Display results in tabs
        st.divider()
        st.subheader("📊 Results")
        
        tab1, tab2, tab3 = st.tabs(["📋 Table View", "📈 Charts & Analytics", "💾 Export"])
        
        with tab1:
            # Summary metrics
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Total Keywords", total_count)
            col2.metric("Found", found_count)
            col3.metric("Not Found", total_count - found_count)
            if found_count > 0:
                avg_rank = df[df["found"] == True]["organic_rank"].mean()
                col4.metric("Avg Rank", f"{avg_rank:.1f}" if pd.notna(avg_rank) else "N/A")
            
            # Table
            st.dataframe(df, width="stretch", height=400)
            
            # Quick preview of top rankings
            if found_count > 0:
                with st.expander("🎯 Top 10 Rankings Preview"):
                    top_df = df[df["found"] == True].sort_values("organic_rank").head(10)
                    preview_cols = ["keyword", "organic_rank", "absolute_rank", "url", "title"]
                    st.dataframe(top_df[preview_cols], width="stretch")
        
        with tab2:
            if found_count > 0:
                # Rank distribution chart
                st.markdown("### 📊 Rank Distribution")
                rank_counts = df[df["found"] == True]["organic_rank"].value_counts().sort_index()
                fig_dist = px.bar(
                    x=rank_counts.index,
                    y=rank_counts.values,
                    labels={"x": "Rank Position", "y": "Number of Keywords"},
                    title="Keywords by Rank Position"
                )
                fig_dist.update_traces(marker_color='#1f77b4')
                st.plotly_chart(fig_dist, use_container_width=True)
                
                # Rank range breakdown
                st.markdown("### 📈 Rank Range Breakdown")
                rank_ranges = {
                    "Top 3 (1-3)": len(df[(df["found"] == True) & (df["organic_rank"] <= 3)]),
                    "Top 10 (4-10)": len(df[(df["found"] == True) & (df["organic_rank"] > 3) & (df["organic_rank"] <= 10)]),
                    "Top 20 (11-20)": len(df[(df["found"] == True) & (df["organic_rank"] > 10) & (df["organic_rank"] <= 20)]),
                    "Top 50 (21-50)": len(df[(df["found"] == True) & (df["organic_rank"] > 20) & (df["organic_rank"] <= 50)]),
                    "Beyond 50": len(df[(df["found"] == True) & (df["organic_rank"] > 50)])
                }
                
                fig_pie = go.Figure(data=[go.Pie(
                    labels=list(rank_ranges.keys()),
                    values=list(rank_ranges.values()),
                    hole=.3
                )])
                fig_pie.update_layout(title="Keyword Distribution by Rank Range")
                st.plotly_chart(fig_pie, use_container_width=True)
                
                # Performance metrics
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("### 🏆 Performance Metrics")
                    top_3 = rank_ranges["Top 3 (1-3)"]
                    top_10 = rank_ranges["Top 3 (1-3)"] + rank_ranges["Top 10 (4-10)"]
                    st.metric("Top 3 Rankings", f"{top_3} ({top_3/found_count*100:.1f}%)")
                    st.metric("Top 10 Rankings", f"{top_10} ({top_10/found_count*100:.1f}%)")
                
                with col2:
                    st.markdown("### 📉 Rank Statistics")
                    ranks = df[df["found"] == True]["organic_rank"]
                    st.metric("Best Rank", int(ranks.min()))
                    st.metric("Median Rank", f"{ranks.median():.0f}")
                    st.metric("Worst Rank", int(ranks.max()))
            else:
                st.info("No rankings found. Charts will appear when keywords are found.")
        
        with tab3:
            st.markdown("### 💾 Download Results")
            st.caption(f"Export {total_count} keywords in your preferred format")
            
            # CSV Export
            csv = df.to_csv(index=False).encode("utf-8")
            csv_filename = f"dataforseo_ranks_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            
            # Excel Export
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
                # Main results sheet
                df.to_excel(writer, sheet_name='Results', index=False)
                
                # Summary sheet
                if found_count > 0:
                    summary_df = pd.DataFrame({
                        'Metric': ['Total Keywords', 'Found', 'Not Found', 'Average Rank', 
                                  'Top 3', 'Top 10', 'Top 20', 'Best Rank', 'Worst Rank'],
                        'Value': [
                            total_count,
                            found_count,
                            total_count - found_count,
                            f"{df[df['found'] == True]['organic_rank'].mean():.1f}",
                            rank_ranges["Top 3 (1-3)"],
                            rank_ranges["Top 3 (1-3)"] + rank_ranges["Top 10 (4-10)"],
                            rank_ranges["Top 3 (1-3)"] + rank_ranges["Top 10 (4-10)"] + rank_ranges["Top 20 (11-20)"],
                            int(df[df['found'] == True]['organic_rank'].min()),
                            int(df[df['found'] == True]['organic_rank'].max())
                        ]
                    })
                    summary_df.to_excel(writer, sheet_name='Summary', index=False)
            
            excel_data = excel_buffer.getvalue()
            excel_filename = f"dataforseo_ranks_{domain}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
            
            # Download buttons
            col1, col2 = st.columns(2)
            with col1:
                st.download_button(
                    label="📄 Download CSV",
                    data=csv,
                    file_name=csv_filename,
                    mime="text/csv",
                    use_container_width=True
                )
            
            with col2:
                st.download_button(
                    label="📊 Download Excel",
                    data=excel_data,
                    file_name=excel_filename,
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True
                )
            
            st.info("💡 **Tip:** Excel export includes a Summary sheet with key metrics")
        
    except Exception as e:
        st.error(f"❌ **Error during execution**: {str(e)}")
        import traceback
        with st.expander("Show error details"):
            st.code(traceback.format_exc())

