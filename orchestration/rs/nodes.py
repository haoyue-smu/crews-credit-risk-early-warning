"""Retrieval Subgraph (RS) — Node implementations.

Async nodes for the retrieval pipeline:
  1. plan_retrieval        — LLM generates search queries per coverage topic
  2. execute_search        — Tavily search (dispatched via Send per query batch)
  3. normalize_and_dedup   — Deterministic dedup by URL, field normalization
  4. relevance_filter      — Hybrid: keyword filter + LLM relevance scoring
  5. coverage_gate         — Policy: checks topic coverage, decides retry or proceed
  6. retrieval_retry       — Generates refined queries for missing topics
  7. source_quality_assessment — Deterministic quality scoring of sources

All Tavily calls use the tavily-python SDK.
LLM calls go through OpenRouter (Gemini Flash).
"""

import asyncio
import hashlib
import json
import traceback
from datetime import datetime
from typing import Any, Dict
from urllib.parse import urlparse

from openai import AsyncOpenAI
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from shared.config import settings
from shared.llm import get_async_client, MODEL_RS
from shared.states.case_state import (
    AuditEvent,
    CoverageStatus,
    RawRetrievedItem,
    RetrievalQuery,
)
from orchestration.rs.coverage import (
    CoverageState,
    CoverageTopic,
    build_default_coverage_topics,
)
from orchestration.rs.prompts import PLAN_RETRIEVAL_SYSTEM, RELEVANCE_FILTER_SYSTEM
from orchestration.state import AgentWorkerState


# ---------------------------------------------------------------------------
# Clients
# ---------------------------------------------------------------------------

def _get_tavily_client():
    """Returns a TavilyClient. Raises clearly if the API key is missing.

    Import is deferred so the module loads without tavily installed.
    """
    settings.require_retrieval()
    from tavily import TavilyClient
    return TavilyClient(api_key=settings.tavily_api_key)


# ---------------------------------------------------------------------------
# Audit helper
# ---------------------------------------------------------------------------

def _audit(node_name: str, event: str, details: dict | None = None) -> AuditEvent:
    return AuditEvent(
        timestamp=datetime.utcnow(),
        node_name=node_name,
        event=event,
        details=details or {},
    )


# ---------------------------------------------------------------------------
# LLM helper (async + retry)
# ---------------------------------------------------------------------------

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((Exception,)),
    reraise=True,
)
async def _async_llm_json_call(
    client: AsyncOpenAI, model_id: str, system: str, user: str
) -> dict:
    """Async LLM call expecting JSON response."""
    response = await client.chat.completions.create(
        model=model_id,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
    )
    raw = response.choices[0].message.content
    return json.loads(raw)


# ---------------------------------------------------------------------------
# Domain reputation for source quality
# ---------------------------------------------------------------------------

_DOMAIN_QUALITY: dict[str, float] = {
    "reuters.com": 0.95, "bloomberg.com": 0.95, "wsj.com": 0.93,
    "ft.com": 0.92, "sec.gov": 0.98, "edgar.sec.gov": 0.98,
    "nytimes.com": 0.88, "bbc.com": 0.88, "cnbc.com": 0.85,
    "marketwatch.com": 0.82, "seekingalpha.com": 0.75,
    "yahoo.com": 0.70, "finance.yahoo.com": 0.78,
    "reddit.com": 0.45, "twitter.com": 0.40, "x.com": 0.40,
    "facebook.com": 0.30, "glassdoor.com": 0.55,
    "wikipedia.org": 0.65,
}


def _score_domain(url: str) -> float:
    """Score a URL's domain quality. Unknown domains get 0.50."""
    try:
        domain = urlparse(url).netloc.lower().lstrip("www.")
    except Exception:
        return 0.50

    # Check exact match first, then partial
    if domain in _DOMAIN_QUALITY:
        return _DOMAIN_QUALITY[domain]
    for known_domain, score in _DOMAIN_QUALITY.items():
        if known_domain in domain or domain in known_domain:
            return score
    return 0.50


def _recency_score(published_date: datetime | None) -> float:
    """Score recency: last 30 days = 1.0, decay to 0.3 over 2 years."""
    if published_date is None:
        return 0.50  # Unknown date
    days_old = (datetime.utcnow() - published_date).days
    if days_old < 0:
        days_old = 0
    if days_old <= 30:
        return 1.0
    if days_old <= 90:
        return 0.90
    if days_old <= 365:
        return 0.70
    if days_old <= 730:
        return 0.50
    return 0.30


