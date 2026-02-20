"""
Batch Processing Service - Handle multiple videos simultaneously

This service allows the same message to be embedded into several videos
concurrently, or different messages into different videos, all submitted
as a single batch job.

Architecture:
  - BatchService holds an in-memory dict of all active/completed batches.
  - Each batch contains a list of BatchJob dataclass instances.
  - start_batch() uses a ThreadPoolExecutor (up to max_workers=4 threads)
    so multiple jobs run in parallel.
  - A threading.Lock protects shared state updates so progress counters
    remain consistent when multiple threads complete simultaneously.

Why in-memory storage?
  For simplicity in development/demo deployments.  A production system
  would store batch state in Redis or a database so it survives worker
  restarts and scales across multiple processes.

Usage pattern:
  batch_id = batch_service.create_batch([...job configs...])
  batch_service.start_batch(batch_id, output_folder)
  status = batch_service.get_batch_status(batch_id)
"""

import os
import uuid
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class BatchStatus(Enum):
    """Possible states for a batch or individual job."""
    PENDING = "pending"        # Not yet started
    PROCESSING = "processing"  # Currently running
    COMPLETED = "completed"    # Finished (may include partial failures)
    FAILED = "failed"          # All jobs failed
    CANCELLED = "cancelled"    # Manually cancelled before completion


@dataclass
class BatchJob:
    """Represents a single embedding job within a batch.

    Uses a dataclass for convenient attribute access and repr output.
    All fields are set at creation time; status, progress, result, and
    error are updated as the job runs.
    """
    job_id: str
    video_path: str
    message: str
    password: str
    frames: List[int]
    encryption_strength: str
    cipher_mode: str
    status: BatchStatus
    progress: int             # 0-100 percentage
    result: Optional[Dict]    # Set on success
    error: Optional[str]      # Set on failure


