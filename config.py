"""
HMA Stock Scanner — Configuration
All tunable parameters, sector mappings, and stock universes.
"""

# ─── Indicator Parameters ────────────────────────────────────────
HMA_FAST_PERIOD = 20
HMA_SLOW_PERIOD = 55
RSI_PERIOD = 14
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9
OBV_SLOPE_LOOKBACK = 20
HMA_SLOPE_LOOKBACK = 5
VOLUME_LOOKBACK = 20

# ─── Scoring Thresholds ─────────────────────────────────────────
RSI_MIN = 40
RSI_MAX = 65
OVEREXTENSION_THRESHOLD = 15  # %
STOP_LOSS_MULTIPLIER = 0.97
MAX_RISK_PCT = 7  # %
FRESHNESS_TIER1_DAYS = 10
FRESHNESS_TIER2_DAYS = 20

# ─── Score Classification ───────────────────────────────────────
HIGH_CONVICTION_MIN = 7
WATCHLIST_MIN = 4

# ─── Data Fetching ──────────────────────────────────────────────
DAILY_DATA_DAYS = 600  # ~2 years for weekly HMA55
CHUNK_SIZE_DAYS = 35   # NSE API limit per request
REQUEST_DELAY = 0.5    # seconds between API requests
DELIVERY_LOOKBACK_DAYS = 30

# ─── Symbol → Sector Mapping ────────────────────────────────────
SYMBOL_SECTOR_MAP = {
    # Pharma (+1)
    "SUNPHARMA": "Pharma", "DRREDDY": "Pharma", "CIPLA": "Pharma",
    "DIVISLAB": "Pharma", "AUROPHARMA": "Pharma", "BIOCON": "Pharma",
    "LUPIN": "Pharma", "TORNTPHARM": "Pharma", "ALKEM": "Pharma",
    "LAURUSLABS": "Pharma", "GLENMARK": "Pharma", "IPCALAB": "Pharma",
    "NATCOPHARMA": "Pharma", "ABBOTINDIA": "Pharma", "SYNGENE": "Pharma",
    "ZYDUSLIFE": "Pharma", "GRANULES": "Pharma", "AJANTPHARM": "Pharma",
    # Healthcare (+1)
    "APOLLOHOSP": "Healthcare", "MAXHEALTH": "Healthcare",
    "FORTIS": "Healthcare", "METROPOLIS": "Healthcare",
    "LALPATHLAB": "Healthcare",
    # Defence (+1)
    "HAL": "Defence", "BEL": "Defence", "COCHINSHIP": "Defence",
    "DATAPATTNS": "Defence", "MAZAGONDOCK": "Defence", "GRSE": "Defence",
    "BDL": "Defence",
    # PSU (+1)
    "COALINDIA": "PSU", "IRCTC": "PSU", "IRFC": "PSU",
    "BANKBARODA": "PSU", "CANBK": "PSU", "PNB": "PSU",
    "INDIANB": "PSU", "BHEL": "PSU", "NBCC": "PSU",
    "NHPC": "PSU", "SJVN": "PSU", "RECLTD": "PSU", "PFC": "PSU",
    "HUDCO": "PSU", "CONCOR": "PSU", "NLCINDIA": "PSU", "NMDC": "PSU",
    "SAIL": "PSU",
    # Infra (+1)
    "LT": "Infra", "ADANIPORTS": "Infra", "IRB": "Infra",
    "NCC": "Infra", "KEC": "Infra", "ENGINERSIN": "Infra",
    # Power (+1)
    "NTPC": "Power", "POWERGRID": "Power", "TATAPOWER": "Power",
    "ADANIGREEN": "Power", "JSWENERGY": "Power", "CESC": "Power",
    "TORNTPOWER": "Power",
    # Energy (+1)
    "RELIANCE": "Energy", "ONGC": "Energy", "BPCL": "Energy",
    "HINDPETRO": "Energy", "IOC": "Energy", "GAIL": "Energy",
    "OIL": "Energy", "PETRONET": "Energy", "GUJGASLTD": "Energy",
    "MGL": "Energy", "IGL": "Energy", "ADANIENT": "Energy",
    # IT (0)
    "TCS": "IT", "INFY": "IT", "WIPRO": "IT", "HCLTECH": "IT",
    "TECHM": "IT", "LTIM": "IT", "COFORGE": "IT", "MPHASIS": "IT",
    "PERSISTENT": "IT", "LTTS": "IT", "TATAELXSI": "IT",
    # FMCG (0)
    "HINDUNILVR": "FMCG", "ITC": "FMCG", "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG", "DABUR": "FMCG", "MARICO": "FMCG",
    "GODREJCP": "FMCG", "COLPAL": "FMCG", "TATACONSUM": "FMCG",
    "EMAMILTD": "FMCG", "VBL": "FMCG", "UBL": "FMCG",
    # Auto (0)
    "MARUTI": "Auto", "TATAMOTORS": "Auto", "M&M": "Auto",
    "BAJAJ-AUTO": "Auto", "HEROMOTOCO": "Auto", "EICHERMOT": "Auto",
    "ASHOKLEY": "Auto", "TVSMOTORS": "Auto", "BHARATFORG": "Auto",
    "MRF": "Auto", "BOSCH": "Auto", "MOTHERSON": "Auto",
    # Banks (0)
    "HDFCBANK": "Banks", "ICICIBANK": "Banks", "SBIN": "Banks",
    "KOTAKBANK": "Banks", "AXISBANK": "Banks", "INDUSINDBK": "Banks",
    "BANDHANBNK": "Banks", "IDFCFIRSTB": "Banks", "AUBANK": "Banks",
    "FEDERALBNK": "Banks",
    # Finance (0)
    "BAJFINANCE": "Finance", "BAJAJFINSV": "Finance", "SBILIFE": "Finance",
    "HDFCLIFE": "Finance", "ICICIPRU": "Finance", "CHOLAFIN": "Finance",
    "SHRIRAMFIN": "Finance", "MUTHOOTFIN": "Finance",
    "MANAPPURAM": "Finance", "M&MFIN": "Finance", "LICHSGFIN": "Finance",
    # Metal/Steel (-1)
    "TATASTEEL": "Metal", "JSWSTEEL": "Steel", "HINDALCO": "Metal",
    "VEDL": "Metal", "NATIONALUM": "Metal", "JINDALSTEL": "Steel",
    "APLAPOLLO": "Steel", "HINDZINC": "Metal",
    # Other Neutral (0)
    "TITAN": "Consumer", "ASIANPAINT": "Consumer", "PIDILITIND": "Chemicals",
    "GRASIM": "Cement", "ULTRACEMCO": "Cement", "AMBUJACEM": "Cement",
    "SHREECEM": "Cement", "BHARTIARTL": "Telecom", "DLF": "Realty",
    "GODREJPROP": "Realty", "OBEROIRLTY": "Realty", "PIIND": "Chemicals",
    "UPL": "Chemicals", "SRF": "Chemicals", "TRENT": "Consumer",
    "DMART": "Consumer", "ZOMATO": "Consumer",
}

# ─── Default Stock Universes ────────────────────────────────────
NIFTY_50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BEL", "BPCL",
    "BHARTIARTL", "BRITANNIA", "CIPLA", "COALINDIA", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NTPC", "NESTLEIND", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SUNPHARMA",
    "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TECHM",
    "TITAN", "ULTRACEMCO", "WIPRO", "SHRIRAMFIN",
]
