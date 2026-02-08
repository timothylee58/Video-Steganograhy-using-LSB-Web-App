"""
Batch Processing Service - Handle multiple videos simultaneously
"""

import os
import uuid
from typing import List, Dict, Optional, Callable
from dataclasses import dataclass
from enum import Enum
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


class BatchStatus(Enum):
    """Batch job status."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class BatchJob:
    """Represents a single job in a batch."""
    job_id: str
    video_path: str
    message: str
    password: str
    frames: List[int]
    encryption_strength: str
    cipher_mode: str
    status: BatchStatus
    progress: int
    result: Optional[Dict]
    error: Optional[str]


class BatchService:
    """Service for batch processing multiple videos."""
    
    def __init__(self, max_workers: int = 4):
        self.max_workers = max_workers
        self.batches: Dict[str, Dict] = {}
        self._lock = threading.Lock()
    
    def create_batch(self, jobs_config: List[Dict]) -> str:
        """
        Create a new batch of embedding jobs.
        
        Args:
            jobs_config: List of job configurations
            
        Returns:
            Batch ID
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
        """
        Start processing a batch of jobs.
        
        Args:
            batch_id: Batch ID to process
            output_folder: Output folder for processed videos
            progress_callback: Optional callback for progress updates
            
        Returns:
            Batch result dictionary
        """
        if batch_id not in self.batches:
            raise ValueError(f"Batch {batch_id} not found")
        
        batch = self.batches[batch_id]
        batch['status'] = BatchStatus.PROCESSING
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {}
            
            for job in batch['jobs']:
                future = executor.submit(
                    self._process_single_job,
                    job,
                    output_folder,
                    lambda p, s, jid=job.job_id: self._update_job_progress(
                        batch_id, jid, p, s, progress_callback
                    )
                )
                futures[future] = job
            
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
                
                # Update batch progress
                total = batch['total_jobs']
                done = batch['completed_jobs'] + batch['failed_jobs']
                batch['progress'] = int((done / total) * 100)
                
                if progress_callback:
                    progress_callback(batch['progress'], f"Job {done}/{total} complete")
        
        # Final status
        if batch['failed_jobs'] == batch['total_jobs']:
            batch['status'] = BatchStatus.FAILED
        elif batch['failed_jobs'] > 0:
            batch['status'] = BatchStatus.COMPLETED  # Partial success
        else:
            batch['status'] = BatchStatus.COMPLETED
        
        return self.get_batch_status(batch_id)
    
    def _process_single_job(self, job: BatchJob, output_folder: str,
                           progress_callback: Callable) -> Dict:
        """Process a single job in the batch."""
        from app.services import CryptoService, VideoService, SteganographyService
        
        job.status = BatchStatus.PROCESSING
        
        # Encrypt message
        progress_callback(10, "Encrypting...")
        encrypted_data, _ = CryptoService.encrypt(
            job.message, job.password,
            job.encryption_strength, job.cipher_mode
        )
        
        # Read frames
        progress_callback(30, "Reading frames...")
        frame_data = VideoService.read_frames(job.video_path, job.frames)
        
        # Embed message
        progress_callback(50, "Embedding...")
        result = SteganographyService.embed_message(frame_data, encrypted_data)
        
        # Write output
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
        """Update progress for a specific job."""
        if batch_id in self.batches:
            batch = self.batches[batch_id]
            for job in batch['jobs']:
                if job.job_id == job_id:
                    job.progress = progress
                    break
        
        if callback:
            callback(progress, f"Job {job_id}: {step}")
    
    def get_batch_status(self, batch_id: str) -> Dict:
        """Get current status of a batch."""
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
        """Cancel a batch processing job."""
        if batch_id in self.batches:
            batch = self.batches[batch_id]
            if batch['status'] == BatchStatus.PROCESSING:
                batch['status'] = BatchStatus.CANCELLED
                return True
        return False


# Global batch service instance
batch_service = BatchService()
