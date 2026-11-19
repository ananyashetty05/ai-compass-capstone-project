"""Labelled evaluation of the query-understanding stage (task, domain, complexity, multi-intent, constraints, ambiguity).

The labels below were written by hand *before* the analyzer was tuned and are independent of its regexes. The set is small
(see ``len(CASES)``) and hand-made, so accuracy figures are indicative of regressions, not population estimates.

Usage (from backend/):  python -m benchmarks.understanding_eval [--json out.json] [--verbose]
"""
import argparse
import json
import sys
from typing import Any, Dict, List

from app.services.routing_engine import understanding

BANDS = ["simple", "moderate", "complex", "highly_complex"]


def C(q: str, intent: str, domain: str, band: str, *, secondary: List[str] = (), reqs: List[str] = (), clarify: bool = False) -> Dict[str, Any]:
    return {"q": q, "intent": intent, "domain": domain, "band": band, "secondary": list(secondary), "reqs": list(reqs), "clarify": clarify}


CASES: List[Dict[str, Any]] = [
    # simple factual / explanation
    C("What is the capital of France?", "qa", "general", "simple"),
    C("Who wrote Pride and Prejudice?", "qa", "general", "simple"),
    C("Explain what a hash map is in two sentences.", "reasoning", "computer_science", "simple", reqs=["length_target"]),
    C("What does HTTP status 404 mean?", "qa", "computer_science", "simple"),
    C("Translate 'good morning' into Spanish.", "translation", "general", "simple", reqs=["output_language"]),
    # mathematics - short but hard
    C("Prove that there are infinitely many prime numbers.", "math", "mathematics", "complex"),
    C("Prove that the sum of the reciprocals of the primes diverges, and give a rigorous argument for each step.", "math", "mathematics", "highly_complex"),
    C("What is 17 * 23?", "math", "mathematics", "simple"),
    C("Solve x^2 - 5x + 6 = 0.", "math", "mathematics", "simple"),
    C("I need the most accurate model for a hard mathematical olympiad problem about inequalities.", "math", "mathematics", "complex", reqs=["accuracy"]),
    C("Derive the closed form of the Fibonacci sequence using generating functions.", "math", "mathematics", "complex"),
    # coding
    C("Write a Python function that reverses a string.", "coding", "computer_science", "simple", reqs=["programming_language"]),
    C("Write a Python async web crawler with rate limiting, retries with exponential backoff and unit tests.", "coding", "computer_science", "complex", reqs=["programming_language"]),
    C("Implement a lock-free concurrent queue in Rust and prove it is linearizable.", "coding", "computer_science", "highly_complex", secondary=["math"], reqs=["programming_language"]),
    C("Refactor this class to use dependency injection:\n```java\nclass A { B b = new B(); }\n```", "coding", "computer_science", "moderate", reqs=["programming_language"]),
    C("Design a scalable microservices architecture for a ride-sharing platform and justify the trade-offs.", "architecture", "computer_science", "complex"),
    # debugging
    C("My script fails with a TypeError:\n```python\nprint(1 + 'a')\n```\nWhy and how do I fix it?", "debugging", "computer_science", "simple", reqs=["programming_language"]),
    C("Getting a segfault in my C++ program when the vector resizes, here's the traceback:\n```\nSegmentation fault at 0x0\n```", "debugging", "computer_science", "moderate", reqs=["programming_language"]),
    # summarisation / editing / writing / creative
    C("Summarize the following article in under 100 words:\n" + "Energy storage costs fell across several markets this year. " * 20, "summarization", "general", "simple", reqs=["length_limit"]),
    C("Proofread this paragraph: their going to the store tomorow.", "editing", "general", "simple"),
    C("Write a cover letter for a junior data analyst position, formal tone, under 250 words.", "writing", "business", "moderate", reqs=["length_limit"]),
    C("Write a short story about a lighthouse keeper who discovers a message in a bottle.", "creative", "creative", "simple"),
    C("Brainstorm ten names for a coffee shop.", "creative", "general", "simple"),
    # data
    C("Analyse this dataset and identify anomalies:\n" + "\n".join(f"row{i},{i * 3},{i % 4}" for i in range(12)), "data_analysis", "general", "moderate"),
    C("Analyse this dataset, create visualisations and explain the important findings.\n```csv\na,b\n1,2\n3,4\n```", "data_analysis", "general", "moderate", secondary=["reasoning"]),
    C("Extract all the named entities from this paragraph and return them as JSON: Apple hired Tim in Cupertino.", "extraction", "general", "simple", reqs=["output_format"]),
    C("Classify the sentiment of these reviews: great product, terrible support, it was okay.", "classification", "general", "simple"),
    # research / planning / education
    C("Research and compare the main approaches to retrieval-augmented generation, with citations and limitations.", "research", "computer_science", "complex", reqs=["citations"]),
    C("Create a 12-week study plan for learning linear algebra for machine learning.", "planning", "education", "moderate"),
    C("Explain photosynthesis to a ten year old.", "education", "science", "simple"),
    # multimodal
    C("Generate an image of a lighthouse at dawn.", "image_generation", "general", "simple"),
    C("Create a short video clip of waves crashing on rocks.", "video_generation", "general", "simple"),
    C("Transcribe this audio recording of a meeting.", "audio_transcription", "general", "simple", clarify=True),
    # developer
    C("Suggest an embedding model for semantic search in my college project.", "qa", "general", "simple"),
    C("I'm building a chatbot app for my startup. Which free open-weight models can I integrate through an API?", "qa", "computer_science", "moderate"),
    # constraints / preferences
    C("Use the cheapest suitable model to classify these sentiments: good, bad, ok.", "classification", "general", "simple", reqs=["cost"]),
    C("Respond as quickly as possible: what is the boiling point of water?", "qa", "science", "simple", reqs=["latency"]),
    # sensitive domains
    C("Summarize my patient's medical record and diagnosis for a referral letter.", "summarization", "medical", "moderate"),
    C("What are the legal liability implications of a data breach under GDPR for a small company?", "reasoning", "legal", "complex"),
    C("Should I put my savings into index funds or a mortgage prepayment? Compare the tax and investment implications.", "reasoning", "finance", "complex"),
    # science reasoning
    C("Explain why the sky is blue.", "reasoning", "science", "simple"),
    C("Derive the Schwarzschild radius from general relativity and discuss its limits of validity.", "math", "science", "highly_complex"),
    # ambiguity
    C("fix this", "qa", "general", "simple", clarify=True),
    C("help", "qa", "general", "simple", clarify=True),
    C("Summarize this document", "summarization", "general", "simple", clarify=True),
    C("Translate the attached file into French", "translation", "general", "simple", clarify=True),
]


