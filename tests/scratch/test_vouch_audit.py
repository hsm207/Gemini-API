"""Full Vouch Audit implementation using Gemini WebAPI.

Combines:
- Local tools: read_file, list_directory, check_line_lengths, measure_cyclomatic_complexity
- Vouch audit contracts: VouchStepResult, VouchStepTurnResponse, VouchReport
- Stage 1: File Size & Formatting Topology (fail-fast gate)
- Stage 2: Function Abstraction & Structure
- Fail-fast short-circuiting: halts immediately on REJECTED
- Zero persistent chat history leakage: runs in temporary ChatSession
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any, Literal
from dotenv import load_dotenv
from pydantic import BaseModel
import lizard

from gemini_webapi import GeminiClient

# ==========================================
# 1. Local Tool Definitions
# ==========================================

def read_file(filepath: str, start_line: int | None = None, end_line: int | None = None) -> str:
    """Read a file and return numbered lines, optionally bounded by line numbers."""
    path = Path(filepath).resolve()
    if not path.is_file():
        return f"Error: File not found: {filepath}"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        total_lines = len(lines)
        start = max(1, start_line or 1)
        end = min(total_lines, end_line or total_lines)
        
        numbered = [f"{i}: {lines[i-1]}" for i in range(start, end + 1)]
        header = f"[File: {filepath} | Showing lines {start} to {end} of {total_lines} total lines]\n"
        return header + "\n".join(numbered)
    except Exception as e:
        return f"Error reading file: {e}"

def list_directory(dirpath: str) -> str:
    """List directory contents."""
    path = Path(dirpath).resolve()
    if not path.is_dir():
        return f"Error: Directory not found: {dirpath}"
    try:
        items = []
        for entry in sorted(path.iterdir()):
            if entry.name.startswith((".", "__pycache__")):
                continue
            kind = "DIR " if entry.is_dir() else "FILE"
            items.append(f"{kind} {entry.name}")
        return "\n".join(items) if items else "(empty directory)"
    except Exception as e:
        return f"Error listing directory: {e}"

def check_line_lengths(filepath: str, max_length: int = 120) -> str:
    """Measure physical line lengths and report violations over max_length."""
    path = Path(filepath).resolve()
    if not path.is_file():
        return f"Error: File not found: {filepath}"
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        violations = [
            (idx + 1, len(line), line[:80] + ("..." if len(line) > 80 else ""))
            for idx, line in enumerate(lines)
            if len(line) > max_length
        ]
        if not violations:
            return f"PASSED: All {len(lines)} lines are within {max_length} characters."
        
        viol_lines = "\n".join([f"  Line {line_num} ({length} chars): {sample}" for line_num, length, sample in violations[:15]])
        extra = f"\n  ... and {len(violations) - 15} more violations" if len(violations) > 15 else ""
        return f"FAILED: Found {len(violations)} lines exceeding {max_length} characters:\n{viol_lines}{extra}"
    except Exception as e:
        return f"Error checking line lengths: {e}"

def measure_cyclomatic_complexity(filepath: str) -> str:
    """Measure cyclomatic complexity using lizard per function."""
    path = Path(filepath).resolve()
    if not path.is_file():
        return f"Error: File not found: {filepath}"
    try:
        result = lizard.analyze_file(str(path))
        complex_funcs = [
            {"name": f.name, "line": f.start_line, "cc": f.cyclomatic_complexity, "nloc": f.nloc}
            for f in result.function_list
            if f.cyclomatic_complexity > 10
        ]
        summary = {
            "filepath": filepath,
            "average_cc": round(result.average_cyclomatic_complexity, 2),
            "total_functions": len(result.function_list),
            "high_complexity_count (>10)": len(complex_funcs),
            "high_complexity_functions": complex_funcs[:10]
        }
        return json.dumps(summary, indent=2)
    except Exception as e:
        return f"Error measuring complexity: {e}"

TOOL_REGISTRY = {
    "read_file": read_file,
    "list_directory": list_directory,
    "check_line_lengths": check_line_lengths,
    "measure_cyclomatic_complexity": measure_cyclomatic_complexity,
}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read file contents with 1-based line numbers. Can specify start_line and end_line range.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Absolute or relative file path to read."},
                    "start_line": {"type": "integer", "description": "Optional starting line number (1-based)."},
                    "end_line": {"type": "integer", "description": "Optional ending line number (1-based)."}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List visible files and directories inside a directory path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dirpath": {"type": "string", "description": "Directory path to list."}
                },
                "required": ["dirpath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_line_lengths",
            "description": "Measure physical line lengths and report all violations exceeding max_length.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "File path to inspect."},
                    "max_length": {"type": "integer", "description": "Maximum allowed line length, default 120."}
                },
                "required": ["filepath"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "measure_cyclomatic_complexity",
            "description": "Measure McCabe's cyclomatic complexity per function in a source file using lizard.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filepath": {"type": "string", "description": "Source file to analyze."}
                },
                "required": ["filepath"]
            }
        }
    }
]

# ==========================================
# 2. Vouch Domain Data Contracts
# ==========================================

class VouchStepResult(BaseModel):
    step_name: str
    status: Literal["APPROVED", "REJECTED", "APPROVED_WITH_EXCEPTION", "INCONCLUSIVE"]
    violating_code_snippet: str | None = None
    explanation: str
    recommended_change: str = ""

class VouchStepTurnResponse(BaseModel):
    thinking: str
    action: Literal["SUBMIT_RESULT"]
    step_result: VouchStepResult

class VouchReport(BaseModel):
    input_target: str
    overall_status: Literal["VOUCHED", "REJECTED", "VOUCHED_WITH_EXCEPTION", "INCONCLUSIVE"]
    short_circuited_at_step: str | None = None
    step_results: list[VouchStepResult] = []
    explanation: str = ""

# ==========================================
# 3. Stage Prompts
# ==========================================

STAGE_1_INSTRUCTIONS = """You are the expert Inspector for Stage 1: File Size & Formatting Topology (Clean Code 2nd Edition).

