"""稠密余弦门限标定 + 证据门限（gates.evaluate）回归验证。

跑法（仓库根目录）：
    .venv/bin/python scripts/calibrate_dense_threshold.py
    .venv/bin/python scripts/calibrate_dense_threshold.py --sweep   # 扫描候选阈值

它走的是**真实检索链路**（rag.retriever_docs），因此会真实调用 embedding API；
不会调用对话模型（不生成答案），代价很低。

输出：
  1. 每条样本的实际稠密余弦、BM25 覆盖率、以及门限最终判定
  2. 域内召回率 / 域外误放行率（两路分开统计，便于判断该调哪一路）
  3. 建议阈值 = (域外最高 + 域内最低) / 2，并给出几档候选的实际效果
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

# 兼容 host 模式：.env 里的 GOOGLE_APPLICATION_CREDENTIALS 是容器内绝对路径
adc = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "")
if adc and not Path(adc).exists():
    fallback = ROOT / ".gcp" / "application_default_credentials.json"
    if fallback.exists():
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(fallback)

from rag import gates  # noqa: E402
from rag.rag_service import RagSummarizeService, rerank_status  # noqa: E402

# ── 标注样本：域内 = 应在知识库中有依据；域外 = 应被拒答 ──────────────────────
IN_DOMAIN = [
    "How do I renew my student pass before it expires?",
    "What is the FTSM academic calendar for semester 2?",
    "Which campus bus goes to the student dormitories?",
    "Where can I find halal food near the faculty?",
    "How do I register for courses on the student portal?",
    "Who is the coordinator for the Cybersecurity master programme?",
    "What documents does EMGS require for new international students?",
    "学生准证快到期了怎么续签？",
    "新生办理 EMGS 需要哪些材料？",
    "从 UKM 车站怎么去 FTSM 学院？",
    "UKM 附近哪里有便宜的清真美食？",
    "补考和重考的时间表在哪里看？",
]
OUT_OF_DOMAIN = [
    "What is the weather forecast in Tokyo tomorrow?",
    "Who won the 2024 Formula 1 world championship?",
    "Write me a Python function to reverse a linked list.",
    "What is the price of Bitcoin today?",
    "Give me a recipe for chocolate chip cookies.",
    "How do I file my tax return in Germany?",
    "今天日元对人民币汇率是多少？",
    "帮我写一首关于春天的诗。",
    "推荐几部 2025 年上映的科幻电影。",
    "如何用 Rust 实现一个内存池？",
]


def probe(rag: RagSummarizeService, question: str) -> dict:
    """跑真实检索链路，取回门限判定明细（不含生成）。"""
    trace: dict = {}
    docs = rag.retriever_docs(question, trace=trace)
    detail = dict(trace.get("gate") or {})
    bm25_cov = 0.0
    bm25_hits = 0
    bm25_docs = rag._bm25_retrieve(question, 3)
    if bm25_docs:
        bm25_cov = max(gates.bm25_coverage(question, d) for d in bm25_docs)
        bm25_hits = max(gates.bm25_matches(question, d) for d in bm25_docs)
    return {
        "admitted": bool(docs),
        "dense": trace.get("denseCosine"),
        "bm25": round(bm25_cov, 4),
        "bm25Hits": bm25_hits,
        "admittedBy": detail.get("admittedBy"),
        "docs": len(docs),
        "rerank": trace.get("rerankProvider"),
        "rerankApplied": trace.get("rerankApplied", False),
        "rerankDegraded": trace.get("rerankDegraded", False),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sweep", action="store_true", help="扫描候选稠密阈值")
    args = parser.parse_args()

    dense_min, bm25_min = gates._thresholds()
    print("=" * 96)
    print(f"当前配置：dense_cosine_min={dense_min}  bm25_coverage_min={bm25_min}")
    print(f"精排状态：{rerank_status()}")
    print("=" * 96)

    rag = RagSummarizeService()

    results = {"IN": [], "OUT": []}
    for label, questions in (("IN", IN_DOMAIN), ("OUT", OUT_OF_DOMAIN)):
        print(f"\n──── {label}（{'域内，期望放行' if label == 'IN' else '域外，期望拒答'}）────")
        for q in questions:
            r = probe(rag, q)
            results[label].append(r)
            dense = "None" if r["dense"] is None else f"{r['dense']:.4f}"
            verdict = "ADMIT " if r["admitted"] else "REJECT"
            print(
                f"  {verdict} dense={dense:>8} bm25={r['bm25']:.3f} "
                f"hits={r['bm25Hits']} by={str(r['admittedBy']):<16} docs={r['docs']}  {q[:40]}"
            )

    in_dense = [r["dense"] for r in results["IN"] if r["dense"] is not None]
    out_dense = [r["dense"] for r in results["OUT"] if r["dense"] is not None]
    in_recall = sum(1 for r in results["IN"] if r["admitted"]) / len(results["IN"])
    out_false = sum(1 for r in results["OUT"] if r["admitted"]) / len(results["OUT"])

    print("\n" + "=" * 96)
    if in_dense and out_dense:
        print(f"稠密余弦  域内 min={min(in_dense):.4f}  域外 max={max(out_dense):.4f}  "
              f"gap={min(in_dense) - max(out_dense):+.4f}")
    print(f"门限整体效果  域内召回={in_recall:.0%}  域外误放行={out_false:.0%}")

    by_branch = {}
    for label in ("IN", "OUT"):
        for r in results[label]:
            if r["admitted"]:
                by_branch.setdefault(r["admittedBy"], {"IN": 0, "OUT": 0})[label] += 1
    print(f"放行来源分布  {by_branch}")

    if args.sweep and in_dense and out_dense:
        print("\n候选阈值扫描（只影响稠密路；域外仍可能被 BM25 路放行）")
        for t in (0.58, 0.60, 0.62, 0.64, 0.65, 0.66, 0.68):
            keep = sum(1 for v in in_dense if v >= t) / len(in_dense)
            drop = sum(1 for v in out_dense if v < t) / len(out_dense)
            print(f"  t={t:.2f}  域内保留={keep:.0%}  域外被稠密路拦下={drop:.0%}")
        print(f"\n  建议值 ≈ {(min(in_dense) + max(out_dense)) / 2:.4f}"
              f"（域内最低与域外最高的中点）")

    print("=" * 96)
    # 域外误放行是当前最需要关注的指标
    return 0 if out_false <= 0.2 else 1


if __name__ == "__main__":
    raise SystemExit(main())