# ---------------------------------------------------------------------------
# Node 1: Plan Retrieval (LLM)
# ---------------------------------------------------------------------------

async def plan_retrieval(state: AgentWorkerState) -> Dict[str, Any]:
    """LLM generates search queries based on company profile and financial features.

    Also initializes the dynamic coverage topic system.
    """
    print("--- [RS] PLAN RETRIEVAL ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    company = case.company
    features_summary = ""
    if case.financial_features:
        ff = case.financial_features
        z = ff.current_z_score
        z_info = f"Z-Score: {z.score} ({z.zone.value})" if z and z.score else "Z-Score: not computed"
        features_summary = (
            f"Key financials: Revenue={ff.income_statement.revenue}, "
            f"Net Income={ff.income_statement.net_income}, "
            f"D/E={ff.ratios.debt_to_equity}, "
            f"Current Ratio={ff.ratios.current_ratio}, "
            f"{z_info}"
        )

    # Build default coverage topics
    coverage_topics = build_default_coverage_topics(
        company_name=company.company_name,
        industry=company.industry_sector,
    )
    coverage_state = CoverageState(topics=coverage_topics)

    # Build LLM prompt
    topic_list = "\n".join(
        f"- {t.name}: {t.description} (min {t.min_sources} sources)"
        for t in coverage_topics
    )

    user_prompt = (
        f"Company: {company.company_name}\n"
        f"Type: {company.company_type}\n"
        f"Industry: {company.industry_sector or 'Unknown'}\n"
        f"Jurisdiction: {company.jurisdiction or 'Unknown'}\n"
        f"Ticker: {company.ticker or 'N/A'}\n"
        f"\n{features_summary}\n"
        f"\nRequired coverage topics:\n{topic_list}\n"
        f"\nGenerate search queries for comprehensive credit risk assessment."
    )

    client = get_async_client()
    model_id = MODEL_RS

    try:
        result = await _async_llm_json_call(client, model_id, PLAN_RETRIEVAL_SYSTEM, user_prompt)

        # Parse queries
        queries = []
        for q in result.get("queries", []):
            try:
                query = RetrievalQuery(
                    source=q["source"],
                    query=q["query"],
                    rationale=q.get("rationale", ""),
                    priority=q.get("priority", 2),
                )
                queries.append(query)
            except Exception as e:
                print(f"  Skipping malformed query: {e}")

        # Handle additional topics from LLM
        for at in result.get("additional_topics", []):
            new_topic = CoverageTopic(
                name=at.get("name", "custom"),
                description=at.get("description", ""),
                min_sources=at.get("min_sources", 1),
                sample_queries=at.get("sample_queries", []),
            )
            coverage_state.topics.append(new_topic)
            print(f"  + Dynamic topic added: {new_topic.name}")

        case.retrieval_plan = queries
        audit_events.append(_audit("plan_retrieval", "queries_generated", {
            "query_count": len(queries),
            "topics": [t.name for t in coverage_state.topics],
            "additional_topics": [at.get("name") for at in result.get("additional_topics", [])],
        }))
        print(f"  Generated {len(queries)} queries across {len(coverage_state.topics)} topics")

    except Exception as e:
        tb = traceback.format_exc()
        print(f"  ERROR in plan_retrieval: {e}")
        case.errors.append(f"plan_retrieval failed: {str(e)}")
        audit_events.append(_audit("plan_retrieval", "error", {"error": str(e), "traceback": tb}))

    case.status = "rs_plan_complete"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    # Store coverage state in the graph state for downstream nodes
    return {
        "case": case,
        "_rs_coverage": coverage_state.model_dump(),
    }


# ---------------------------------------------------------------------------
# Node 2: Execute Searches (Async — Tavily)
# ---------------------------------------------------------------------------

async def execute_searches(state: AgentWorkerState) -> Dict[str, Any]:
    """Execute all planned retrieval queries via Tavily in parallel (async).

    Groups queries by source type and runs them concurrently with asyncio.gather.
    Each Tavily call is wrapped with error handling per query.
    """
    print("--- [RS] EXECUTE SEARCHES ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    if not case.retrieval_plan:
        print("  No queries to execute.")
        audit_events.append(_audit("execute_searches", "no_queries"))
        case.audit_log.extend(audit_events)
        return {"case": case}

    tavily = _get_tavily_client()
    all_results: list[RawRetrievedItem] = []

    # Map source types to Tavily params
    SOURCE_PARAMS = {
        "news": {"topic": "news", "search_depth": "advanced", "max_results": 5},
        "web":  {"topic": "general", "search_depth": "basic", "max_results": 5},
        "financial_filings": {
            "topic": "general", "search_depth": "advanced", "max_results": 3,
            "include_domains": ["sec.gov", "edinet.go.jp", "annualreports.com"],
        },
        "forums": {
            "topic": "general", "search_depth": "basic", "max_results": 3,
            "include_domains": ["reddit.com", "quora.com"],
        },
        "social": {
            "topic": "general", "search_depth": "basic", "max_results": 3,
            "include_domains": ["twitter.com", "x.com", "linkedin.com"],
        },
    }

    async def _search_one(query: RetrievalQuery) -> list[RawRetrievedItem]:
        """Execute a single Tavily search for one query."""
        params = SOURCE_PARAMS.get(query.source, {"topic": "general", "search_depth": "basic", "max_results": 5})
        items = []
        try:
            # Tavily SDK is synchronous — run in executor
            loop = asyncio.get_running_loop()
            search_kwargs = {
                "query": query.query,
                "search_depth": params.get("search_depth", "basic"),
                "max_results": params.get("max_results", 5),
            }
            if "topic" in params:
                search_kwargs["topic"] = params["topic"]
            if "include_domains" in params:
                search_kwargs["include_domains"] = params["include_domains"]

            response = await loop.run_in_executor(None, lambda: tavily.search(**search_kwargs))

            for r in response.get("results", []):
                pub_date = None
                if r.get("published_date"):
                    try:
                        pub_date = datetime.fromisoformat(r["published_date"].replace("Z", "+00:00"))
                    except (ValueError, TypeError):
                        pass

                items.append(RawRetrievedItem(
                    source=query.source,
                    query=query.query,
                    title=r.get("title"),
                    url=r.get("url", ""),
                    snippet=r.get("content", "")[:500],
                    published_date=pub_date,
                    raw_payload=r,
                ))

        except Exception as e:
            print(f"  Search failed for [{query.source}] '{query.query[:50]}...': {e}")
            audit_events.append(_audit("execute_searches", "search_error", {
                "source": query.source, "query": query.query[:100], "error": str(e),
            }))

        return items

    # Run all searches concurrently
    tasks = [_search_one(q) for q in case.retrieval_plan]
    results = await asyncio.gather(*tasks)

    for batch in results:
        all_results.extend(batch)

    case.raw_retrieval_results.extend(all_results)
    audit_events.append(_audit("execute_searches", "searches_complete", {
        "total_queries": len(case.retrieval_plan),
        "total_results": len(all_results),
    }))
    print(f"  Retrieved {len(all_results)} results from {len(case.retrieval_plan)} queries")

    case.status = "rs_searches_complete"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {"case": case}


# ---------------------------------------------------------------------------
# Node 3: Normalize and Deduplicate (Deterministic)
# ---------------------------------------------------------------------------

async def normalize_and_dedup(state: AgentWorkerState) -> Dict[str, Any]:
    """Deterministic: remove exact-URL duplicates and normalize fields."""
    print("--- [RS] NORMALIZE & DEDUPLICATE ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    original_count = len(case.raw_retrieval_results)
    seen_urls: set[str] = set()
    deduped: list[RawRetrievedItem] = []

    for item in case.raw_retrieval_results:
        # Normalize URL
        url_key = item.url.strip().rstrip("/").lower()
        if url_key in seen_urls or not url_key:
            continue
        seen_urls.add(url_key)
        deduped.append(item)

    case.raw_retrieval_results = deduped
    removed = original_count - len(deduped)

    audit_events.append(_audit("normalize_and_dedup", "dedup_complete", {
        "original": original_count, "after_dedup": len(deduped), "removed": removed,
    }))
    print(f"  {original_count} → {len(deduped)} (removed {removed} duplicates)")

    case.status = "rs_normalized"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {"case": case}


# ---------------------------------------------------------------------------
# Node 4: Relevance Filter (Hybrid)
# ---------------------------------------------------------------------------

async def relevance_filter(state: AgentWorkerState) -> Dict[str, Any]:
    """Filter results by relevance. Two-pass:

    Pass 1 (deterministic): Remove results with empty snippets or non-matching URLs.
    Pass 2 (LLM): Score remaining results for relevance (batched).
    """
    print("--- [RS] RELEVANCE FILTER ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    company_name = case.company.company_name.lower()
    company_terms = set(company_name.split())

    # Pass 1: Deterministic filter
    pre_filter = []
    for item in case.raw_retrieval_results:
        snippet = (item.snippet or "").lower()
        title = (item.title or "").lower()
        # Keep if any company name term appears in title or snippet
        if any(term in snippet or term in title for term in company_terms if len(term) > 2):
            pre_filter.append(item)
        elif item.source in ("financial_filings",):
            # Keep all filing results regardless
            pre_filter.append(item)

    dropped_deterministic = len(case.raw_retrieval_results) - len(pre_filter)

    # Pass 2: LLM relevance scoring — batched in chunks of 25 to handle large result sets
    scored_results = pre_filter  # Default: keep all pre-filtered results
    _BATCH_SIZE = 25
    if pre_filter:
        try:
            client = get_async_client()
            model_id = MODEL_RS

            url_scores: dict[str, float] = {}
            url_topics: dict[str, list[str]] = {}

            # Process in batches so large result sets are always scored
            for batch_start in range(0, len(pre_filter), _BATCH_SIZE):
                batch = pre_filter[batch_start: batch_start + _BATCH_SIZE]
                items_for_scoring = [
                    {
                        "url": item.url,
                        "title": item.title or "",
                        "snippet": (item.snippet or "")[:200],
                        "source": item.source,
                    }
                    for item in batch
                ]
                user_prompt = (
                    f"Company: {case.company.company_name}\n"
                    f"Industry: {case.company.industry_sector or 'Unknown'}\n\n"
                    f"Items to score:\n{json.dumps(items_for_scoring, indent=2)}\n\n"
                    f"Score each item's relevance to credit risk assessment for this company."
                )
                result = await _async_llm_json_call(client, model_id, RELEVANCE_FILTER_SYSTEM, user_prompt)
                for s in result.get("scores", []):
                    url_scores[s.get("url", "")] = s.get("relevance_score", 0.5)
                    url_topics[s.get("url", "")] = s.get("matched_topics", [])

            # Keep items scoring >= 0.3
            scored_results = []
            for item in pre_filter:
                score = url_scores.get(item.url, 0.5)
                if score >= 0.3:
                    item.raw_payload["_relevance_score"] = score
                    item.raw_payload["_matched_topics"] = url_topics.get(item.url, [])
                    scored_results.append(item)

        except Exception as e:
            print(f"  LLM relevance scoring failed, keeping all pre-filtered: {e}")
            scored_results = pre_filter

    dropped_relevance = len(pre_filter) - len(scored_results)
    case.raw_retrieval_results = scored_results

    audit_events.append(_audit("relevance_filter", "filter_complete", {
        "dropped_deterministic": dropped_deterministic,
        "dropped_relevance": dropped_relevance,
        "remaining": len(scored_results),
    }))
    print(f"  Filtered: -{dropped_deterministic} (keywords) -{dropped_relevance} (relevance) → {len(scored_results)} remaining")

    case.status = "rs_filtered"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {"case": case}


# ---------------------------------------------------------------------------
# Node 5: Coverage Gate (Policy)
# ---------------------------------------------------------------------------

async def coverage_gate(state: AgentWorkerState) -> Dict[str, Any]:
    """Policy gate: checks if coverage topics have sufficient evidence.

    Returns updated case with coverage status + routing decision.
    The graph edges will use coverage.status to decide next step.
    """
    print("--- [RS] COVERAGE GATE ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    # Rebuild coverage state
    rs_cov_data = state.get("_rs_coverage")
    if rs_cov_data:
        coverage_state = CoverageState(**rs_cov_data)
    else:
        coverage_state = CoverageState(
            topics=build_default_coverage_topics(case.company.company_name, case.company.industry_sector)
        )

    # Extended keyword aliases: topic name → synonyms to match in snippets
    _TOPIC_KEYWORDS: dict[str, list[str]] = {
        "financials": ["financial", "revenue", "earnings", "profit", "income", "debt", "cash flow", "ebitda", "balance sheet", "credit"],
        "controversy": ["controversy", "controversial", "scandal", "allegation", "misconduct", "fraud", "investigate"],
        "operational_efficiency": ["operational", "efficiency", "productivity", "cost reduction", "margin", "throughput", "utilization"],
        "governance": ["governance", "board", "director", "executive", "oversight", "shareholder", "audit committee"],
        "legal_regulatory": ["legal", "regulatory", "lawsuit", "regulation", "compliance", "sec", "fine", "penalty", "litigation"],
        "market_position": ["market", "position", "market share", "competitive", "industry", "sector", "ranking", "leadership"],
        "management": ["management", "ceo", "cfo", "executive", "leadership", "officer", "president", "appointment"],
        "competition": ["competition", "competitor", "rival", "peer", "industry trend", "market dynamics"],
        "environmental": ["environmental", "esg", "sustainability", "carbon", "emissions", "climate", "green"],
        "supply_chain_risk": ["supply chain", "supplier", "procurement", "logistics", "inventory", "sourcing", "disruption"],
    }

    # Count results matching each topic
    for topic in coverage_state.topics:
        matching_count = 0
        keywords = _TOPIC_KEYWORDS.get(topic.name, topic.name.replace("_", " ").split())
        for item in case.raw_retrieval_results:
            matched_topics = item.raw_payload.get("_matched_topics", [])
            if topic.name in matched_topics:
                matching_count += 1
            elif not matched_topics:
                # Heuristic: check extended keyword aliases in snippet + title
                text = ((item.snippet or "") + " " + (item.title or "")).lower()
                if any(kw in text for kw in keywords):
                    matching_count += 1
        coverage_state.update_topic(topic.name, matching_count)

    coverage_state.current_attempt += 1
    coverage_state.overall_status = coverage_state.check_coverage()

    # Update CaseState coverage
    covered = [t.name for t in coverage_state.get_covered_topics()]
    missing = [t.name for t in coverage_state.get_missing_topics()]

    case.coverage = CoverageStatus(
        status=coverage_state.overall_status,
        topics_covered=covered,
        topics_missing=missing,
        attempts=coverage_state.current_attempt,
    )

    audit_events.append(_audit("coverage_gate", "coverage_assessed", {
        "status": coverage_state.overall_status,
        "covered": covered,
        "missing": missing,
        "attempt": coverage_state.current_attempt,
        "can_retry": coverage_state.can_retry(),
    }))
    print(f"  Coverage: {coverage_state.overall_status} (attempt {coverage_state.current_attempt})")
    print(f"  Covered: {covered}")
    print(f"  Missing: {missing}")

    # Set status for routing
    if coverage_state.overall_status == "sufficient":
        case.status = "rs_coverage_sufficient"
    elif coverage_state.can_retry():
        case.status = "rs_coverage_retry"
    else:
        case.status = "rs_coverage_exhausted"

    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {
        "case": case,
        "_rs_coverage": coverage_state.model_dump(),
    }


# ---------------------------------------------------------------------------
# Node 6: Retrieval Retry (generates new queries for missing topics)
# ---------------------------------------------------------------------------

async def retrieval_retry(state: AgentWorkerState) -> Dict[str, Any]:
    """Generate refined queries for coverage topics that are still missing."""
    print("--- [RS] RETRIEVAL RETRY ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    missing_topics = case.coverage.topics_missing
    if not missing_topics:
        print("  No missing topics to retry.")
        case.status = "rs_retry_noop"
        case.audit_log.extend(audit_events)
        return {"case": case}

    # Re-read coverage state
    rs_cov_data = state.get("_rs_coverage")
    coverage_state = CoverageState(**rs_cov_data) if rs_cov_data else None

    # Generate new queries using LLM
    client = get_async_client()
    model_id = MODEL_RS

    retry_prompt = (
        f"Company: {case.company.company_name}\n"
        f"Industry: {case.company.industry_sector or 'Unknown'}\n\n"
        f"The following coverage topics need more evidence:\n"
    )
    for topic_name in missing_topics:
        desc = ""
        if coverage_state:
            for t in coverage_state.topics:
                if t.name == topic_name:
                    desc = t.description
                    break
        retry_prompt += f"- {topic_name}: {desc}\n"

    retry_prompt += (
        "\nGenerate 2 refined search queries per missing topic. "
        "Use DIFFERENT query formulations than before. "
        "Return JSON: {\"queries\": [{\"source\": \"...\", \"query\": \"...\", \"rationale\": \"...\", \"priority\": 1}]}"
    )

    try:
        result = await _async_llm_json_call(client, model_id, PLAN_RETRIEVAL_SYSTEM, retry_prompt)

        new_queries = []
        for q in result.get("queries", []):
            try:
                query = RetrievalQuery(
                    source=q["source"],
                    query=q["query"],
                    rationale=q.get("rationale", "retry query"),
                    priority=q.get("priority", 1),
                )
                new_queries.append(query)
            except Exception:
                pass

        case.retrieval_plan = new_queries  # Replace plan with retry queries
        audit_events.append(_audit("retrieval_retry", "retry_queries_generated", {
            "query_count": len(new_queries),
            "missing_topics": missing_topics,
        }))
        print(f"  Generated {len(new_queries)} retry queries for {missing_topics}")

    except Exception as e:
        print(f"  Retry query generation failed: {e}")
        audit_events.append(_audit("retrieval_retry", "error", {"error": str(e)}))

    case.status = "rs_retrying"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {"case": case, "_rs_coverage": rs_cov_data}


# ---------------------------------------------------------------------------
# Node 7: Source Quality Assessment (Deterministic)
# ---------------------------------------------------------------------------

async def source_quality_assessment(state: AgentWorkerState) -> Dict[str, Any]:
    """Score each retrieved item for source quality.

    Factors: domain reputation, recency, corroboration (URL overlap).
    Produces normalized_documents ready for SIS handoff.
    """
    print("--- [RS] SOURCE QUALITY ASSESSMENT ---")
    case = state["case"].model_copy(deep=True)
    audit_events = []

    # Score each item
    url_counts: dict[str, int] = {}
    for item in case.raw_retrieval_results:
        domain = urlparse(item.url).netloc.lower()
        url_counts[domain] = url_counts.get(domain, 0) + 1

    scored_items = []
    for item in case.raw_retrieval_results:
        domain_score = _score_domain(item.url)
        recency = _recency_score(item.published_date)
        domain = urlparse(item.url).netloc.lower()
        corroboration = min(url_counts.get(domain, 1) / 3.0, 1.0)

        quality = round(0.5 * domain_score + 0.3 * recency + 0.2 * corroboration, 3)
        item.raw_payload["_quality_score"] = quality
        item.raw_payload["_domain_score"] = domain_score
        item.raw_payload["_recency_score"] = recency
        scored_items.append(item)

    case.raw_retrieval_results = scored_items

    # Build normalized documents for SIS handoff
    from shared.schemas.documents import DocumentInput, SourceType

    source_type_map = {
        "news": SourceType.news,
        "web": SourceType.web,
        "financial_filings": SourceType.filing,
        "forums": SourceType.forum,
        "social": SourceType.social,
    }

    normalized = []
    for item in scored_items:
        quality = item.raw_payload.get("_quality_score", 0.5)
        if quality < 0.2:
            continue  # Skip very low quality sources

        doc_id = hashlib.md5(item.url.encode()).hexdigest()[:12]
        source_type = source_type_map.get(item.source, SourceType.web)

        try:
            normalized.append(DocumentInput(
                document_id=f"rs-{doc_id}",
                company_id=case.company.company_id,
                source_name=item.source,
                source_type=source_type,
                published_date=item.published_date or datetime.utcnow(),
                fetched_date=datetime.utcnow(),
                url=item.url,
                full_text=item.snippet or item.title or "",
                language="en",
                source_quality_score=quality,
            ))
        except Exception as e:
            print(f"  Skipping item {item.url}: {e}")

    case.normalized_documents = normalized

    audit_events.append(_audit("source_quality_assessment", "assessment_complete", {
        "total_scored": len(scored_items),
        "normalized_for_sis": len(normalized),
        "avg_quality": round(sum(i.raw_payload.get("_quality_score", 0) for i in scored_items) / max(len(scored_items), 1), 3),
    }))
    print(f"  Scored {len(scored_items)} items, {len(normalized)} normalized for SIS")

    case.status = "rs_complete"
    case.updated_at = datetime.utcnow()
    case.audit_log.extend(audit_events)

    return {"case": case}
