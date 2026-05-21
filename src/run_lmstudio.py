from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

import httpx
import yaml

from common import write_jsonl


def load(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def chat_completion(base_url: str, model: str, messages: list[dict], temperature: float, max_tokens: int, timeout: float) -> str:
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LMSTUDIO_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    with httpx.Client(timeout=timeout) as client:
        r = client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


def write_txt_output(txt_root: Path, model_name: str, task: str, dsa_id: str, output: str) -> None:
    safe_model = model_name.replace("/", "_").replace(" ", "_")
    out = txt_root / task / safe_model / f"{dsa_id}.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(output.strip() + "\n", encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Run T1 and T2 DSA prompts against an OpenAI-compatible local LLM server.")
    ap.add_argument("--config", type=Path, default=Path("configs/run.yaml"))
    ap.add_argument("--limit", type=int, default=None, help="Optional smoke-test limit over the first N TTL files.")
    args = ap.parse_args()

    cfg = yaml.safe_load(args.config.read_text(encoding="utf-8"))
    input_dir = Path(cfg.get("input_dir", "data/ttl"))
    raw_output_jsonl = Path(cfg.get("raw_output_jsonl", "results/raw_jsonl/model_outputs.jsonl"))
    txt_output_dir = Path(cfg.get("txt_output_dir", "results/txt_outputs"))
    base_url = cfg.get("base_url", "http://localhost:1234/v1")
    temperature = float(cfg.get("temperature", 0.1))
    timeout = float(cfg.get("timeout_seconds", 240))

    system_prompt = load(Path("prompts/system.txt"))
    t1_prompt = load(Path("prompts/T1_executive_summary.txt"))
    t2_prompt = load(Path("prompts/T2_competency_questions.txt"))

    ttl_files = sorted([p for p in input_dir.glob("*.ttl") if p.is_file()])
    if args.limit:
        ttl_files = ttl_files[: args.limit]

    rows = []
    for model_cfg in cfg.get("models", []):
        model_id = model_cfg["id"]
        model_name = model_cfg.get("name", model_id)
        for ttl_path in ttl_files:
            ttl_text = ttl_path.read_text(encoding="utf-8")
            for task, template, max_tokens in [
                ("T1", t1_prompt, int(cfg.get("max_tokens_T1", 600))),
                ("T2", t2_prompt, int(cfg.get("max_tokens_T2", 900))),
            ]:
                prompt = template.replace("{{TTL input}}", ttl_text)
                started = time.time()
                try:
                    output = chat_completion(
                        base_url=base_url,
                        model=model_id,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": prompt},
                        ],
                        temperature=temperature,
                        max_tokens=max_tokens,
                        timeout=timeout,
                    )
                    status = "ok"
                    error = None
                except Exception as exc:
                    output = ""
                    status = "error"
                    error = repr(exc)
                elapsed = round(time.time() - started, 3)
                row = {
                    "task": task,
                    "dsa_id": ttl_path.stem,
                    "ttl_file": ttl_path.name,
                    "model": model_name,
                    "model_id": model_id,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                    "status": status,
                    "error": error,
                    "elapsed_seconds": elapsed,
                    "output": output,
                }
                rows.append(row)
                write_txt_output(txt_output_dir, model_name, task, ttl_path.stem, output)
                print(f"{model_name} {ttl_path.name} {task}: {status} ({elapsed}s)")
    write_jsonl(raw_output_jsonl, rows)
    print(f"Wrote {len(rows)} raw outputs to {raw_output_jsonl}")
    print(f"Wrote per-DSA TXT outputs under {txt_output_dir}")

if __name__ == "__main__":
    main()
