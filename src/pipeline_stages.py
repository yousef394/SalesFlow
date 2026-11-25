"""One command per pipeline stage, used by the Airflow DAG (and runnable by hand).

    python -m src.pipeline_stages <stage> --run-id <id>

Stages: validate_sales_csv, source_etl, validate_source_db, dwh_etl,
validate_dwh, build_views, predictions, pipeline_complete.

Each stage records running/success/failed in pipeline_run_status (best effort:
a status-write problem is logged but never hides the stage's own result) and
lets the original exception propagate, so the process exits non-zero with the
full traceback and Airflow marks the task as failed.

Stages run in separate processes, so the prepared tables travel from
validate_sales_csv to source_etl through a run-specific staging folder
(data/staging/<run_id>/), which pipeline_complete removes.
"""

import argparse
import json
import logging
import os
import pickle
import re
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from src import pipeline_checks, pipeline_status
from src.config import get_engine

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("SALESFLOW_DATA_DIR") or PROJECT_ROOT / "data")
ANALYTICS_SQL = PROJECT_ROOT / "sql" / "analytics.sql"
FORECAST_COLUMNS = ["year", "month", "product_key", "predicted_sales"]

log = logging.getLogger("salesflow.stages")


# ----------------------------------------------------------------------
# staging of the prepared tables between processes
# ----------------------------------------------------------------------

def staging_dir(run_id):
    return DATA_DIR / "staging" / re.sub(r"[^A-Za-z0-9_.-]", "_", run_id)


