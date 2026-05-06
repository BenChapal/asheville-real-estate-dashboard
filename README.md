# Asheville Real Estate Market Dashboard

A live, automated real estate market dashboard tracking home sale prices, rental rates, and market trends across all 15 neighborhoods in Buncombe County, NC.

## Live Dashboard
👉 [View the live dashboard](https://benchapal.streamlit.app/asheville-market-dashboard)

## What It Does
- Tracks median sale prices and rental rates across 15 Buncombe County zip codes
- Shows 6-month historical price trends by neighborhood
- Compares days on market, total listings, and price-to-rent ratios
- Automatically refreshes data twice monthly (1st and 15th)
- Monitors API usage to stay within free tier limits

## Data Source
- **Rentcast API** — live rental and sale market data updated daily
- **Coverage** — Downtown Asheville, South, North, East, West Asheville, Candler, Fairview, Fletcher, Leicester, Swannanoa, Weaverville, Alexander, Arden, Barnardsville, Black Mountain

## Tech Stack
- **Python** — data collection and processing
- **Rentcast API** — real estate market data
- **Pandas** — data manipulation and analysis
- **Streamlit** — interactive web dashboard
- **Matplotlib/Seaborn** — data visualization
- **Folium** — interactive mapping
- **GitHub Actions + Cron** — automated scheduling

## Project Structure
- `asheville_dashboard.py` — Streamlit dashboard
- `update_data.py` — Automated data refresh script
- `asheville_market_data.csv` — Local data store
- `api_usage.json` — API call tracker
- `requirements.txt` — Python dependencies

## Running Locally
1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Add your Rentcast API key: `export RENTCAST_API_KEY="your_key_here"`
4. Run the dashboard: `streamlit run asheville_dashboard.py`

## Automated Data Refresh
The `update_data.py` script runs automatically on the 1st and 15th of every month via cron, pulling fresh market data for all 15 zip codes while tracking API usage against the monthly limit.

## Author
Ben Chapal | [GitHub](https://github.com/BenChapal)
