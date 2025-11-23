import unittest
from unittest.mock import MagicMock, AsyncMock, patch
import asyncio
import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db import Base, User, Job, JobStatus, SequenceTemplate, GlobalState
from src.drip_logic import initiate_drip_campaign, job_runner_tick, send_paced_message_callback
from src.messages import generate_default_sequence
from telegram.error import RetryAfter, Forbidden

# Use in-memory SQLite for testing
TEST_DB_URL = "sqlite:///:memory:"

class TestJulesCommand(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.engine = create_engine(TEST_DB_URL, connect_args={'check_same_thread': False})
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Patch get_db_sync to use our test db
        self.db_patcher = patch('src.drip_logic.get_db_sync', side_effect=self.get_test_db)
        self.mock_get_db = self.db_patcher.start()

        # Patch asyncio loop to run executors synchronously
        self.loop_patcher = patch('asyncio.get_running_loop')
        self.mock_loop_cls = self.loop_patcher.start()

        # Configure the mock loop to run the function immediately
        self.mock_loop = MagicMock()
        self.mock_loop.run_in_executor.side_effect = lambda executor, func, *args: asyncio.Future()
        # Wait, run_in_executor returns a future. If I want it sync, I should return a completed future or just the result?
        # In the code: await loop.run_in_executor(...)
        # So it must awaitable.

        async def mock_run_in_executor(executor, func, *args):
            return func(*args)

        self.mock_loop.run_in_executor.side_effect = mock_run_in_executor
        self.mock_loop_cls.return_value = self.mock_loop

    def tearDown(self):
        self.db_patcher.stop()
        self.loop_patcher.stop()
        Base.metadata.drop_all(self.engine)

    def get_test_db(self):
        return self.SessionLocal()

    async def test_initiate_drip_campaign_injection(self):
        """Test that 100 jobs are correctly injected into the database."""
        user_id = 123456789

        # Mock Context
        context = MagicMock()

        # Execute injection
        await initiate_drip_campaign(user_id, "SEQ_100_STEP_ALPHA", context)

        db = self.SessionLocal()

        # Verify User created
        user = db.query(User).filter(User.target_chat_id == user_id).first()
        self.assertIsNotNone(user)
        self.assertEqual(user.sequence_template_id, "SEQ_100_STEP_ALPHA")

        # Verify Jobs
        jobs = db.query(Job).filter(Job.user_id == user_id).all()
        self.assertEqual(len(jobs), 100)

        db.close()

    @patch('src.drip_logic.send_paced_message_callback')
    async def test_job_runner_tick(self, mock_callback):
        """Test that the runner picks up due jobs."""
        user_id = 999
        db = self.SessionLocal()

        # Create a job that is DUE (past timestamp)
        past_time = datetime.datetime.now() - datetime.timedelta(minutes=10)
        job = Job(
            user_id=user_id,
            message_index=1,
            content_payload='{"text": "test"}',
            scheduled_timestamp=past_time,
            status=JobStatus.QUEUED
        )
        db.add(job)
        db.commit()
        job_id = job.job_id
        db.close()

        # Mock Context
        context = MagicMock()
        context.job_queue.run_once = MagicMock()

        await job_runner_tick(context)

        # Verify that run_once was called
        context.job_queue.run_once.assert_called_once()
        args, kwargs = context.job_queue.run_once.call_args
        self.assertEqual(kwargs['data']['job_id'], job_id)

    @patch('src.drip_logic.track_message_sent')
    async def test_send_paced_message_execution(self, mock_track):
        """Test the actual sending logic and state update."""
        user_id = 888
        db = self.SessionLocal()

        # Create User
        user = User(target_chat_id=user_id, status="ACTIVE")
        db.add(user)

        # Create Job
        job = Job(
            user_id=user_id,
            message_index=5,
            content_payload='{"text": "Hello World"}',
            scheduled_timestamp=datetime.datetime.now(),
            status=JobStatus.QUEUED
        )
        db.add(job)
        db.commit()
        job_id = job.job_id
        db.close()

        # Mock Context
        context = MagicMock()
        context.bot.send_message = AsyncMock()
        context.job.data = {"job_id": job_id}

        await send_paced_message_callback(context)

        # Verify Bot Send
        context.bot.send_message.assert_called_with(chat_id=user_id, text="Hello World", reply_markup=None)

        # Verify DB Update
        db = self.SessionLocal()
        updated_job = db.query(Job).filter(Job.job_id == job_id).first()
        updated_user = db.query(User).filter(User.target_chat_id == user_id).first()

        self.assertEqual(updated_job.status, JobStatus.SENT)
        self.assertEqual(updated_user.current_message_index, 5)

        db.close()

    async def test_global_flood_pause(self):
        """Test that global flood pause prevents job fetching."""
        db = self.SessionLocal()

        # Set Global Pause in future
        future = datetime.datetime.now() + datetime.timedelta(minutes=10)
        state = GlobalState(key="FLOOD_PAUSE_UNTIL", expires_at=future)
        db.add(state)

        # Add a due job
        job = Job(
            user_id=111,
            message_index=1,
            content_payload='{"text": "test"}',
            scheduled_timestamp=datetime.datetime.now() - datetime.timedelta(minutes=1),
            status=JobStatus.QUEUED
        )
        db.add(job)
        db.commit()
        db.close()

        context = MagicMock()
        context.job_queue.run_once = MagicMock()

        await job_runner_tick(context)

        # Should NOT call run_once because of pause
        context.job_queue.run_once.assert_not_called()

if __name__ == "__main__":
    unittest.main()
