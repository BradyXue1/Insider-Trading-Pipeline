import os
import hashlib
import pandas as pd
from edgar import set_identity, get_filings 
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne

load_dotenv()
set_identity(os.getenv("SEC_IDENTITY"))

for year in [2022, 2023, 2024, 2025]:
    print(f"\n--- ANALYZING YEAR {year} ---")
    
    # Fetch index payload
    filings = get_filings(year=year, form="4")
    df = filings.to_pandas()
    
    # Total raw lines from SEC
    total_raw_rows = len(df)
    
    # Filter using your specific conditions: valid ticker AND net_value != 0
    if 'ticker' in df.columns and 'net_value' in df.columns:
        filtered_df = df[
            df['ticker'].notna() & (df['ticker'] != "UNKNOWN") & (df['ticker'] != "") &
            df['net_value'].notna() & (df['net_value'] != 0)
        ]
    else:
        filtered_df = df
        
    total_filtered_rows = len(filtered_df)
    
    # Count unique filings (Accession Numbers) that survive the filter
    acc_col = "accession_number" if "accession_number" in df.columns else "accession_no"
    if acc_col in filtered_df.columns:
        unique_filings = filtered_df[acc_col].nunique()
    else:
        unique_filings = "Unknown"
    
    print(f"Raw lines in SEC Index:          {total_raw_rows:,}")
    print(f"Lines with Ticker & Non-Zero:   {total_filtered_rows:,}")
    print(f"Actual Unique Documents (_id):   {unique_filings:,}")