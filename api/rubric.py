"""
Governance rubric for n8n workflows.

Methodology note (for README / interview defense):
This rubric's autonomy classification is *adapted from* Gartner's
AI-agent autonomy model (May 2026 press release, "Gartner Says Applying
Uniform Governance Across AI Agents Will Lead to Enterprise AI Agent
Failure"), which defines four levels: Observe (read-only), Advise
(drafts/recommendations, human executes), Act with Approval (every
action requires explicit human sign-off), and Act Autonomously (executes
independently, humans review exceptions/audit logs rather than
individual decisions).

Two things this implementation does to genuinely earn those labels,
rather than approximate them:
  1. Observe vs. Advise is distinguished by checking for the presence of
     an AI/LLM node. A workflow with zero write actions and no AI node is
     pure data movement (Observe). A workflow with zero write actions but
     an AI/LLM node present is treated as generating a recommendation for
     a human to act on manually (Advise).
  2. "Act with Approval" requires a VERIFIED approval gate upstream of
     EVERY individual write-action node, checked via backward traversal
     of n8n's actual `connections` graph — not merely checking that a
     gate node exists somewhere in the workflow. A single write action
     with no confirmed upstream gate disqualifies the whole workflow from
     this tier and drops it to "Act Autonomously," matching Gartner's
     definition that Act with Approval means *every* action is gated.

This is still an adaptation, not a certified implementation of Gartner's
model — node-type detection lists are necessarily incomplete against
n8n's full ecosystem, and "AI node present" is an imperfect proxy for
"this workflow is specifically generating a recommendation." Documented
in docs/validation_notes.md.

n8n's own documented security guidance (the Credentials system, the
Error Trigger / error-workflow mechanism) is followed directly.

Each workflow is scored 0-100 (100 = lowest risk) across four dimensions.
Every flag the scorer raises is traceable to a specific node in the
workflow JSON, so results can be manually audited against the raw file.
"""

from __future__ import annotations
import re
from typing import Any


# --- Node type taxonomies -------------------------------------------------
# These lists are heuristic and intentionally conservative (favor false
# negatives over false positives) since they drive a portfolio artifact,
# not a production security product. Documented as a known limitation.

WRITE_ACTION_NODE_TYPES = {
    "n8n-nodes-base.httpRequest",       # only counts as write if method is POST/PUT/PATCH/DELETE
    "n8n-nodes-base.slack",
    "n8n-nodes-base.gmail",
    "n8n-nodes-base.emailSend",
    "n8n-nodes-base.postgres",
    "n8n-nodes-base.mySql",
    "n8n-nodes-base.mongoDb",
    "n8n-nodes-base.googleSheets",
    "n8n-nodes-base.airtable",
    "n8n-nodes-base.notion",
    "n8n-nodes-base.hubspot",
    "n8n-nodes-base.salesforce",
    "n8n-nodes-base.twilio",
    "n8n-nodes-base.discord",
}

APPROVAL_GATE_NODE_TYPES = {
    "n8n-nodes-base.wait",
    "n8n-nodes-base.formTrigger",
    "n8n-nodes-base.form",
}

# Node types/operations that represent an explicit human-in-the-loop gate
APPROVAL_GATE_OPERATIONS = {
    "sendAndWait",  # Slack/Telegram/etc "send message and wait for response"
}

# Substring match (case-insensitive) against node type strings. n8n's AI/LLM
# node type names vary a lot (openAi, langchain.agent, lmChatAnthropic,
# chainLlm, etc.) so a substring list is more robust than an exact-match set
# across a real, varied corpus.
AI_NODE_TYPE_KEYWORDS = (
    "openai", "langchain", "anthropic", "huggingface",
    "cohere", "azureopenai", "vertexai", "ollama",
)

ERROR_TRIGGER_NODE_TYPE = "n8n-nodes-base.errorTrigger"

LOGGING_KEYWORDS = ("log", "audit", "history", "logging", "logsheet", "log entry")


def _get_nodes(workflow: dict[str, Any]) -> list[dict[str, Any]]:
    return workflow.get("nodes", []) or []


