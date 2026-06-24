import os
import json
import pandas as pd
from config import TEST_CSV_FILENAME, FAISS_INDEX_FILE, CHUNKS_FILE
from src.data_processing import run_data_preprocessing
from src.vector_store import build_vector_index
from src.retriever import DualPathRetriever
from src.agent import SREReActAgent
from src.memory import init_db, write_episode, query_episodic_memory

def main():
    print("="*50)
    print("🚀 SRE ReACT Agent Pipeline Starting")
    print("="*50)

    # Smart Caching for Vector Index
    if not os.path.exists(FAISS_INDEX_FILE) or not os.path.exists(CHUNKS_FILE):
        print("⏳ Running Data Preprocessing and Encoding...")
        run_data_preprocessing()
        build_vector_index()
    else:
        print("✅ Vector index found. Skipping encoding.\n")

    # Initialize Components
    retriever = DualPathRetriever()
    init_db()
    agent = SREReActAgent()

    # --- RUN TEST ---
    print("\n🧪 Running Test Alert...")
    df_test = pd.read_csv(TEST_CSV_FILENAME)
    df_test = df_test.loc[:, ~df_test.columns.str.contains('^Unnamed')]
    
    row = df_test.iloc[0]
    test_alert = {
        "timestamp": int(row.get('timestamp', 0)),
        "cmdb_id": str(row.get('cmdb_id', 'node-6')),
        "failure_type": str(row.get('failure_type', 'Node CPU Failure')),
        "mapped_service": str(row.get('mapped_service', 'Kubernetes')),
        "priority": str(row.get('priority', 'Critical')),
        "severity": str(row.get('severity', 'critical'))
    }
    test_alert["service"] = test_alert["mapped_service"]

    # 1. Retrieve Context (Dual-Path RAG)
    alert_text = f"{test_alert['service']} {test_alert['failure_type']} priority={test_alert['priority']}"
    print(f"🔍 Querying RAG: {alert_text}")
    retrieval_output = retriever.retrieve(
        alert_text=alert_text, 
        target_service=test_alert['service'], 
        target_severity=test_alert['severity']
    )
    print(f"🏆 Max Retrieval Score: {retrieval_output['max_score']}")

    # 🧠 2. MEMORY-FIRST CHECK: Have we seen this exact alert before?
    print("\n🧠 Checking Episodic Memory for past successful resolutions...")
    # We use a dummy step (100) just to calculate decay relative to "now"
    past_episodes = query_episodic_memory(
        alert_type=test_alert['failure_type'], 
        service=test_alert['mapped_service'], 
        current_step=100, 
        limit=2 
    )
    
    if past_episodes:
        print(f"✅ Found {len(past_episodes)} past episode(s)! Injecting into Agent's context.")
        for ep in past_episodes:
            print(f"   -> Past Action: {ep['action_taken']} (Score: {ep['final_score']})")
    else:
        print("⚠️ No past episodes found. Agent will rely purely on RAG and reasoning.")

    # 3. Run Agent (Pass the past_episodes into the agent!)
    print("\n🤖 Running ReACT Agent...")
    trace, outcome = agent.run(test_alert, retrieval_output, past_episodes=past_episodes)

    # 4. Print Trace
    print("\n" + "="*50)
    print("📜 AGENT TRACE")
    print("="*50)
    for entry in trace:
        if entry['type'] == "THOUGHT":
            print(f"\n💭 [STEP {entry['step']} | THOUGHT]:\n   {entry['content']}")
        elif entry['type'] == "ACTION":
            print(f"\n🛠️  [STEP {entry['step']} | ACTION]: {entry['tool']}\n   Args: {json.dumps(entry['args'])}")
        elif entry['type'] == "OBSERVATION":
            print(f"\n👁️  [STEP {entry['step']} | OBSERVATION]:\n   {entry['content']}")

    print(f"\n🏁 FINAL OUTCOME: {outcome.upper()}")

    # 5. Save to Episodic Memory (Write-back)
    chunk_ids_used = [r['chunk_id'] for r in retrieval_output.get('results', [])]
    write_episode(test_alert, trace, agent.state_engine, chunk_ids_used, current_step=len(trace))

if __name__ == "__main__":
    main()