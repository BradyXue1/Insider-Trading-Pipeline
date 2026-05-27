import os
import time
import hashlib
from edgar import set_identity, get_filings 
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
import edgar.httprequests

os.environ['EDGAR_RATE_LIMIT_PER_SEC'] = '5'  # Keep it safely below 10

load_dotenv()
set_identity(os.getenv("SEC_IDENTITY"))

# Connect directly to your Atlas database with built-in retry handling
client = MongoClient(
    os.getenv("MONGO_URI"), 
    retryWrites=True, 
    w="majority",
    maxPoolSize=50
)
db = client["insider_trading"]
filings_collection = db["filings"]

def safe_float(obj, attr, default=0.0):
    val = getattr(obj, attr, None)
    return float(val) if val is not None else default

def safe_int(obj, attr, default=0):
    val = getattr(obj, attr, None)
    return int(val) if val is not None else default

def safe_str(obj, attr, default="UNKNOWN"):
    val = getattr(obj, attr, None)
    return str(val) if val is not None else default

def parse_filing_to_record(filing, composite_id):
    try:
        form_data = filing.obj()
        summary = form_data.get_ownership_summary()
        
        shares = safe_int(summary, "net_change")
        value = safe_float(summary, "net_value")
        mongo_safe_date = str(filing.filing_date) 

        return {
            "_id": composite_id,  
            "accession_no": filing.accession_number,
            "filing_date": mongo_safe_date,  
            "ticker": safe_str(summary, "issuer_ticker"),
            "company": safe_str(summary, "issuer_name"),
            "insider_name": safe_str(summary, "insider_name"),
            "position": safe_str(summary, "position"),
            "transaction_date": safe_str(summary, "reporting_date"),
            "net_shares": shares,
            "net_value": value,
            "is_purchase": getattr(summary, 'primary_activity', None) == "Purchase"
        }
    except edgar.httprequests.TooManyRequestsError:
        print("Too many requests sleep 10 minutes")
        time.sleep(605)
        return None
    except Exception as e:
        return None

def run_pipeline():
    print("Scraper starting")
    filings = get_filings(year=2026, form="4")
    print(len(filings))
    batch = []
    batch_size = 50  

    for idx, f in enumerate(filings):
        if idx % 1000 == 0 and idx > 0:
            print(f"Progress: Checked {idx} filings")
        raw_id = f"{f.accession_number}"
        composite_id = hashlib.md5(raw_id.encode('utf-8')).hexdigest()
        is_duplicate = False
        for retry in range(3):
            try:
                if filings_collection.find_one({"_id": composite_id}):
                    is_duplicate = True
                break 
            except Exception as e:
                if retry == 2:
                    print(f"Mongo check timed out, exception: {e}")
                else:
                    time.sleep(1*(retry+1))
        if is_duplicate:
            continue
        record = parse_filing_to_record(f, composite_id)
        if record:
            if record.get("ticker") != "UNKNOWN": 
                batch.append(record)
        if len(batch) >= batch_size:
            try:
                operations = [
                    UpdateOne({"_id": record["_id"]}, {"$set": record}, upsert=True)
                    for record in batch
                ]
                filings_collection.bulk_write(operations, ordered=False)
            except Exception as e:
                print(f"Failed to save batch: {e}")
            batch = []
            time.sleep(0.5)
    if batch:
        try:
            operations = [
                UpdateOne({"_id": record["_id"]}, {"$set": record}, upsert=True)
                for record in batch
            ]
            filings_collection.bulk_write(operations, ordered=False)
            print(f"Sent final batch of {len(batch)} fresh trades to Atlas")
        except Exception as e:
            print(f"Failed to save final batch: {e}")
        
    print("Pipeline done")
if __name__ == "__main__":
    run_pipeline()