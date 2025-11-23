import logging
import json
import datetime
import asyncio
from sqlalchemy.orm import Session
from telegram.error import RetryAfter, Forbidden
from telegram.ext import ContextTypes
from telegram import InlineKeyboardMarkup, InlineKeyboardButton

from src.db import User, Job, JobStatus, UserStatus, SequenceTemplate, GlobalState, get_db_sync
from src.analytics import track_message_sent
from src.messages import generate_default_sequence
from src.config import FLOOD_WAIT_SAFETY_MARGIN

logger = logging.getLogger(__name__)

def _initiate_drip_campaign_sync(user_id: int, sequence_template_id: str):
    """
    Synchronous implementation of DB operations for initiating campaign.
    To be run in executor.
    """
    db = get_db_sync()
    try:
        # 1. Check or Create User
        user = db.query(User).filter(User.target_chat_id == user_id).first()
        if not user:
            user = User(target_chat_id=user_id, sequence_template_id=sequence_template_id)
            db.add(user)
        elif user.status in [UserStatus.BLOCKED, UserStatus.UNSUBSCRIBED]:
            logger.warning(f"User {user_id} is blocked/unsubscribed. Skipping.")
            return 0

        # 2. Get Sequence Template
        template_msgs = db.query(SequenceTemplate).filter(SequenceTemplate.template_id == sequence_template_id).all()
        if not template_msgs:
            logger.info(f"Template {sequence_template_id} not found in DB. Loading defaults.")
            default_msgs = generate_default_sequence(sequence_template_id)
            for msg in default_msgs:
                t = SequenceTemplate(**msg)
                db.add(t)
            db.commit()
            template_msgs = db.query(SequenceTemplate).filter(SequenceTemplate.template_id == sequence_template_id).all()

        template_msgs.sort(key=lambda x: x.message_index)

        # 3. Job Queue Injection
        current_time = datetime.datetime.now()

        # Delete existing queued jobs if any (restart logic)
        existing_jobs = db.query(Job).filter(Job.user_id == user_id, Job.status == JobStatus.QUEUED).all()
        for job in existing_jobs:
            db.delete(job)

        jobs_to_schedule = []
        accumulated_delay_minutes = 0

        for msg in template_msgs:
            accumulated_delay_minutes += msg.base_delay_minutes
            scheduled_time = current_time + datetime.timedelta(minutes=accumulated_delay_minutes)

            job = Job(
                user_id=user_id,
                message_index=msg.message_index,
                content_payload=msg.content_payload,
                scheduled_timestamp=scheduled_time,
                status=JobStatus.QUEUED
            )
            db.add(job)
            jobs_to_schedule.append(job)

        db.commit()
        return len(jobs_to_schedule)

    except Exception as e:
        logger.error(f"Error initiating campaign sync: {e}")
        db.rollback()
        raise
    finally:
        db.close()

async def initiate_drip_campaign(user_id: int, sequence_template_id: str, context: ContextTypes.DEFAULT_TYPE):
    """
    Async wrapper for initiating campaign.
    """
    logger.info(f"Initiating drip campaign for user {user_id}")
    loop = asyncio.get_running_loop()
    try:
        count = await loop.run_in_executor(None, _initiate_drip_campaign_sync, user_id, sequence_template_id)
        logger.info(f"Successfully injected {count} jobs for User {user_id}.")
    except Exception as e:
        logger.error(f"Failed to initiate drip campaign: {e}")

def _fetch_due_jobs_sync(limit=50):
    """
    Fetches jobs that are due and checks for global pause.
    """
    db = get_db_sync()
    try:
        now = datetime.datetime.now()

        # Check Global Pause
        global_pause = db.query(GlobalState).filter(GlobalState.key == "FLOOD_PAUSE_UNTIL").first()
        if global_pause and global_pause.expires_at and global_pause.expires_at > now:
            logger.info("Global Flood Pause active. Skipping job fetch.")
            return []

        # Fetch jobs
        due_jobs = db.query(Job).filter(
            Job.status == JobStatus.QUEUED,
            Job.scheduled_timestamp <= now
        ).limit(limit).all()

        # Return lightweight dicts or detached objects to avoid session issues across threads
        # But for simplicity in this logic, we will just return ID and user_id to re-fetch
        return [{"job_id": j.job_id, "user_id": j.user_id} for j in due_jobs]

    finally:
        db.close()

async def job_runner_tick(context: ContextTypes.DEFAULT_TYPE):
    """
    Periodic task to fetch due jobs.
    """
    loop = asyncio.get_running_loop()
    try:
        due_jobs = await loop.run_in_executor(None, _fetch_due_jobs_sync)

        for job_data in due_jobs:
             # Schedule immediate execution
             context.job_queue.run_once(
                 send_paced_message_callback,
                 0,
                 chat_id=job_data["user_id"],
                 data={"job_id": job_data["job_id"]}
             )
    except Exception as e:
        logger.error(f"Error in job runner tick: {e}")

def _get_job_details_sync(job_id):
    db = get_db_sync()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if not job: return None

        user = db.query(User).filter(User.target_chat_id == job.user_id).first()

        # Detach or copy data
        return {
            "job_id": job.job_id,
            "status": job.status,
            "user_id": job.user_id,
            "user_status": user.status,
            "message_index": job.message_index,
            "content_payload": job.content_payload
        }
    finally:
        db.close()

