"""
Neurosymbolic Guardrails & Debouncing Hooks for Strands Agents
Derived from patterns in aws-samples/sample-why-agents-fail:
1. Memory Pointer Pattern (Context Window Overflow Prevention)
2. Debounce Hook (Reasoning Loop Prevention)
3. Neurosymbolic Rule Enforcement (Deterministic Rule Validation)
4. Executor-Validator-Critic Verification
"""

import os
import json
import logging
import re
from typing import Dict, Any, Tuple, List, Optional

logger = logging.getLogger("clintrial_agent.guardrails")

# ==============================================================================
# 1. DEBOUNCE HOOK (Reasoning Loop Prevention)
# ==============================================================================
class DebounceHook:
    """
    Prevents agents from entering infinite loops by repeating identical tool calls.
    Tracks (tool_name, serialized_args) history and debounces repeated invocations.
    """
    def __init__(self, max_repeats: int = 2):
        self.max_repeats = max_repeats
        self.call_counts: Dict[str, int] = {}

    def _hash_call(self, tool_name: str, tool_args: Dict[str, Any]) -> str:
        serialized = json.dumps(tool_args, sort_keys=True, default=str)
        return f"{tool_name}:{serialized}"

    def check_call(self, tool_name: str, tool_args: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Returns (is_allowed, reason). If repeated > max_repeats, returns (False, error_msg).
        """
        call_key = self._hash_call(tool_name, tool_args)
        count = self.call_counts.get(call_key, 0) + 1
        self.call_counts[call_key] = count

        if count > self.max_repeats:
            logger.warning(f"DebounceHook: Suppressed repeated call to '{tool_name}' ({count} times)")
            return False, (
                f"DEBOUNCE GUARDRAIL: Tool '{tool_name}' with arguments {tool_args} "
                f"has been called {count} times in succession. "
                "Repeated execution blocked to prevent reasoning loops. "
                "Proceed with the gathered results or transition to the next step."
            )
        return True, ""

    def reset(self):
        """Reset call history for a new trial invocation."""
        self.call_counts.clear()


# ==============================================================================
# 2. MEMORY POINTER PATTERN (Context Window Overflow Prevention)
# ==============================================================================
class MemoryPointer:
    """
    Saves large tool outputs to disk/cache and returns a concise, token-efficient
    pointer representation for the LLM context window.
    """
    @staticmethod
    def create_pointer(nct_id: str, payload_type: str, full_data: Dict[str, Any], max_summary_chars: int = 1200) -> Dict[str, Any]:
        os.makedirs("analysis_json", exist_ok=True)
        pointer_path = os.path.abspath(os.path.join("analysis_json", f"{nct_id}_{payload_type}_pointer.json"))
        
        with open(pointer_path, "w") as f:
            json.dump(full_data, f, indent=2, default=str)
            
        # Build concise context summary
        summary = full_data.get("summary", {})
        if not summary and "design" in full_data:
            summary = {
                "design_type": full_data.get("design", {}).get("design_type"),
                "phases": full_data.get("design", {}).get("phases"),
                "sample_size": full_data.get("power", {}).get("enrollment"),
                "power_status": full_data.get("power", {}).get("assessment")
            }

        return {
            "pointer_id": f"{nct_id}_{payload_type}",
            "pointer_path": pointer_path,
            "status": "STORED_OFF_CONTEXT",
            "summary": summary,
            "instruction": "Full payload saved off-context to pointer_path. Use field values from summary."
        }


# ==============================================================================
# 3. NEUROSYMBOLIC GUARDRAIL (Deterministic Rule Validation)
# ==============================================================================
class NeurosymbolicGuardrail:
    """
    Enforces non-negotiable symbolic domain rules that LLMs cannot hallucinate past.
    """
    
    @staticmethod
    def validate_phase_power_solver(phase_str: str, solver_name: str) -> Tuple[bool, str]:
        """Rule 1: Phase 1 trials MUST NOT call efficacy power solvers."""
        normalized_phase = phase_str.upper().replace(" ", "")
        if "PHASE1" in normalized_phase or "PHASEI" in normalized_phase:
            if solver_name in ["simon2stage", "n_survival", "powertost", "gsdesign2_nph"]:
                return False, (
                    f"NEUROSYMBOLIC RULE VIOLATION: Trial phase is '{phase_str}'. "
                    f"Solver '{solver_name}' cannot be run for Phase I safety/dose-escalation designs. "
                    "Report power as N/A per Textbook Ch. 2."
                )
        return True, ""

    @staticmethod
    def validate_simon2stage_params(pu: float, pa: float) -> Tuple[float, float, Optional[str]]:
        """Rule 2: Simon's Two-Stage requires p0 (pu) < p1 (pa). Auto-corrects ordering."""
        warning = None
        if pu >= pa:
            logger.warning(f"NeurosymbolicGuardrail: Corrected reversed Simon's 2-stage parameters pu={pu}, pa={pa}")
            new_pu = min(pu, pa)
            new_pa = max(pu, pa)
            if new_pu == new_pa:
                new_pa = min(0.99, new_pu + 0.15)
            warning = f"Auto-corrected parameter order from pu={pu}, pa={pa} to pu={new_pu}, pa={new_pa}."
            return new_pu, new_pa, warning
        return pu, pa, None

    @staticmethod
    def validate_report_content(report_text: str) -> Tuple[bool, List[str], str]:
        """Rule 3: Reports must not contain unpopulated placeholders or missing required sections."""
        placeholders = re.findall(r"\[[A-Za-z0-9_\s]{3,40}\]", report_text)
        
        required_sections = [
            "Trial Overview & Design",
            "Statistical Plan & Power",
            "Safety & Pharmacogenetics",
            "Feasibility & Recruitment",
            "Executive Recommendations"
        ]
        
        missing_sections = [sec for sec in required_sections if sec.lower() not in report_text.lower()]
        
        clean_text = report_text
        for ph in placeholders:
            # Replace placeholder with clean domain fallback
            clean_text = clean_text.replace(ph, "the protocol specification")
            
        is_valid = len(placeholders) == 0 and len(missing_sections) == 0
        return is_valid, placeholders, clean_text
