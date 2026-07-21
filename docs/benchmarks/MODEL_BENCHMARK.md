# Local LLM Backend Benchmark: Gemma-4 (Q8) vs. Qwythos (9B)

This document records the empirical evaluation of local open-weight model backends running via `llama-server` on Apple Silicon M4 GPU (port 8080) for the Strands Clinical Agentic Pipeline.

---

## 📊 Summary Comparison

| Evaluation Metric | 💎 Gemma-4-E2B-it (Q8_0) | 🐉 Qwythos-9B-Claude-Mythos-5-1M (Q4_K_M) |
| :--- | :--- | :--- |
| **Model Size / Quantization** | ~9.6 GB (Q8_0) | ~5.8 GB (Q4_K_M) |
| **Workflow Completion Rate** | **3 / 3 (100% Success)** | **1 / 3 (66% Token Limit Failure)** |
| **Instruction Adherence** | **Strict / Focused** | **Conversational / Overly Verbose** |
| **Output Token Budget** | ~50 lines per trial assessment | Exceeds 3,000 output tokens (Generates unasked boilerplate & appendices) |
| **Execution Stability** | 🟢 **Stable** | 🔴 Triggers `MaxTokensReachedException` |
| **Tool Calling Integration** | Native FastMCP compatible | FastMCP compatible (with high latency) |

---

## 🔍 Key Findings

1. **Gemma-4 Q8 (Chosen Default):**
   * Produces concise, publication-grade markdown assessments.
   * Accurately parses RBridge statistical results without inventing empty templates.
   * Executes multi-node State-Machine Graphs (`strands_clinical_graph.py`) with zero context window crashes.

2. **Qwythos 9B:**
   * Tends to emit multi-page boilerplate document templates (operational details, data management policies, ethical considerations, Appendices A/B/C).
   * Generates long output strings that exceed agent loop limits (`MaxTokensReachedException`).

---

## 🎯 Production Recommendation
**Gemma-4-E2B-it (Q8_0)** is configured as the default LLM backend for all local clinical agent workflows.
