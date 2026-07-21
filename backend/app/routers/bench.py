"""The bench surface — thin HTTP over app.bench (datasets → gold → run → report).

Long operations (gold drafting, the run itself) stream NDJSON, same protocol as
the graph page's upload/dream streams, so the Bench page narrates progress live.
"""

from __future__ import annotations

import json
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse, StreamingResponse
from pydantic import BaseModel

import shutil

from app import bench
from app.bench import estimate as bench_estimate
from app.bench import fetch, goldgen, jobs, runner, store

router = APIRouter(prefix="/bench")


def _line(obj: dict) -> bytes:
    return (json.dumps(obj) + "\n").encode("utf-8")


@router.get("/datasets")
def datasets() -> dict:
    return {"datasets": bench.list_datasets(), "raw_dir": str(store.RAW_DIR)}


class DownloadBody(BaseModel):
    url: str


@router.post("/download")
def download(body: DownloadBody) -> StreamingResponse:
    """Fetch a dataset file from a URL into the raw dir, streaming progress."""
    def stream():
        for ev in fetch.download(body.url):
            yield _line(ev)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


class DeleteDatasetBody(BaseModel):
    name: str


@router.post("/delete-dataset")
def delete_dataset(body: DeleteDatasetBody) -> dict:
    """Remove a dataset's raw file(s) and derived work dir (corpus, gold, manifest,
    runs). Graph saves built from it are NOT touched — manage those on the graph page."""
    name = body.name.strip()
    if not re.fullmatch(r"[A-Za-z0-9._-]+", name):
        raise HTTPException(status_code=400, detail="Bad dataset name.")
    removed = []
    for suffix in (".jsonl", ".json"):
        f = store.RAW_DIR / f"{name}{suffix}"
        if f.exists():
            f.unlink()
            removed.append(f.name)
    work = store.WORK_DIR / name
    if work.exists():
        shutil.rmtree(work)
        removed.append(f"{name}/ (prepared corpus, gold, runs)")
    if not removed:
        raise HTTPException(status_code=404, detail="No such dataset.")
    return {"removed": removed}


class PrepareBody(BaseModel):
    dataset: str
    cap_tokens: int = 100_000


@router.post("/prepare")
def prepare(body: PrepareBody) -> dict:
    try:
        prepared = bench.prepare(body.dataset, max(10_000, body.cap_tokens))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"prepared": prepared, **bench.dataset_status(body.dataset)}


class GoldGenBody(BaseModel):
    dataset: str
    total: int = 24


@router.post("/goldgen")
def goldgen_stream(body: GoldGenBody) -> StreamingResponse:
    async def stream():
        async for ev in goldgen.generate(body.dataset, max(1, min(body.total, 100))):
            yield _line(ev)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


class VerifyBody(BaseModel):
    dataset: str


@router.post("/goldverify")
def goldverify_stream(body: VerifyBody) -> StreamingResponse:
    async def stream():
        async for ev in goldgen.verify(body.dataset):
            yield _line(ev)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/gold")
def get_gold(dataset: str) -> dict:
    return {"questions": store.load_gold(dataset)}


class GoldBody(BaseModel):
    dataset: str
    questions: list[dict]


@router.put("/gold")
def put_gold(body: GoldBody) -> dict:
    keep = []
    for q in body.questions:
        if not (q.get("question") and q.get("answer")):
            continue
        q["status"] = q.get("status") if q.get("status") in ("draft", "approved") else "draft"
        keep.append(q)
    store.save_gold(body.dataset, keep)
    return {"saved": len(keep),
            "approved": sum(1 for q in keep if q["status"] == "approved")}


class RunBody(BaseModel):
    dataset: str
    configs: list[str] = list(runner.CONFIGS)
    extract_model: str | None = None  # graph (and LightRAG) builder
    answer_model: str | None = None   # the generator every config shares
    judge_model: str | None = None    # verdict model (on the judge endpoint if set)
    context_model: str | None = None  # chunk contextualizer (RAG build blurbs)
    scope: str = "auto"  # "auto" = follow the dataset (scope to each question's doc_id when it has one); "corpus" = force whole-corpus


