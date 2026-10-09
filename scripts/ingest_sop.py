import os
import re
import math
import hashlib
from collections import Counter
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from google import genai
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

class ResilientFactoryEmbedder(EmbeddingFunction):
    """
    Embedder công nghiệp có cơ chế Fallback an toàn:
    - Mode 1: Dùng Gemini API (gemini-embedding-001)
    - Mode 2 (Fallback): Local Feature Hashing Vectorizer (nhẹ, độc lập, không tải weights)
    """
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = genai.Client(api_key=api_key) if api_key else None

    def _local_embed(self, text: str, dim: int = 128) -> list[float]:
        tokens = re.findall(r'\w+', text.lower())
        counts = Counter(tokens)
        vec = [0.0] * dim
        for word, count in counts.items():
            idx = int(hashlib.md5(word.encode('utf-8')).hexdigest(), 16) % dim
            vec[idx] += float(count)
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        return [x / norm for x in vec]

    def __call__(self, input: Documents) -> Embeddings:
        if self.client:
            try:
                response = self.client.models.embed_content(
                    model="gemini-embedding-001",
                    contents=input,
                )
                print(f"[✓] Vectorized {len(input)} chunks via Google Gemini API.")
                return [list(e.values) for e in response.embeddings]
            except Exception as e:
                print(f"[!] Gemini Cloud Timeout/Error ({e}). Chuyen sang Local Vectorizer...")
        
        # Fallback local
        return [self._local_embed(doc) for doc in input]

CHROMA_DATA_PATH = "./chroma_db"
COLLECTION_NAME = "packaging_sops"

def load_and_chunk_sop(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    sections = re.split(r'(?=\n##\s+\d+\.\s+MÃ LỖI:)', content)
    chunks = []
    for sec in sections:
        sec = sec.strip()
        if not sec:
            continue
        
        match = re.search(r'MÃ LỖI:\s*(E-\d+)', sec)
        error_code = match.group(1) if match else "GENERAL"
        
        chunks.append({
            "error_code": error_code,
            "text": sec
        })
    return chunks

def ingest():
    print("[*] Khoi tao Factory Resilient Embedder...")
    embedder = ResilientFactoryEmbedder(api_key=GEMINI_API_KEY)

    print("[*] Khoi tao ChromaDB tai:", CHROMA_DATA_PATH)
    client = chromadb.PersistentClient(path=CHROMA_DATA_PATH)

    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"[*] Da reset collection cu '{COLLECTION_NAME}'")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        embedding_function=embedder,
        metadata={"hnsw:space": "cosine"}
    )

    chunks = load_and_chunk_sop("data/SOP_Packaging_Troubleshooting.md")
    print(f"[*] Tim thay {len(chunks)} doan quy trinh SOP.")

    documents = [item["text"] for item in chunks]
    metadatas = [{"error_code": item["error_code"]} for item in chunks]
    ids = [f"sop_chunk_{idx}_{item['error_code']}" for idx, item in enumerate(chunks)]

    print("[*] Dang nap vao ChromaDB...")
    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"[+] Hoan tat! Da index thanh cong {collection.count()} ban ghi SOP vao ChromaDB.")

if __name__ == "__main__":
    ingest()