class BatchService:
    """Service for batch processing multiple videos."""

    def __init__(self, max_workers: int = 4):
        # Maximum number of concurrent embedding threads.
        # Kept at 4 to avoid saturating CPU and memory on typical hardware.
        self.max_workers = max_workers

        # In-memory storage: batch_id -> batch dict.
        self.batches: Dict[str, Dict] = {}

        # Lock to serialise updates to shared batch state from multiple threads.
        self._lock = threading.Lock()

    def create_batch(self, jobs_config: List[Dict]) -> str:
        """Create a new batch of embedding jobs.

        Constructs BatchJob objects from the provided config dicts and
        stores the batch in memory.  The batch is in PENDING state until
        start_batch() is called.

        Args:
            jobs_config: List of dicts, each with keys:
                video_path, message, password, frames (optional),
                encryption_strength (optional, default 'AES-256'),
                cipher_mode (optional, default 'GCM')

        Returns:
            Unique batch_id string used to reference this batch
        """
        batch_id = str(uuid.uuid4())

        jobs = []
        for config in jobs_config:
            job = BatchJob(
                job_id=str(uuid.uuid4()),
                video_path=config['video_path'],
                message=config['message'],
                password=config['password'],
                frames=config.get('frames', []),
                encryption_strength=config.get('encryption_strength', 'AES-256'),
                cipher_mode=config.get('cipher_mode', 'GCM'),
                status=BatchStatus.PENDING,
                progress=0,
                result=None,
                error=None
            )
            jobs.append(job)

        # Acquire lock before writing to shared state.
        with self._lock:
            self.batches[batch_id] = {
                'batch_id': batch_id,
                'jobs': jobs,
                'total_jobs': len(jobs),
                'completed_jobs': 0,
                'failed_jobs': 0,
                'status': BatchStatus.PENDING,
                'progress': 0
            }

        return batch_id

    def start_batch(self, batch_id: str, output_folder: str,
                   progress_callback: Optional[Callable] = None) -> Dict:
        """Start processing a batch of embedding jobs.

        Submits all jobs to a ThreadPoolExecutor and waits for them to
        complete.  as_completed() iterates futures as they finish, so
        progress updates are delivered promptly rather than in submission order.

        Batch final status logic:
          - All jobs failed  -> FAILED
          - Some jobs failed -> COMPLETED (partial success, user sees which failed)
          - All jobs succeed -> COMPLETED

        Args:
            batch_id: ID of the batch to process
            output_folder: Directory to save processed output videos
            progress_callback: Optional fn(progress%, step_str) for UI updates

        Returns:
            Batch status dictionary (same as get_batch_status())
        """
        if batch_id not in self.batches:
            raise ValueError(f"Batch {batch_id} not found")

        batch = self.batches[batch_id]
        batch['status'] = BatchStatus.PROCESSING

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}

            # Submit each job to the thread pool.
            for job in batch['jobs']:
                future = executor.submit(
                    self._process_single_job,
                    job,
                    output_folder,
                    # Capture job_id in a default argument to avoid closure issues
                    # inside the loop (each lambda must reference its own job_id).
                    lambda p, s, jid=job.job_id: self._update_job_progress(
                        batch_id, jid, p, s, progress_callback
                    )
                )
                futures[future] = job

            # Process results as each job completes.
            for future in as_completed(futures):
                job = futures[future]
                try:
                    result = future.result()
                    job.result = result
                    job.status = BatchStatus.COMPLETED
                    batch['completed_jobs'] += 1
                except Exception as e:
                    job.error = str(e)
                    job.status = BatchStatus.FAILED
                    batch['failed_jobs'] += 1

                # Recalculate overall batch progress after each job finishes.
                total = batch['total_jobs']
                done = batch['completed_jobs'] + batch['failed_jobs']
                batch['progress'] = int((done / total) * 100)

                if progress_callback:
                    progress_callback(batch['progress'], f"Job {done}/{total} complete")

        # Determine overall batch outcome.
        if batch['failed_jobs'] == batch['total_jobs']:
            batch['status'] = BatchStatus.FAILED
        elif batch['failed_jobs'] > 0:
            # Partial success: at least one job succeeded.
            batch['status'] = BatchStatus.COMPLETED
        else:
            batch['status'] = BatchStatus.COMPLETED

        return self.get_batch_status(batch_id)

    def _process_single_job(self, job: BatchJob, output_folder: str,
                           progress_callback: Callable) -> Dict:
        """Process a single embedding job in the batch.

        Runs the full embed pipeline (encrypt -> read frames -> embed -> write)
        for one video.  Called from a thread pool worker, so it must be
        thread-safe with respect to the job's mutable fields.

        Returns a result dict with output_file_id, bits_embedded, and frames_used.
        """
        from app.services import CryptoService, VideoService, SteganographyService

        job.status = BatchStatus.PROCESSING

        # Step 1: Encrypt the message.
        progress_callback(10, "Encrypting...")
        encrypted_data, _ = CryptoService.encrypt(
            job.message, job.password,
            job.encryption_strength, job.cipher_mode
        )

        # Step 2: Read the target frames from the video.
        progress_callback(30, "Reading frames...")
        frame_data = VideoService.read_frames(job.video_path, job.frames)

        # Step 3: Embed the encrypted data into the frame LSBs.
        progress_callback(50, "Embedding...")
        result = SteganographyService.embed_message(frame_data, encrypted_data)

        # Step 4: Write the modified frames back to a new video file.
        progress_callback(70, "Writing video...")
        output_id = str(uuid.uuid4())
        output_path = os.path.join(output_folder, f"{output_id}_output.mp4")
        VideoService.write_video(output_path, result['modified_frames'], job.video_path)

        progress_callback(100, "Complete")

        return {
            'success': True,
            'output_file_id': output_id,
            'bits_embedded': result['bits_embedded'],
            'frames_used': result['frames_used']
        }

    def _update_job_progress(self, batch_id: str, job_id: str,
                            progress: int, step: str,
                            callback: Optional[Callable]):
        """Update progress for a specific job within a batch.

        Finds the job by ID in the batch's job list and updates its
        progress field.  Also forwards the update to the batch-level
        callback so the UI can show per-job progress.
        """
        if batch_id in self.batches:
            batch = self.batches[batch_id]
            for job in batch['jobs']:
                if job.job_id == job_id:
                    job.progress = progress
                    break

        if callback:
            callback(progress, f"Job {job_id}: {step}")

    def get_batch_status(self, batch_id: str) -> Dict:
        """Get the current status of a batch and all its jobs.

        Returns a serialisable dict (no Enum objects) suitable for JSON
        responses.  Each job entry includes its status, progress, result,
        and any error message.

        Args:
            batch_id: ID of the batch to query

        Returns:
            Dict with batch-level stats and a 'jobs' list
        """
        if batch_id not in self.batches:
            raise ValueError(f"Batch {batch_id} not found")

        batch = self.batches[batch_id]

        return {
            'batch_id': batch_id,
            'status': batch['status'].value,
            'total_jobs': batch['total_jobs'],
            'completed_jobs': batch['completed_jobs'],
            'failed_jobs': batch['failed_jobs'],
            'progress': batch['progress'],
            'jobs': [
                {
                    'job_id': job.job_id,
                    'status': job.status.value,
                    'progress': job.progress,
                    'result': job.result,
                    'error': job.error
                }
                for job in batch['jobs']
            ]
        }

    def cancel_batch(self, batch_id: str) -> bool:
        """Cancel a batch that is currently processing.

        Sets the batch status to CANCELLED.  Note: this does not
        interrupt already-running thread pool futures; it only marks
        the batch so callers can distinguish a cancelled batch from
        a failed one.  In-flight jobs will still complete.

        Args:
            batch_id: ID of the batch to cancel

        Returns:
            True if the batch was successfully cancelled, False otherwise
        """
        if batch_id in self.batches:
            batch = self.batches[batch_id]
            if batch['status'] == BatchStatus.PROCESSING:
                batch['status'] = BatchStatus.CANCELLED
                return True
        return False


# Module-level singleton instance.
# Most of the application uses this shared instance so batch state is
# preserved across requests within the same process lifetime.
batch_service = BatchService()
