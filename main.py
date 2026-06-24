import os
import re
import json
import random
import pandas as pd
from config import TEST_CSV_FILENAME, FAISS_INDEX_FILE, CHUNKS_FILE
from src.data_processing import run_data_preprocessing
from src.vector_store import build_vector_index
from src.retriever import DualPathRetriever
from src.agent import SREReActAgent
from src.memory import init_db, write_episode, query_episodic_memory

# ==========================================
# 📊 EVALUATION ENGINE (Tracks your Metrics)
# ==========================================
class EvaluationEngine:
    def __init__(self):
        self.metrics_history = []

    def evaluate_run(self, alert_data, trace, outcome, retrieval_output, state_engine):
        metrics = {}
        metrics['success'] = 1.0 if outcome == "resolved" else 0.0
        
        action_steps = [t for t in trace if t['type'] == 'ACTION']
        metrics['step_efficiency'] = len(action_steps)
        
        is_low_conf = retrieval_output.get('is_low_confidence', False)
        blast_exceeded = state_engine.state.get('rollback_applied', False)
        should_escalate = is_low_conf or blast_exceeded
        actually_escalated = (outcome == "escalated")
        metrics['escalation_compliance'] = 1.0 if (should_escalate == actually_escalated) else 0.0
        
        thoughts = [t['content'] for t in trace if t['type'] == 'THOUGHT' and t['content']]
        if thoughts:
            citation_pattern = re.compile(r'(INC-\d+|PLAYBOOK-\d+)')
            cited_thoughts = sum(1 for t in thoughts if citation_pattern.search(t))
            metrics['explainability_score'] = cited_thoughts / len(thoughts)
        else:
            metrics['explainability_score'] = 0.0
            
        if outcome == "resolved" and blast_exceeded:
            metrics['contamination_attempted'] = 1.0
        else:
            metrics['contamination_attempted'] = 0.0
            
        self.metrics_history.append(metrics)
        return metrics

    def print_dashboard(self):
        if not self.metrics_history: return
        print("\n" + "="*50)
        print("📊 AGENT EVALUATION DASHBOARD")
        print("="*50)
        total_runs = len(self.metrics_history)
        avg_success = sum(m['success'] for m in self.metrics_history) / total_runs
        avg_steps = sum(m['step_efficiency'] for m in self.metrics_history) / total_runs
        avg_compliance = sum(m['escalation_compliance'] for m in self.metrics_history) / total_runs
        avg_explain = sum(m['explainability_score'] for m in self.metrics_history) / total_runs
        total_contamination = sum(m['contamination_attempted'] for m in self.metrics_history)
        
        print(f"🎯 Total Runs Evaluated: {total_runs}")
        print(f"✅ Success Rate:          {avg_success * 100:.1f}%")
        print(f"⚡ Avg Step Efficiency:   {avg_steps:.1f} steps/run")
        print(f"🚨 Escalation Compliance: {avg_compliance * 100:.1f}%")
        print(f"🧠 Explainability Score:  {avg_explain * 100:.1f}% (Thoughts citing evidence)")
        print(f"☣️  Contamination Blocks:  {int(total_contamination)} (False positives caught)")
        print("="*50)

# ==========================================
# 🚀 MAIN ORCHESTRATOR
# ==========================================
def main():
    print("="*50)
    print("🚀 SRE ReACT Agent Pipeline Starting")
    print("="*50)

    # 1. Smart Caching for Vector Index
    if not os.path.exists(FAISS_INDEX_FILE) or not os.path.exists(CHUNKS_FILE):
        print("⏳ Running Data Preprocessing and Encoding...")
        run_data_preprocessing()
        build_vector_index()
    else:
        print("✅ Vector index found. Skipping encoding.\n")

    # 2. Initialize Components
    retriever = DualPathRetriever()
    init_db()
    agent = SREReActAgent()
    evaluator = EvaluationEngine()

    # 3. Load Test Dataset
    df_test = pd.read_csv(TEST_CSV_FILENAME)
    df_test = df_test.loc[:, ~df_test.columns.str.contains('^Unnamed')]
    
    # 🎲 CONFIGURATION: How many random alerts do you want to test?
    NUM_TEST_RUNS = 1 
    
    print(f"\n🧪 Starting Batch Test: Running {NUM_TEST_RUNS} RANDOM alerts...\n")

    # 4. The Testing Loop
    for run_num in range(1, NUM_TEST_RUNS + 1):
        print(f"\n{'='*20} RUN {run_num} of {NUM_TEST_RUNS} {'='*20}")
        
        # 🎲 RANDOMIZE: Pick a random row instead of iloc[0]
        random_row = df_test.sample(n=1).iloc[0]
        
        test_alert = {
            "timestamp": int(random_row.get('timestamp', 0)),
            "cmdb_id": str(random_row.get('cmdb_id', 'unknown')),
            "failure_type": str(random_row.get('failure_type', 'Unknown Failure')),
            "mapped_service": str(random_row.get('mapped_service', 'Unknown Service')),
            "priority": str(random_row.get('priority', 'Medium')),
            "severity": str(random_row.get('severity', 'moderate'))
        }
        test_alert["service"] = test_alert["mapped_service"]
        
        print(f"🎯 Random Alert Selected: {test_alert['failure_type']} on {test_alert['mapped_service']}")

        # A. Retrieve Context (Dual-Path RAG)
        alert_text = f"{test_alert['service']} {test_alert['failure_type']} priority={test_alert['priority']}"
        retrieval_output = retriever.retrieve(
            alert_text=alert_text, 
            target_service=test_alert['service'], 
            target_severity=test_alert['severity']
        )
        print(f"🏆 Max Retrieval Score: {retrieval_output['max_score']}")
        # B. MEMORY-FIRST CHECK
        past_episodes = query_episodic_memory(
            alert_type=test_alert['failure_type'], 
            service=test_alert['mapped_service'], 
            current_step=100, # Dummy step for decay calculation
            limit=2 
        )
        
        if past_episodes:
            print(f"🧠 Found {len(past_episodes)} past episode(s). Injecting into context.")
            for ep in past_episodes:
                print(f"   - Episode ID: {ep.get('episode_id', 'N/A')}, Outcome: {ep.get('outcome', 'Unknown')}, Steps: {ep.get('steps', 'N/A')}")
        else :
            print("🧠 No relevant past episodes found. Agent will rely purely on RAG and reasoning")

        # C. Run Agent
        print("\n🤖 Running ReACT Agent...")
        trace, outcome = agent.run(test_alert, retrieval_output, past_episodes=past_episodes)
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
        print(f"🏁 Outcome: {outcome.upper()}")

        # D. Evaluate Metrics
        run_metrics = evaluator.evaluate_run(test_alert, trace, outcome, retrieval_output, agent.state_engine)
        
        # E. Save to Episodic Memory (Write-back)
        chunk_ids_used = [r['chunk_id'] for r in retrieval_output.get('results', [])]
        write_episode(test_alert, trace, agent.state_engine, chunk_ids_used, current_step=len(trace))

    # 5. Print Final Aggregated Dashboard
    evaluator.print_dashboard()

if __name__ == "__main__":
    main()