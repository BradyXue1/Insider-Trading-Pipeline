import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import yfinance as yf

CACHE_FILE = "filings_cache.parquet"
MASTER_BACKTEST_FILE = "insider_trading_master_backtest.parquet"

def get_data(force_refresh=False):
    if os.path.exists(CACHE_FILE) and not force_refresh:
        print("📖 Loading raw data from local cache...")
        return pd.read_parquet(CACHE_FILE)
        
    print("🔌 Fetching fresh data from MongoDB...")
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI"))
    collection = client["insider_trading"]["filings"]
    
    df = pd.DataFrame(list(collection.find({})))
    if not df.empty and '_id' in df.columns:
        df = df.drop(columns=['_id'])
        
    df.to_parquet(CACHE_FILE, index=False)
    return df

def fetch_ticker_prices_for_dates(ticker, dates_needed):
    """
    Fetches minimal daily price history covering the span of required dates,
    returning a clean dictionary mapping string dates to close prices.
    """
    if not dates_needed:
        return {}
    
    # Calculate a safe bounding box for this specific ticker's timeline
    start_str = (min(dates_needed) - pd.Timedelta(days=5)).strftime('%Y-%m-%d')
    end_str = (max(dates_needed) + pd.Timedelta(days=5)).strftime('%Y-%m-%d')
    
    try:
        # Fetch clean history directly
        history = yf.download(ticker, start=start_str, end=end_str, progress=False, group_by='ticker')
        if history.empty:
            return {}
            
        # Handle structural consistency if yfinance multi-indexes the columns
        if isinstance(history.columns, pd.MultiIndex):
            close_series = history.loc[:, (ticker, 'Close')] if ticker in history.columns.levels[0] else history['Close']
        else:
            close_series = history['Close']
            
        # Strip timezone info and drop missing rows
        close_series.index = close_series.index.tz_localize(None)
        close_series = close_series.dropna()
        
        # Turn it into a flat, fast lookup: { 'YYYY-MM-DD': price }
        return {date.strftime('%Y-%m-%d'): float(val) for date, val in close_series.items()}
    except Exception:
        return {}

def add_price_horizons_inverted(df, ticker_col='ticker', date_col='transaction_date'):
    df_clean = df.copy()
    
    # 1. Force strict datetime conversion and turn garbage text into NaT
    df_clean[date_col] = pd.to_datetime(df_clean[date_col], errors='coerce', utc=True)
    
    # 2. DROP ROWS WITH YEAR 0 OR PREHISTORIC DATES (The Crash Fix)
    # This guarantees every year is strictly between 2010 and 2030
    initial_len = len(df_clean)
    df_clean = df_clean[
        (df_clean[date_col].dt.year >= 2010) & 
        (df_clean[date_col].dt.year <= 2030)
    ]
    
    dropped_dates = initial_len - len(df_clean)
    if dropped_dates > 0:
        print(f"🧹 Cleaned out {dropped_dates} rows with corrupt/impossible years (e.g., year 0 or year 0001).")
        
    # Strip timezone info out safely
    df_clean[date_col] = df_clean[date_col].dt.tz_localize(None)
    
    print("🗓️ Pre-calculating exact target calendar horizons...")
    # ... the rest of your original horizons logic follows ...
    horizons = {
        'price_trade_day': lambda d: d,
        'price_1d_later':  lambda d: d + pd.Timedelta(days=1),
        'price_1w_later':  lambda d: d + pd.Timedelta(weeks=1),
        'price_1m_later':  lambda d: d + pd.DateOffset(months=1),
        'price_3m_later':  lambda d: d + pd.DateOffset(months=3),
        'price_6m_later':  lambda d: d + pd.DateOffset(months=6)
    }
    
    # Populate empty baseline tracking columns
    for col in horizons.keys():
        df_clean[col] = None

    # Group records by ticker so we only call Yahoo Finance ONCE per individual asset
    grouped = df_clean.groupby(ticker_col)
    total_tickers = len(grouped)
    
    print(f"🚀 Processing exactly {total_tickers} unique asset clusters...")
    
    processed_dfs = []
    
    for idx, (ticker, group_df) in enumerate(grouped, 1):
        if idx % 50 == 0 or idx == 1:
            print(f"📦 Processing [{idx}/{total_tickers}] -> {ticker}")
            
        # Collect every target date this ticker will ever need to look up
        all_required_dates = set()
        row_target_maps = []
        
        for _, row in group_df.iterrows():
            base_date = row[date_col]
            targets = {}
            for h_name, h_func in horizons.items():
                target_date = h_func(base_date)
                targets[h_name] = target_date
                all_required_dates.add(target_date)
            row_target_maps.append(targets)
            
        # Fetch the historical price block map for this specific ticker
        price_lookup = fetch_ticker_prices_for_dates(ticker, list(all_required_dates))
        
        if not price_lookup:
            # If the ticker is dead or missing, yield the rows with None values
            processed_dfs.append(group_df)
            continue
            
        # Match target dates against our real price lookup map
        # If an exact match isn't found, walk backwards up to 4 days to handle weekends/holidays
        updated_rows = []
        for (_, row), targets in zip(group_df.iterrows(), row_target_maps):
            for h_name, target_date in targets.items():
                matched_price = None
                # Check target day, then step backward up to 4 days if it falls on a closed market day
                for days_back in range(5):
                    check_str = (target_date - pd.Timedelta(days=days_back)).strftime('%Y-%m-%d')
                    if check_str in price_lookup:
                        matched_price = price_lookup[check_str]
                        break
                row[h_name] = matched_price
            updated_rows.append(row)
            
        processed_dfs.append(pd.DataFrame(updated_rows))
        
    final_df = pd.concat(processed_dfs, axis=0).reset_index(drop=True)
    return final_df