def _node_name(node: dict[str, Any]) -> str:
    return (node.get("name") or "").lower()


def _is_write_action(node: dict[str, Any]) -> bool:
    ntype = node.get("type", "")
    if ntype not in WRITE_ACTION_NODE_TYPES:
        return False
    if ntype == "n8n-nodes-base.httpRequest":
        method = (node.get("parameters", {}) or {}).get("method", "GET")
        return str(method).upper() in {"POST", "PUT", "PATCH", "DELETE"}
    return True


def _is_approval_gate(node: dict[str, Any]) -> bool:
    if node.get("type") in APPROVAL_GATE_NODE_TYPES:
        return True
    params = node.get("parameters", {}) or {}
    op = params.get("operation", "")
    if op in APPROVAL_GATE_OPERATIONS:
        return True
    return False


CREDENTIAL_KEY_HINTS = ("token", "key", "secret", "password", "passwd", "apikey", "auth", "bearer", "credential")

# n8n auto-generates UUIDs for internal structural purposes (condition IDs,
# node IDs, etc.) — these are NOT secrets even though they're long
# alphanumeric-with-hyphen strings. Explicitly exclude standard UUID shape.
_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# Structural/non-secret key names that should never be scanned even if they
# happen to contain a "credential-like" substring (e.g. "keyword").
_STRUCTURAL_KEY_NAMES = {"id", "nodeid", "workflowid", "executionid"}


def _looks_like_secret(value: str) -> bool:
    """Heuristic for a hardcoded credential/token literal (not an n8n internal ID)."""
    if not isinstance(value, str) or len(value) < 16:
        return False
    if value.startswith("={{"):  # n8n expression, not a literal
        return False
    if _UUID_RE.match(value.strip()):  # n8n internal structural UUID, not a secret
        return False
    patterns = [
        r"^sk-[A-Za-z0-9]{16,}$",          # OpenAI-style key
        r"^Bearer\s+[A-Za-z0-9_\-\.]{16,}$",
        r"^xox[baprs]-[A-Za-z0-9-]+$",      # Slack token
        r"^AKIA[0-9A-Z]{16}$",              # AWS access key
        r"^[A-Za-z0-9_\-]{32,}$",           # generic long token (last resort, key-name-gated below)
    ]
    return any(re.match(p, value.strip()) for p in patterns)


