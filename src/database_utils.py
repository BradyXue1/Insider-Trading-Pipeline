from pymongo import MongoClient, errors
from pymongo.server_api import ServerApi
import os
from dotenv import load_dotenv

load_dotenv()
uri = os.getenv("MONGO_URI")
def setup_collection():
    cluster = MongoClient(uri)
    db=cluster["insider_trading"]
    return db["filings"]
def initialize_database():
    """Runs once to set up safety constraints like blocking duplicate records."""
    try:
        collection=setup_collection()
        collection.create_index("accession_no", unique=True)
        print("Database initialized: Uniqueness constraints enforced.")
    except Exception as e:
        print(f"Could not initialize database indexes: {e}")
def save_records_to_db(records):
    """Takes your list of parsed dictionaries and inserts them in a single batch."""
    if not records:
        return
    collection = setup_collection()
    inserted_count = 0
    duplicate_count = 0
    # We loop and insert individually *or* bulk write. 
    # To handle duplicates gracefully without crashing the whole loop, we do this:
    for record in records:
        try:
            collection.insert_one(record)
            inserted_count += 1
        except errors.DuplicateKeyError:
            # If the accession_no already exists, Mongo blocks it, and we skip it!
            duplicate_count += 1
            continue
    print(f"Database Sync Complete: {inserted_count} new trades saved. ({duplicate_count} duplicates skipped).")