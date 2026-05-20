import asyncio
import logging
from dataclasses import dataclass

from telegram.ext import Application

from db_service import (
    get_queued_jobs,
    recover_processing_jobs,
    update_job_status,
)


logger = logging.getLogger("ai_video_bot.queue")


@dataclass(frozen=True)
class VideoJob:
    job_id: str
    telegram_user_id: int
    chat_id: int
    topic: str
    quality: str
    required_credits: int
    created_at: str


VIDEO_JOB_QUEUE: asyncio.Queue[VideoJob] | None = None
_ENQUEUED_JOB_IDS: set[str] = set()
_JOB_PROCESSOR = None


def _get_queue(max_queue_size: int = 100) -> asyncio.Queue[VideoJob]:
    global VIDEO_JOB_QUEUE
    if VIDEO_JOB_QUEUE is None:
        VIDEO_JOB_QUEUE = asyncio.Queue(maxsize=max_queue_size)
    return VIDEO_JOB_QUEUE


def _from_db_job(job) -> VideoJob | None:
    if job.chat_id is None:
        logger.warning("queued_job_missing_chat_id job_id=%s", job.job_id)
        update_job_status(
            job.job_id,
            "failed",
            error_message="Cannot recover queued job: missing chat_id.",
        )
        return None

    return VideoJob(
        job_id=job.job_id,
        telegram_user_id=job.telegram_user_id,
        chat_id=job.chat_id,
        topic=job.topic,
        quality=job.quality,
        required_credits=job.required_credits,
        created_at=job.created_at,
    )


async def enqueue_video_job(job: VideoJob) -> None:
    queue = _get_queue()
    if job.job_id in _ENQUEUED_JOB_IDS:
        logger.info("job_already_enqueued job_id=%s", job.job_id)
        return

    queue.put_nowait(job)
    _ENQUEUED_JOB_IDS.add(job.job_id)
    logger.info(
        "job_enqueued job_id=%s user_id=%s queue_size=%s",
        job.job_id,
        job.telegram_user_id,
        queue.qsize(),
    )


async def video_worker(app: Application, worker_id: int) -> None:
    queue = _get_queue()
    logger.info("video_worker_started worker_id=%s", worker_id)

    while True:
        job = await queue.get()
        _ENQUEUED_JOB_IDS.discard(job.job_id)

        try:
            logger.info(
                "video_worker_job_picked worker_id=%s job_id=%s user_id=%s",
                worker_id,
                job.job_id,
                job.telegram_user_id,
            )
            if _JOB_PROCESSOR is None:
                update_job_status(
                    job.job_id,
                    "failed",
                    error_message="Video worker processor is not configured.",
                )
                logger.error("video_worker_processor_missing job_id=%s", job.job_id)
                continue

            await _JOB_PROCESSOR(app, job, worker_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception(
                "video_worker_job_crashed worker_id=%s job_id=%s error=%s",
                worker_id,
                job.job_id,
                exc,
            )
            update_job_status(job.job_id, "failed", error_message=str(exc))
        finally:
            queue.task_done()


async def _recover_and_enqueue_jobs() -> None:
    recovered_count = recover_processing_jobs()
    if recovered_count:
        logger.warning("processing_jobs_recovered count=%s", recovered_count)

    for db_job in get_queued_jobs(limit=10_000):
        queue_job = _from_db_job(db_job)
        if queue_job:
            try:
                await enqueue_video_job(queue_job)
            except asyncio.QueueFull:
                logger.warning("queue_full_during_recovery job_id=%s", queue_job.job_id)
                break


async def start_video_workers(
    app: Application,
    worker_count: int = 2,
    processor=None,
    max_queue_size: int = 100,
) -> None:
    global _JOB_PROCESSOR
    _JOB_PROCESSOR = processor
    _get_queue(max_queue_size)

    await _recover_and_enqueue_jobs()

    for worker_id in range(1, worker_count + 1):
        asyncio.create_task(
            video_worker(app, worker_id),
            name=f"video_worker_{worker_id}",
        )

    logger.info("Video workers started: %s", worker_count)
