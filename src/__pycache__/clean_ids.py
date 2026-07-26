import os
import hashlib
from dotenv import load_dotenv
from pymongo import MongoClient, InsertOne, DeleteOne

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"), retryWrites=True, w="majority")
db = client["insider_trading"]
filings_collection = db["filings_with_prices_2"]
def fix_object_ids_in_place():
    print("Search")
    # Target only documents where the _id is an objectId type
    bad_docs = list(filings_collection.find({ "_id": { "$type": "objectId" } }))
    if not bad_docs:
        print("No ObjectId documents found")
        return
    print(f"Found {len(bad_docs)} documents to fix")
    operations = []
    for doc in bad_docs:
        # Pull the accession number that's already saved inside the document
        acc_num = doc.get("accession_no")
        # If it doesn't have an accession number, we can't make an MD5, so skip
        if not acc_num or acc_num == "None":
            continue
        # Re-generate your correct composite MD5 key
        composite_id = hashlib.md5(str(acc_num).encode('utf-8')).hexdigest()
        # Clone the original document data
        new_doc = doc.copy()
        new_doc["_id"] = composite_id  # Assign the new correct string ID
        operations.append(InsertOne(new_doc))
        operations.append(DeleteOne({"_id": doc["_id"]}))
        # Execute in batches of 1000 
        if len(operations) >= 1000:
            filings_collection.bulk_write(operations, ordered=True)  # ordered=True ensures insert happens before delete
            operations = []
            print(f"Processed 1000 documents")
    if operations:
        filings_collection.bulk_write(operations, ordered=True)

if __name__ == "__main__":
    fix_object_ids_in_place()