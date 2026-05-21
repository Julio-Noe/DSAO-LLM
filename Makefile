.PHONY: help setup references oracle llm-smoke llm-all evaluate tables ci-smoke clean

help:
	@echo "Available targets:"
	@echo "  setup       Create .venv and install dependencies"
	@echo "  references  Extract graph-derived references from data/ttl"
	@echo "  oracle      Generate reference-oracle outputs and evaluate them"
	@echo "  llm-smoke   Run the first two DSAs against configured local LLMs"
	@echo "  llm-all     Run all 100 DSAs against configured local LLMs"
	@echo "  evaluate    Evaluate results/raw_jsonl/model_outputs.jsonl"
	@echo "  ci-smoke    Run a dependency-free three-DSA oracle smoke test"
	@echo "  clean       Remove generated result artifacts"

setup:
	python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt

references:
	python src/extract_references.py --input-dir data/ttl --jsonl results/reference/jsonl/reference_answers.jsonl --txt-dir results/reference/txt --stats results/reference/jsonl/reference_stats.json

oracle: references
	python src/generate_oracle_outputs.py --reference results/reference/jsonl/reference_answers.jsonl --jsonl results/raw_jsonl/oracle_outputs.jsonl --txt-dir results/txt_outputs
	python src/evaluate_outputs.py --reference results/reference/jsonl/reference_answers.jsonl --outputs results/raw_jsonl/oracle_outputs.jsonl --ttl-dir data/ttl --out-dir results/metrics --tables-dir results/tables

llm-smoke: references
	python src/run_lmstudio.py --config configs/run.yaml --limit 2
	python src/evaluate_outputs.py --reference results/reference/jsonl/reference_answers.jsonl --outputs results/raw_jsonl/model_outputs.jsonl --ttl-dir data/ttl --out-dir results/metrics --tables-dir results/tables

evaluate: references
	python src/evaluate_outputs.py --reference results/reference/jsonl/reference_answers.jsonl --outputs results/raw_jsonl/model_outputs.jsonl --ttl-dir data/ttl --out-dir results/metrics --tables-dir results/tables

llm-all: references
	python src/run_lmstudio.py --config configs/run.yaml
	python src/evaluate_outputs.py --reference results/reference/jsonl/reference_answers.jsonl --outputs results/raw_jsonl/model_outputs.jsonl --ttl-dir data/ttl --out-dir results/metrics --tables-dir results/tables

ci-smoke:
	rm -rf /tmp/dsa_eval_ci
	mkdir -p /tmp/dsa_eval_ci/ttl
	cp data/ttl/DSA_0001.ttl data/ttl/DSA_0002.ttl data/ttl/DSA_0003.ttl /tmp/dsa_eval_ci/ttl/
	python src/extract_references.py --input-dir /tmp/dsa_eval_ci/ttl --jsonl /tmp/dsa_eval_ci/reference.jsonl --txt-dir /tmp/dsa_eval_ci/reference_txt --stats /tmp/dsa_eval_ci/reference_stats.json
	python src/generate_oracle_outputs.py --reference /tmp/dsa_eval_ci/reference.jsonl --jsonl /tmp/dsa_eval_ci/oracle_outputs.jsonl --txt-dir /tmp/dsa_eval_ci/txt_outputs
	python src/evaluate_outputs.py --reference /tmp/dsa_eval_ci/reference.jsonl --outputs /tmp/dsa_eval_ci/oracle_outputs.jsonl --ttl-dir /tmp/dsa_eval_ci/ttl --out-dir /tmp/dsa_eval_ci/metrics --tables-dir /tmp/dsa_eval_ci/tables

clean:
	rm -rf results/raw_jsonl/*.jsonl results/txt_outputs/* results/metrics/* results/tables/*