def _update_job_status_sync(job_id, status: JobStatus, user_update=None):
    db = get_db_sync()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if job:
            job.status = status

            if user_update:
                user = db.query(User).filter(User.target_chat_id == job.user_id).first()
                if user:
                    for k, v in user_update.items():
                        setattr(user, k, v)
        db.commit()
    finally:
        db.close()

def _handle_flood_wait_sync(retry_after):
    """
    Sets the global pause state.
    """
    db = get_db_sync()
    try:
        pause_until = datetime.datetime.now() + datetime.timedelta(seconds=retry_after + FLOOD_WAIT_SAFETY_MARGIN)

        state = db.query(GlobalState).filter(GlobalState.key == "FLOOD_PAUSE_UNTIL").first()
        if not state:
            state = GlobalState(key="FLOOD_PAUSE_UNTIL")
            db.add(state)

        state.value = str(pause_until)
        state.expires_at = pause_until
        db.commit()
        logger.warning(f"Global Flood Pause set until {pause_until}")
    finally:
        db.close()

def _handle_blocked_user_sync(user_id):
    """
    Marks user as blocked and cancels all queued jobs.
    """
    db = get_db_sync()
    try:
        user = db.query(User).filter(User.target_chat_id == user_id).first()
        if user:
            user.status = UserStatus.BLOCKED

        jobs = db.query(Job).filter(Job.user_id == user_id, Job.status == JobStatus.QUEUED).all()
        for j in jobs:
            j.status = JobStatus.CANCELLED
        db.commit()
    finally:
        db.close()

def _reschedule_job_sync(job_id, delay_seconds):
    db = get_db_sync()
    try:
        job = db.query(Job).filter(Job.job_id == job_id).first()
        if job:
            job.scheduled_timestamp = datetime.datetime.now() + datetime.timedelta(seconds=delay_seconds)
            # Ensure it stays queued
            job.status = JobStatus.QUEUED
        db.commit()
    finally:
        db.close()

async def send_paced_message_callback(context: ContextTypes.DEFAULT_TYPE):
    """
    Callback to actually send the message.
    """
    job_data_input = context.job.data
    job_id = job_data_input.get("job_id")
    loop = asyncio.get_running_loop()

    # 1. Fetch Job Details (Async-wrapped)
    job_details = await loop.run_in_executor(None, _get_job_details_sync, job_id)

    if not job_details or job_details['status'] != JobStatus.QUEUED:
        return

    if job_details['user_status'] in [UserStatus.BLOCKED, UserStatus.UNSUBSCRIBED]:
         await loop.run_in_executor(None, _update_job_status_sync, job_id, JobStatus.CANCELLED, None)
         return

    try:
        # 2. Parse Payload
        content = json.loads(job_details['content_payload'])
        text = content.get("text")
        buttons_data = content.get("buttons")

        reply_markup = None
        if buttons_data:
            keyboard = []
            for row in buttons_data:
                k_row = []
                for btn in row:
                    # Dynamic URL Injection for Tracking
                    url = btn.get('url')
                    if url and "/tracking" in url:
                        # Append chat_id (cid) for tracking
                        separator = "&" if "?" in url else "?"
                        url = f"{url}{separator}cid={job_details['user_id']}"

                    k_row.append(InlineKeyboardButton(text=btn['text'], url=url))
                keyboard.append(k_row)
            reply_markup = InlineKeyboardMarkup(keyboard)

        # 3. Analytics (Pre-Send)
        phase = "P1" # Simplified logic for now
        if job_details['message_index'] > 10: phase = "P2"
        if job_details['message_index'] > 60: phase = "P3"
        if job_details['message_index'] > 90: phase = "P4"

        await track_message_sent(job_details['user_id'], job_details['message_index'], phase)

        # 4. Send Message
        await context.bot.send_message(chat_id=job_details['user_id'], text=text, reply_markup=reply_markup)

        # 5. Update State
        user_update = {
            "current_message_index": job_details['message_index'],
            "last_message_sent_timestamp": datetime.datetime.now()
        }
        await loop.run_in_executor(None, _update_job_status_sync, job_id, JobStatus.SENT, user_update)

    except RetryAfter as e:
        logger.warning(f"FloodWait (RetryAfter) triggered. Waiting {e.retry_after} seconds.")
        # Resilience Step 1: Set Global Pause
        await loop.run_in_executor(None, _handle_flood_wait_sync, e.retry_after)

        # Resilience Step 2: Reschedule this specific job
        # We add a bit more than the global pause to be safe
        await loop.run_in_executor(None, _reschedule_job_sync, job_id, e.retry_after + FLOOD_WAIT_SAFETY_MARGIN)

    except Forbidden:
        logger.info(f"User {job_details['user_id']} blocked bot.")
        await loop.run_in_executor(None, _handle_blocked_user_sync, job_details['user_id'])

    except Exception as e:
        logger.error(f"Failed to send message for job {job_id}: {e}")
        await loop.run_in_executor(None, _update_job_status_sync, job_id, JobStatus.FAILED_TEMP, None)
