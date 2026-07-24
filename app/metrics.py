"""
Prometheus Metrics - App-level instrumentation for embed/extract pipelines

Exposes a plain-text /metrics endpoint (registered in routes.py on main_bp,
NOT api_bp, so it lands at the root path Fly's managed Prometheus scraper
and most external Prometheus configs expect by default).

Instruments run_embed_pipeline / run_extract_pipeline in tasks.py so both
the Celery async path and the synchronous fallback report identical metrics
(same rule as any other pipeline behavior: it lives in the shared pipeline
function, never duplicated into the Celery task body).

gunicorn runs with a single worker (-w 1, --threads 4) in this app's
Dockerfile, so a plain in-process CollectorRegistry is safe here — the
usual multiprocess-mode workaround for multi-worker gunicorn is not needed.
If that ever changes, see prometheus_client's multiprocess docs.
"""

import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram, CONTENT_TYPE_LATEST, generate_latest

# Buckets tuned for embed/extract jobs, which run seconds-to-low-minutes for
# the video sizes this app targets (480p-1440p, capped at MAX_UPLOAD_MB).
PIPELINE_DURATION_SECONDS = Histogram(
    'vidstega_pipeline_duration_seconds',
    'Time spent in the embed/extract pipeline, by operation and outcome',
    ['operation', 'status'],
    buckets=(0.5, 1, 2.5, 5, 10, 30, 60, 120, 300, 600),
)

PIPELINE_RUNS_TOTAL = Counter(
    'vidstega_pipeline_runs_total',
    'Number of embed/extract pipeline runs, by operation and outcome',
    ['operation', 'status'],
)

ECC_SYMBOLS_USED = Histogram(
    'vidstega_ecc_symbols_used',
    'Reed-Solomon ecc_symbols value used per embed/extract call',
    ['operation'],
    buckets=(2, 5, 10, 15, 20, 25, 30),
)


@contextmanager
def track_pipeline(operation: str, ecc_symbols: int = None):
    """Time a pipeline run and record its outcome.

    Usage:
        with track_pipeline('embed', ecc_symbols=ecc_symbols):
            ... pipeline body ...

    Re-raises any exception from the wrapped block after recording it as a
    'failure' outcome, so callers keep their existing error handling.
    """
    start = time.time()
    status = 'success'
    try:
        yield
    except Exception:
        status = 'failure'
        raise
    finally:
        PIPELINE_DURATION_SECONDS.labels(operation=operation, status=status).observe(time.time() - start)
        PIPELINE_RUNS_TOTAL.labels(operation=operation, status=status).inc()
        if ecc_symbols is not None:
            ECC_SYMBOLS_USED.labels(operation=operation).observe(ecc_symbols)


def render_metrics():
    """Return (body, content_type) for the /metrics endpoint."""
    return generate_latest(), CONTENT_TYPE_LATEST
