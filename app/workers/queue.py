"""RQ queue setup — shared by API (enqueue) and worker (dequeue)."""

import redis
from rq import Queue

from app.settings import settings

_redis_conn: redis.Redis | None = None
_queue: Queue | None = None


def get_redis() -> redis.Redis:
    global _redis_conn
    if _redis_conn is None:
        _redis_conn = redis.from_url(settings.redis_url)
    return _redis_conn


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = Queue(settings.rq_queue_name, connection=get_redis())
    return _queue


def enqueue_invoice_processing(invoice_id: str) -> str:
    """
    Enqueue the invoice processing pipeline job.
    Returns the job ID for status tracking.
    """
    from app.workers.invoice_pipeline import process_invoice  # avoid circular import

    job = get_queue().enqueue(
        process_invoice,
        args=(invoice_id,),
        job_timeout=300,  # 5 minutes max per invoice
        result_ttl=3600,  # keep result for 1 hour
        failure_ttl=86400,  # keep failed job info for 24 hours
    )
    return job.id
