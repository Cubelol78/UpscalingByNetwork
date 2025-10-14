"""
Batch processor for handling multiple concurrent batches
"""

import asyncio
import logging
from typing import Dict, Any, Optional, List
from pathlib import Path


class BatchProcessor:
    """Handle multiple batch processing tasks"""

    def __init__(self, processor, max_concurrent: int = 1):
        self.processor = processor
        self.max_concurrent = max_concurrent
        self.logger = logging.getLogger(__name__)

        # Active batches
        self.active_batches: Dict[str, asyncio.Task] = {}
        self.batch_queue: asyncio.Queue = asyncio.Queue()
        self.processing_lock = asyncio.Semaphore(max_concurrent)

        # Statistics
        self.stats = {
            "total_batches": 0,
            "completed_batches": 0,
            "failed_batches": 0,
            "queued_batches": 0,
        }

    async def submit_batch(
        self, batch_data: bytes, batch_id: str, batch_config: Dict[str, Any]
    ) -> asyncio.Task:
        """
        Submit batch for processing

        Args:
            batch_data: Encrypted batch data
            batch_id: Batch identifier
            batch_config: Configuration

        Returns:
            Async task for the batch
        """
        self.stats["total_batches"] += 1
        self.stats["queued_batches"] += 1

        task = asyncio.create_task(
            self._process_batch_with_semaphore(batch_data, batch_id, batch_config)
        )

        self.active_batches[batch_id] = task
        return task

    async def _process_batch_with_semaphore(
        self, batch_data: bytes, batch_id: str, batch_config: Dict[str, Any]
    ):
        """Process batch with concurrency control"""
        async with self.processing_lock:
            self.stats["queued_batches"] -= 1

            try:
                result = await self.processor.process_batch(
                    batch_data, batch_id, batch_config
                )

                if result:
                    self.stats["completed_batches"] += 1
                else:
                    self.stats["failed_batches"] += 1

                return result

            except Exception as e:
                self.logger.error(f"Error processing batch {batch_id}: {e}")
                self.stats["failed_batches"] += 1
                return None

            finally:
                if batch_id in self.active_batches:
                    del self.active_batches[batch_id]

    def get_active_batches(self) -> List[str]:
        """Get list of active batch IDs"""
        return list(self.active_batches.keys())

    def is_processing(self) -> bool:
        """Check if any batches are being processed"""
        return len(self.active_batches) > 0

    def get_stats(self) -> Dict[str, Any]:
        """Get batch processor statistics"""
        return {
            **self.stats,
            "active_batches": len(self.active_batches),
            "max_concurrent": self.max_concurrent,
        }