def save_staged(run_id, tables):
    folder = staging_dir(run_id)
    folder.mkdir(parents=True, exist_ok=True)
    counts = {name: len(frame) for name, frame in tables.items()}
    # Pickle keeps dtypes exactly as sales.main() produced them. The file is
    # written and read only by this pipeline, inside the project's data folder.
    with open(folder / "prepared.pkl", "wb") as handle:
        pickle.dump(tables, handle, protocol=pickle.HIGHEST_PROTOCOL)
    (folder / "meta.json").write_text(
        json.dumps({"counts": counts, "created_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    return counts


def load_staged(run_id):
    folder = staging_dir(run_id)
    if not (folder / "prepared.pkl").exists():
        raise FileNotFoundError(
            f"No prepared data for run {run_id!r} in {folder}. "
            "Run (or re-run) validate_sales_csv for the same run first."
        )
    with open(folder / "prepared.pkl", "rb") as handle:
        tables = pickle.load(handle)
    counts = json.loads((folder / "meta.json").read_text(encoding="utf-8"))["counts"]
    return tables, counts


def clean_staging(run_id):
    shutil.rmtree(staging_dir(run_id), ignore_errors=True)
    root = DATA_DIR / "staging"
    if root.exists() and not any(root.iterdir()):
        root.rmdir()


# ----------------------------------------------------------------------
# stages
# ----------------------------------------------------------------------

def validate_sales_csv(run_id):
    import pandas as pd

    from src import sales

    path = Path(sales.CSV_PATH)
    if not path.is_file():
        raise FileNotFoundError(f"Sales CSV not found: {path}")
    df = pd.read_csv(path)
    pipeline_checks.validate_csv_frame(df, path)
    tables = sales.main(df=df)  # the project's existing validation + table building, same frame
    counts = save_staged(run_id, tables)
    log.info("Prepared tables staged for run %s: %s", run_id, counts)


def source_etl(run_id):
    from src import ETL

    tables, _ = load_staged(run_id)
    ETL.main(tables)


def validate_source_db(run_id):
    _, counts = load_staged(run_id)
    engine = get_engine("SOURCE_DB_NAME")
    try:
        pipeline_checks.validate_source_db(engine, counts)
    finally:
        engine.dispose()


def dwh_etl(run_id):
    from src import dwh_etl as dwh

    dwh.main()


def validate_dwh(run_id):
    dwh_engine, source_engine = get_engine("DWH_DB_NAME"), get_engine("SOURCE_DB_NAME")
    try:
        pipeline_checks.validate_dwh(dwh_engine, source_engine)
    finally:
        dwh_engine.dispose()
        source_engine.dispose()


def build_views(run_id):
    sql_text = ANALYTICS_SQL.read_text(encoding="utf-8")
    names = pipeline_checks.view_names(sql_text)
    if not names:
        raise RuntimeError(f"No CREATE OR REPLACE VIEW statements found in {ANALYTICS_SQL}")
    engine = get_engine("DWH_DB_NAME")
    try:
        with engine.begin() as connection:  # all views or none
            connection.exec_driver_sql(sql_text)
        pipeline_checks.validate_views(engine, names)
    finally:
        engine.dispose()


def predictions(run_id):
    import pandas as pd
    import runpy

    out = pipeline_status.output_dir()
    out.mkdir(parents=True, exist_ok=True)
    started = time.time()
    try:
        runpy.run_module("src.prediction", run_name="__main__")
    finally:
        # src/prediction.py stops Spark itself on success; make sure it is stopped on failure too.
        try:
            from pyspark.sql import SparkSession

            active = SparkSession.getActiveSession()
            if active is not None:
                active.stop()
        except Exception:
            log.warning("Could not stop the Spark session cleanly", exc_info=True)

    forecast = pipeline_status.forecast_file()
    if not forecast.exists() or forecast.stat().st_mtime < started - 2:
        raise RuntimeError(
            f"src.prediction finished but {forecast} was not written in this run. "
            "Check that src/prediction.py writes to PREDICTION_OUTPUT_DIR (or <project>/prediction_outputs)."
        )
    frame = pd.read_csv(forecast)
    problems = [f"forecast.csv is missing column {c}" for c in FORECAST_COLUMNS if c not in frame.columns]
    if not problems:
        if frame.empty:
            problems.append("forecast.csv has no rows")
        if frame["predicted_sales"].isna().any():
            problems.append("forecast.csv has empty predicted_sales values")
    if not (out / "metrics.json").exists():
        problems.append("metrics.json was not written")
    if problems:
        raise pipeline_checks.ValidationError("Prediction output validation failed", problems)
    meta = pipeline_status.write_forecast_meta(run_id, len(frame), frame["year"].unique())
    log.info("Forecast ready for run %s: %s", run_id, meta)


def pipeline_complete(run_id):
    log.info("SalesFlow pipeline run %s completed successfully", run_id)
    clean_staging(run_id)


STAGES = {
    "validate_sales_csv": validate_sales_csv,
    "source_etl": source_etl,
    "validate_source_db": validate_source_db,
    "dwh_etl": dwh_etl,
    "validate_dwh": validate_dwh,
    "build_views": build_views,
    "predictions": predictions,
    "pipeline_complete": pipeline_complete,
}
assert list(STAGES) == pipeline_status.STAGES


# ----------------------------------------------------------------------
# runner
# ----------------------------------------------------------------------

def _status(run_id, stage, status, message=None):
    engine = None
    try:
        engine = get_engine("DWH_DB_NAME")
        pipeline_status.ensure_table(engine)
        pipeline_status.record(engine, run_id, stage, status, message)
    except Exception as exc:
        log.warning("Could not record status %s/%s: %s", stage, status, pipeline_status.scrub(exc))
    finally:
        if engine is not None:
            engine.dispose()


def run(stage, run_id):
    log.info("Stage %s started (run %s)", stage, run_id)
    started = time.perf_counter()
    _status(run_id, stage, "running")
    try:
        STAGES[stage](run_id)
    except BaseException as exc:
        _status(run_id, stage, "failed", f"{type(exc).__name__}: {exc}")
        log.error("Stage %s FAILED after %.1fs", stage, time.perf_counter() - started)
        raise
    _status(run_id, stage, "success")
    log.info("Stage %s completed in %.1fs", stage, time.perf_counter() - started)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Run one SalesFlow pipeline stage.")
    parser.add_argument("stage", choices=list(STAGES))
    parser.add_argument(
        "--run-id",
        default=os.getenv("AIRFLOW_CTX_DAG_RUN_ID")
        or "manual-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S"),
    )
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        run(args.stage, args.run_id)
    except Exception:
        log.exception("Stage %s failed", args.stage)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