def _scan_hardcoded_secrets(node: dict[str, Any]) -> list[str]:
    """
    Only scans string values sitting under a parameter key that plausibly
    holds credential material (token/key/secret/password/auth/bearer),
    OR values matching a known provider-prefix pattern (sk-, xox-, AKIA)
    regardless of key name. This deliberately avoids flagging every long
    string in a workflow (e.g. n8n's internal structural UUIDs), which
    produced false positives in early testing against the real corpus.
    """
    findings = []
    params = node.get("parameters", {}) or {}

    def key_suggests_credential(key: str) -> bool:
        k = key.lower()
        if k in _STRUCTURAL_KEY_NAMES:
            return False
        return any(hint in k for hint in CREDENTIAL_KEY_HINTS)

    def walk(obj, path="", last_key=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                walk(v, f"{path}.{k}" if path else k, last_key=k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]", last_key=last_key)
        elif isinstance(obj, str):
            if not _looks_like_secret(obj):
                return
            # Known provider-prefix patterns are flagged regardless of key name.
            provider_prefixed = bool(re.match(r"^(sk-|xox[baprs]-|AKIA|Bearer\s)", obj.strip()))
            if provider_prefixed or key_suggests_credential(last_key):
                findings.append(f"{node.get('name', 'unnamed node')}.parameters.{path}")

    walk(params)
    return findings


def _has_proper_credentials(node: dict[str, Any]) -> bool:
    return bool(node.get("credentials"))


def _has_error_handling(workflow: dict[str, Any], nodes: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    reasons = []
    has_trigger_node = any(n.get("type") == ERROR_TRIGGER_NODE_TYPE for n in nodes)
    if has_trigger_node:
        reasons.append("workflow contains an Error Trigger node")

    settings = workflow.get("settings", {}) or {}
    has_error_workflow_setting = bool(settings.get("errorWorkflow"))
    if has_error_workflow_setting:
        reasons.append("workflow settings reference an errorWorkflow")

    retry_nodes = [n.get("name") for n in nodes if n.get("retryOnFail") or (n.get("parameters", {}) or {}).get("retryOnFail")]
    if retry_nodes:
        reasons.append(f"retryOnFail configured on: {', '.join(retry_nodes)}")

    return (has_trigger_node or has_error_workflow_setting), reasons


def _has_audit_logging(nodes: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    matches = [n.get("name") for n in nodes if any(kw in _node_name(n) for kw in LOGGING_KEYWORDS)]
    return (len(matches) > 0), matches


def _has_ai_node(nodes: list[dict[str, Any]]) -> bool:
    """Detects whether any node is an AI/LLM node (used to distinguish
    Gartner's 'Observe' from 'Advise' — both have zero write actions, but
    Advise implies an AI node is generating a recommendation for a human
    to act on, while Observe is pure data movement with no AI involved)."""
    for n in nodes:
        ntype = (n.get("type") or "").lower()
        if any(kw in ntype for kw in AI_NODE_TYPE_KEYWORDS):
            return True
    return False


def _build_reverse_graph(nodes: list[dict[str, Any]], connections: dict[str, Any]) -> dict[str, list[str]]:
    """
    Builds a reverse adjacency map (target node name -> [source node names])
    from n8n's connections object, so we can walk backward from any node to
    find its actual upstream ancestors.

    n8n's connections format: {"SourceNodeName": {"main": [[{node:
    "TargetName", type: "main", index: 0}, ...], ...]}}. We flatten every
    output branch into simple source -> target edges, then invert.
    """
    reverse: dict[str, list[str]] = {n.get("name", ""): [] for n in nodes}
    for source_name, outputs in (connections or {}).items():
        for connection_type, branches in (outputs or {}).items():
            for branch in (branches or []):
                for edge in (branch or []):
                    target_name = edge.get("node")
                    if target_name is not None:
                        reverse.setdefault(target_name, []).append(source_name)
    return reverse


def _has_upstream_approval_gate(
    target_node_name: str,
    reverse_graph: dict[str, list[str]],
    gate_node_names: set[str],
) -> bool:
    """BFS backward from target_node_name through the reverse graph, checking
    whether any ancestor node is an approval-gate node. This verifies the
    gate genuinely sits upstream of THIS specific write action, rather than
    just existing somewhere in the workflow (the earlier, weaker check)."""
    visited = set()
    queue = list(reverse_graph.get(target_node_name, []))
    while queue:
        current = queue.pop()
        if current in visited:
            continue
        visited.add(current)
        if current in gate_node_names:
            return True
        queue.extend(reverse_graph.get(current, []))
    return False


def _classify_autonomy_tier(nodes: list[dict[str, Any]], connections: dict[str, Any]) -> tuple[str, str]:
    """
    Autonomy classification adapted from Gartner's four-level AI-agent
    autonomy model (May 2026): Observe, Advise, Act with Approval, Act
    Autonomously. See module docstring for the exact relationship to
    Gartner's definitions and what remains a heuristic vs. a verified check.

    Unlike an earlier version of this function, "Act with Approval" now
    requires a VERIFIED upstream approval gate for every individual
    write-action node (via backward graph traversal on n8n's connections
    object) rather than merely checking that a gate node exists somewhere
    in the workflow. A workflow only qualifies if every write action has
    its own confirmed gate; a single ungated write action anywhere
    disqualifies the whole workflow from this tier.
    """
    write_nodes = [n for n in nodes if _is_write_action(n) and not _is_approval_gate(n)]

    if not write_nodes:
        if _has_ai_node(nodes):
            return "Advise", (
                "No write/action nodes detected, but an AI/LLM node is present — "
                "workflow appears to generate a recommendation or draft for a human "
                "to act on manually, rather than acting itself."
            )
        return "Observe", (
            "No write/action nodes and no AI/LLM node detected — workflow appears "
            "to be pure data retrieval or transformation."
        )

    gate_node_names = {n.get("name", "") for n in nodes if _is_approval_gate(n)}
    reverse_graph = _build_reverse_graph(nodes, connections)

    ungated_write_nodes = []
    for wn in write_nodes:
        wn_name = wn.get("name", "")
        if not gate_node_names or not _has_upstream_approval_gate(wn_name, reverse_graph, gate_node_names):
            ungated_write_nodes.append(wn_name)

    if not ungated_write_nodes:
        return "Act with Approval", (
            f"All {len(write_nodes)} write-action node(s) — "
            f"{', '.join(n.get('name','?') for n in write_nodes)} — have a verified "
            "approval-gate node upstream in the execution graph."
        )

    return "Act Autonomously", (
        f"{len(ungated_write_nodes)} of {len(write_nodes)} write-action node(s) — "
        f"{', '.join(ungated_write_nodes)} — execute with no verified approval gate "
        "upstream in the execution graph."
    )


def score_workflow(workflow: dict[str, Any], filename: str = "") -> dict[str, Any]:
    nodes = _get_nodes(workflow)
    connections = workflow.get("connections", {}) or {}

    # --- Dimension 1: Credential exposure ---
    secret_findings: list[str] = []
    unprotected_write_nodes = []
    for n in nodes:
        secret_findings.extend(_scan_hardcoded_secrets(n))
        if _is_write_action(n) and not _has_proper_credentials(n):
            # not every write node needs n8n credentials (e.g. googleSheets via OAuth
            # sometimes stores differently) — flagged as a finding, weighted lightly
            unprotected_write_nodes.append(n.get("name", "unnamed"))

    credential_score = 100
    if secret_findings:
        credential_score -= min(60, 20 * len(secret_findings))
    if unprotected_write_nodes:
        credential_score -= min(20, 5 * len(unprotected_write_nodes))
    credential_score = max(0, credential_score)

    # --- Dimension 2: Error handling ---
    has_error_handling, error_reasons = _has_error_handling(workflow, nodes)
    error_score = 100 if has_error_handling else 20

    # --- Dimension 3: Autonomy tier ---
    autonomy_tier, autonomy_reason = _classify_autonomy_tier(nodes, connections)
    # Ordered per Gartner's own risk framing: Observe is lowest risk (lightweight
    # controls sufficient); Advise is still fairly low risk; Act with Approval
    # carries real risk Gartner explicitly flags (approval fatigue, rubber-
    # stamping under time pressure) so it is NOT treated as low-risk despite
    # having a gate; Act Autonomously is highest risk, requiring the most
    # rigorous governance.
    autonomy_score_map = {
        "Observe": 100,
        "Advise": 85,
        "Act with Approval": 55,
        "Act Autonomously": 15,
    }
    autonomy_score = autonomy_score_map[autonomy_tier]

    # --- Dimension 4: Audit trail ---
    has_audit, audit_matches = _has_audit_logging(nodes)
    audit_score = 100 if has_audit else 50  # softer penalty — hardest to detect reliably from JSON alone

    # --- Composite (weighted) ---
    weights = {"credential": 0.30, "error": 0.20, "autonomy": 0.35, "audit": 0.15}
    composite = (
        credential_score * weights["credential"]
        + error_score * weights["error"]
        + autonomy_score * weights["autonomy"]
        + audit_score * weights["audit"]
    )

    return {
        "filename": filename,
        "workflow_name": workflow.get("name", "unnamed"),
        "node_count": len(nodes),
        "composite_risk_score": round(composite, 1),
        "dimensions": {
            "credential_exposure": {
                "score": credential_score,
                "hardcoded_secret_findings": secret_findings,
                "write_nodes_without_credentials": unprotected_write_nodes,
            },
            "error_handling": {
                "score": error_score,
                "has_error_handling": has_error_handling,
                "reasons": error_reasons,
            },
            "autonomy_tier": {
                "score": autonomy_score,
                "tier": autonomy_tier,
                "reason": autonomy_reason,
            },
            "audit_trail": {
                "score": audit_score,
                "has_logging_node": has_audit,
                "matched_nodes": audit_matches,
            },
        },
    }
