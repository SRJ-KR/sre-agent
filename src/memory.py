import sqlite3
import json
import math
from config import EPISODES_DB_FILE

def get_db_connection():
    conn = sqlite3.connect(str(EPISODES_DB_FILE))
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS episodes (
        episode_id INTEGER PRIMARY KEY AUTOINCREMENT,
        alert_type TEXT, service TEXT, action_taken TEXT,
        state_before TEXT, state_after TEXT, verified_outcome TEXT,
        rollback_applied INTEGER, chunk_ids_used TEXT,
        step_counter INTEGER, outcome_weight REAL,
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

def validate_outcome(rollback_applied: bool, verified_outcome: str) -> float:
    """Prevents hallucinated 'success' from contaminating future memory."""
    if rollback_applied and verified_outcome == "success":
        return 0.0  # False positive!
    return 1.0

def write_episode(alert_data, trace, state_engine, chunk_ids_used, current_step):
    """Writes the structured episode record to SQLite."""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    state_before = json.dumps({"initial_health": "degraded"})
    state_after = json.dumps(state_engine.state["service_health"])

    actions_taken = [f"{e['tool']}({e['args']})" for e in trace if e['type'] == 'ACTION']
    action_str = " -> ".join(actions_taken) if actions_taken else "No actions"
    
    verified_outcome = "escalated"
    for e in trace:
        if e['type'] == 'OBSERVATION' and 'target_health' in e['content']:
            obs_data = json.loads(e['content'])
            verified_outcome = "success" if obs_data.get('target_health') == 'healthy' else "failed"

    rollback_applied = 1 if state_engine.state.get("rollback_applied", False) else 0
    outcome_weight = validate_outcome(bool(rollback_applied), verified_outcome)

    cursor.execute('''INSERT INTO episodes 
        (alert_type, service, action_taken, state_before, state_after,
         verified_outcome, rollback_applied, chunk_ids_used, step_counter, outcome_weight)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''', (
        alert_data.get('failure_type', 'unknown'),
        alert_data.get('mapped_service', 'unknown'),
        action_str, state_before, state_after,
        verified_outcome, rollback_applied, json.dumps(chunk_ids_used),
        current_step, outcome_weight
    ))
    conn.commit()
    conn.close()
    print(f"💾 Episode saved. Outcome: {verified_outcome} | Rollback: {bool(rollback_applied)} | Weight: {outcome_weight}")

def query_episodic_memory(alert_type, service, current_step, limit=2):
    """Queries SQLite for past episodes, applying Recency Decay."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM episodes')
    rows = cursor.fetchall()
    conn.close()

    scored_episodes = []
    for row in rows:
        row_dict = dict(row)
        
        # 1. Binary Matches
        type_match = 1.0 if row_dict['alert_type'].lower() == alert_type.lower() else 0.0
        svc_match = 1.0 if row_dict['service'].lower() == service.lower() else 0.0
        
        # Only count validated, non-contaminated successes
        verified_outcome_score = 1.0 if (row_dict['verified_outcome'] == 'success' and row_dict['outcome_weight'] == 1.0) else 0.0

        # 2. Exponential Recency Decay
        step_diff = max(0, current_step - row_dict['step_counter'])
        decay = math.exp(-0.001 * step_diff)

        # 3. Final Score
        final_score = (0.5 * type_match + 0.3 * svc_match + 0.2 * verified_outcome_score) * decay

        if final_score > 0:
            scored_episodes.append({
                "episode_id": row_dict['episode_id'],
                "action_taken": row_dict['action_taken'],
                "verified_outcome": row_dict['verified_outcome'],
                "decay": round(decay, 4),
                "final_score": round(final_score, 4)
            })

    scored_episodes.sort(key=lambda x: x['final_score'], reverse=True)
    return scored_episodes[:limit]