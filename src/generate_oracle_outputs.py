from __future__ import annotations

import argparse
from pathlib import Path

from common import read_jsonl, write_jsonl


def write_txt(txt_root: Path, model_name: str, task: str, dsa_id: str, output: str) -> None:
    safe_model = model_name.replace("/", "_").replace(" ", "_")
    path = txt_root / task / safe_model / f"{dsa_id}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(output.strip() + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Create reference-oracle T1/T2 outputs to test the evaluator.")
    ap.add_argument("--reference", type=Path, default=Path("results/reference/jsonl/reference_answers.jsonl"))
    ap.add_argument("--jsonl", type=Path, default=Path("results/raw_jsonl/oracle_outputs.jsonl"))
    ap.add_argument("--txt-dir", type=Path, default=Path("results/txt_outputs"))
    args = ap.parse_args()
    rows = []
    for rec in read_jsonl(args.reference):
        dsa_id = rec["dsa_id"]
        t1 = rec["T1"]["reference_summary"]
        t2 = rec["T2"]["reference_answers"]
        for task, output in [("T1", t1), ("T2", t2)]:
            rows.append({"task": task, "dsa_id": dsa_id, "ttl_file": rec["ttl_file"], "model": "reference-oracle", "model_id": "reference-oracle", "status": "ok", "output": output})
            write_txt(args.txt_dir, "reference-oracle", task, dsa_id, output)
    write_jsonl(args.jsonl, rows)
    print(f"Wrote {len(rows)} reference-oracle outputs to {args.jsonl}")
    print(f"Wrote TXT outputs under {args.txt_dir}")

if __name__ == "__main__":
    main()
