# Structured Agent Outputs: Stochastic Expectation to Contract-based Transactions

### TIQ Agents Refactoring - Q3 '25
**Date:** 2025-07-10
**Status:** Implemented for Consultant Agent

---

### 1. Executive Summary (TL;DR)

This document outlines the successful refactoring of **the agent output processing layer**. We have transitioned from a fragile, parsing-based model (**Stochastic Expectations**) to a robust, schema-driven system (**Contract-Based Transactions**). This change enforces a strict data contract with our AI agents, **eliminating a major source of runtime errors and significantly increasing workflow reliability**. This provides a stable foundation for all future agentic development.

---

### 2. Previous State & Associated Problems

Initially, the system relied on **instructing the LLM via prompting to format its final output as a JSON string, which was then extracted from the text using regular expressions**.

This approach was subject to several critical problems:

*   **Fragility:** The entire workflow was vulnerable to minor deviations in the LLM's output format. An extra sentence, a misplaced comma, or a change in markdown formatting would cause the parsing logic to fail.
*   **High Maintenance:** Any change to the desired output structure required meticulously updating both the natural language prompt and the corresponding regex/parsing code, making the system brittle and slow to evolve.
*   **Poor Debuggability:** When failures occurred, it was difficult to isolate the root cause. The issue could be a faulty prompt, an LLM hallucination, or a bug in our parsing logic, leading to time-consuming investigations.
*   **Unpredictability:** We were fundamentally *hoping* the agent would follow instructions, with no mechanism to enforce the output structure, leading to unpredictable and inconsistent behavior in production.

---

### 3. Refactored Approach & Implementation

The new architecture implements a **Pydantic Contract-Based Transaction** model using AutoGen's native structured output capabilities.

**Old Workflow:**
```
[Service] → [Agent] → [LLM] → (Hopes for good format) 
→ [String] → [Regex Parser] → (Crash?) → [Data]

```
**New Workflow:**
```
[Service] → [Agent + Pydantic Schema] → [LLM (Tool/Function Call)]
→ [Validated JSON] → [Type-Safe Data Object]
```
The implementation involved three key changes:

1.  **Schema Definition:** A Pydantic model (`FinalAnalysis`) was created in `schemas.py`. This model serves as the formal, machine-readable "contract" that defines the required fields and data types for the agent's final output.
2.  **Agent Configuration:** The final agent in the workflow (`consultant_agent`) was configured with `output_content_type=FinalAnalysis`. This instructs AutoGen to leverage the LLM's tool-calling functionality to force its response into a JSON object that strictly conforms to our Pydantic schema.
3.  **Service Layer Simplification:** The fragile regex parsing function (`_process_chat_results`) was entirely **removed**. The service now directly receives a `StructuredMessage` from the agent team, accessing the validated data safely through its `.content` attribute.

---

### 4. Impact and Strategic Benefits

This refactoring delivers immediate and long-term value across several key areas:

*   **Reliability:** By eliminating parsing errors, we have drastically increased the success rate of our analysis workflows. The system is no longer vulnerable to the stochastic nature of LLM text generation for its core data exchange.
*   **Maintainability:** The Pydantic schema is now the single source of truth for the output format. Modifying the final report structure is as simple as updating the model, with no changes needed in the service layer.
*   **Developer Experience:** We have replaced brittle, error-prone code with type-safe data objects. This enables static analysis, IDE autocompletion, and reduces the cognitive load for developers working with agent outputs.
*   **Foundation for Future Work:** This robust, contract-based approach is a prerequisite for building more complex, multi-step, and branching agentic workflows. It provides the predictable building blocks needed for reliable system composition.