def upload_saved_file_to_mongo():
    print(f"📖 Reading compiled data from '{MASTER_BACKTEST_FILE}'...")
    df = pd.read_parquet(MASTER_BACKTEST_FILE)
    
    print("🔌 Connecting to MongoDB...")
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client["insider_trading"]
    collection = db["filings_with_prices_2"]
    
    print("🧹 Cleaning NaNs out for MongoDB compatibility...")
    df_clean = df.astype(object).where(pd.notnull(df), None)
    records = df_clean.to_dict(orient='records')
    
    if records:
        print(f"📤 Uploading {len(records)} documents to 'filings_with_prices'...")
        collection.delete_many({}) 
        result = collection.insert_many(records)
        print(f"✅ SUCCESS! Inserted {len(result.inserted_ids)} records.")
    else:
        print("⚠️ Warning: No records found to upload.")

if __name__ == "__main__":
    # 1. SILENCE YAHOO FINANCE LOGGING NOISE
    import logging
    logging.getLogger('yfinance').setLevel(logging.CRITICAL)
    
    df = get_data(force_refresh=True)
    
    if not df.empty:
        print(f"Loaded {len(df)} rows. Standardizing text filters...")
        df['accession_no'] = df['accession_no'].astype(str).str.strip()
        df = df.drop_duplicates(subset=['accession_no'], keep='first')
        
        if 'net_shares' in df.columns:
            df = df[df['net_shares'] != 0]
            
        # 2. STRIP QUOTES AND WHITESPACE BEFORE CLEANING CHARACTER MATCHES
        df['ticker'] = df['ticker'].astype(str).str.replace('"', '').str.replace("'", "").str.upper().str.strip()
        
        # Keep ONLY core alphabetic characters
        df['ticker'] = df['ticker'].str.replace(r"[^A-Z]", "", regex=True)
        
        # 3. EXPLICITLY DROP TRASH TICKERS BEFORE COMPILING
        trash_tickers = {'NONE', 'NA', 'UNKNOWN', 'NULL', 'NAN'}
        df = df[~df['ticker'].isin(trash_tickers)]
        df = df[df['ticker'].str.len() > 0]
        
        print(f"Filtered dataset down to {len(df)} active rows. Compiling target matrix...")
        
        df_master = add_price_horizons_inverted(df)
        df_master.to_parquet(MASTER_BACKTEST_FILE, index=False)
        print(f"\n🎉 Master file successfully created and saved to '{MASTER_BACKTEST_FILE}'")
        
        upload_saved_file_to_mongo()