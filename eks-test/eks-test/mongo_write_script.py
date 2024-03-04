from pymongo import MongoClient
import time

# MongoDB connection string
#uri = "mongodb://username:password@host:port/dbname"
uri = "mongodb://root:So1pXs1aIX@localhost:40133/?directConnection=true"
client = MongoClient(uri)

# Specify the database and collection
db = client['test']
collection = db['collecttest']

while True:
    # Data to insert
    data = {
        "name": "John Doe",
        "timestamp": time.time()
    }
    
    # Insert data into the collection
    collection.insert_one(data)

    # Print a message
    print(f"Inserted data: {data}")

    # Wait for a bit before the next write (e.g., 1 second)
    time.sleep(1)
