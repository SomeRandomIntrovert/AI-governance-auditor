"""
Regression test suite for approval-gate detection.

Origin: a LinkedIn comment on this project pointed out that a "control
that exists somewhere" is meaningless if it isn't verified to actually
sit on the path of the risky action — and asked whether the 68-workflow
corpus had turned up any case where a gate-typed node existed but didn't
actually protect a write action. Checking that surfaced a second,
unrelated bug: 4 of the 6 such cases were themselves false positives —
generic n8n Wait (polling/delay) nodes being misidentified as human
checkpoints by the gate-detection taxonomy, not a graph-position problem
at all.

Per that commenter's own suggestion: this fixture set is re-run on every
future change to gate-detection logic, not checked once and forgotten.
The fix for one blind spot can introduce a new one for the next case.

Run with: python -m pytest tests/test_gate_detection_regressions.py -v
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from api.rubric import score_workflow

CORPUS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "samples", "corpus")

# Cases identified during the LinkedIn review (see docs/validation_notes.md
# for the full narrative). Each entry records what SHOULD be true after a
# correct fix, so a regression shows up as a failing assertion, not a
# silent behavior change someone has to notice by eye.
KNOWN_CASES = [
    {
        "filename": "Airtable__vAssistant_for_Hubspot_Chat_using_OpenAi_and_Airtable.json",
        "note": "4 bare Wait nodes (timed delay only, no resume=webhook/form) — none should count as gates.",
        "expected_tier": "Act Autonomously",
    },
    {
        "filename": "Other_Integrations_and_Use_Cases__Tunova_-_Generate_a_song_via_webhook.json",
        "note": "Wait node is a post-generation polling delay, not a pre-write checkpoint.",
        "expected_tier": "Act Autonomously",
    },
    {
        "filename": "PDF_and_Document_Processing__Manipulate_PDF_with_Adobe_developer_API.json",
        "note": "Wait node is a fixed 5-second delay, not a human checkpoint.",
        "expected_tier": "Act Autonomously",
    },
    {
        "filename": "WhatsApp__Respond_to_WhatsApp_Messages_with_AI_Like_a_Pro!.json",
        "note": "Wait node with amount=0 — not a meaningful delay or a checkpoint.",
        "expected_tier": "Act Autonomously",
    },
    {
        "filename": "Forms_and_Surveys__Email_Subscription_Service_with_n8n_Forms,_Airtable_and_AI.json",
        "note": (
            "Genuine Form Trigger gates the subscribe path (Create Subscriber), "
            "but three other write actions run off a Schedule Trigger with no "
            "human involvement at all — same workflow, one path guarded, one "
            "path free. This should still classify Act Autonomously overall, "
            "since not every write action is gated."
        ),
        "expected_tier": "Act Autonomously",
    },
    {
        "filename": "Google_Drive_and_Google_Sheets__Extract_Information_from_a_Logo_Sheet_using_forms,_AI,_Google_Sheet_and_Airtable.json",
        "note": "Form Trigger is the workflow's entry point, but at least one write action downstream lacks a verified gate.",
        "expected_tier": "Act Autonomously",
    },
]


def test_known_gate_detection_cases():
    failures = []
    for case in KNOWN_CASES:
        path = os.path.join(CORPUS_DIR, case["filename"])
        if not os.path.exists(path):
            failures.append(f"MISSING FILE: {case['filename']} (corpus may have changed)")
            continue
        with open(path, "r", encoding="utf-8") as f:
            wf = json.load(f)
        result = score_workflow(wf, filename=case["filename"])
        actual_tier = result["dimensions"]["autonomy_tier"]["tier"]
        if actual_tier != case["expected_tier"]:
            failures.append(
                f"{case['filename']}: expected '{case['expected_tier']}', got '{actual_tier}'. "
                f"Context: {case['note']}"
            )

    assert not failures, "Gate-detection regression(s) found:\n" + "\n".join(failures)


def test_name_based_signal_surfaces_novel_gate_without_upgrading_tier():
    """
    Synthetic case: an unknown/novel node type named to suggest a human
    checkpoint, sitting upstream of a write action. The name-based
    secondary signal should surface it as a note in the reasoning text,
    but must NOT upgrade the tier to 'Act with Approval' — only a
    type-verified gate is allowed to do that. This code path never fires
    on the real 68-workflow corpus (no workflow happens to use an unknown
    node type with an approval-suggesting name), so it's only exercised
    here, deliberately, rather than left completely untested.
    """
    wf = {
        "name": "Test - novel approval node type",
        "nodes": [
            {"name": "Trigger", "type": "n8n-nodes-base.webhook", "parameters": {}},
            {"name": "Manager Approval Required", "type": "n8n-nodes-base.someUnknownNode", "parameters": {}},
            {"name": "Send Refund", "type": "n8n-nodes-base.httpRequest", "parameters": {"method": "POST", "url": "x"}},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Manager Approval Required", "type": "main", "index": 0}]]},
            "Manager Approval Required": {"main": [[{"node": "Send Refund", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    result = score_workflow(wf, filename="synthetic_novel_gate_type.json")
    tier = result["dimensions"]["autonomy_tier"]["tier"]
    reason = result["dimensions"]["autonomy_tier"]["reason"]

    assert tier == "Act Autonomously", (
        f"Name-based signal must never upgrade the tier on its own — expected "
        f"'Act Autonomously', got '{tier}'"
    )
    assert "Manager Approval Required" in reason and "unverified" in reason, (
        "Expected the novel-typed node to be surfaced as a possible unverified "
        "gate in the reasoning text, but it wasn't mentioned."
    )


def test_write_action_name_collision_does_not_self_flag():
    """
    Regression for a bug found while verifying the name-based signal itself:
    a write-action node whose own name happens to contain an approval-like
    word (e.g. an 'Auto-Approve and Send Slack' node — a fully automated
    action, no human involved) must NOT be flagged as a 'possible
    unverified approval step' for itself. A node cannot meaningfully gate
    its own execution.
    """
    wf = {
        "name": "Test - write node name collision",
        "nodes": [
            {"name": "Trigger", "type": "n8n-nodes-base.webhook", "parameters": {}},
            {"name": "Auto-Approve and Send Slack", "type": "n8n-nodes-base.slack", "parameters": {"text": "x"}},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Auto-Approve and Send Slack", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    result = score_workflow(wf, filename="synthetic_name_collision.json")
    reason = result["dimensions"]["autonomy_tier"]["reason"]

    assert "possible unverified approval step" not in reason, (
        f"Write-action node incorrectly self-flagged as its own possible gate. Reason: {reason}"
    )


def test_fallback_branch_bypassing_gate_is_detected():
    """
    Regression for a real-world failure pattern raised directly by a
    practitioner in review: a gate exists and is correctly wired on the
    'happy path,' but a separate retry/fallback branch reaches the same
    write action without ever passing through the gate. An earlier
    version of this rubric asked only 'does this write action have SOME
    gated ancestor' (backward traversal) — satisfied by the happy path
    alone, even though the fallback path bypasses the gate entirely. The
    correct question is forward reachability: is the write action
    reachable from any trigger via a path that never touches a gate node.
    """
    wf = {
        "name": "Test - fallback branch bypasses gate",
        "nodes": [
            {"name": "Trigger", "type": "n8n-nodes-base.webhook", "parameters": {}},
            {"name": "Try Primary API", "type": "n8n-nodes-base.httpRequest", "parameters": {"method": "GET", "url": "x"}},
            {"name": "Manager Approval", "type": "n8n-nodes-base.form", "parameters": {}},
            {"name": "Send Refund", "type": "n8n-nodes-base.httpRequest", "parameters": {"method": "POST", "url": "x"}},
            {"name": "On Primary Failure - Fallback", "type": "n8n-nodes-base.noOp", "parameters": {}},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Try Primary API", "type": "main", "index": 0}]]},
            "Try Primary API": {
                "main": [
                    [{"node": "Manager Approval", "type": "main", "index": 0}],
                    [{"node": "On Primary Failure - Fallback", "type": "main", "index": 1}],
                ]
            },
            "Manager Approval": {"main": [[{"node": "Send Refund", "type": "main", "index": 0}]]},
            "On Primary Failure - Fallback": {"main": [[{"node": "Send Refund", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    result = score_workflow(wf, filename="synthetic_fallback_bypass.json")
    tier = result["dimensions"]["autonomy_tier"]["tier"]
    assert tier == "Act Autonomously", (
        f"Expected the fallback-branch bypass to be detected as ungated ('Act Autonomously'), "
        f"got '{tier}' — the write action is reachable via a path that never passes through "
        f"the gate, so it must not be classified as protected."
    )


def test_properly_gated_workflow_with_no_bypass_still_passes():
    """
    Sanity-check counterpart to the bypass test above: the SAME workflow
    with only the bypass edge removed must correctly classify as
    genuinely gated. This confirms the forward-reachability fix didn't
    become overly strict and start flagging properly-gated workflows too.
    """
    wf = {
        "name": "Test - no bypass, genuinely gated",
        "nodes": [
            {"name": "Trigger", "type": "n8n-nodes-base.webhook", "parameters": {}},
            {"name": "Try Primary API", "type": "n8n-nodes-base.httpRequest", "parameters": {"method": "GET", "url": "x"}},
            {"name": "Manager Approval", "type": "n8n-nodes-base.form", "parameters": {}},
            {"name": "Send Refund", "type": "n8n-nodes-base.httpRequest", "parameters": {"method": "POST", "url": "x"}},
        ],
        "connections": {
            "Trigger": {"main": [[{"node": "Try Primary API", "type": "main", "index": 0}]]},
            "Try Primary API": {"main": [[{"node": "Manager Approval", "type": "main", "index": 0}]]},
            "Manager Approval": {"main": [[{"node": "Send Refund", "type": "main", "index": 0}]]},
        },
        "settings": {},
    }
    result = score_workflow(wf, filename="synthetic_no_bypass.json")
    tier = result["dimensions"]["autonomy_tier"]["tier"]
    assert tier == "Act with Approval", (
        f"Expected a genuinely single-path, gated write action to classify as "
        f"'Act with Approval', got '{tier}'"
    )


if __name__ == "__main__":
    test_known_gate_detection_cases()
    test_name_based_signal_surfaces_novel_gate_without_upgrading_tier()
    test_write_action_name_collision_does_not_self_flag()
    test_fallback_branch_bypassing_gate_is_detected()
    test_properly_gated_workflow_with_no_bypass_still_passes()
    print(f"All {len(KNOWN_CASES) + 4} gate-detection regression cases passed.")
