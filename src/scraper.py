import os
import time
from edgar import set_identity, get_filings, Company
from dotenv import load_dotenv

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

def test_if_relevant(filing):
    return filing.obj().get_ownership_summary().primary_activity in ["Purchase", "Sale"]
def parse_filing_to_record(filing):
    try:
        form_data = filing.obj()
        summary = form_data.get_ownership_summary()
        return {
            "accession_no": filing.accession_number,
            "filing_date": filing.filing_date,
            "ticker": safe_str(summary, "issuer_ticker"),
            "company": safe_str(summary, "issuer_name"),
            "insider_name": safe_str(summary, "insider_name"),
            "position": safe_str(summary, "position"),
            "transaction_date": safe_str(summary, "reporting_date"),
            "net_shares": safe_int(summary, "net_change"),
            "net_value": safe_float(summary, "net_value"),
            "is_purchase": getattr(summary, 'primary_activity', None) == "Purchase"
        }
    except Exception as e:
        print(f"Error parsing {filing.accession_number}: {e}")
        return None

def run_pipeline():
    print("Scraper starting")
    #If I want to test on a specific company I can do like this and set filings=company.get_filings...
    #roblox=Company("BROS")
    filings = get_filings(form="4").latest(10)
    records = []
    net_value=0
    purchases=0
    sales=0
    for f in filings:
        if test_if_relevant(f):
            record = parse_filing_to_record(f)
            records.append(record)
            net_value += record["net_value"]
            if record["is_purchase"]:
                purchases += 1
            else:
                sales += 1
            print(f"Parsed {record['ticker']} trade by {record['insider_name']}")
    print(f"-- Scrape Complete: Found {len(records)} records")
    print(f"Total net value: {net_value}")
    print(f"%Sales: {sales*100/(purchases+sales):.2f}%")
    return records
if __name__ == "__main__":
    run_pipeline()