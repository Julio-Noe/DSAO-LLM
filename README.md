# Anonymous Review Artifact: Ontology-Grounded LLM Evaluation for Data Sharing Agreements

This repository is an **anonymised review artifact** for a paper under peer review. It provides the non-identifying material needed to understand the evaluation design, prompts, aggregate results, and reported tables for an ontology-grounded Large Language Model (LLM) evaluation over 100 Turtle-encoded Data Sharing Agreements (DSAs).

> **Anonymous-review status.** The executable source code is intentionally **not included in this review version**. The full implementation, runnable scripts, CI configuration, software citation metadata, and final open-source license will be released after paper acceptance and de-anonymisation.

## Purpose of this review artifact

The artifact supports reviewer inspection of the experimental setup without revealing author-identifying information. It documents two ontology-grounded tasks:

- **T1 — Executive-summary generation:** generate a concise professional summary from a DSA represented as RDF/Turtle.
- **T2 — Competency-question answering:** answer the best-set competency questions using only graph-supported evidence, with explicit abstention when the TTL does not contain the answer.

The evaluation is designed around Turtle-aware comparison between model outputs and graph-derived references. It accounts for equivalent lexical forms such as full URIs, compact URIs, local names, underscore/space variants, and common date/duration aliases.

## What is included during anonymous review

```text
configs/                 Non-identifying runtime configuration summary
data/ttl/                Anonymised RDF/Turtle DSA instances, when included
prompts/                 System, T1, and T2 prompts used for the experiments
results/metrics/         Aggregate metric files and per-item score artifacts
docs/                    Reproducibility notes, metric decisions, and structure notes
.github/                 Non-identifying issue and pull-request templates
```

## What is intentionally withheld until acceptance

```text
src/                     Source code for reference extraction, model execution, and evaluation
Makefile                 Convenience targets for reproducing the pipeline
```

The withheld material will be added to the public repository after acceptance. The post-acceptance version will include the complete runnable workflow for:

1. extracting graph-derived reference answers from the Turtle files;
2. running local OpenAI-compatible LLM endpoints;
3. evaluating T1 and T2 outputs;
4. regenerating JSON, CSV, JSONL, and LaTeX result artifacts; and
5. running a lightweight continuous-integration smoke test.

## Experimental configuration summary

The experiments use a local OpenAI-compatible chat-completions endpoint. The reported configuration is:

```yaml
temperature: 0.1
max_tokens_T1: 600
max_tokens_T2: 1200
timeout_seconds: 240
```

The evaluated local models are reported in the paper and configuration summary using their non-identifying model labels. Exact executable setup files will be released after acceptance.

## Prompt files

The review version includes the prompt files so reviewers can inspect the task instructions directly:

```text
prompts/system.txt
prompts/T1_executive_summary.txt
prompts/T2_competency_questions.txt
```

These prompts define the graph-only evidence constraint, the no-fabrication rule, the executive-summary facets, and the competency-question answer format.

## Result artifacts

The main aggregate result files are:

```text
results/metrics/t1_summary_metrics.json
results/metrics/t2_model_metrics.json
results/metrics/t1_field_level_metrics.csv
results/metrics/t2_cq_level_metrics.csv
results/tables/t1_summary_metrics.tex
results/tables/t2_model_metrics.tex
results/tables/t2_per_cq_semantic.tex
```

These files are provided to make the paper tables and aggregate claims auditable during review. The executable scripts used to generate them are withheld only for the anonymous-review phase and will be released after acceptance.

## Metrics overview

### T1 metrics

T1 is evaluated against the facets requested in the executive-summary prompt. The main metric families are:

- `prompt_facet_coverage`
- `value_level_coverage`
- `complete_facet_coverage`
- `missing_facet_behavior_accuracy`
- `unsupported_missing_facet_rate`
- `ttl_supported_wrong_facet_rate`
- `identifier_sensitive_exactness`
- `word_limit_pass_rate`

### T2 metrics

T2 evaluates competency-question answers over the graph-supported reference values. The main metric families are:

- `strict_accuracy`
- `semantic_match`
- `answerable_accuracy`
- `abstention_accuracy`
- `unsupported_answer_rate`
- `ttl_supported_wrong_field_rate`
- `identifier_sensitive_exactness`
- `policy_facet_separation`

## Reproducibility statement for review

This anonymous repository is **not yet intended to be executed** because the source code is withheld until acceptance. During review, it should be used to inspect:

- the task definitions;
- the prompt wording;
- the anonymised DSA representation, when included;
- the metric families and evaluation rationale;
- the reported aggregate results; and
- the LaTeX-ready tables used in the paper.

After acceptance, the repository will be updated with the complete source code and execution instructions so that the full evaluation can be rerun locally.

## Anonymity and citation

Please do not attempt to infer author identity from this anonymous-review artifact. Author metadata, institutional information, repository ownership, and final citation details are intentionally omitted. A complete `CITATION.cff` file will be added after acceptance.

## License status

This anonymous-review artifact is provided for peer-review inspection only. The final public release will include the full source code and the definitive open-source license after acceptance.
