# Imports
import os
import time
import hashlib
from edgar import set_identity, get_filings 
from dotenv import load_dotenv
from pymongo import MongoClient, UpdateOne
import edgar.httprequests
# The Edgar API has a limit of 10 requests per second, violating it leads to a temporary IP ban
os.environ['EDGAR_RATE_LIMIT_PER_SEC'] = '6'  # Keep it well below 10
#Get my identity from .env  
load_dotenv()
set_identity(os.getenv("SEC_IDENTITY"))
# Sets up connection to Atlas, retry means it can handle network blips without crashes
client = MongoClient(
    os.getenv("MONGO_URI"), 
    retryWrites=True, 
    w="majority",
    maxPoolSize=50
)
db = client["insider_trading"]
filings_collection = db["filings"]
#These functions use getattr to extract attributes in a more robust way with defaults
def safe_float(obj, attr, default=0.0):
    val = getattr(obj, attr, None)
    return float(val) if val is not None else default
def safe_int(obj, attr, default=0):
    val = getattr(obj, attr, None)
    return int(val) if val is not None else default
def safe_str(obj, attr, default="UNKNOWN"):
    val = getattr(obj, attr, None)
    return str(val) if val is not None else default
#This is the parser function that extracts data from filings
def parse_filing_to_record(filing, composite_id):
    #The try block increases robustness
    try:
        #Setup
        form_data = filing.obj()
        summary = form_data.get_ownership_summary()
        #Net metrics
        shares = safe_int(summary, "net_change")
        value = safe_float(summary, "net_value")
        if value == 0.0:
            return None
        #Edgar uses an unusual date format that MongoDB doesn't like, so we convert it to a string
        mongo_safe_date = str(filing.filing_date)
        #Self explanatory 
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
    #This will maybe save the pipeline if we somehow do too many requests but it's kind of pointless
    except edgar.httprequests.TooManyRequestsError:
        print("Too many requests sleep 10 minutes")
        time.sleep(605)
        return None
    #Another backup for robustness
    except Exception as e:
        return None
#This is our central function that defines the whole thing
def run_pipeline():
    print("Scraper starting")
    #Filings is fucking massive, I don't know how get_filings is so fast
    filings = get_filings(year=2022, quarter=1, form="4")
    print(len(filings))
    '''
    We're gonna batch it by 50 which seems to be a sweet spot, individual inserts would be slow
    and huge batches causes issues with bad records or network blips.
    I'd rather mess up 49 records than 999, which is what I was doing earlier
    '''
    batch = []
    batch_size = 50  
    '''
    enumerate(filings) adds a counter to an iterable, in this case filings
    we get a list of (index, filing) items that we call (idx, f)
    '''
    for idx, f in enumerate(filings):
        #This is a little progress bar
        if idx % 1000 == 0 and idx > 0:
            print(f"Progress: Checked {idx} filings")
        '''
        I believe this part is actually unneccesary, I wrote it after finding that a bunch of trades
        were getting skipped because their accession number was a duplicate.
        This was because multiple trades by the same insider on the same day had 
        the same accession number, so I used composite keys which work perfectly fine.
        However, this issue was already accounted for with the net_shares and net_value fields, so
        it's kinda pointless but it's not like it breaks the pipeline or anything and I already 
        had like 100K rows with composite keys by the time I realized so I just kept it in. 
        '''
        raw_id = f"{f.accession_number}"
        #This is a line I do not understand, I got it from Gemini
        composite_id = hashlib.md5(raw_id.encode('utf-8')).hexdigest()
        is_duplicate = False
        '''
        This tests if a record is a duplicate. It's also a retry loop that makes 
        this part of the pipeline more robust to network blips
        '''
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
        #Extracts using previously defined function
        record = parse_filing_to_record(f, composite_id)
        #if parse failed we can just skip the record that's ok
        if record:
            #I want only records with tickers
            if record.get("ticker") != "UNKNOWN": 
                #This is how batch works, we append stuff to it until it reaches the batch size
                batch.append(record)
        #Once it hits the batch size we send it to Atlas and reset 
        if len(batch) >= batch_size:
            #Again try/except blocks make the pipeline more robust
            try:
                '''
                UpdateOne is cool, it creates a row if the composite id doesn't exist 
                and updates a row if it does exist already
                I think this is handles by the whole duplicate check from earlier but I 
                found the function in the docs and it seems to work just fine so why not
                '''
                operations = [
                    UpdateOne({"_id": record["_id"]}, {"$set": record}, upsert=True)
                    for record in batch
                ]                
                #This is why we do batches! We can write 50 rows at once using bulk_write!
                filings_collection.bulk_write(operations, ordered=False)
            except Exception as e:
                print(f"Failed to save batch: {e}")
            batch = []
            #This is kind of to just make sure we're under the rate limit, kind of unnecessary
            time.sleep(0.5)
    #This happens after the original loop is over in case we end on a batch that isn't full
    if batch:
        #Checks if there's still a batch after the loop is done
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