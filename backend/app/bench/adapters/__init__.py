"""Offline converters: official benchmark releases -> noema-humanqa-v1 raw files
(the format app/bench/humanqa.py prepares). One module per dataset, each with a
CLI — run from backend/ with the venv, e.g.:

    .venv/bin/python -m app.bench.adapters.financebench
    .venv/bin/python -m app.bench.adapters.baselfaq
    .venv/bin/python -m app.bench.adapters.crag data/bench/raw/crag_task_1_and_2_dev_v5.jsonl.bz2

No LLM calls anywhere — pure deterministic conversion, so the committed output is
reproducible from the official sources.
"""