@router.post("/run")
async def run(body: RunBody) -> StreamingResponse:
    """Start a run as a DETACHED job and tail it. Closing the tab only drops the
    tail — the run keeps going server-side; GET /bench/job reattaches to it."""
    job = jobs.start(body.dataset, "run", runner.run_bench(
        body.dataset, body.configs,
        extract_model=body.extract_model, answer_model=body.answer_model,
        judge_model=body.judge_model, context_model=body.context_model,
        scope=body.scope,
    ))

    async def stream():
        if job is None:
            yield _line({"phase": "error",
                         "detail": "A run is already in progress for this dataset — reattach "
                                   "to it (reload the page) or pause it first. Starting a "
                                   "second run would rebuild the same memory and pay twice."})
            return
        async for ev in job.tail():
            yield _line(ev)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/job")
async def job_for_dataset(dataset: str) -> dict:
    """The dataset's newest job (running or finished) so a reopened page can reattach."""
    job = jobs.active_for(dataset) or jobs.latest_for(dataset)
    return {"job": job.info() if job else None}


@router.get("/job/{job_id}/stream")
async def job_stream(job_id: str, since: int = 0) -> StreamingResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job (server restarted?) — "
                                                    "press Run to resume; nothing is re-paid.")

    async def stream():
        async for ev in job.tail(since):
            yield _line(ev)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.post("/job/{job_id}/stop")
async def job_stop(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="No such job.")
    job.stop()
    return {"stopped": True}


@router.get("/jobs")
def all_jobs() -> dict:
    """Every running job across datasets — lets the page show the whole overnight
    campaign, not just the selected dataset's job."""
    return {"jobs": [j.info() for j in jobs.all_active()]}


@router.get("/estimate")
def estimate(dataset: str, configs: str = "", extract_model: str = "",
             context_model: str = "", answer_model: str = "") -> dict:
    """Cost ballpark for a run BEFORE it starts (±2× until calibrated). `configs`
    is comma-separated; empty = every config. Model overrides mirror the run's
    pickers so the gate prices what will actually launch."""
    wanted = [c for c in configs.split(",") if c] or list(runner.CONFIGS)
    return bench_estimate.estimate(dataset, wanted, extract_model or None,
                                   context_model or None, answer_model or None)


class RejudgeBody(BaseModel):
    dataset: str
    run_id: str
    judge_model: str | None = None


@router.post("/rejudge")
async def rejudge(body: RejudgeBody) -> StreamingResponse:
    """Re-score a stored run with the current judge/gold — no generation re-paid.
    Also a detached job, so a closed tab doesn't abandon paid verdicts mid-pass."""
    job = jobs.start(body.dataset, "rejudge",
                     runner.rejudge_run(body.dataset, body.run_id, body.judge_model))

    async def stream():
        if job is None:
            yield _line({"phase": "error",
                         "detail": "A job is already running for this dataset — wait for it "
                                   "or pause it first."})
            return
        async for ev in job.tail():
            yield _line(ev)

    return StreamingResponse(stream(), media_type="application/x-ndjson")


@router.get("/runs")
def runs(dataset: str) -> dict:
    return {"runs": store.list_runs(dataset)}


class DeleteRunBody(BaseModel):
    dataset: str
    run_id: str


@router.post("/delete-run")
def delete_run(body: DeleteRunBody) -> dict:
    """Remove one run's report from the dataset's workdir. The local archive copy
    (bench_archive/) is kept — deleting from the UI never destroys the last record."""
    if not re.fullmatch(r"[A-Za-z0-9._-]+", body.dataset):
        raise HTTPException(status_code=400, detail="Bad dataset name.")
    if not re.fullmatch(r"[A-Za-z0-9._-]+", body.run_id):
        raise HTTPException(status_code=400, detail="Bad run id.")
    if not store.delete_run(body.dataset, body.run_id):
        raise HTTPException(status_code=404, detail="No such run.")
    return {"deleted": body.run_id}


@router.get("/report")
def report(dataset: str, run_id: str, full: bool = False) -> dict:
    """The report; `full=true` includes the raw per-question records (large — at
    1000 questions they are megabytes, so the page never loads them by default)."""
    r = store.load_run(dataset, run_id)
    if not r:
        raise HTTPException(status_code=404, detail="No such run.")
    return r if full else {**r, "records": []}


@router.get("/report.md", response_class=PlainTextResponse)
def report_md(dataset: str, run_id: str) -> str:
    md = store.load_run_markdown(dataset, run_id)
    if md is None:
        raise HTTPException(status_code=404, detail="No such run.")
    return md