Checklist Criteria (DO-CONFIRM):
1. The 200-500 Line Rule (File Size): VERIFY total file length is under 500 lines (~200 lines target). REJECT any file exceeding 500 lines as a monolithic blob that violates Single Responsibility.
2. The Newspaper Metaphor (Vertical Layout): VERIFY high-level entry points and public functions are positioned near the top, descending vertically to low-level private details. REJECT files with chaotic or upside-down function order.
3. Vertical Density & Openness: VERIFY concepts (imports, classes, functions, code blocks) are separated by clean blank lines. REJECT dense walls of code lacking vertical breathing space.
4. Horizontal Formatting Limits: Assess whether physical source lines exceed the 120-character guideline.

Protocol:
- You must use tools (`read_file`, `check_line_lengths`) to inspect the target file before delivering a verdict.
- When ready, submit your final verdict using the SUBMIT_RESULT action format.
"""

STAGE_2_INSTRUCTIONS = """You are an expert Inspector for Stage 2: Function Abstraction & Structure (Clean Code 2nd Edition).

SCOPE — PROJECT-OWNED CODE ONLY:
This checklist judges ONLY code the project authors and owns. Constructs that a
third-party framework/SDK forces the project to forward verbatim — a required
keyword argument, a forced signature, or a side effect executed inside a library
constructor the project cannot change — are downstream of an external contract,
not project design defects. When project code must conform to such a contract,
do NOT reject it: verify the project code documents the third-party rationale at
the call site and mark APPROVED (or note the contract in your explanation).

Checklist Criteria (DO-CONFIRM):
1. Level of Abstraction (Roller Coaster): VERIFY functions operate at a single, homogenous level of abstraction. REJECT functions that mix high-level policy (orchestration, formatting) with low-level implementation (raw indexing, bit manipulation, string formatting).
2. Top-to-Bottom Prose (Stepdown Rule): VERIFY caller functions are placed above the callee functions they invoke. REJECT upside-down function placement.
3. Single Level of Abstraction & Block Decomposition: VERIFY nested block bodies (if/else, loops) express one coherent step at a single abstraction level.
   DEFAULT BIAS:
     - A nested block should express one coherent step; delegate lower-level computation to named helpers.
   REJECT:
     - Blocks that interleave steps at different abstraction levels (e.g., a loop that both orchestrates and performs raw string parsing, formatting, or math), so the block's single intent is not readable at a glance.
   PERMITTED EXCEPTIONS (Justified Violations):
     - Cohesive Assembly Pipelines: a short inline loop that instantiates, maps, and appends local components into a collection, where all steps share one abstraction level and the block's intent is "assemble X".
   TRACEABILITY: When a normally-reject condition is permitted under an exception, the explanation MUST name the exception category (e.g., "PERMITTED — Cohesive Assembly Pipeline") and state why the abstraction-mixing harm is absent. A pass under a permitted exception is APPROVED, not APPROVED_WITH_EXCEPTION (which remains reserved for supplied human_overrides).
4. Encapsulated Conditionals (No Gerbils): VERIFY multi-branch type selection conditionals are encapsulated behind polymorphic abstractions or factory functions. REJECT raw switch/if-else ladders computing types.