# Held-out set: written after the analyzer was tuned on CASES and never used to tune it. It is the figure to quote for
# generalisation (still small and hand-made; do not read it as a population estimate).
HELD_OUT: List[Dict[str, Any]] = [
    C("How tall is Mount Everest?", "qa", "general", "simple"),
    C("Show that the square root of 2 is irrational.", "math", "mathematics", "complex"),
    C("What is the derivative of sin(x) * x^2?", "math", "mathematics", "simple"),
    C("Write a JavaScript function that debounces another function, with TypeScript types and Jest tests.", "coding", "computer_science", "moderate", reqs=["programming_language"]),
    C("Why does my React component re-render endlessly?\n```jsx\nuseEffect(() => setX(x+1))\n```", "debugging", "computer_science", "moderate"),
    C("Design a fault-tolerant event-driven order pipeline using Kafka and explain the consistency trade-offs.", "architecture", "computer_science", "complex"),
    C("Condense the meeting notes below into five bullet points:\n" + "We agreed to ship on Friday and review the budget next week. " * 15, "summarization", "general", "simple"),
    C("Rewrite this sentence to sound more professional: hey, send me the report asap", "editing", "general", "simple"),
    C("Write a haiku-style poem about monsoon rain.", "creative", "creative", "simple"),
    C("Draft an email to my landlord asking to fix the leaking tap, polite tone, under 120 words.", "writing", "general", "moderate", reqs=["length_limit"]),
    C("Here is a CSV of monthly sales. Find the correlation between ad spend and revenue and flag outliers.\n```csv\nmonth,ad,rev\n1,10,100\n2,20,190\n3,5,40\n```", "data_analysis", "finance", "moderate"),
    C("Pull every date and amount out of this invoice text and output them as a table: Paid 12 March, 450 dollars.", "extraction", "general", "simple", reqs=["output_format"]),
    C("Make a 6-month roadmap for launching a mobile app startup.", "planning", "business", "moderate"),
    C("Teach me the basics of recursion as a beginner.", "education", "computer_science", "simple"),
    C("Create a poster image of a cyberpunk city at night.", "image_generation", "general", "simple"),
    C("Is it legal for my employer to monitor my personal email under GDPR? Explain the liability and compliance angles.", "reasoning", "legal", "complex"),
    C("What are the side effects of mixing ibuprofen and paracetamol? My patient is an adult with a fever.", "qa", "medical", "moderate"),
    C("Compare PostgreSQL and MongoDB for a read-heavy analytics workload and justify your recommendation.", "reasoning", "computer_science", "moderate"),
    C("Quickly tell me what year World War 2 ended.", "qa", "general", "simple", reqs=["latency"]),
    C("Which open-source LLMs can I run locally and integrate into my college project API?", "qa", "computer_science", "moderate"),
    C("Explain this", "reasoning", "general", "simple", clarify=True),
    C("Summarize the attached PDF", "summarization", "general", "simple", clarify=True),
    C("What is the integral of 1/x from 1 to e? Give an exact answer.", "math", "mathematics", "simple", reqs=["accuracy"]),
    C("Write a lock-free ring buffer in C++ and prove its correctness under the C++ memory model, rigorously.", "coding", "computer_science", "highly_complex", reqs=["programming_language"]),
]


