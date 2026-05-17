import os
import time
from edgar import set_identity, get_filings
from dotenv import load_dotenv

load_dotenv()
set_identity(os.getenv("SEC_IDENTITY"))
def test_if_relevant(filing):
    return filing.obj().get_ownership_summary().primary_activity in ["Purchase", "Sale"]
def parse_filing_to_record(filing):
    """
    Turns a raw SEC filing into a clean Python dictionary.
    """
    try:
        form_data = filing.obj()
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
    filings = get_filings(form="4").latest(10)
    records = []
    for f in filings:
        if test_if_relevant(f):
            record = parse_filing_to_record(f)
            records.append(record)
            print(f"Parsed {record['ticker']} trade by {record['insider_name']}")
    print(f"-- Scrape Complete: Found {len(records)} records")
    return records
if __name__ == "__main__":
    print(run_pipeline())