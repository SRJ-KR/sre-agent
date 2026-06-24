import os
import json
import random
import hashlib
from openai import OpenAI
from config import OPENAI_API_KEY, OPENAI_MODEL_NAME, MAX_AGENT_STEPS

# --- Mock State Engine ---
DEPENDENCY_GRAPH = {
    "node-6": ["cartservice", "emailservice", "adservice"],
    "frontend": ["checkoutservice", "cartservice", "productcatalogservice"],
    "kubernetes": ["node-1", "node-2", "node-3", "node-4", "node-5", "node-6"]
}

class SREMockStateEngine:
    def __init__(self, alert_id, target_service, related_services):
        self.target_service = target_service
        self.related_services = related_services
        seed = int(hashlib.md5(str(alert_id).encode()).hexdigest(), 16) % (10**8)
        self.rng = random.Random(seed)
        self.state = {
            "service_health": {target_service: "degraded"},
            "metrics": {target_service: {"cpu": "95%", "mem": "80%", "error_rate": "15%"}},
            "rollback_applied": False, "actions_taken": []
        }
        for svc in related_services:
            if svc not in self.state["service_health"]:
                self.state["service_health"][svc] = "healthy"

    def check_health(self, service, scope="target"):
        result = {"target": service, "target_health": self.state["service_health"].get(service, "unknown")}
        if scope == "dependencies":
            result["dependencies"] = {dep: self.state["service_health"].get(dep, "unknown") for dep in self.related_services}
        return result

    def apply_remediation(self, service, action):
        self.state["actions_taken"].append({"service": service, "action": action})
        self.state["service_health"][service] = "healthy"
        return {"status": "success", "message": f"Action '{action}' applied to {service}."}

    def verify_state(self, service, scope="target"):
        target_health = self.state["service_health"].get(service, "unknown")
        verification_result = {"target": service, "target_health": target_health, "blast_radius_status": "contained"}
        if scope == "dependencies":
            dep_health, degraded_deps = {}, []
            for dep in self.related_services:
                if self.rng.random() < 0.05: # 5% chance of side-effect
                    self.state["service_health"][dep] = "degraded"
                    dep_health[dep] = "degraded"
                    degraded_deps.append(dep)
                else:
                    dep_health[dep] = self.state["service_health"].get(dep, "healthy")
            verification_result["dependencies"] = dep_health
            if degraded_deps:
                verification_result["blast_radius_status"] = "exceeded"
                verification_result["degraded_dependencies"] = degraded_deps
        return verification_result

    def trigger_rollback(self, service):
        self.state["rollback_applied"] = True
        self.state["service_health"][service] = "degraded"
        return {"status": "rolled_back", "message": f"State for {service} reverted."}

# --- Agent Core ---
TOOL_REGISTRY = [
    {"type": "function", "function": {"name": "check_service_health", "description": "Checks health status.", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "scope": {"type": "string", "enum": ["target", "dependencies"]}}, "required": ["service", "scope"]}}},
    {"type": "function", "function": {"name": "trigger_remediation", "description": "Executes remediation.", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "action": {"type": "string"}}, "required": ["service", "action"]}}},
    {"type": "function", "function": {"name": "verify_service_state", "description": "Post-action verification.", "parameters": {"type": "object", "properties": {"service": {"type": "string"}, "scope": {"type": "string", "enum": ["target", "dependencies"]}}, "required": ["service", "scope"]}}},
    {"type": "function", "function": {"name": "package_escalation", "description": "Escalates to human.", "parameters": {"type": "object", "properties": {"reason": {"type": "string"}, "blast_radius_map": {"type": "string"}}, "required": ["reason", "blast_radius_map"]}}}
]

