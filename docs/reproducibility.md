# Reproducibility protocol

This document records the recommended protocol for reproducing the local LLM evaluation.

## 1. Environment

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Record the following in any paper, report, or artifact appendix:

- operating system;
- Python version;
- local model server and version;
- hardware used for inference;
- model identifiers exactly as exposed by the server;
- quantization metadata, when applicable;
- temperature, max-token limits, and timeout settings from `configs/run.yaml`.

## 2. Reference extraction

```bash
make references
```

This creates graph-derived references from the Turtle files:

```text
results/reference/jsonl/reference_answers.jsonl
results/reference/jsonl/reference_stats.json
results/reference/txt/
```

## 3. Evaluator sanity check

```bash
make oracle
```

The oracle target generates outputs directly from the graph-derived references and evaluates them. Use this to check that the evaluator, aliases, and table writers are functioning before running LLMs.

## 4. Local LLM run

Start an OpenAI-compatible local server, then update `configs/run.yaml` with the model IDs exposed by that server.

For a quick check:

```bash
make llm-smoke
```

For the full experiment:

```bash
make llm-all
```

## 5. Evaluation only

When `results/raw_jsonl/model_outputs.jsonl` already exists:

```bash
make evaluate
```

## 6. Result files to report

Use these files for paper tables and aggregate interpretation:

```text
results/metrics/t1_summary_metrics.json
results/metrics/t2_model_metrics.json
results/metrics/t1_field_level_metrics.csv
results/metrics/t2_cq_level_metrics.csv
results/tables/t1_summary_metrics.tex
results/tables/t2_model_metrics.tex
results/tables/t2_per_cq_semantic.tex
```

## 7. Reproducibility cautions

- Do not compare outputs generated with different prompt versions without stating the prompt version.
- Do not report smoke-test results as full 100-DSA results.
- Regenerate outputs after changing `prompts/`, `src/common.py`, `src/extract_references.py`, or `src/evaluate_outputs.py`.
- If a model server returns a different model ID than expected, update `configs/run.yaml` rather than renaming outputs manually.
