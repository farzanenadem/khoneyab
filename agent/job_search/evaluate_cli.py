from __future__ import annotations

import json

from agent.agent_jobs.snap.arguments import get_args
from agent.job_search.evaluation import evaluate, load_labels
from agent.job_search.service import create_search_service, resolve


def main() -> None:
    args = get_args("evaluate_jobs")
    labels = load_labels(resolve(args.labels))
    service = create_search_service()
    methods = [m.strip() for m in args.methods.split(",") if m.strip()]
    report = evaluate(service, labels, methods=methods)

    print(f"{len(labels)} labelled queries, {len(service.index)} indexed jobs\n")
    print(f"{'method':<10} {'P@5':>6} {'nDCG@10':>8}")
    for method, r in report.items():
        print(f"{method:<10} {r['P@5']:>6.3f} {r['nDCG@10']:>8.3f}")

    out = resolve(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nPer-query report: {out}")


if __name__ == "__main__":
    main()