class SREReActAgent:
    def __init__(self):
        self.client = OpenAI(api_key=OPENAI_API_KEY)
        self.model = OPENAI_MODEL_NAME
        self.trace = []
        self.state_engine = None

    def _execute_tool(self, tool_name, arguments):
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
        if tool_name == "check_service_health":
            return json.dumps(self.state_engine.check_health(args["service"], args.get("scope", "target")))
        elif tool_name == "trigger_remediation":
            return json.dumps(self.state_engine.apply_remediation(args["service"], args["action"]))
        elif tool_name == "verify_service_state":
            obs = self.state_engine.verify_state(args["service"], args.get("scope", "target"))
            if obs.get("blast_radius_status") == "exceeded":
                self.state_engine.trigger_rollback(args["service"])
                obs["message"] = "Blast radius exceeded. Automatic rollback applied."
            return json.dumps(obs)
        elif tool_name == "package_escalation":
            return json.dumps({"status": "escalated", "ticket_id": "INC-ESCALATION-999"})
        return json.dumps({"error": "Unknown tool"})

    def run(self, alert_data, retrieval_output, past_episodes=None):
        self.trace = []
        
        # 1. Initialize State Engine cleanly as an instance variable
        alert_id = f"{alert_data.get('timestamp', '')}_{alert_data.get('cmdb_id', '')}_{alert_data.get('failure_type', '')}"
        target_svc = alert_data.get('mapped_service', alert_data.get('cmdb_id', 'unknown'))
        related_svcs = DEPENDENCY_GRAPH.get(target_svc.lower(), [])
        self.state_engine = SREMockStateEngine(alert_id, target_svc, related_svcs)

        # 2. Low Confidence Bypass
        if retrieval_output.get('is_low_confidence', False):
            self.trace.append({"step": 0, "type": "THOUGHT", "content": "Low confidence. Escalating."})
            self.trace.append({"step": 1, "type": "ACTION", "tool": "package_escalation", "args": {}})
            return self.trace, "escalated"

        # 3. Build Prompt with Episodic Memory Injection
        evidence_block = "\n".join([f"[{r['metadata']['source_type']} | {r['chunk_id']}]\n{r['text'][:300]}..." for r in retrieval_output.get('results', [])])
        
        episodes_block = "No past episodes found."
        if past_episodes:
            episodes_block = "\n".join([f"Episode {ep['episode_id']}: {ep['action_taken']} (Score: {ep['final_score']})" for ep in past_episodes])

        system_prompt = f"""You are an expert IT SRE Agent. Resolve or escalate the alert using ONLY provided evidence.
[PAST EPISODES - Use these as exact templates if applicable]
{episodes_block}

[EVIDENCE - CSV for Strategy, Playbooks for CLI Commands]
{evidence_block}

[ALERT]
{json.dumps(alert_data, indent=2)}

RULES:
1. If a Past Episode matches, follow its exact action sequence.
2. Call tools sequentially. MAX {MAX_AGENT_STEPS} STEPS.
3. After remediation, you MUST call verify_service_state with scope="dependencies".
4. If blast radius is exceeded, escalate immediately.
"""

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "A new alert triggered. Begin ReAct loop."}
        ]

        outcome = "running"
        for step in range(1, MAX_AGENT_STEPS + 1):
            response = self.client.chat.completions.create(
                model=self.model, messages=messages, tools=TOOL_REGISTRY, tool_choice="auto", temperature=0.0
            )
            message = response.choices[0].message
            if message.content:
                self.trace.append({"step": step, "type": "THOUGHT", "content": message.content})
            if not message.tool_calls:
                outcome = "resolved"
                break

            messages.append(message)
            for tool_call in message.tool_calls:
                func_name = tool_call.function.name
                func_args = tool_call.function.arguments
                self.trace.append({"step": step, "type": "ACTION", "tool": func_name, "args": json.loads(func_args)})
                
                observation = self._execute_tool(func_name, func_args)
                self.trace.append({"step": step, "type": "OBSERVATION", "content": observation})
                messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": observation})

                if func_name == "package_escalation":
                    outcome = "escalated"
                    break
                if func_name == "verify_service_state" and "exceeded" in observation:
                    messages.append({"role": "user", "content": "Blast radius exceeded! Escalate now."})
            if outcome == "escalated": break

        if outcome == "running": outcome = "escalated"
        return self.trace, outcome