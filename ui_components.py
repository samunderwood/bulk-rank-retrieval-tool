"""
Reusable UI Components for DataForSEO tools
"""
import streamlit as st
import pandas as pd
from typing import Optional, Tuple
from dataforseo_client import DataForSEOClient


def setup_page_config(title: str = "DataForSEO Tool", layout: str = "wide"):
    """Configure Streamlit page settings."""
    st.set_page_config(page_title=title, layout=layout)


def render_credentials_sidebar(client_class=DataForSEOClient) -> Optional[Tuple]:
    """
    Render credentials input in sidebar and return authenticated client.
    
    Args:
        client_class: DataForSEOClient subclass to instantiate
    
    Returns:
        Tuple of (client instance, headers dict, auth tuple) or None
    """
    # Initialize session state
    if "user_login" not in st.session_state:
        st.session_state.user_login = ""
    if "user_password" not in st.session_state:
        st.session_state.user_password = ""
    if "remember_creds" not in st.session_state:
        st.session_state.remember_creds = False
    
    st.sidebar.header("🔐 DataForSEO Credentials")
    st.sidebar.info("Don't have an account? [Sign up here](https://dataforseo.com/)")
    
    # Check for admin credentials in secrets
    admin_client = None
    try:
        login = st.secrets.get("DATAFORSEO_LOGIN")
        password = st.secrets.get("DATAFORSEO_PASSWORD")
        if login and password:
            admin_client = client_class(login=login, password=password)
    except:
        pass
    
    if admin_client:
        use_admin = st.sidebar.checkbox(
            "Use configured credentials", 
            value=False,
            help="Use credentials from Streamlit secrets (for private deployments)"
        )
        if use_admin:
            st.sidebar.success("✅ Using configured credentials")
            return admin_client
    
    # User credential inputs
    user_login = st.sidebar.text_input(
        "Login",
        type="default",
        placeholder="your_login",
        value=st.session_state.user_login,
        key="login_input"
    )
    user_password = st.sidebar.text_input(
        "Password",
        type="password",
        placeholder="your_password",
        value=st.session_state.user_password,
        key="password_input"
    )
    
    # Remember credentials
    remember = st.sidebar.checkbox(
        "Remember credentials",
        value=st.session_state.remember_creds,
        help="Keep credentials for this browser session"
    )
    
    if remember and user_login and user_password:
        st.session_state.user_login = user_login
        st.session_state.user_password = user_password
        st.session_state.remember_creds = True
    elif not remember:
        st.session_state.remember_creds = False
    
    # Clear credentials button
    if st.session_state.user_login or st.session_state.user_password:
        if st.sidebar.button("🗑️ Clear saved credentials"):
            st.session_state.user_login = ""
            st.session_state.user_password = ""
            st.session_state.remember_creds = False
            st.session_state.credentials_verified = False
            st.rerun()
    
    if user_login and user_password:
        try:
            client = client_class(login=user_login, password=user_password)
            return client
        except Exception as e:
            st.error(f"Error creating client: {e}")
            return None
    else:
        # Don't stop - let the page show a message instead
        return None


def verify_credentials(client: DataForSEOClient) -> bool:
    """
    Verify client credentials and show appropriate messages.
    
    Args:
        client: DataForSEOClient instance
    
    Returns:
        True if credentials are valid, False otherwise
    """
    # Show tip only on first verification
    if not st.session_state.get("credentials_verified", False):
        st.info("👈 **Tip:** Check 'Remember credentials' in the sidebar to keep them for your browser session.")
    
    try:
        with st.spinner("Verifying credentials..."):
            success, message = client.test_connection()
            
            if success:
                st.session_state.credentials_verified = True
                return True
            else:
                st.error(f"❌ **{message}**")
                st.session_state.credentials_verified = False
                st.stop()
                
    except Exception as e:
        st.error(f"❌ **Connection Error**: {str(e)}")
        st.session_state.credentials_verified = False
        st.stop()


