# Retrieval Subgraph (RS) Implementation Plan

Based on your LangGraph architecture and the established `CaseState` schema, here is the detailed plan for building the **Retrieval Subgraph (RS)**.

## Goal Description
The objective of the RS is to dynamically generate targeted search queries based on the company's profile and extracted financial data, execute them concurrently using Tavily, filter the results, and ensure sufficient information coverage before handing off to the Signal Intelligence Subgraph (SIS).

## 1. Graph State and Concurrency Architecture

We will adhere to **Option B (Dynamic Map-Reduce)** as requested previously.
* Rather than hardcoding separate `search_news` or `search_web` nodes, we will use LangGraph's dynamic `Send` API.
* The `plan_retrieval` node will analyze the company and generate a list of `RetrievalQuery` objects.
* We will return `[Send("parallel_fetch", query) for query in queries]`, which forces LangGraph to spawn isolated parallel nodes for every search query simultaneously.

## 2. Node Implementations (`orchestration/rs/nodes.py`)

1. **`plan_retrieval`**
   * **Role:** Analyzes `CaseState.company` and `CaseState.financial_features`.
   * **Action:** Prompts OpenRouter to yield a Pydantic list of `RetrievalQuery` (specifying `source` as "news", "web", etc., along with a `rationale`).

2. **`parallel_fetch` (The Map Node)**
   * **Role:** Executes a single `RetrievalQuery`.
   * **Action:** Uses the `tavily-python` REST SDK. If `source == "news"`, it sets Tavily's `topic="news"`. Extracts the payloads and returns them as `RawRetrievedItem`s. Uses `operator.add` in the state to safely push results to the global list concurrently.

3. **`normalize_and_deduplicate` (The Reduce Node)**
   * **Role:** Sync point after all parallel fetches complete.
   * **Action:** Strips exact duplicate URLs and poorly formatted snippets. Converts `RawRetrievedItem`s into the uniform `DocumentInput` format expected by your SIS schema.

4. **`relevance_filter`**
   * **Role:** Quick pass to drop irrelevant context.
   * **Action:** OpenRouter evaluates snippets against the company ticker/name to drop false positives (e.g., matching a totally different company with a similar name).

5. **`coverage_gate` & `retrieval_retry`**
   * **Role:** Determines routing.
   * **Action:** Evaluates `topics_missing`. If the `CoverageStatus.status` is "insufficient" and `CoverageStatus.attempts < 3`, we route to `retrieval_retry` which prompts OpenRouter to formulate new gap-filling queries, looping back to `parallel_fetch`. If sufficient (or max attempts hit), we route to `END`.

## 3. Tool & API Dependencies
* We will install `tavily-python` in your `venv`.
* We will add `TAVILY_API_KEY` to your `.env` and `shared/config.py`.

## User Review Required

> [!CAUTION]
> **Open Question 1:** For `relevance_filter`, doing an LLM call on *every single snippet* can be slow and expensive. Do you want an LLM to evaluate relevance, or a deterministic string-matching approach (e.g., ensuring the snippet contains the company name)?
>
> **Open Question 2:** Should we mock the Tavily implementation first so you can test it without an API key, or do you have a Tavily API key ready to go?

Please review this plan and let me know your choices for the open questions!
