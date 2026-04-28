"""
Simple RAG evaluation for the graduation project.

Default mode evaluates retrieval only. Add --with-answer to call the LLM and
check whether the generated answer contains expected key terms.

Metrics computed
----------------
- source_hit          : 1/0，是否至少一个检索结果来自期望来源
- mrr                 : Mean Reciprocal Rank（期望来源首次出现位置的倒数）
- precision_at_k      : 前 K 条结果中期望来源占比
- recall_at_k         : 期望来源在前 K 条中被覆盖的比例
- answer_hit          : 答案中是否包含期望关键词
- retrieval_seconds   : 检索阶段耗时
- answer_seconds      : 回答阶段耗时（--with-answer 时）
- Latency P50 / P90   : 汇总时计算

Export
------
- --output  results/rag_eval.json    （机器可读）
- --markdown results/rag_eval.md     （论文直接引用）
- --csv     results/rag_eval.csv     （Excel/pandas 进一步分析）
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from langchain_core.documents import Document  # noqa: E402
from rag.rag_service import RagSummarizeService  # noqa: E402

EVAL_TOP_K = 5  # 计算 Precision@K / Recall@K 所用的 K

TEST_CASES: list[dict[str, Any]] = [
    {
        "id": "academic_calendar",
        "question": "Where can I view the academic calendar?",
        "expected_sources": ["academic_calendar", "student_portal_academic_calendar"],
        "expected_terms": ["academic calendar", "semester"],
    },
    {
        "id": "course_timetable",
        "question": "How do I check my course timetable?",
        "expected_sources": ["timetable", "course_mode"],
        "expected_terms": ["timetable", "course"],
    },
    {
        "id": "visa_renewal",
        "question": "How do I renew my student visa?",
        "expected_sources": ["registration_renewal", "student_portal"],
        "expected_terms": ["renewal", "student"],
    },
    {
        "id": "graduation_certification",
        "question": "What should I know about graduation certification?",
        "expected_sources": ["graduation_certification_guide"],
        "expected_terms": ["graduation", "certificate"],
    },
    {
        "id": "campus_bus",
        "question": "How can I check UKM campus bus routes?",
        "expected_sources": ["ukm_campus_bus_routes_guide"],
        "expected_terms": ["bus", "route"],
    },
    {
        "id": "academic_staff",
        "question": "How can I find FTSM academic staff and their expertise?",
        "expected_sources": ["advisors", "academic_staff", "expertise"],
        "expected_terms": ["academic staff", "expertise"],
    },
    {
        "id": "industrial_training",
        "question": "Where can I find industrial training information and contacts?",
        "expected_sources": ["industrial_training_and_contacts"],
        "expected_terms": ["industrial training", "contact"],
    },
    {
        "id": "facilities",
        "question": "What facilities and services are available at FTSM?",
        "expected_sources": ["facilities_and_services"],
        "expected_terms": ["facilities", "services"],
    },
    {
        "id": "admissions",
        "question": "What are the admission requirements for FTSM postgraduate programs?",
        "expected_sources": ["programmes_and_admissions"],
        "expected_terms": ["admission", "programme"],
    },
    {
        "id": "exam_schedule",
        "question": "Where can I check my final exam schedule?",
        "expected_sources": ["exam_schedule"],
        "expected_terms": ["exam", "schedule"],
    },
]


def source_name(doc: Document) -> str:
    metadata = doc.metadata or {}
    file_path = str(metadata.get("file_path") or metadata.get("source") or "")
    return (
        str(metadata.get("filename") or "")
        or str(metadata.get("title") or "")
        or (Path(file_path).name if file_path else "")
        or "unknown"
    )


def _doc_matches_expected(doc: Document, expected_sources: list[str]) -> bool:
    name = source_name(doc).lower()
    return any(exp.lower() in name for exp in expected_sources)


def compute_mrr(docs: list[Document], expected_sources: list[str]) -> float:
    for rank, doc in enumerate(docs, start=1):
        if _doc_matches_expected(doc, expected_sources):
            return 1.0 / rank
    return 0.0


def compute_precision_at_k(docs: list[Document], expected_sources: list[str], k: int) -> float:
    top_k = docs[:k]
    if not top_k:
        return 0.0
    hits = sum(1 for doc in top_k if _doc_matches_expected(doc, expected_sources))
    return hits / len(top_k)


def compute_recall_at_k(docs: list[Document], expected_sources: list[str], k: int) -> float:
    """期望来源中，有多少被前 K 条覆盖（按来源去重计数）。"""
    if not expected_sources:
        return 0.0
    top_k = docs[:k]
    covered = {
        exp for exp in expected_sources
        if any(exp.lower() in source_name(doc).lower() for doc in top_k)
    }
    return len(covered) / len(expected_sources)


def source_hit(docs: list[Document], expected_sources: list[str]) -> bool:
    haystack = "\n".join(source_name(doc).lower() for doc in docs)
    return any(source.lower() in haystack for source in expected_sources)


def answer_hit(answer: str, expected_terms: list[str]) -> bool | None:
    if not answer:
        return None
    haystack = answer.lower()
    matched = [term for term in expected_terms if term.lower() in haystack]
    needed = min(2, len(expected_terms))
    return len(matched) >= needed


def evaluate_case(
    rag: RagSummarizeService,
    case: dict[str, Any],
    *,
    with_answer: bool,
) -> dict[str, Any]:
    started = time.perf_counter()
    docs = rag.retriever_docs(case["question"])
    retrieval_seconds = time.perf_counter() - started

    expected = case["expected_sources"]

    answer = ""
    answer_seconds: float | None = None
    if with_answer:
        answer_started = time.perf_counter()
        answer = rag.rag_summarize(case["question"])
        answer_seconds = time.perf_counter() - answer_started

    top_sources = [source_name(doc) for doc in docs[:EVAL_TOP_K]]
    return {
        "id": case["id"],
        "question": case["question"],
        "source_hit": source_hit(docs, expected),
        "mrr": round(compute_mrr(docs, expected), 4),
        "precision_at_k": round(compute_precision_at_k(docs, expected, EVAL_TOP_K), 4),
        "recall_at_k": round(compute_recall_at_k(docs, expected, EVAL_TOP_K), 4),
        "answer_hit": answer_hit(answer, case["expected_terms"]),
        "retrieved_count": len(docs),
        "retrieval_seconds": round(retrieval_seconds, 3),
        "answer_seconds": round(answer_seconds, 3) if answer_seconds is not None else None,
        "top_sources": top_sources,
        "answer_preview": answer[:240] if answer else "",
    }


def _percentile(data: list[float], pct: float) -> float:
    """简单线性插值百分位（无需 numpy）。"""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    n = len(sorted_data)
    rank = pct / 100 * (n - 1)
    lower = int(rank)
    upper = min(lower + 1, n - 1)
    frac = rank - lower
    return sorted_data[lower] + frac * (sorted_data[upper] - sorted_data[lower])


def print_table(results: list[dict[str, Any]]) -> None:
    header = "| Case | SrcHit | MRR | P@5 | R@5 | AnsHit | Retr(s) | Top source |"
    sep    = "| --- | --- | ---: | ---: | ---: | --- | ---: | --- |"
    print(header)
    print(sep)
    for row in results:
        answer = "-" if row["answer_hit"] is None else ("yes" if row["answer_hit"] else "no")
        top_source = row["top_sources"][0] if row["top_sources"] else "-"
        print(
            f"| {row['id']} | {'yes' if row['source_hit'] else 'no'} | "
            f"{row['mrr']:.3f} | {row['precision_at_k']:.3f} | {row['recall_at_k']:.3f} | "
            f"{answer} | {row['retrieval_seconds']} | {top_source} |"
        )

    print()
    source_rate = sum(1 for r in results if r["source_hit"]) / max(len(results), 1)
    avg_mrr = statistics.mean(r["mrr"] for r in results)
    avg_p = statistics.mean(r["precision_at_k"] for r in results)
    avg_r = statistics.mean(r["recall_at_k"] for r in results)
    latencies = [r["retrieval_seconds"] for r in results]
    p50 = _percentile(latencies, 50)
    p90 = _percentile(latencies, 90)

    print(f"Source hit rate : {source_rate:.0%}  ({len(results)} cases)")
    print(f"Mean MRR        : {avg_mrr:.4f}")
    print(f"Mean Precision@{EVAL_TOP_K}: {avg_p:.4f}")
    print(f"Mean Recall@{EVAL_TOP_K}   : {avg_r:.4f}")
    print(f"Latency P50/P90 : {p50:.3f}s / {p90:.3f}s")

    answer_rows = [r for r in results if r["answer_hit"] is not None]
    if answer_rows:
        answer_rate = sum(1 for r in answer_rows if r["answer_hit"]) / len(answer_rows)
        ans_latencies = [r["answer_seconds"] for r in answer_rows if r["answer_seconds"]]
        ap50 = _percentile(ans_latencies, 50)
        ap90 = _percentile(ans_latencies, 90)
        print(f"Answer hit rate : {answer_rate:.0%}  ({len(answer_rows)} cases)")
        print(f"Answer P50/P90  : {ap50:.3f}s / {ap90:.3f}s")


def write_markdown(results: list[dict[str, Any]], path: Path) -> None:
    """将评估结果写成 Markdown 表格，可直接嵌入论文实验章节。"""
    lines: list[str] = []
    lines.append("# RAG Evaluation Results\n")

    # Summary
    source_rate = sum(1 for r in results if r["source_hit"]) / max(len(results), 1)
    avg_mrr = statistics.mean(r["mrr"] for r in results)
    avg_p = statistics.mean(r["precision_at_k"] for r in results)
    avg_r = statistics.mean(r["recall_at_k"] for r in results)
    latencies = [r["retrieval_seconds"] for r in results]
    p50 = _percentile(latencies, 50)
    p90 = _percentile(latencies, 90)

    lines.append("## Summary\n")
    lines.append(f"| Metric | Value |")
    lines.append(f"| --- | --- |")
    lines.append(f"| Test cases | {len(results)} |")
    lines.append(f"| Source hit rate | {source_rate:.1%} |")
    lines.append(f"| Mean MRR | {avg_mrr:.4f} |")
    lines.append(f"| Mean Precision@{EVAL_TOP_K} | {avg_p:.4f} |")
    lines.append(f"| Mean Recall@{EVAL_TOP_K} | {avg_r:.4f} |")
    lines.append(f"| Retrieval P50 / P90 | {p50:.3f}s / {p90:.3f}s |")

    answer_rows = [r for r in results if r["answer_hit"] is not None]
    if answer_rows:
        answer_rate = sum(1 for r in answer_rows if r["answer_hit"]) / len(answer_rows)
        ans_latencies = [r["answer_seconds"] for r in answer_rows if r["answer_seconds"]]
        ap50 = _percentile(ans_latencies, 50)
        ap90 = _percentile(ans_latencies, 90)
        lines.append(f"| Answer hit rate | {answer_rate:.1%} |")
        lines.append(f"| Answer P50 / P90 | {ap50:.3f}s / {ap90:.3f}s |")

    lines.append("")
    lines.append("## Per-case Results\n")
    lines.append(f"| Case | SrcHit | MRR | P@{EVAL_TOP_K} | R@{EVAL_TOP_K} | AnsHit | Retr(s) | Top source |")
    lines.append("| --- | --- | ---: | ---: | ---: | --- | ---: | --- |")
    for row in results:
        answer = "-" if row["answer_hit"] is None else ("✓" if row["answer_hit"] else "✗")
        top_source = row["top_sources"][0] if row["top_sources"] else "-"
        lines.append(
            f"| {row['id']} | {'✓' if row['source_hit'] else '✗'} | "
            f"{row['mrr']:.3f} | {row['precision_at_k']:.3f} | {row['recall_at_k']:.3f} | "
            f"{answer} | {row['retrieval_seconds']} | {top_source} |"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def write_csv(results: list[dict[str, Any]], path: Path) -> None:
    """将评估结果写成 CSV，方便用 Excel 或 pandas 进行进一步分析。"""
    fieldnames = [
        "id", "question", "source_hit", "mrr",
        f"precision_at_{EVAL_TOP_K}", f"recall_at_{EVAL_TOP_K}",
        "answer_hit", "retrieved_count",
        "retrieval_seconds", "answer_seconds",
        "top_sources", "answer_preview",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow({
                "id": row["id"],
                "question": row["question"],
                "source_hit": row["source_hit"],
                "mrr": row["mrr"],
                f"precision_at_{EVAL_TOP_K}": row["precision_at_k"],
                f"recall_at_{EVAL_TOP_K}": row["recall_at_k"],
                "answer_hit": "" if row["answer_hit"] is None else row["answer_hit"],
                "retrieved_count": row["retrieved_count"],
                "retrieval_seconds": row["retrieval_seconds"],
                "answer_seconds": "" if row["answer_seconds"] is None else row["answer_seconds"],
                "top_sources": "; ".join(row["top_sources"]),
                "answer_preview": row["answer_preview"],
            })
    print(f"Wrote {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate RAG retrieval and answer quality.")
    parser.add_argument("--with-answer", action="store_true",
                        help="Call the chat model and evaluate answer terms.")
    parser.add_argument("--limit", type=int, default=0,
                        help="Only run the first N test cases.")
    parser.add_argument("--output", type=Path, default=None,
                        help="JSON output path (e.g. results/rag_eval.json).")
    parser.add_argument("--markdown", type=Path, default=None,
                        help="Markdown output path (e.g. results/rag_eval.md).")
    parser.add_argument("--csv", type=Path, default=None,
                        help="CSV output path (e.g. results/rag_eval.csv).")
    args = parser.parse_args()

    cases = TEST_CASES[: args.limit] if args.limit else TEST_CASES
    rag = RagSummarizeService()
    results = [evaluate_case(rag, case, with_answer=args.with_answer) for case in cases]

    print_table(results)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nWrote {args.output}")

    if args.markdown:
        write_markdown(results, args.markdown)

    if args.csv:
        write_csv(results, args.csv)


if __name__ == "__main__":
    main()
