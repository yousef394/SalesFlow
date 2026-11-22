"""Run the SalesFlow project locally.

    python run_pipeline.py                  # ETL -> DWH -> predictions -> dashboard
    python run_pipeline.py --skip-ml        # same, without re-running the Spark forecast
    python run_pipeline.py --no-dashboard   # stop after the finite stages

Stages run in dependency order, each exactly once, and the run stops at the
first failure with a non-zero exit code:

    prepare_data (src.sales.main)  ->  source_etl (src.ETL.main)  ->  dwh_etl (src.dwh_etl.main)
        ->  predictions (python -m src.prediction)  ->  dashboard (streamlit run src/dashboard.py)

The three ETL stages are imported and their main() is called explicitly;
importing them runs nothing. src.sales.main() returns the prepared tables and
the runner hands them to src.ETL.main(), so the CSV is read and validated once
per run.

src/prediction.py does its work at module level (it has no main()), so it runs
in its own process. That keeps Spark's JVM away from the ETL stages and leaves
the model code untouched. The dashboard is a long-running app: it is launched
last, only if every earlier stage succeeded, and runs until you press Ctrl+C.

Database transactions and rollback stay inside the ETL modules. This script
holds no credentials: connection settings come from .env via src.config.
"""

import argparse
import importlib
import importlib.util
import logging
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
DASHBOARD_FILE = PROJECT_ROOT / "src" / "dashboard.py"
# The dashboard reads the forecast from here (see src/dashboard.py, "Prediction" tab).
FORECAST_FILE = PROJECT_ROOT / "prediction_outputs" / "forecast.csv"

# Everything src.config and the ETL modules read. Names only, values are never logged.
REQUIRED_ENV = [
    "DB_HOST",
    "DB_PORT",
    "DB_USER",
    "DB_PASSWORD",
    "SOURCE_DB_NAME",
    "DWH_DB_NAME",
]

log = logging.getLogger("salesflow.pipeline")


def java_available():
    java_home = os.getenv("JAVA_HOME")
    return shutil.which("java") is not None or bool(
        java_home and (Path(java_home) / "bin" / "java").exists()
    )


def check_environment(ml=False, dashboard=False):
    """Fail early, with a clear message, before any stage touches a database."""
    import src.config  # noqa: F401  (its load_dotenv() reads .env)

    missing = [name for name in REQUIRED_ENV if not os.getenv(name)]
    if missing:
        raise RuntimeError("Missing environment variables: " + ", ".join(missing))

    try:
        int(os.getenv("DB_PORT"))  # src.config.get_engine() does int(DB_PORT)
    except ValueError:
        raise RuntimeError("DB_PORT must be an integer") from None

    problems = []
    if ml:
        if importlib.util.find_spec("pyspark") is None:
            problems.append("pyspark is not installed in this Python environment")
        if not java_available():
            problems.append("Java was not found (Spark needs it): install a JDK or set JAVA_HOME")
    if dashboard and importlib.util.find_spec("streamlit") is None:
        problems.append("streamlit is not installed in this Python environment")
    if problems:
        raise RuntimeError(
            "; ".join(problems) + " (use --skip-ml / --no-dashboard to skip those stages)"
        )


def run_stage(name, func, *args):
    log.info("Stage '%s' started", name)
    started = time.perf_counter()
    try:
        result = func(*args)
    except Exception:
        log.exception("Stage '%s' FAILED after %.1fs", name, time.perf_counter() - started)
        raise
    log.info("Stage '%s' completed in %.1fs", name, time.perf_counter() - started)
    return result


def run_predictions():
    """Run src/prediction.py in its own process and check that it refreshed the forecast."""
    started = time.time()
    result = subprocess.run([sys.executable, "-m", "src.prediction"], cwd=PROJECT_ROOT)
    if result.returncode != 0:
        raise RuntimeError(f"src.prediction exited with code {result.returncode}")
    # 2s of slack for file-system timestamp granularity.
    if not FORECAST_FILE.exists() or FORECAST_FILE.stat().st_mtime < started - 2:
        raise RuntimeError(
            f"src.prediction finished but {FORECAST_FILE} was not updated; "
            "the dashboard reads the forecast from that path"
        )


def launch_dashboard():
    """Run the Streamlit dashboard until the user stops it with Ctrl+C."""
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(PROJECT_ROOT), env.get("PYTHONPATH")])
    )
    log.info("Dashboard starting, press Ctrl+C to stop it")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(DASHBOARD_FILE)],
        cwd=PROJECT_ROOT,
        env=env,
    )
    try:
        code = proc.wait()
    except KeyboardInterrupt:
        # Ctrl+C reaches the dashboard process too; give it a moment to shut down.
        log.info("Stopping the dashboard")
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            proc.terminate()
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
        return
    if code != 0:
        raise RuntimeError(f"Dashboard exited with code {code}")
    log.info("Dashboard stopped")


def run_pipeline(ml=True, dashboard=True):
    check_environment(ml=ml, dashboard=dashboard)

    # Import every ETL stage module before running any stage. Importing runs
    # nothing, but a broken import is caught here, before the source ETL
    # rebuilds the source database.
    sales = importlib.import_module("src.sales")
    source_etl = importlib.import_module("src.ETL")
    dwh_etl = importlib.import_module("src.dwh_etl")

    log.info(
        "Targets: host=%s source_db=%s dwh_db=%s",
        os.getenv("DB_HOST"),
        os.getenv("SOURCE_DB_NAME"),
        os.getenv("DWH_DB_NAME"),
    )

    data_started = time.perf_counter()
    tables = run_stage("prepare_data", sales.main)
    run_stage("source_etl", source_etl.main, tables)
    run_stage("dwh_etl", dwh_etl.main)
    if ml:
        run_stage("predictions", run_predictions)
    else:
        log.info("Stage 'predictions' skipped (--skip-ml)")
    log.info("All data stages completed in %.1fs", time.perf_counter() - data_started)

    if dashboard:
        launch_dashboard()
    else:
        log.info("Dashboard not launched (--no-dashboard)")


def parse_args(argv):
    parser = argparse.ArgumentParser(
        description="Run the SalesFlow pipeline: ETL, data warehouse, predictions, dashboard."
    )
    parser.add_argument(
        "--skip-ml", action="store_true",
        help="skip the Spark prediction stage (the dashboard then shows the last forecast)",
    )
    parser.add_argument(
        "--no-dashboard", action="store_true",
        help="do not launch the Streamlit dashboard at the end",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or [])
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    started = time.perf_counter()
    log.info("Pipeline started")

    try:
        run_pipeline(ml=not args.skip_ml, dashboard=not args.no_dashboard)
    except KeyboardInterrupt:
        log.error("Pipeline interrupted, remaining stages skipped")
        return 130
    except Exception as exc:
        log.error("Pipeline FAILED (%s: %s), remaining stages skipped", type(exc).__name__, exc)
        return 1

    log.info("Pipeline finished successfully in %.1fs", time.perf_counter() - started)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))