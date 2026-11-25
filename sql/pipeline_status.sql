-- One row per (DAG run, stage). Written by the Airflow tasks (src/pipeline_stages.py),
-- read by the dashboard to know which run it is looking at and whether it is ready.
CREATE TABLE IF NOT EXISTS pipeline_run_status (
    run_id      TEXT        NOT NULL,
    stage       TEXT        NOT NULL,
    status      TEXT        NOT NULL CHECK (status IN ('running', 'success', 'failed')),
    started_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,
    message     TEXT,
    PRIMARY KEY (run_id, stage)
);
