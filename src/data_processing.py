import os
import re
import csv
import json
import shutil
import zipfile
import pandas as pd
from tqdm import tqdm
import sys

# 1. Calculate the absolute path to the root directory
# (Goes up one level from the current subfolder)
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 2. Add the root directory to the beginning of Python's search path
sys.path.insert(0, ROOT_DIR)
from config import CSV_FILENAME, ZIP_FILENAME, PLAYBOOK_DIR, CHUNKS_FILE

def parse_sre_csv(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        raw_lines = f.readlines()

    header_idx = None
    for i, line in enumerate(raw_lines):
        if 'incident_id' in line.lower():
            header_idx = i
            break

    if header_idx is None:
        raise ValueError("Could not find header row with 'incident_id'")

    reader = csv.reader(raw_lines[header_idx:])
    header = next(reader)
    header = [h.strip().lower().replace(' ', '_') for h in header if h.strip()]

    incidents = []
    current_incident = None

    for row in reader:
        row = row[:len(header)]
        while len(row) < len(header):
            row.append('')

        record = dict(zip(header, [cell.strip() for cell in row]))
        incident_id = record.get('incident_id', '').strip()
        is_new_incident = bool(re.match(r'^INC-\d+', incident_id, re.IGNORECASE))

        if is_new_incident:
            if current_incident:
                incidents.append(current_incident)
            current_incident = {
                'incident_id': incident_id, 'service': record.get('service', ''),
                'issue': record.get('issue', ''), 'workflow': record.get('workflow', ''),
                'resolution': record.get('resolution', ''), 'priority': record.get('priority', ''),
                'severity': record.get('severity', ''), 'scope': record.get('scope', ''),
                'confidence': record.get('confidence', ''), 'impact': record.get('impact', ''),
                'frequency': record.get('frequency', ''), 'annotation': record.get('annotation', ''),
            }
        else:
            if current_incident is None:
                continue
            continuation_text = ' '.join([v for v in record.values() if v.strip()])
            if not continuation_text.strip():
                continue
            
            # Smart append logic (simplified for brevity, keeping original logic intact)
            if re.match(r'^(Phase|Step)\s+\d+', continuation_text, re.IGNORECASE):
                current_incident['workflow'] += ' ' + continuation_text
            else:
                current_incident['resolution'] += ' ' + continuation_text

    if current_incident:
        incidents.append(current_incident)
    return incidents

def normalize(value, valid_list, default='unknown'):
    if not value or pd.isna(value): return default
    v = str(value).strip().lower()
    return v if v in valid_list else default

def safe_float(value, default=0.0):
    try: return float(value)
    except (ValueError, TypeError): return default

def infer_tech_stack(file_path):
    path_lower = file_path.lower()
    if any(kw in path_lower for kw in ['kubernetes', 'k8s', 'kube']): return 'kubernetes'
    elif any(kw in path_lower for kw in ['aws', 'amazon', 'ec2', 's3', 'rds']): return 'aws'
    elif any(kw in path_lower for kw in ['sentry', 'error-tracking']): return 'sentry'
    elif any(kw in path_lower for kw in ['docker', 'container']): return 'docker'
    elif any(kw in path_lower for kw in ['terraform', 'iac', 'infrastructure']): return 'terraform'
    else: return 'general_sre'

def chunk_markdown(file_path, max_chars=2000):
    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
    if not content.strip(): return []

    sections = re.split(r'(?m)^(?=#{1,3}\s)', content)
    chunks = []
    file_name = os.path.basename(file_path)

    for section in sections:
        section = section.strip()
        if not section or len(section) < 20: continue

        header_match = re.match(r'^(#{1,3})\s+(.*)', section)
        header = header_match.group(2).strip() if header_match else file_name

        if len(section) > max_chars:
            paragraphs = section.split('\n\n')
            buffer = ""
            for para in paragraphs:
                if len(buffer) + len(para) < max_chars:
                    buffer += para + "\n\n"
                else:
                    if buffer.strip(): chunks.append({"header": header, "text": buffer.strip()})
                    buffer = para + "\n\n"
            if buffer.strip(): chunks.append({"header": header, "text": buffer.strip()})
        else:
            chunks.append({"header": header, "text": section})
    return chunks

def run_data_preprocessing():
    print("🚀 Starting Data Preprocessing...")
    
    # 1. Extract Playbooks
    if os.path.exists(PLAYBOOK_DIR):
        shutil.rmtree(PLAYBOOK_DIR)
    os.makedirs(PLAYBOOK_DIR, exist_ok=True)
    
    with zipfile.ZipFile(ZIP_FILENAME, 'r') as z:
        z.extractall(PLAYBOOK_DIR)
    print(f"✅ Extracted playbooks to {PLAYBOOK_DIR}")

    # 2. Parse CSV
    incidents = parse_sre_csv(CSV_FILENAME)
    VALID_PRIORITIES = ['critical', 'high', 'medium', 'low']
    VALID_SEVERITIES = ['catastrophic', 'major', 'moderate', 'minor']
    VALID_SCOPES = ['system-wide', 'multi-service', 'single-service']

    normalized_incidents = []
    for inc in incidents:
        normalized_incidents.append({
            'incident_id': inc['incident_id'].strip().upper(),
            'service': inc['service'].strip() or 'UnknownService',
            'issue': inc['issue'].strip() or 'UnknownIssue',
            'workflow': inc['workflow'].strip() or 'No workflow provided.',
            'resolution': inc['resolution'].strip() or 'No resolution provided.',
            'priority': normalize(inc['priority'], VALID_PRIORITIES),
            'severity': normalize(inc['severity'], VALID_SEVERITIES),
            'scope': normalize(inc['scope'], VALID_SCOPES),
            'confidence': safe_float(inc['confidence']),
            'impact': normalize(inc['impact'], ['catastrophic', 'major', 'moderate', 'minor']),
            'frequency': normalize(inc['frequency'], ['recurring', 'one-off', 'sporadic']),
            'annotation': inc['annotation'].strip() if inc['annotation'] else '',
            'source_type': 'synthetic_csv'
        })

    # 3. Chunk Playbooks
    playbook_chunks_raw = []
    chunk_counter = 20000
    for root, dirs, files_in_dir in os.walk(PLAYBOOK_DIR):
        for fname in files_in_dir:
            if not fname.endswith('.md'): continue
            fpath = os.path.join(root, fname)
            tech = infer_tech_stack(fpath)
            raw_chunks = chunk_markdown(fpath)
            for c in raw_chunks:
                playbook_chunks_raw.append({
                    'incident_id': f'PLAYBOOK-{chunk_counter}', 'service': tech,
                    'issue': c['header'], 'workflow': c['text'], 'resolution': '',
                    'priority': 'medium', 'severity': 'moderate', 'scope': 'single-service',
                    'confidence': 0.95, 'impact': 'moderate', 'frequency': 'recurring',
                    'annotation': f'Source: {fpath}', 'source_type': 'git_playbook', 'tech_stack': tech
                })
                chunk_counter += 1

    # 4. Unify and Save
    all_chunks = []
    for inc in normalized_incidents:
        chunk_text = f"[Source: Synthetic Incident Record]\nService: {inc['service']}\nIssue: {inc['issue']}\nWorkflow:\n{inc['workflow']}\nResolution:\n{inc['resolution']}"
        if len(chunk_text) > 2048: chunk_text = chunk_text[:2045] + "... "
        metadata = {k: v for k, v in inc.items() if k != 'incident_id'}
        metadata['annotation'] = metadata.get('annotation', '')[:500]
        all_chunks.append({"id": inc['incident_id'], "text": chunk_text, "metadata": metadata})

    for pc in playbook_chunks_raw:
        chunk_text = f"[Source: Git Playbook - {pc['tech_stack'].upper()}]\nSection: {pc['issue']}\nContent:\n{pc['workflow']}"
        if len(chunk_text) > 2048: chunk_text = chunk_text[:2045] + "... "
        metadata = {k: v for k, v in pc.items() if k != 'incident_id'}
        all_chunks.append({"id": pc['incident_id'], "text": chunk_text, "metadata": metadata})

    with open(CHUNKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, indent=2, ensure_ascii=False)
        
    print(f"✅ Data Preprocessing Complete. Saved {len(all_chunks)} chunks to {CHUNKS_FILE}")
    return all_chunks