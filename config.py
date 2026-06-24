import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- API Keys ---
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# --- Paths ---
BASE_DIR = Path(__file__).resolve().parent
DATA_RAW_DIR = BASE_DIR / "data" / "raw"
DATA_PROCESSED_DIR = BASE_DIR / "data" / "processed"
STORAGE_DIR = BASE_DIR / "storage"
SRC_DIR = BASE_DIR / "src"

# Ensure directories exist
DATA_PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
STORAGE_DIR.mkdir(parents=True, exist_ok=True)

# --- File Names ---
CSV_FILENAME = DATA_RAW_DIR / "synthetic_training_sre_alerts.csv"
ZIP_FILENAME = DATA_RAW_DIR / "playbooks.zip"
TEST_CSV_FILENAME = DATA_RAW_DIR / "test against.csv"
PLAYBOOK_DIR = DATA_PROCESSED_DIR / "playbooks"

CHUNKS_FILE = STORAGE_DIR / "chunks.json"
FAISS_INDEX_FILE = STORAGE_DIR / "faiss.index"
META_STORE_FILE = STORAGE_DIR / "meta_store.pkl"
EPISODES_DB_FILE = STORAGE_DIR / "episodes.db"

# --- Model Configurations ---
# Using CPU for embeddings since no GPU is available
#EMBEDDING_MODEL_NAME = "nomic-ai/nomic-embed-text-v1.5"
#EMBEDDING_MODEL_NAME = "nomic-ai/modernbert-embed-base"
EMBEDDING_MODEL_NAME = "ibm-granite/granite-embedding-english-r2"
OPENAI_MODEL_NAME = "gpt-4o-mini"
EMBEDDING_DEVICE = "cpu" 

# --- Agent Thresholds ---
RETRIEVAL_CONFIDENCE_THRESHOLD = 0.72
MAX_AGENT_STEPS = 5