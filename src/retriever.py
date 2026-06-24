import json
import numpy as np
import faiss
import pickle
from sentence_transformers import SentenceTransformer
import sys
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2. Add the root directory to the beginning of Python's search path
sys.path.insert(0, ROOT_DIR)
from config import EMBEDDING_MODEL_NAME, EMBEDDING_DEVICE, FAISS_INDEX_FILE, META_STORE_FILE, CHUNKS_FILE, RETRIEVAL_CONFIDENCE_THRESHOLD

class DualPathRetriever:
    def __init__(self):
        print("🔄 Loading Retrieval Artifacts...")
        self.model = SentenceTransformer(EMBEDDING_MODEL_NAME, device=EMBEDDING_DEVICE)
        self.index = faiss.read_index(str(FAISS_INDEX_FILE))
        
        with open(META_STORE_FILE, 'rb') as f:
            self.meta_store = pickle.load(f)
        with open(CHUNKS_FILE, 'r', encoding='utf-8') as f:
            self.chunks = json.load(f)
            
        self.chunk_text_lookup = {chunk['id']: chunk['text'] for chunk in self.chunks}
        print("✅ Retrieval Engine Ready.")

    def retrieve(self, alert_text, target_service=None, target_severity=None,
                 k_csv=3, k_playbook=2, candidate_pool=50):
        
        query_vec = self.model.encode([alert_text], normalize_embeddings=True).astype('float32')
        cosine_scores, indices = self.index.search(query_vec, candidate_pool)
        cosine_scores, indices = cosine_scores[0], indices[0]

        csv_candidates, playbook_candidates = [], []

        for i in range(candidate_pool):
            if indices[i] == -1: continue
            chunk_id = self.chunks[indices[i]]['id']
            meta = self.meta_store[chunk_id]
            source_type = meta.get('source_type', 'unknown')

            svc_match = 1.0 if (target_service and meta.get('service', '').lower() == str(target_service).lower()) else 0.0
            sev_match = 1.0 if (target_severity and meta.get('severity', '').lower() == str(target_severity).lower()) else 0.0
            source_boost = 0.05 if source_type == 'git_playbook' else 0.0

            cos_sim = float(cosine_scores[i])
            final_score = (0.65 * cos_sim) + (0.20 * svc_match) + (0.10 * sev_match) + source_boost

            result_obj = {
                "chunk_id": chunk_id, "text": self.chunk_text_lookup[chunk_id],
                "metadata": meta, "cosine_score": round(cos_sim, 4),
                "final_score": round(final_score, 4), "source_type": source_type
            }

            if source_type == 'synthetic_csv': csv_candidates.append(result_obj)
            elif source_type == 'git_playbook': playbook_candidates.append(result_obj)

        csv_candidates.sort(key=lambda x: x['final_score'], reverse=True)
        playbook_candidates.sort(key=lambda x: x['final_score'], reverse=True)

        final_results = csv_candidates[:k_csv]
        valid_playbooks = [p for p in playbook_candidates[:k_playbook] if p['final_score'] > 0.5]
        final_results.extend(valid_playbooks)

        remaining_slots = (k_csv + k_playbook) - len(final_results)
        if remaining_slots > 0:
            used_ids = {r['chunk_id'] for r in final_results}
            for c in csv_candidates:
                if c['chunk_id'] not in used_ids:
                    final_results.append(c)
                    remaining_slots -= 1
                if remaining_slots == 0: break

        final_results.sort(key=lambda x: x['final_score'], reverse=True)
        max_score = final_results[0]['final_score'] if final_results else 0.0

        return {
            "results": final_results, "max_score": round(max_score, 4),
            "is_low_confidence": max_score < RETRIEVAL_CONFIDENCE_THRESHOLD,
            "threshold": RETRIEVAL_CONFIDENCE_THRESHOLD
        }