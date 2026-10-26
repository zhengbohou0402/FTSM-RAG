"""
Semantic cache experiment for the thesis/demo.

This script uses an in-memory experiment cache, so it does not clear or modify
data/ukm_ftsm/semantic_cache.json used by the running app.

Typical usage:
    python scripts/evaluate_cache.py --report-dir results/cache_eval
    python scripts/evaluate_cache.py --limit 5 --report-dir results/cache_eval_smoke
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from model.factory import get_embed_model  # noqa: E402
from rag.rag_service import RagSummarizeService  # noqa: E402
from scripts.evaluate_rag import TEST_CASES, percentile  # noqa: E402

DEFAULT_THRESHOLD = 0.92

SIMILAR_QUESTIONS = {
    "academic_calendar": "Give me key academic calendar dates for this academic year.",
    "course_timetable": "Give me information I need to understand my course timetable.",
    "visa_renewal": "Explain the student visa renewal steps and documents required.",
    "graduation_certification": "Summarize graduation certification process and required documents.",
    "campus_bus": "Give me UKM campus bus route information relevant to students.",
    "academic_staff": "Give me information on FTSM academic staff and their expertise.",
    "industrial_training": "Summarize industrial training information and important contacts.",
    "facilities": "List facilities and services available at FTSM.",
    "admissions": "Summarize admission requirements for FTSM postgraduate programs.",
    "exam_schedule": "Give me final exam schedule information and what I should check.",
}


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = sum(x * x for x in a) ** 0.5
    norm_b = sum(x * x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


class ExperimentCache:
    def __init__(self, threshold: float):
        self.threshold = threshold
        self.entries: list[dict[str, Any]] = []
        self.hits = 0
        self.misses = 0
        self.embedder = get_embed_model()

    def set(self, question: str, answer: str) -> None:
        self.entries.append({
            "question": question,
            "answer": answer,
            "vector": self.embedder.embed_query(question),
        })

    def get(self, question: str) -> tuple[bool, str | None, float]:
        q_vec = self.embedder.embed_query(question)
        best_score = 0.0
        best_answer: str | None = None
        for entry in self.entries:
            score = cosine_similarity(q_vec, entry["vector"])
            if score > best_score:
                best_score = score
                best_answer = entry["answer"]

        if best_score >= self.threshold and best_answer:
            self.hits += 1
            return True, best_answer, best_score

        self.misses += 1
        return False, None, best_score

    def stats(self) -> dict[str, Any]:
        total = self.hits + self.misses
        return {
            "entries": len(self.entries),
            "hit_count": self.hits,
            "miss_count": self.misses,
            "hit_rate": round(self.hits / total, 4) if total else 0.0,
            "threshold": self.threshold,
        }


def run_experiment(cases: list[dict[str, Any]], threshold: float) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rag = RagSummarizeService()
    cache = ExperimentCache(threshold=threshold)
    rows: list[dict[str, Any]] = []

    for case in cases:
        question = case["question"]
        similar_question = SIMILAR_QUESTIONS.get(case["id"], question + " Please summarize.")

        cold_started = time.perf_counter()
        answer = rag.rag_summarize(question)
        cold_seconds = time.perf_counter() - cold_started
        cache.set(question, answer)

        exact_started = time.perf_counter()
        exact_hit, _, exact_score = cache.get(question)
        exact_seconds = time.perf_counter() - exact_started

        similar_started = time.perf_counter()
        similar_hit, _, similar_score = cache.get(similar_question)
        similar_seconds = time.perf_counter() - similar_started

        rows.append({
            "id": case["id"],
            "question": question,
            "similar_question": similar_question,
            "no_cache_seconds": round(cold_seconds, 3),
            "exact_cache_hit": exact_hit,
            "exact_cache_seconds": round(exact_seconds, 3),
            "exact_similarity": round(exact_score, 4),
            "similar_cache_hit": similar_hit,
            "similar_cache_seconds": round(similar_seconds, 3),
            "similar_similarity": round(similar_score, 4),
            "answer_chars": len(answer),
        })

    cold = [row["no_cache_seconds"] for row in rows]
    exact = [row["exact_cache_seconds"] for row in rows]
    similar = [row["similar_cache_seconds"] for row in rows]
    exact_hits = sum(1 for row in rows if row["exact_cache_hit"])
    similar_hits = sum(1 for row in rows if row["similar_cache_hit"])

    summary = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "test_cases": len(rows),
        "threshold": threshold,
        "no_cache_avg_seconds": round(statistics.mean(cold), 3),
        "no_cache_p50_seconds": round(percentile(cold, 50), 3),
        "exact_cache_avg_seconds": round(statistics.mean(exact), 3),
        "exact_cache_p50_seconds": round(percentile(exact, 50), 3),
        "similar_cache_avg_seconds": round(statistics.mean(similar), 3),
        "similar_cache_p50_seconds": round(percentile(similar, 50), 3),
        "exact_hit_rate": round(exact_hits / len(rows), 4) if rows else 0.0,
        "similar_hit_rate": round(similar_hits / len(rows), 4) if rows else 0.0,
        "overall_cache_stats": cache.stats(),
    }
    return rows, summary


def write_markdown(rows: list[dict[str, Any]], summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# Semantic Cache Experiment",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | ---: |",
        f"| Test cases | {summary['test_cases']} |",
        f"| Similarity threshold | {summary['threshold']} |",
        f"| No-cache average latency | {summary['no_cache_avg_seconds']:.3f}s |",
        f"| Exact-cache average latency | {summary['exact_cache_avg_seconds']:.3f}s |",
        f"| Similar-question cache average latency | {summary['similar_cache_avg_seconds']:.3f}s |",
        f"| Exact-question hit rate | {summary['exact_hit_rate']:.1%} |",
        f"| Similar-question hit rate | {summary['similar_hit_rate']:.1%} |",
        "",
        "## Per-case Results",
        "",
        "| Case | No Cache(s) | Exact Hit | Exact(s) | Similar Hit | Similar(s) | Similarity |",
        "| --- | ---: | --- | ---: | --- | ---: | ---: |",
    ]
    for row in rows:
        lines.append(
            f"| {row['id']} | {row['no_cache_seconds']} | "
            f"{'yes' if row['exact_cache_hit'] else 'no'} | {row['exact_cache_seconds']} | "
            f"{'yes' if row['similar_cache_hit'] else 'no'} | {row['similar_cache_seconds']} | "
            f"{row['similar_similarity']:.4f} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def write_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
        if rows:
            writer.writeheader()
            writer.writerows(rows)
    print(f"Wrote {path}")


def write_report(rows: list[dict[str, Any]], summary: dict[str, Any], report_dir: Path) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "cache_eval.json").write_text(
        json.dumps({"summary": summary, "results": rows}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"Wrote {report_dir / 'cache_eval.json'}")
    write_markdown(rows, summary, report_dir / "cache_eval.md")
    write_csv(rows, report_dir / "cache_eval.csv")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate semantic cache effectiveness.")
    parser.add_argument("--limit", type=int, default=0, help="Only run the first N cases.")
    parser.add_argument("--threshold", type=float, default=DEFAULT_THRESHOLD)
    parser.add_argument("--report-dir", type=Path, default=ROOT / "results" / "cache_eval")
    args = parser.parse_args()

    cases = TEST_CASES[: args.limit] if args.limit else TEST_CASES
    rows, summary = run_experiment(cases, threshold=args.threshold)

    print("| Metric | Value |")
    print("| --- | ---: |")
    print(f"| Test cases | {summary['test_cases']} |")
    print(f"| No-cache avg | {summary['no_cache_avg_seconds']:.3f}s |")
    print(f"| Exact-cache avg | {summary['exact_cache_avg_seconds']:.3f}s |")
    print(f"| Similar-cache avg | {summary['similar_cache_avg_seconds']:.3f}s |")
    print(f"| Exact hit rate | {summary['exact_hit_rate']:.1%} |")
    print(f"| Similar hit rate | {summary['similar_hit_rate']:.1%} |")

    write_report(rows, summary, args.report_dir)


if __name__ == "__main__":
    main()
