"""
RQ queue setup — shared by API (enqueue) and worker (dequeue).

Three named queues processed in priority order by the worker:
  high    — urgent / carrier-escalated invoices
  default — normal invoice uploads
  low     — background tasks (seed-demo, reprocessing)

Worker start command:  rq worker high default low --url $REDIS_URL

File bytes for invoice jobs travel through Redis with the job args, so the
worker service requires no shared disk with the web service.
"""

import redis
from rq import Queue
from rq.job import Job, Retry
from rq.registry import FailedJobRegistry

from app.settings import settings

# ── Queue name constants ───────────────────────────────────────────────────────

QUEUE_HIGH = "high"
QUEUE_DEFAULT = "default"
QUEUE_LOW = "low"

_VALID_PRIORITIES = {QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW}

# ── Redis singleton ────────────────────────────────────────────────────────────

_redis_conn: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = redis.from_url(settings.redis_url)
    return _redis_conn


def get_queue(priority: str = QUEUE_DEFAULT) -> Queue:
    """Return the Queue for the given priority name."""
    if priority not in _VALID_PRIORITIES:
        raise ValueError(
            f"Invalid queue priority {priority!r}. "
            f"Must be one of: {sorted(_VALID_PRIORITIES)}"
        )
    return Queue(priority, connection=get_redis())


# ── Invoice processing ─────────────────────────────────────────────────────────


def enqueue_invoice_processing(
    invoice_id: str,
    file_bytes: bytes,
    filename: str,
    priority: str = QUEUE_DEFAULT,
) -> str:
    """
    Enqueue invoice processing as a background job.

    File bytes are passed directly through Redis with the job — no shared
    disk is required between the web and worker services. Typical CSV invoices
    are well under 1 MB so this adds negligible Redis pressure.

    Automatic retry: up to 3 attempts at 30 s / 60 s / 5 min intervals before
    the job lands in the FailedJobRegistry (DLQ).

    Args:
        invoice_id: String UUID of the Invoice row.
        file_bytes: Raw bytes of the uploaded file (already in memory).
        filename:   Original filename for format detection in the worker.
        priority:   Queue name — QUEUE_HIGH | QUEUE_DEFAULT | QUEUE_LOW.

    Returns:
        The RQ job ID string (store on Invoice.job_id for DLQ tracking).
    """
    from app.workers.invoice_pipeline import process_invoice  # avoid circular import

    job = get_queue(priority).enqueue(
        process_invoice,
        args=(invoice_id, file_bytes, filename),
        job_timeout=300,  # 5 minutes max per invoice
        result_ttl=3_600,  # keep successful result 1 hour
        failure_ttl=7 * 86_400,  # keep failed job info 7 days for DLQ review
        retry=Retry(max=3, interval=[30, 60, 300]),
    )
    return job.id


# ── Background / low-priority ─────────────────────────────────────────────────


def enqueue_seed_demo(carrier_id: str, clean: bool = False) -> str:
    """
    Enqueue the synthetic data seeder as a background job on the low queue.
    Returns the job ID for status polling.
    """
    from app.workers.seed_worker import run_seed  # avoid circular import

    job = get_queue(QUEUE_LOW).enqueue(
        run_seed,
        kwargs={"carrier_id": carrier_id, "clean": clean},
        job_timeout=600,  # 10 minutes — seeder makes ~56 Claude calls
        result_ttl=3_600,
        failure_ttl=86_400,
    )
    return job.id


# ── DLQ helpers ───────────────────────────────────────────────────────────────


def get_failed_jobs(limit: int = 100) -> list[dict]:
    """
    Return summary dicts for jobs in the FailedJobRegistry across all queues.
    Used by the admin DLQ endpoint.
    """
    conn = get_redis()
    result: list[dict] = []

    for queue_name in (QUEUE_HIGH, QUEUE_DEFAULT, QUEUE_LOW):
        registry = FailedJobRegistry(queue=Queue(queue_name, connection=conn))
        for job_id in registry.get_job_ids()[:limit]:
            try:
                job = Job.fetch(job_id, connection=conn)
                result.append(
                    {
                        "job_id": job_id,
                        "queue": queue_name,
                        "enqueued_at": (
                            job.enqueued_at.isoformat() if job.enqueued_at else None
                        ),
                        "failed_at": (
                            job.ended_at.isoformat() if job.ended_at else None
                        ),
                        "exc_info": (str(job.exc_info) or "")[:500],
                        # First arg is invoice_id; skip file_bytes (too large to log)
                        "invoice_id": job.args[0] if job.args else None,
                        "retries_left": job.retries_left,
                    }
                )
            except Exception:
                result.append(
                    {"job_id": job_id, "queue": queue_name, "error": "could not fetch"}
                )

    return result


def retry_failed_job(job_id: str) -> str:
    """
    Re-enqueue a failed job from the DLQ.

    The job is re-created with the same function and args on the same queue
    as the original. A fresh Retry budget is attached.

    Returns the new job ID.
    """
    conn = get_redis()
    job = Job.fetch(job_id, connection=conn)
    origin_queue = job.origin or QUEUE_DEFAULT

    new_job = get_queue(origin_queue).enqueue(
        job.func,
        args=job.args,
        kwargs=job.kwargs,
        job_timeout=300,
        result_ttl=3_600,
        failure_ttl=7 * 86_400,
        retry=Retry(max=3, interval=[30, 60, 300]),
    )
    return new_job.id
