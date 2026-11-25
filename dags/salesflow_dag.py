"""SalesFlow pipeline.

    validate_sales_csv -> source_etl -> validate_source_db -> dwh_etl -> validate_dwh
        -> [ build_views , predictions ]  (parallel)  -> pipeline_complete

Every task runs one stage of src/pipeline_stages.py inside the project's own Python
environment (/home/airflow/salesflow-venv, built from requirements-pipeline.txt), so
the project's pinned pandas / SQLAlchemy / PySpark versions are used exactly as
tested and never have to agree with Airflow's own dependency constraints.

The Streamlit dashboard is NOT part of this DAG: it is its own Docker service.

Trigger it manually (schedule=None): the source is a CSV file, not a feed.
The stages report to the table pipeline_run_status in the warehouse using the
Airflow run id, which is how the dashboard knows which run it is showing.
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_DIR = "/opt/airflow"
PYTHON = "/home/airflow/salesflow-venv/bin/python"

default_args = {
    "owner": "salesflow",
    # No automatic retries: source_etl drops and rebuilds the source tables, so a failure
    # should be read and fixed, not repeated blindly.
    "retries": 0,
    "execution_timeout": timedelta(minutes=30),
}


def stage(task_id, **kwargs):
    return BashOperator(
        task_id=task_id,
        # run_id is passed to the stage so its status rows and staging folder belong to this run
        bash_command=f"{PYTHON} -m src.pipeline_stages {task_id} --run-id '{{{{ run_id }}}}'",
        cwd=PROJECT_DIR,
        append_env=True,  # keep the container's DB_* variables
        env={"PYTHONPATH": PROJECT_DIR},
        **kwargs,
    )


with DAG(
    dag_id="salesflow_pipeline",
    description="CSV -> source DB -> data warehouse -> analytics views + forecast",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    default_args=default_args,
    tags=["salesflow"],
    doc_md=__doc__,
) as dag:
    validate_sales_csv = stage("validate_sales_csv")
    source_etl = stage("source_etl")
    validate_source_db = stage("validate_source_db")
    dwh_etl = stage("dwh_etl")
    validate_dwh = stage("validate_dwh")
    build_views = stage("build_views")
    predictions = stage("predictions", execution_timeout=timedelta(hours=1))
    # default trigger rule (all_success): runs only if BOTH branches succeeded
    pipeline_complete = stage("pipeline_complete")

    validate_sales_csv >> source_etl >> validate_source_db >> dwh_etl >> validate_dwh
    validate_dwh >> [build_views, predictions] >> pipeline_complete
