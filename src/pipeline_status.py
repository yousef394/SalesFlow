"""Pipeline run status: which DAG run is current, and are its outputs ready?

Used by the Airflow task runner (writes) and by the dashboard (reads).
Only needs SQLAlchemy and the standard library, so it also runs in the small
dashboard image.

Status rows live in the data warehouse database (table pipeline_run_status,
see sql/pipeline_status.sql). The forecast gets a small side file,
forecast_meta.json, written next to forecast.csv after the prediction task has
checked the forecast; it carries the run id the forecast belongs to.
"""

import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATUS_SQL = PROJECT_ROOT / "sql" / "pipeline_status.sql"

STAGES = [
    "validate_sales_csv",
    "source_etl",
    "validate_source_db",
    "dwh_etl",
    "validate_dwh",
    "build_views",
    "predictions",
    "pipeline_complete",
]


def output_dir():
    """Where forecast.csv lives. Shared between the worker and the dashboard."""
    return Path(os.getenv("PREDICTION_OUTPUT_DIR") or PROJECT_ROOT / "prediction_outputs")


def forecast_file():
    return output_dir() / "forecast.csv"


def meta_file():
    return output_dir() / "forecast_meta.json"


def scrub(message):
    """Keep secrets out of stored/logged messages."""
    message = str(message)
    password = os.getenv("DB_PASSWORD")
    if password:
        message = message.replace(password, "***")
    return re.sub(r"(postgresql[+\w]*://[^:/\s]+:)[^@\s]+@", r"\1***@", message)[:1000]


def ensure_table(engine):
    with engine.begin() as connection:
        connection.exec_driver_sql(STATUS_SQL.read_text(encoding="utf-8"))


def record(engine, run_id, stage, status, message=None):
    finished = None if status == "running" else datetime.now(timezone.utc)
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO pipeline_run_status (run_id, stage, status, started_at, finished_at, message)
                VALUES (:run_id, :stage, :status, now(), :finished, :message)
                ON CONFLICT (run_id, stage) DO UPDATE
                SET status = EXCLUDED.status,
                    finished_at = EXCLUDED.finished_at,
                    message = EXCLUDED.message
                """
            ),
            {
                "run_id": run_id,
                "stage": stage,
                "status": status,
                "finished": finished,
                "message": scrub(message) if message else None,
            },
        )


def latest_run(engine):
    """The most recently started run and its stages, or None if there are no runs yet.

    Raises if the status table does not exist; callers decide what that means.
    """
    with engine.connect() as connection:
        run = connection.execute(
            text(
                """
                SELECT run_id FROM pipeline_run_status
                GROUP BY run_id
                ORDER BY MIN(started_at) DESC
                LIMIT 1
                """
            )
        ).scalar()
        if run is None:
            return None
        rows = connection.execute(
            text(
                """
                SELECT stage, status, finished_at, message
                FROM pipeline_run_status WHERE run_id = :run_id
                """
            ),
            {"run_id": run},
        ).all()
    return {
        "run_id": run,
        "stages": {
            r.stage: {"status": r.status, "finished_at": r.finished_at, "message": r.message}
            for r in rows
        },
    }


def read_forecast_meta():
    try:
        return json.loads(meta_file().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return None


def write_forecast_meta(run_id, rows, years):
    """Atomic write, so the dashboard never reads half a file."""
    out = output_dir()
    out.mkdir(parents=True, exist_ok=True)
    payload = {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "rows": int(rows),
        "years": [int(y) for y in years],
    }
    fd, tmp = tempfile.mkstemp(dir=out, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        os.chmod(tmp, 0o644)  # mkstemp creates 0600; the dashboard container runs as another user
        os.replace(tmp, meta_file())
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise
    return payload


def forecast_state(engine):
    """Decide whether the forecast file may be shown.

    Returns (state, info):
      "ready"   forecast belongs to the latest run and that run's prediction succeeded
      "legacy"  no pipeline run has ever been recorded (the project was run by hand,
                e.g. with run_pipeline.py), so only the file itself can be checked
      "waiting" anything else; info says why
    """
    try:
        run = latest_run(engine)
    except Exception:
        run = "no-status-table"

    if run in (None, "no-status-table"):
        if forecast_file().exists():
            return "legacy", {"reason": "No pipeline run is recorded; showing the forecast file as found."}
        return "waiting", {"reason": "No pipeline run has been recorded yet."}

    prediction = run["stages"].get("predictions")
    if prediction is None or prediction["status"] == "running":
        return "waiting", {"reason": f"Predictions for run {run['run_id']} are still running.", "run_id": run["run_id"]}
    if prediction["status"] == "failed":
        return "waiting", {"reason": f"Predictions failed in run {run['run_id']}.", "run_id": run["run_id"]}

    meta = read_forecast_meta()
    if not forecast_file().exists():
        return "waiting", {
            "reason": f"Run {run['run_id']} reports a finished prediction, but forecast.csv is missing.",
            "run_id": run["run_id"],
        }
    if meta is None or meta.get("run_id") != run["run_id"]:
        found = meta.get("run_id") if meta else None
        return "waiting", {
            "reason": f"Run {run['run_id']} reports a finished prediction, but the forecast on disk belongs to "
                      f"{('run ' + str(found)) if found else 'no recorded run'}.",
            "run_id": run["run_id"],
        }
    return "ready", {"run_id": run["run_id"], "generated_at": meta.get("generated_at")}
