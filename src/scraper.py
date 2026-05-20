import os
import time
from edgar import set_identity, get_filings, Company
from dotenv import load_dotenv
from database_utils import save_records_to_db

load_dotenv()
set_identity(os.getenv("SEC_IDENTITY"))

def safe_float(obj, attr, default=0.0):
    val = getattr(obj, attr, None)
    return float(val) if val is not None else default
def safe_int(obj, attr, default=0):
    val = getattr(obj, attr, None)
    return int(val) if val is not None else default
def safe_str(obj, attr, default="UNKNOWN"):
    val = getattr(obj, attr, None)
    return str(val) if val is not None else default

def parse_filing_to_record(filing):
    """Parses the filing safely. Returns None if parsing fails."""
    try:
        form_data = filing.obj()
        summary = form_data.get_ownership_summary()

       # 1. Keep your existing clean filing date logic
        filing_date_str = filing.filing_date.strftime("%Y-%m-%d") if getattr(filing, 'filing_date', None) else None
        
        # 2. THE FIX: Safely convert the raw transaction date into a clean string!
        raw_tx_date = getattr(summary, 'reporting_date', None)
        if hasattr(raw_tx_date, 'strftime'):
            transaction_date_str = raw_tx_date.strftime("%Y-%m-%d")
        else:
            transaction_date_str = str(raw_tx_date) if raw_tx_date else None

        activity = getattr(summary, 'primary_activity', None)
        if activity not in ["Purchase", "Sale"]:
            return None
        
        return {
            "accession_no": filing.accession_number,
            "ticker": safe_str(summary, "issuer_ticker"),
            "company": safe_str(summary, "issuer_name"),
            "insider_name": safe_str(summary, "insider_name"),
            "position": safe_str(summary, "position"),
            "transaction_date": transaction_date_str,
            "filing_date": filing_date_str,
            "net_shares": safe_int(summary, "net_change"),
            "net_value": safe_float(summary, "net_value"),
            "is_purchase": activity == "Purchase"
        }
    except Exception as e:
        print(f"Error parsing {filing.accession_number}: {e}")
        return None
    
def run_pipeline():
    print("Scraper starting")
    #If I want to test on a specific company I can do like this and set filings=company.get_filings...
    #roblox=Company("RBLX")
    filings = get_filings(form="4").latest(10)
    records = []
    for f in filings:
        record = parse_filing_to_record(f)
        if record is None:
            continue 
        records.append(record)
        print(f"Parsed {record['ticker']} trade by {record['insider_name']}")
    print(f"-- Scrape Complete: Found {len(records)} records")
    save_records_to_db(records)
    return records
if __name__ == "__main__":
    run_pipeline()