Operational Protocol: In your `explanation`, you MUST provide a dispassionate Challenge-Verification-Response breakdown verifying each of the 4 items (e.g. "Item 1: VERIFIED at single abstraction level...").
"""

SYSTEM_BASE_TEMPLATE = """You are a Vouch Code Quality Inspector.
Available Tools:
{tools_json}

INSPECTION STAGE RULES:
{stage_rules}

INTERACTION PROTOCOL:
1. To invoke tools, respond ONLY with a raw JSON tool_calls payload:
{{
  "tool_calls": [
    {{
      "name": "<tool_name>",
      "arguments": {{ "<arg>": "<val>" }}
    }}
  ]
}}
2. When you have collected enough evidence and are ready to submit your stage verdict, you MUST respond ONLY with a raw JSON VouchStepTurnResponse:
{{
  "thinking": "<detailed step-by-step reasoning evaluating the checklist against verified tool observations>",
  "action": "SUBMIT_RESULT",
  "step_result": {{
    "step_name": "{step_name}",
    "status": "APPROVED" | "REJECTED" | "INCONCLUSIVE",
    "violating_code_snippet": "<snippet if REJECTED, else null>",
    "explanation": "<Item-by-item Challenge-Verification-Response breakdown>",
    "recommended_change": "<Actionable remediation if REJECTED, else empty string>"
  }}
}}
DO NOT include markdown backticks or extra text outside the JSON.
"""

# ==========================================
# 4. Agentic ReAct Stage Runner
# ==========================================

async def run_vouch_stage(
    client: GeminiClient,
    target_file: str,
    stage_name: str,
    stage_instructions: str,
    max_turns: int = 5,
) -> VouchStepResult:
    print(f"\n{'='*70}\n[STARTING STAGE] {stage_name}\nTarget: {target_file}\n{'='*70}")
    
    # Stateless temporary chat session - suppresses all persistence
    chat = client.start_chat()
    
    system_prompt = SYSTEM_BASE_TEMPLATE.format(
        tools_json=json.dumps(TOOL_SCHEMAS, indent=2),
        stage_rules=stage_instructions,
        step_name=stage_name,
    )
    
    user_prompt = (
        f"{system_prompt}\n\n"
        f"TARGET FILE: {target_file}\n"
        f"Perform your inspection using your tools and return your final VouchStepTurnResponse verdict."
    )
    
    prompt = user_prompt
    for turn in range(1, max_turns + 1):
        print(f"\n[Turn {turn}] Sending request to Gemini...")
        await asyncio.sleep(2.5)  # rate-limit pacing
        
        response = await chat.send_message(prompt, temporary=True, extended_thinking=True)
        text = response.text.strip()
        
        # Clean potential markdown fences
        clean_text = text
        if clean_text.startswith("```json"):
            clean_text = clean_text[7:]
        elif clean_text.startswith("```"):
            clean_text = clean_text[3:]
        if clean_text.endswith("```"):
            clean_text = clean_text[:-3]
        clean_text = clean_text.strip()
        
        try:
            data = json.loads(clean_text)
        except Exception:
            start = clean_text.find("{")
            end = clean_text.rfind("}")
            if start != -1 and end != -1:
                try:
                    data = json.loads(clean_text[start:end+1])
                except Exception:
                    data = None
            else:
                data = None
        
        if not data or not isinstance(data, dict):
            print(f"Warning: Non-JSON response received: {text[:200]}")
            prompt = "Please output ONLY a valid JSON object: either a 'tool_calls' payload or a 'SUBMIT_RESULT' VouchStepTurnResponse payload."
            continue
            
        # Case A: Tool Call
        if "tool_calls" in data:
            tool_calls = data["tool_calls"]
            print(f"[Turn {turn}] Agent requested {len(tool_calls)} tool call(s):")
            results = []
            for tc in tool_calls:
                fn_name = tc.get("name")
                args = tc.get("arguments", {})
                print(f"  -> Tool: {fn_name}({args})")
                func = TOOL_REGISTRY.get(fn_name)
                if not func:
                    out = f"Error: Tool '{fn_name}' not found."
                else:
                    try:
                        out = func(**args)
                    except Exception as err:
                        out = f"Tool Execution Error: {err}"
                
                snippet = out[:150] + "..." if len(out) > 150 else out
                print(f"     Result: {snippet}")
                results.append({"name": fn_name, "output": out})
            
            prompt = (
                f"Tool Execution Results:\n{json.dumps(results, indent=2)}\n\n"
                f"Continue your evaluation. If you have enough evidence, submit your final VouchStepTurnResponse JSON."
            )
            continue
            
        # Case B: Final Verdict (VouchStepTurnResponse)
        if data.get("action") == "SUBMIT_RESULT" and "step_result" in data:
            print(f"[Turn {turn}] Agent SUBMITTED final verdict:")
            thinking = data.get("thinking", "")
            print(f"  Thinking: {thinking[:200]}...")
            step_result_dict = data["step_result"]
            step_result = VouchStepResult(**step_result_dict)
            print(f"  Verdict: {step_result.status}")
            print(f"  Explanation: {step_result.explanation}")
            if step_result.recommended_change:
                print(f"  Recommended Change: {step_result.recommended_change}")
            return step_result
            
        print(f"Unrecognized payload structure: {list(data.keys())}")
        prompt = "Unrecognized response. Please output either 'tool_calls' or a 'SUBMIT_RESULT' payload."
        
    return VouchStepResult(
        step_name=stage_name,
        status="INCONCLUSIVE",
        explanation=f"Exhausted maximum tool turns ({max_turns}) without final verdict.",
    )

# ==========================================
# 5. Full Multi-Stage Audit Pipeline
# ==========================================

async def run_vouch_audit(client: GeminiClient, target_file: str) -> VouchReport:
    print(f"\n======================================================================")
    print(f"STARTING VOUCH AUDIT PIPELINE ON: {target_file}")
    print(f"======================================================================")
    
    stages = [
        ("Stage 1: File Size & Formatting Topology", STAGE_1_INSTRUCTIONS),
        ("Stage 2: Function Abstraction & Structure", STAGE_2_INSTRUCTIONS),
    ]
    
    step_results = []
    
    for stage_name, instructions in stages:
        result = await run_vouch_stage(client, target_file, stage_name, instructions)
        step_results.append(result)
        
        # FAIL-FAST SHORT-CIRCUIT:
        if result.status == "REJECTED":
            print(f"\n>>> [FAIL-FAST SHORT-CIRCUIT TRIGGERED] <<<")
            print(f"Stage '{stage_name}' REJECTED target code.")
            print(f"Halting audit pipeline immediately. Subsequent stages skipped.")
            return VouchReport(
                input_target=target_file,
                overall_status="REJECTED",
                short_circuited_at_step=stage_name,
                step_results=step_results,
                explanation=result.explanation,
            )
        elif result.status != "APPROVED":
            print(f"\n>>> [AUDIT INCONCLUSIVE] <<<")
            return VouchReport(
                input_target=target_file,
                overall_status="INCONCLUSIVE",
                short_circuited_at_step=stage_name,
                step_results=step_results,
                explanation=result.explanation,
            )
            
    print(f"\n>>> [AUDIT COMPLETED: VOUCHED] <<<")
    return VouchReport(
        input_target=target_file,
        overall_status="VOUCHED",
        step_results=step_results,
        explanation="All audit stages passed Clean Code standards successfully.",
    )

async def main():
    load_dotenv(override=True)
    sec_1psid = os.getenv("GEMINI_SECURE_1PSID")
    sec_1psidts = os.getenv("GEMINI_SECURE_1PSIDTS")
    
    if not sec_1psid:
        print("GEMINI_SECURE_1PSID missing from environment.")
        sys.exit(1)
        
    client = GeminiClient(
        secure_1psid=sec_1psid,
        secure_1psidts=sec_1psidts,
        auto_close=True,
        close_delay=60,
    )
    await client.init(timeout=30, auto_refresh=True)
    print("GeminiClient initialized successfully.")
    
    # Audit Target 1: Monolithic client.py (>2,600 lines) -> MUST REJECT AT STAGE 1 & SHORT-CIRCUIT!
    target_monolith = "src/gemini_webapi/client.py"
    report_monolith = await run_vouch_audit(client, target_monolith)
    print("\n--- REPORT 1 SUMMARY ---")
    print(f"Target: {report_monolith.input_target}")
    print(f"Status: {report_monolith.overall_status}")
    print(f"Short-circuited at: {report_monolith.short_circuited_at_step}")
    print(f"Stages Executed: {len(report_monolith.step_results)}")
    
    print("\nWaiting 5 seconds before next audit to maintain polite API pacing...")
    await asyncio.sleep(5)
    
    # Audit Target 2: Clean citation utility (80 lines, CC=6) -> MUST PASS STAGE 1 & PROCEED TO STAGE 2!
    target_clean = "src/gemini_webapi/utils/citation.py"
    report_clean = await run_vouch_audit(client, target_clean)
    print("\n--- REPORT 2 SUMMARY ---")
    print(f"Target: {report_clean.input_target}")
    print(f"Status: {report_clean.overall_status}")
    print(f"Short-circuited at: {report_clean.short_circuited_at_step}")
    print(f"Stages Executed: {len(report_clean.step_results)}")
    for res in report_clean.step_results:
        print(f"  * {res.step_name}: {res.status}")

if __name__ == "__main__":
    asyncio.run(main())

