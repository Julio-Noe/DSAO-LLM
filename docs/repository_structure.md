# Repository structure

```text
.
├── .github/
│   ├── ISSUE_TEMPLATE/
│   ├── workflows/ci.yml
│   └── pull_request_template.md
├── configs/
│   └── run.yaml
├── data/
│   └── ttl/
├── docs/
│   ├── process_and_metric_decisions.md
│   ├── reproducibility.md
│   └── repository_structure.md
├── prompts/
│   ├── system.txt
│   ├── T1_executive_summary.txt
│   └── T2_competency_questions.txt
├── results/
│   ├── metrics/
│   ├── raw_jsonl/
│   ├── reference/
│   ├── tables/
│   └── txt_outputs/
├── src/
│   ├── common.py
│   ├── evaluate_outputs.py
│   ├── extract_references.py
│   ├── generate_oracle_outputs.py
│   └── run_lmstudio.py
├── .env.example
├── .gitattributes
├── .gitignore
├── CITATION.cff
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── LICENSE
├── Makefile
├── README.md
├── SECURITY.md
├── pyproject.toml
├── requirements-dev.txt
└── requirements.txt
```

## Core scripts

- `src/extract_references.py`: reads the DSA TTL files and creates graph-derived reference answers for T1 and T2.
- `src/run_lmstudio.py`: sends T1/T2 prompts to a local OpenAI-compatible chat-completions endpoint.
- `src/evaluate_outputs.py`: computes Turtle-aware metrics and writes JSON, CSV, JSONL, and LaTeX table outputs.
- `src/generate_oracle_outputs.py`: creates reference-oracle outputs for evaluator sanity checks.
- `src/common.py`: shared constants, CQ definitions, aliases, and helper functions.
