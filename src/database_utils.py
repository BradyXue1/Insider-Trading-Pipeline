import os
from dotenv import load_dotenv
from pymongo import MongoClient, errors, UpdateOne

load_dotenv()
uri = os.getenv("MONGO_URI")

# Instantiate MongoClient ONCE globally to utilize connection pooling efficiently
client = MongoClient(uri, maxPoolSize=50)
db = client["insider_trading"]
collection = db["filings"]

def initialize_database():
    """
    Runs once to set up safety constraints. Since MongoDB automatically enforces 
    uniqueness on the primary '_id' field, we don't need to build a custom index.
    We just log that the database layer is ready.
    """
    print("Database connection verified. MongoDB default '_id' uniqueness enforced.")

def save_records_to_db(records_generator, batch_size=1000):
    """
    Accepts a generator of records (preventing RAM bloat) and streams them 
    to Atlas using high-performance bulk operations matching on our collective ID.
    """
    operations = []
    total_new_inserted = 0
    total_already_existed = 0
    batch_count = 1

    def flush_batch(ops):
        if not ops:
            return 0, 0
        try:
            result = collection.bulk_write(ops, ordered=False)
            # upserted_count = brand new documents created
            # matched_count = documents that already existed and were skipped
            return (result.upserted_count or 0), (result.matched_count or 0)
        except errors.BulkWriteError as bwe:
            # Handle mixed states if a network interruption happens mid-batch
            return (bwe.details.get('nUpserted', 0)), (bwe.details.get('nMatched', 0))

    print("Beginning high-performance stream to Atlas...")
    
    for record in records_generator:
        # Match using our collective string/hash identifier
        operations.append(
            UpdateOne(
                {"_id": record["_id"]},
                {"$setOnInsert": record},
                upsert=True
            )
        )

        # Once a batch is full, stream it and clear memory
        if len(operations) >= batch_size:
            new_ins, old_match = flush_batch(operations)
            total_new_inserted += new_ins
            total_already_existed += old_match
            print(f"Synced batch {batch_count}: {len(operations)} rows streamed.")
            operations = []
            batch_count += 1

    # Flush any remaining items left over from the trailing batch
    if operations:
        new_ins, old_match = flush_batch(operations)
        total_new_inserted += new_ins
        total_already_existed += old_match

    print(f"Sync complete: {total_new_inserted} brand new trades saved | {total_already_existed} duplicates skipped.")