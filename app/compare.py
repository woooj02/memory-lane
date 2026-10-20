"""Pick the Together model by reading its work, not by guessing.

    ./run.sh compare                      the doctor visit from the sample day, 5 models
    ./run.sh compare --bee 1234           a real conversation from Bee instead
    ./run.sh compare --models a/b c/d     your own list
    ./run.sh compare --list               every chat model your key can use, with prices

For each model it runs the same two calls the app makes (cards + line-by-line
English) and writes data/compare-<time>.md: each Nepali line with every
model's English, the questions each one asked, time taken and cost.
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from . import bee, config, digest, llm

CANDIDATES = [
    "moonshotai/Kimi-K3",
    "zai-org/GLM-5.3",
    "Qwen/Qwen3.7-Max",
    "deepseek-ai/DeepSeek-V4-Pro-0813",
    "Qwen/Qwen3.8-Flash",
]


def prices() -> dict[str, dict]:
    """{model id: {"input": $/M, "output": $/M, ...}} from Together's model list."""
    import httpx

    try:
        r = httpx.get("https://api.together.xyz/v1/models", timeout=30,
                      headers={"Authorization": f"Bearer {config.TOGETHER_API_KEY}"})
        r.raise_for_status()
        rows = r.json()
        rows = rows.get("data", rows) if isinstance(rows, dict) else rows
        return {m["id"]: m for m in rows if isinstance(m, dict) and "id" in m}
    except Exception as exc:  # prices are a nice-to-have
        print(f"(couldn't read model prices: {exc})")
        return {}


def cost(info: dict | None, usage: dict) -> float | None:
    p = (info or {}).get("pricing") or {}
    if not p or not usage:
        return None
    return (usage.get("prompt_tokens", 0) * p.get("input", 0) + usage.get("completion_tokens", 0) * p.get("output", 0)) / 1e6


def run(model_id: str, conv: dict, items: list[dict]) -> dict:
    texts = [u["text"] for u in items]
    t0 = time.time()
    out = {"model": model_id}
    try:
        with ThreadPoolExecutor(2) as pool:
            u = pool.submit(llm.together, model_id, digest.UNDERSTAND_SYSTEM,
                            digest.understand_prompt(conv, items), digest.UNDERSTAND_SCHEMA)
            t = pool.submit(llm.together, model_id, digest.TRANSLATE_SYSTEM,
                            digest.translate_prompt(texts), digest.TRANSLATE_SCHEMA, 12000)
            (understood, u1), (translated, u2) = u.result(), t.result()
        out["usage"] = {k: u1.get(k, 0) + u2.get(k, 0) for k in ("prompt_tokens", "completion_tokens")}
        out["data"] = digest.clean({**understood, **{k: translated.get(k, []) for k in
                                                    ("lines_en", "lines_parent", "background")}}, len(items), "together")
    except Exception as exc:
        out["error"] = str(exc)
    out["seconds"] = round(time.time() - t0, 1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--models", nargs="+", default=CANDIDATES)
    ap.add_argument("--bee", type=int, help="a real Bee conversation id (bee conversations list)")
    ap.add_argument("--demo", type=int, default=102, help="sample-day conversation id (default 102, the doctor)")
    ap.add_argument("--list", action="store_true", help="list chat models and prices, then stop")
    args = ap.parse_args()
    if not config.TOGETHER_API_KEY:
        raise SystemExit("Put TOGETHER_API_KEY=... in .env first.")

    info = prices()
    if args.list:
        chat = sorted((m for m in info.values() if m.get("type") in (None, "chat", "language")), key=lambda m: m["id"])
        for m in chat:
            p = m.get("pricing") or {}
            print(f"{m['id']:<55} in ${p.get('input', '?')}/M  out ${p.get('output', '?')}/M  ctx {m.get('context_length', '?')}")
        return

    source = bee.CliBee() if args.bee else bee.DemoBee()
    conv = source.get_conversation(args.bee or args.demo)
    items = bee.utterances(conv)
    reference = {}
    if not args.bee:
        sample = json.loads((config.FIXTURES / "demo_digests.json").read_text()).get(str(args.demo), {})
        reference = {"model": "hand-written reference", "data": sample}
    print(f"{len(items)} lines, {len(args.models)} models, running in parallel…")

    with ThreadPoolExecutor(len(args.models)) as pool:
        results = list(pool.map(lambda m: run(m, conv, items), args.models))

    lines = [f"# Model comparison · {datetime.now():%Y-%m-%d %H:%M}",
             f"Conversation: {'Bee ' + str(args.bee) if args.bee else 'sample day ' + str(args.demo)} · {len(items)} lines\n",
             "| Model | Time | Cost | Cards | Notes |", "|---|---|---|---|---|"]
    for r in results:
        c = cost(info.get(r["model"]), r.get("usage", {}))
        cards = len(r["data"]["cards"]) if "data" in r else "–"
        note = r.get("error", "")[:120] or f"{r['usage'].get('prompt_tokens', 0)} in / {r['usage'].get('completion_tokens', 0)} out tokens"
        lines.append(f"| `{r['model']}` | {r['seconds']}s | {'$%.4f' % c if c is not None else '?'} | {cards} | {note} |")

    shown = ([reference] if reference else []) + [r for r in results if "data" in r]
    lines.append("\n## Line by line")
    for i, u in enumerate(items):
        lines.append(f"\n**[{i}] {u['speaker']}:** {u['text']}")
        for r in shown:  # the rebuilt Nepali, then the English: with Bee's Hindi recognizer, the rebuild is the test
            en = r["data"].get("lines_en") or []
            fixed = r["data"].get("lines_parent") or []
            tv = " *(TV/background)*" if i in (r["data"].get("background") or []) else ""
            ne = fixed[i] if i < len(fixed) and fixed[i] != u["text"] else ""
            lines.append(f"- *{r['model']}*{tv}: {ne + ' · ' if ne else ''}{en[i] if i < len(en) else ''}")

    lines.append("\n## Questions each model asked")
    for r in shown:
        lines.append(f"\n### {r['model']}")
        d = r["data"]
        names = ", ".join(f"{s.get('label')}={s.get('name_en')}" for s in d.get("speakers", []))
        if names:
            lines.append(f"Speakers: {names}")
        for c in d.get("cards", []):
            flag = " · health" if c.get("health") else ""
            lines.append(f"- {c['question_parent']} → **{c['answer_parent']}**  \n  {c['question_en']} → {c['answer_en']} "
                         f"(hint: {c.get('hint_en', '')}; lines {c.get('evidence')}{flag})")
        for p in d.get("promises", []):
            lines.append(f"- Promise: {p.get('text_parent')} / {p.get('text_en')} ({p.get('due_date') or 'no day'})")

    config.DATA.mkdir(parents=True, exist_ok=True)
    path = config.DATA / f"compare-{datetime.now():%Y%m%d-%H%M%S}.md"
    path.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:4 + len(results)]))
    print(f"\nFull side-by-side: {path}")


if __name__ == "__main__":
    main()
