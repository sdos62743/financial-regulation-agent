import chromadb
from retrieval.vector_store import get_vector_store # Or however you initialize it

def diagnostic():
    # 1. Check total count
    # Replace with your actual collection name used in retrieval
    client = chromadb.PersistentClient(path="data/chroma_db") 
    collection = client.get_collection(name="financial_regulation")
    
    count = collection.count()
    print(f"📊 Total documents in Chroma: {count}")

    # 2. Peek at the most recent entries
    if count > 0:
        last_docs = collection.peek(limit=5)
        print("\n👀 Last 5 Metadata entries:")
        for meta in last_docs['metadatas']:
            print(f" - {meta}")
            
    # 3. Test a direct retrieval (bypass the graph)
    print("\n🧪 Testing direct similarity search for 'Basel'...")
    # This uses your actual project's embedding logic
    vs = get_vector_store()
    results = vs.similarity_search("What is Basel?", k=2)
    print(f" ✅ Found {len(results)} results via similarity search.")

if __name__ == "__main__":
    diagnostic()
