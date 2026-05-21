# 100-DSA Local LLM Evaluation Process

A reproducible Python workflow for evaluating local Large Language Models (LLMs) on two ontology-grounded tasks over 100 Turtle-encoded Data Sharing Agreements (DSAs).

The package supports:

- **T1 — Executive-summary generation:** generate a concise professional summary from a DSA represented as RDF/Turtle.
- **T2 — Competency-question answering:** answer the CQ-1–CQ-13 best-set competency questions using only graph-supported evidence, with explicit abstention when the TTL does not contain the answer.

The evaluator is Turtle-aware: it compares model outputs against graph-derived references while accepting equivalent lexical forms such as full URIs, compact URIs, local names, underscore/space variants, and common date/duration aliases.

## Repository contents

```text
configs/                 LM Studio / OpenAI-compatible runtime configuration
data/ttl/                100 DSA instances in RDF/Turtle
prompts/                 System, T1, and T2 prompts
src/                     Reference extraction, local LLM execution, and evaluation scripts
results/                 Current outputs, metrics, and LaTeX-ready result tables
docs/                    Methodological notes and reproducibility documentation
.github/                 Issue templates, pull-request template, and CI workflow
```

## Requirements

- Python 3.10 or newer.
- `make` for the convenience commands.
- LM Studio, llama.cpp server, vLLM, Ollama OpenAI-compatible endpoint, or any local OpenAI-compatible chat-completions server for model runs.

Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Configure local models

Edit `configs/run.yaml`:

```yaml
base_url: http://localhost:1234/v1
temperature: 0.1
max_tokens_T1: 600
max_tokens_T2: 1200
timeout_seconds: 240
models:
  - id: mistral-7b-v0.2
    name: Mistral-7B-v0.2
  - id: meta-llama-3-8b-instruct
    name: Meta-Llama-3-8B-Instruct
  - id: gemma-1.1-7b
    name: Gemma-1.1-7B
```

The `id` value must exactly match the model identifier exposed by the local server.

## Run the workflow

Generate graph-derived references:

```bash
make references
```

Run a two-DSA smoke test against the configured local LLM server:

```bash
make llm-smoke
```

Run the complete 100-DSA experiment:

```bash
make llm-all
```

Evaluate an existing `results/raw_jsonl/model_outputs.jsonl` file without rerunning the models:

```bash
make evaluate
```

Run a reference-oracle sanity check:

```bash
make oracle
```

Run the lightweight CI-style smoke test used by GitHub Actions:

```bash
make ci-smoke
```

## Main outputs

```text
results/txt_outputs/T1/<MODEL>/<DSA_ID>.txt
results/txt_outputs/T2/<MODEL>/<DSA_ID>.txt
results/raw_jsonl/model_outputs.jsonl
results/reference/jsonl/reference_answers.jsonl
results/reference/jsonl/reference_stats.json
results/metrics/t1_field_scores.jsonl
results/metrics/t2_item_scores.jsonl
results/metrics/t1_summary_metrics.json
results/metrics/t2_model_metrics.json
results/metrics/t1_field_level_metrics.json
results/metrics/t2_cq_level_metrics.json
results/metrics/t1_field_level_metrics.csv
results/metrics/t2_cq_level_metrics.csv
results/tables/t1_summary_metrics.tex
results/tables/t2_model_metrics.tex
results/tables/t2_per_cq_semantic.tex
```

## T1 metrics

T1 is evaluated against the prompt facets in the executive-summary prompt rather than a legacy fixed business-field checklist. The main T1 metrics are:

- `prompt_facet_coverage`: whether each answerable prompt facet is represented at least once.
- `value_level_coverage`: fraction of graph-supported reference values found across answerable facets.
- `complete_facet_coverage`: fraction of answerable facets for which all expected graph values are present.
- `missing_facet_behavior_accuracy`: whether optional or missing facets are omitted or explicitly marked as not stated/not specified.
- `unsupported_missing_facet_rate`: concrete unsupported claims for missing facets.
- `ttl_supported_wrong_facet_rate`: values present somewhere in the TTL but used for the wrong missing facet.
- `identifier_sensitive_exactness`: exact preservation for identifier-bearing facets.
- `word_limit_pass_rate`: whether the T1 output respects the 180-word limit.

Backward-compatible aliases such as `supported_field_coverage` are still written for older paper tables/scripts, but the prompt-aligned names should be preferred.

## T2 metrics

T2 uses the 13-question best set. The evaluator accepts both `CQ-1` and legacy `CQ1` line prefixes, but all internal metrics use the canonical `CQ-#` IDs.

The model-level metrics are:

- `strict_accuracy`
- `semantic_match`
- `answerable_accuracy`
- `abstention_accuracy`
- `unsupported_answer_rate`
- `ttl_supported_wrong_field_rate`
- `identifier_sensitive_exactness`
- `policy_facet_separation`

## Important reproducibility note

The repository includes generated results as a snapshot. Before reporting final paper metrics, regenerate outputs with the current prompt files and the exact local model identifiers/settings to be reported in the paper.

```bash
make llm-all
```

See [`docs/reproducibility.md`](docs/reproducibility.md) for a fuller protocol.

## Citation

Use [`CITATION.cff`](CITATION.cff) for software citation metadata. If this repository supports a paper submission, cite both the repository and the corresponding paper.

## License

This package is distributed under the MIT License. Review and change `LICENSE` before public release if a different institutional or project license is required.
