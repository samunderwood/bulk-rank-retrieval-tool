"""
DataForSEO SEO Tools
Multi-page Streamlit application for SEO data analysis.
"""

import streamlit as st
from ui_components import setup_page_config, render_credentials_sidebar
from dataforseo_client import SERPClient

# Configure page
setup_page_config(title="DataForSEO SEO Tools", layout="wide")

st.title("🚀 DataForSEO SEO Tools")

st.markdown("""
Welcome to the DataForSEO SEO Tools suite! This application provides powerful SEO analysis tools powered by DataForSEO APIs.

## 📋 Available Tools

""")

# Navigation buttons
col1, col2 = st.columns(2)

with col1:
    rank_tracking_btn = st.button("📊 Go to Rank Tracking", use_container_width=True, type="primary", key="btn_rank")

with col2:
    search_volume_btn = st.button("🔍 Go to Search Volume", use_container_width=True, type="primary", key="btn_search")

# Handle navigation
if rank_tracking_btn:
    st.switch_page("pages/1_📊_Rank_Tracking.py")

if search_volume_btn:
    st.switch_page("pages/2_🔍_Search_Volume.py")

st.markdown("""

---

## 🔐 Getting Started

### 1. Get Your API Credentials
Visit [DataForSEO API Access](https://app.dataforseo.com/api-access) to get your login and password.

### 2. Enter Credentials
Enter your credentials in the sidebar (on any page) to get started.

### 3. Choose Your Tool
Navigate to the tool you want to use from the sidebar or using the links above.

---

## 💡 About DataForSEO

DataForSEO provides comprehensive SEO and digital marketing data through their APIs:

- **SERP API**: Search engine results data
- **Keywords Data API**: Search volume, keyword difficulty, and more
- **Backlinks API**: Backlink data and analysis
- **On-Page API**: Technical SEO audits

Learn more: [dataforseo.com](https://dataforseo.com)

---

## 🛠️ Support

Having issues? Check out:
- [DataForSEO Documentation](https://docs.dataforseo.com/)
- [DataForSEO Help Center](https://dataforseo.com/help-center)
- [GitHub Issues](https://github.com/samunderwood/bulk-rank-retrieval-tool/issues)
""")


client = render_credentials_sidebar(SERPClient)

if client:
    st.sidebar.success("✅ Credentials verified!")
else:
    st.sidebar.warning("⚠️ Please enter your credentials above")

st.sidebar.divider()
st.sidebar.markdown("""
### 📚 Quick Links
- [API Access Dashboard](https://app.dataforseo.com/api-access)
- [API Documentation](https://docs.dataforseo.com/)
- [Pricing](https://dataforseo.com/apis/pricing)
""")
