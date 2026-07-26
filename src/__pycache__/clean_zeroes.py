import os
import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

def clean_and_overwrite_mongo():
    # 1. Connect to MongoDB
    load_dotenv()
    client = MongoClient(os.getenv("MONGO_URI"))
    db = client["insider_trading"]
    collection = db["filings"]  # Target the existing collection
    
    print("Fetching raw data from MongoDB...")
    df = pd.DataFrame(list(collection.find({})))
    
    if df.empty:
        print("No data found in the collection to clean.")
        return

    initial_rows = len(df)
    print(f"Current rows in MongoDB: {initial_rows}")

    # 2. RUN THE CLEANING LAYER
    print("Cleaning data...")
    
    # Strip whitespace from accession numbers
    df['accession_no'] = df['accession_no'].astype(str).str.strip()
    
    # Drop duplicates based on the unique SEC filing number
    df = df.drop_duplicates(subset=['accession_no'], keep='first')
    
    # Remove transactions with 0 net shares
    df = df[df['net_shares'] != 0]
    # Remove transactions with no ticker
    df = df[df['ticker'].astype(str).str.upper() != 'NONE']
    if '_id' in df.columns:
        df = df.drop(columns=['_id'])

    final_rows = len(df)
    removed_rows = initial_rows - final_rows

    # 3. OVERWRITE THE EXISTING COLLECTION
    if removed_rows > 0:
        print(f"Cleaning complete. Removing {removed_rows} junk rows...")
        
        # Convert the cleaned DataFrame to a list of dictionaries
        cleaned_records = df.to_dict(orient="records")
        
        # Clear the old data out entirely
        collection.delete_many({}) 
        
        # Insert the clean data back into the exact same spot
        collection.insert_many(cleaned_records)
        print(f"✅ Success! 'filings' collection has been cleaned and overwritten. (New total: {final_rows} rows)")
    else:
        print("Information looked perfectly clean already. No changes made to MongoDB.")

# Run the process
if __name__ == "__main__":
    clean_and_overwrite_mongo()