def render_location_selector(client: DataForSEOClient, serp_type: str = "google",
                             default_country: str = "GB") -> Tuple[int, Optional[str]]:
    """
    Render location selection UI (country + optional specific location).
    
    Args:
        client: DataForSEOClient instance
        serp_type: SERP type (google, bing, etc.)
        default_country: Default country ISO code
    
    Returns:
        Tuple of (location_code: int, country_iso: str)
    """
    # Load countries
    if "countries_df" not in st.session_state:
        with st.spinner("Loading countries..."):
            countries = client.get_locations(serp_type=serp_type)
            df = pd.DataFrame(countries)
            if not df.empty:
                countries_df = df[df["location_type"] == "Country"].copy()
                countries_df = countries_df[["location_name", "location_code", "country_iso_code"]].drop_duplicates()
                countries_df = countries_df.sort_values("location_name").reset_index(drop=True)
                st.session_state.countries_df = countries_df
            else:
                st.session_state.countries_df = pd.DataFrame()
    
    countries_df = st.session_state.countries_df
    
    if countries_df.empty:
        st.error("Unable to load countries from DataForSEO API")
        st.stop()
    
    # Country dropdown
    country_options = [
        f"{row.location_name} ({row.country_iso_code}) [{row.location_code}]"
        for row in countries_df.itertuples()
    ]
    
    # Find default index
    default_idx = 0
    for idx, row in enumerate(countries_df.itertuples()):
        if row.country_iso_code.upper() == default_country.upper():
            default_idx = idx
            break
    
    country_selection = st.selectbox(
        "Country",
        country_options,
        index=default_idx,
        help="Select the country for search rankings"
    )
    
    # Extract country info
    selected_country_iso = country_selection.split("(")[1].split(")")[0] if "(" in country_selection else default_country
    
    def parse_location_code(s: str) -> Optional[int]:
        if "[" in s and "]" in s:
            try:
                return int(s.split("[")[-1].split("]")[0])
            except:
                return None
        return None
    
    location_code = parse_location_code(country_selection)
    
    # Optional specific location override
    with st.expander("🔍 Advanced: Override with specific location (city/region)"):
        st.info("By default, we use country-level location. Expand to select a specific city or region.")
        
        if st.checkbox("Use specific location instead of country"):
            with st.spinner(f"Loading locations for {selected_country_iso}..."):
                locations = client.get_locations(serp_type=serp_type, country_iso=selected_country_iso.lower())
                loc_df = pd.DataFrame(locations)
            
            if not loc_df.empty:
                specific_locs = loc_df[loc_df["location_type"] != "Country"]
                if not specific_locs.empty:
                    loc_options = [
                        f'{row.location_name} [{row.location_code}] — {row.location_type}'
                        for row in specific_locs.itertuples()
                    ]
                    specific_location = st.selectbox("Specific Location", loc_options)
                    override_code = parse_location_code(specific_location)
                    if override_code:
                        location_code = override_code
                else:
                    st.warning("No specific locations available for this country")
    
    return location_code, selected_country_iso


def render_language_selector(client: DataForSEOClient, serp_type: str = "google",
                             default_language: str = "en") -> str:
    """
    Render language selection UI.
    
    Args:
        client: DataForSEOClient instance
        serp_type: SERP type (google, bing, etc.)
        default_language: Default language code
    
    Returns:
        Selected language code
    """
    # Load languages
    if "lang_df" not in st.session_state:
        with st.spinner("Loading languages..."):
            languages = client.get_languages(serp_type=serp_type)
            lang_df = pd.DataFrame(languages)
            if not lang_df.empty:
                lang_df = lang_df[["language_name", "language_code"]].drop_duplicates()
                lang_df = lang_df.sort_values("language_name").reset_index(drop=True)
                st.session_state.lang_df = lang_df
            else:
                st.session_state.lang_df = pd.DataFrame()
    
    lang_df = st.session_state.lang_df
    
    if not lang_df.empty:
        lang_options = [f"{row.language_name} [{row.language_code}]" for row in lang_df.itertuples()]
    else:
        lang_options = [f"English [{default_language}]"]
    
    # Find default index
    default_idx = 0
    for idx, option in enumerate(lang_options):
        if f"[{default_language}]" in option:
            default_idx = idx
            break
    
    language = st.selectbox("Language", lang_options, index=default_idx)
    
    # Extract language code
    if "[" in language and "]" in language:
        return language.split("[")[-1].split("]")[0]
    return default_language


def render_results_table(df: pd.DataFrame, domain: str = ""):
    """
    Render results in a nice table with metrics.
    
    Args:
        df: Results dataframe
        domain: Domain name for filename
    """
    st.divider()
    st.subheader("📊 Results")
    
    # Summary metrics
    found_count = df["found"].sum() if "found" in df.columns else 0
    total_count = len(df)
    
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Keywords", total_count)
    col2.metric("Found", found_count)
    col3.metric("Not Found", total_count - found_count)
    
    # Display table
    st.dataframe(df, width="stretch", height=400)
    
    # Download button
    csv = df.to_csv(index=False).encode("utf-8")
    filename = f"dataforseo_results_{domain}_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.csv"
    st.download_button(
        label="📥 Download Results as CSV",
        data=csv,
        file_name=filename,
        mime="text/csv",
        use_container_width=True
    )
    
    # Show sample of results if applicable
    if "found" in df.columns and found_count > 0:
        with st.expander("🎯 Preview Top Results"):
            preview_cols = [col for col in ["keyword", "organic_rank", "absolute_rank", "url", "title"] 
                           if col in df.columns]
            found_df = df[df["found"] == True][preview_cols].head(10)
            st.dataframe(found_df, width="stretch")

