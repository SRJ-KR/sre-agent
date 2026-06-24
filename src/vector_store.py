import json
import pickle
import numpy as np
import faiss
import torch
from sentence_transformers import SentenceTransformer
import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2. Add the root directory to the beginning of Python's search path
sys.path.insert(0, ROOT_DIR)
from config import EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE, CHUNKS_FILE, FAISS_INDEX_FILE, META_STORE_FILE

def build_vector_index():
    print("🚀 Starting Vector Indexing...")
    
    # 1. Load Chunks
    with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
        chunks = json.load(f)
    texts = [chunk['text'] for chunk in chunks]

    # 2. Load Model (Explicitly on CPU)
    print(f"🤖 Loading embedding model: {EMBEDDING_MODEL_NAME} on {EMBEDDING_DEVICE}...")
    model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=EMBEDDING_DEVICE)

    # 3. Encode Texts (Batch size reduced to 16 for CPU stability)
    print("🔄 Encoding texts (This may take a few minutes on CPU)...")
    embeddings = model.encode(
        texts, batch_size=16, show_progress_bar=True,
        convert_to_numpy=True, normalize_embeddings=True
    )

    # 4. Build FAISS Index
    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)
    index.add(embeddings.astype('float32'))
    faiss.write_index(index, str(FAISS_INDEX_FILE))

    # 5. Save Metadata Store
    meta_store = {chunk['id']: chunk['metadata'] for chunk in chunks}
    with open(META_STORE_FILE, 'wb') as f:
        pickle.dump(meta_store, f)

    print(f"✅ Vector Indexing Complete. Indexed {index.ntotal} vectors.")
    return model, index, meta_store, chunks