def evaluate(verbose: bool = False, cases: List[Dict[str, Any]] = None) -> Dict[str, Any]:
    cases = CASES if cases is None else cases
    n = len(cases)
    hit = {"intent": 0, "domain": 0, "band_exact": 0, "band_within1": 0}
    multi_total = multi_hit = 0
    req_total = req_hit = 0
    clar_tp = clar_fp = clar_fn = 0
    fails: List[str] = []
    for c in cases:
        p = understanding.analyze(c["q"])
        got_band = p.complexity.category
        ok_i, ok_d = p.primary_intent == c["intent"], p.domain == c["domain"]
        hit["intent"] += ok_i
        hit["domain"] += ok_d
        d = abs(BANDS.index(got_band) - BANDS.index(c["band"]))
        hit["band_exact"] += d == 0
        hit["band_within1"] += d <= 1
        sec = {i.name for i in p.secondary_intents}
        for s in c["secondary"]:
            multi_total += 1
            multi_hit += s in sec or s == p.primary_intent
        kinds = {r.kind for r in p.explicit_requirements}
        for r in c["reqs"]:
            req_total += 1
            req_hit += r in kinds
        if c["clarify"] and p.needs_clarification:
            clar_tp += 1
        elif c["clarify"]:
            clar_fn += 1
        elif p.needs_clarification:
            clar_fp += 1
        if verbose and not (ok_i and ok_d and d == 0):
            fails.append(f"  {c['q'][:70]!r:74s} intent {p.primary_intent}/{c['intent']}  domain {p.domain}/{c['domain']}  band {got_band}/{c['band']}")
    out = {
        "cases": n,
        "primary_intent_accuracy": round(hit["intent"] / n, 3), "domain_accuracy": round(hit["domain"] / n, 3),
        "complexity_exact": round(hit["band_exact"] / n, 3), "complexity_within_one_band": round(hit["band_within1"] / n, 3),
        "multi_intent_recall": round(multi_hit / multi_total, 3) if multi_total else None, "multi_intent_labels": multi_total,
        "constraint_recall": round(req_hit / req_total, 3) if req_total else None, "constraint_labels": req_total,
        "clarification_precision": round(clar_tp / (clar_tp + clar_fp), 3) if clar_tp + clar_fp else None,
        "clarification_recall": round(clar_tp / (clar_tp + clar_fn), 3) if clar_tp + clar_fn else None,
    }
    if verbose:
        out["mismatches"] = fails
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--json")
    ap.add_argument("--verbose", action="store_true")
    ap.add_argument("--held-out", action="store_true", help="evaluate the held-out set instead of the tuning set")
    a = ap.parse_args()
    res = evaluate(a.verbose, HELD_OUT if a.held_out else CASES)
    print(json.dumps({k: v for k, v in res.items() if k != "mismatches"}, indent=2))
    for line in res.get("mismatches", []):
        print(line)
    if a.json:
        json.dump(res, open(a.json, "w"), indent=2)
    sys.exit(0)
