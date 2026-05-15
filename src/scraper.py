import os
import time
from edgar import set_identity, get_filings
from dotenv import load_dotenv

load_dotenv()
set_identity(os.getenv("SEC_IDENTITY"))

def parse_filing_to_record(filing):
    """
    Turns a raw SEC filing into a clean Python dictionary.
    """
    try:
        # 'obj()' handles the heavy lifting of parsing XML/XBRL
        form_data = filing.obj()
        
        # We use a summary method to get the "bottom line" of the trade
        summary = form_data.get_ownership_summary()
        return {
            "accession_no": filing.accession_number,
            "ticker": summary.issuer_ticker,
            "company": summary.issuer_name,
            "insider_name": summary.insider_name,
            "position": summary.position,
            "transaction_date": summary.reporting_date,
            "filing_date": filing.filing_date,
            "net_shares": summary.net_change,
            "net_value": summary.net_value,
            "is_purchase": summary.primary_activity == "Purchase"
        }
    except Exception as e:
        print(f"Error parsing {filing.accession_number}: {e}")
        return None

def run_pipeline():
    print("Scraper starting")
    
    # Fetch latest 20 Form 4s (Insider Trading)
    filings = get_filings(form="4").latest(20)
    
    records = []
    for f in filings:
        record = parse_filing_to_record(f)
        if record:
            records.append(record)
            print(f"✅ Parsed {record['ticker']} trade by {record['insider_name']}")
    
    print(f"\n--- Scrape Complete: Found {len(records)} records ---")
    # This is where we will call our database_utils soon!
    return records

def run_pipeline_once():
    print("Scraper starting once")
    
    # Fetch latest 20 Form 4s (Insider Trading)
    filing = get_filings(form="4").latest(1)
    print(filing.obj().get_ownership_summary())
    print(filing)
    print(filing.obj())
    return 1
if __name__ == "__main__":
    run_pipeline()