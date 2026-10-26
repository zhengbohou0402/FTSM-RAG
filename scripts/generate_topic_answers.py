# Generate grounded answers for the guide's secondary topic pages.
#
# Runs the production ReactAgent pipeline (hybrid retrieval + grounding gate)
# for every topic question and writes the results to
# web/static/topic_answers.json, which /guide's #topic/<slug> pages render.
#
# Usage (inside the stack container, with .env sourced):
#   python scripts/generate_topic_answers.py
#
# The questions must stay in sync with TOPICS in web/static/guide.js.

import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

OUTPUT_FILE = PROJECT_ROOT / "web" / "static" / "topic_answers.json"

# Mirrors web/static/guide.js TOPICS (title -> questions)
TOPIC_QUESTIONS = {
    "Visa & EMGS": [
        "How do I renew my student pass before it expires?",
        "What documents does EMGS require for new international students?",
    ],
    "Transport & Buses": [
        "How do I get from UKM station to the FTSM faculty?",
        "Which campus bus zone goes to the student dormitories?",
    ],
    "Food & Halal": [
        "Where can I find affordable halal food near UKM?",
        "What is the average cost of a meal at the UKM cafeteria?",
    ],
    "Housing": [
        "How do I apply for UKM on-campus student accommodation?",
        "What should I prepare before moving into the student college?",
    ],
    "Health & Insurance": [
        "Does UKM provide health insurance for international students?",
        "Where is the campus health clinic and what are its operating hours?",
    ],
    "Classes & Academics": [
        "When does course registration open for the new semester?",
        "Where can I check the final exam schedule for FTSM?",
    ],
}


def js_slug(text: str) -> str:
    """Same slug algorithm as slug() in web/static/guide.js."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def main() -> int:
    from agent.react_agent import ReactAgent

    agent = ReactAgent()
    result: dict = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "topics": {}}

    total = sum(len(qs) for qs in TOPIC_QUESTIONS.values())
    done = 0
    failures: list[str] = []

    for title, questions in TOPIC_QUESTIONS.items():
        slug = js_slug(title)
        answers: dict[str, str] = {}
        for question in questions:
            done += 1
            print(f"[{done}/{total}] {title} :: {question}")
            try:
                chunks: list[str] = []
                for chunk in agent.execute_stream(question, history=[]):
                    if not chunk or chunk.startswith("__THINK__"):
                        continue
                    chunks.append(chunk)
                answer = "".join(chunks).strip()
            except Exception as exc:
                answer = ""
                failures.append(f"{title}: {question}: {exc}")
                print(f"  [FAIL] {exc}")
            if not answer or "[Error]" in answer:
                failures.append(f"{title}: {question}: empty/error answer")
                print("  [FAIL] empty or error answer")
                continue
            answers[question] = answer
            print(f"  [OK] {len(answer)} chars")
        if answers:
            result["topics"][slug] = {"title": title, "answers": answers}

    OUTPUT_FILE.write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n[DONE] wrote {OUTPUT_FILE} ({len(result['topics'])} topics)")
    if failures:
        print(f"[WARN] {len(failures)} failures:")
        for f in failures:
            print("  -", f)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
