# Bulk Rank Retrieval Tool

A Streamlit-based web application for bulk keyword rank checking using the DataForSEO API.

## Features

- **Two modes**: Live (immediate) and Standard (batched) rank retrieval
- **Customizable search parameters**: Location, language, device, OS, and search depth
- **Bulk processing**: Handle multiple keywords simultaneously
- **Real-time progress tracking**: Visual progress bars for both submission and retrieval
- **CSV export**: Download results for further analysis
- **Rate limiting controls**: Configurable parallel workers and RPM limits

## Prerequisites

- Python 3.8+
- DataForSEO API credentials (login/password or API key)
- Streamlit

## Installation

1. Clone the repository:
```bash
git clone https://github.com/samunderwood/bulk-rank-retrieval-tool.git
cd bulk-rank-retrieval-tool
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up your DataForSEO credentials in `.streamlit/secrets.toml`:
```toml
DATAFORSEO_LOGIN = "your_login"
DATAFORSEO_PASSWORD = "your_password"
# OR
DATAFORSEO_API_KEY = "your_api_key"
```

## Usage

Run the application:
```bash
streamlit run app.py
```

Then navigate to `http://localhost:8501` in your browser.

### Live Mode
- Immediate results for each keyword
- Configurable parallel workers (1-24)
- RPM rate limiting (30-1200)
- Launch delay controls

### Standard Mode
- Batched task submission
- Configurable batch size (10-1000 tasks per POST)
- Max in-flight tasks control (100-5000)
- Parallel result fetching (2-48)

## Configuration

### Target Domain
Enter your domain without protocol (e.g., `example.com`)

### Location & Language
- Select country by ISO code
- Override with specific location from dropdown
- Choose from available languages

### Device & OS
- Desktop: Windows, macOS
- Mobile: Android, iOS

### Search Parameters
- **Depth**: Number of results to check (10-200)
- **Include subdomains**: Check all subdomains of target domain

## Output

Results include:
- Keyword
- Found status
- Organic rank
- Absolute rank
- URL and title
- Search engine domain
- Location, language, device, OS
- Search depth
- Notes (errors or warnings)

## License

MIT License

## Credits

Built with [Streamlit](https://streamlit.io/) and [DataForSEO API](https://dataforseo.com/)
