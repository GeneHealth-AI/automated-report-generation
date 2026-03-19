"""
Batch processing infrastructure for structured protein analysis.

This module provides the BatchManager class that handles protein processing
in configurable batches with retry logic, progress tracking, and logging.
"""

import time
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Callable, TypeVar, Generic
from enum import Enum
import asyncio
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
from datetime import datetime

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


class BatchStatus(Enum):
    """Status of a batch processing operation."""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"


@dataclass
class RetryConfig:
    """Configuration for retry logic with exponential backoff."""
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 60.0
    exponential_base: float = 2.0
    jitter: bool = True  # Add random jitter to prevent thundering herd
    
    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay with exponential backoff.
        
        Args:
            attempt: Current attempt number (0-based)
            
        Returns:
            Delay in seconds
        """
        delay = min(self.base_delay * (self.exponential_base ** attempt), self.max_delay)
        
        if self.jitter:
            import random
            # Add up to 25% jitter
            jitter_amount = delay * 0.25 * random.random()
            delay += jitter_amount
            
        return delay


@dataclass
class BatchResult(Generic[R]):
    """Result of processing a single batch."""
    batch_id: str
    batch_number: int
    items: List[T]
    results: List[R]
    status: BatchStatus
    start_time: datetime
    end_time: Optional[datetime] = None
    error: Optional[Exception] = None
    retry_count: int = 0
    processing_time: Optional[float] = None
    
    def __post_init__(self):
        """Calculate processing time if end_time is set."""
        if self.end_time and self.start_time:
            self.processing_time = (self.end_time - self.start_time).total_seconds()
    
    def mark_completed(self, results: List[R]):
        """Mark batch as completed with results."""
        self.results = results
        self.status = BatchStatus.COMPLETED
        self.end_time = datetime.now()
        self.processing_time = (self.end_time - self.start_time).total_seconds()
    
    def mark_failed(self, error: Exception):
        """Mark batch as failed with error."""
        self.error = error
        self.status = BatchStatus.FAILED
        self.end_time = datetime.now()
        self.processing_time = (self.end_time - self.start_time).total_seconds()
    
    def mark_retrying(self):
        """Mark batch as retrying."""
        self.status = BatchStatus.RETRYING
        self.retry_count += 1


@dataclass
class BatchProgress:
    """Progress tracking for batch processing."""
    total_batches: int
    completed_batches: int = 0
    failed_batches: int = 0
    retrying_batches: int = 0
    total_items: int = 0
    processed_items: int = 0
    failed_items: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    current_batch: Optional[int] = None
    
    @property
    def completion_percentage(self) -> float:
        """Calculate completion percentage."""
        if self.total_batches == 0:
            return 0.0
        return (self.completed_batches / self.total_batches) * 100.0
    
    @property
    def items_completion_percentage(self) -> float:
        """Calculate items completion percentage."""
        if self.total_items == 0:
            return 0.0
        return (self.processed_items / self.total_items) * 100.0
    
    @property
    def elapsed_time(self) -> float:
        """Get elapsed time in seconds."""
        return (datetime.now() - self.start_time).total_seconds()
    
    @property
    def estimated_time_remaining(self) -> Optional[float]:
        """Estimate remaining time based on current progress."""
        if self.completed_batches == 0:
            return None
        
        avg_time_per_batch = self.elapsed_time / self.completed_batches
        remaining_batches = self.total_batches - self.completed_batches
        return avg_time_per_batch * remaining_batches


class ProgressCallback:
    """Callback interface for progress updates."""
    
    def on_batch_start(self, batch_result: BatchResult, progress: BatchProgress):
        """Called when a batch starts processing."""
        pass
    
    def on_batch_complete(self, batch_result: BatchResult, progress: BatchProgress):
        """Called when a batch completes successfully."""
        pass
    
    def on_batch_failed(self, batch_result: BatchResult, progress: BatchProgress):
        """Called when a batch fails."""
        pass
    
    def on_batch_retry(self, batch_result: BatchResult, progress: BatchProgress):
        """Called when a batch is being retried."""
        pass
    
    def on_progress_update(self, progress: BatchProgress):
        """Called periodically with progress updates."""
        pass


class LoggingProgressCallback(ProgressCallback):
    """Default progress callback that logs to the logger."""
    
    def __init__(self, log_level: int = logging.INFO):
        self.log_level = log_level
    
    def on_batch_start(self, batch_result: BatchResult, progress: BatchProgress):
        total_batches = progress.total_batches if progress else "?"
        logger.log(self.log_level, 
                  f"Starting batch {batch_result.batch_number}/{total_batches} "
                  f"with {len(batch_result.items)} items")
    
    def on_batch_complete(self, batch_result: BatchResult, progress: BatchProgress):
        total_batches = progress.total_batches if progress else "?"
        completion_pct = progress.completion_percentage if progress else 0.0
        logger.log(self.log_level,
                  f"Completed batch {batch_result.batch_number}/{total_batches} "
                  f"in {batch_result.processing_time:.2f}s "
                  f"({completion_pct:.1f}% total progress)")
    
    def on_batch_failed(self, batch_result: BatchResult, progress: BatchProgress):
        logger.error(f"Batch {batch_result.batch_number} failed after {batch_result.retry_count} retries: "
                    f"{batch_result.error}")
    
    def on_batch_retry(self, batch_result: BatchResult, progress: BatchProgress):
        logger.warning(f"Retrying batch {batch_result.batch_number} "
                      f"(attempt {batch_result.retry_count + 1}/{batch_result.retry_count + 1})")
    
    def on_progress_update(self, progress: BatchProgress):
        if progress.completed_batches > 0 and progress.completed_batches % 5 == 0:
            eta = progress.estimated_time_remaining
            eta_str = f", ETA: {eta:.1f}s" if eta else ""
            logger.log(self.log_level,
                      f"Progress: {progress.completion_percentage:.1f}% "
                      f"({progress.completed_batches}/{progress.total_batches} batches){eta_str}")


class BatchManager(Generic[T, R]):
    """
    Manager for processing items in configurable batches with retry logic.
    
    This class handles:
    - Splitting items into batches of configurable size
    - Processing batches with retry logic and exponential backoff
    - Progress tracking and logging
    - Concurrent batch processing (optional)
    """
    
    def __init__(self, 
                 batch_size: int = 10,
                 retry_config: Optional[RetryConfig] = None,
                 max_concurrent_batches: int = 1,
                 progress_callback: Optional[ProgressCallback] = None):
        """
        Initialize the BatchManager.
        
        Args:
            batch_size: Number of items per batch
            retry_config: Configuration for retry logic
            max_concurrent_batches: Maximum number of concurrent batches
            progress_callback: Callback for progress updates
        """
        if batch_size <= 0:
            raise ValueError(f"Batch size must be positive, got {batch_size}")
        
        self.batch_size = batch_size
        self.retry_config = retry_config or RetryConfig()
        self.max_concurrent_batches = max_concurrent_batches
        self.progress_callback = progress_callback or LoggingProgressCallback()
        
        # Thread safety
        self._lock = threading.Lock()
        self._progress: Optional[BatchProgress] = None
        self._batch_results: List[BatchResult] = []
    
    def create_batches(self, items: List[T]) -> List[List[T]]:
        """
        Split items into batches of configured size.
        
        Args:
            items: List of items to batch
            
        Returns:
            List of batches, where each batch is a list of items
        """
        if not items:
            return []
        
        batches = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i + self.batch_size]
            batches.append(batch)
        
        logger.info(f"Created {len(batches)} batches from {len(items)} items "
                   f"(batch_size={self.batch_size})")
        
        return batches
    
    def process_batch(self, 
                     batch: List[T], 
                     batch_number: int,
                     processor_func: Callable[[List[T]], List[R]],
                     context: Optional[Dict[str, Any]] = None) -> BatchResult[R]:
        """
        Process a single batch with retry logic.
        
        Args:
            batch: List of items to process
            batch_number: Batch number for tracking
            processor_func: Function to process the batch
            context: Optional context data for processing
            
        Returns:
            BatchResult with processing results
        """
        batch_id = f"batch_{batch_number}_{int(time.time())}"
        batch_result = BatchResult(
            batch_id=batch_id,
            batch_number=batch_number,
            items=batch,
            results=[],
            status=BatchStatus.PENDING,
            start_time=datetime.now()
        )
        
        # Notify callback
        batch_result.status = BatchStatus.PROCESSING
        self.progress_callback.on_batch_start(batch_result, self._progress)
        
        for attempt in range(self.retry_config.max_retries + 1):
            try:
                logger.debug(f"Processing batch {batch_number}, attempt {attempt + 1}")
                
                # Process the batch
                results = processor_func(batch)
                
                # Mark as completed
                batch_result.mark_completed(results)
                self.progress_callback.on_batch_complete(batch_result, self._progress)
                
                logger.debug(f"Batch {batch_number} completed successfully")
                return batch_result
                
            except Exception as e:
                logger.warning(f"Batch {batch_number} failed on attempt {attempt + 1}: {e}")
                
                if attempt < self.retry_config.max_retries:
                    # Mark as retrying
                    batch_result.mark_retrying()
                    self.progress_callback.on_batch_retry(batch_result, self._progress)
                    
                    # Wait before retry
                    delay = self.retry_config.get_delay(attempt)
                    logger.info(f"Retrying batch {batch_number} in {delay:.2f} seconds")
                    time.sleep(delay)
                else:
                    # Mark as failed
                    batch_result.mark_failed(e)
                    self.progress_callback.on_batch_failed(batch_result, self._progress)
                    
                    logger.error(f"Batch {batch_number} failed after {self.retry_config.max_retries + 1} attempts")
                    return batch_result
        
        return batch_result
    
    def process_all_batches(self,
                           items: List[T],
                           processor_func: Callable[[List[T]], List[R]],
                           context: Optional[Dict[str, Any]] = None) -> List[BatchResult[R]]:
        """
        Process all items in batches.
        
        Args:
            items: List of items to process
            processor_func: Function to process each batch
            context: Optional context data for processing
            
        Returns:
            List of BatchResult objects
        """
        if not items:
            logger.info("No items to process")
            return []
        
        # Create batches
        batches = self.create_batches(items)
        
        # Initialize progress tracking
        with self._lock:
            self._progress = BatchProgress(
                total_batches=len(batches),
                total_items=len(items)
            )
            self._batch_results = []
        
        logger.info(f"Starting batch processing: {len(batches)} batches, "
                   f"{len(items)} total items, "
                   f"max_concurrent={self.max_concurrent_batches}")
        
        if self.max_concurrent_batches == 1:
            # Sequential processing
            return self._process_batches_sequential(batches, processor_func, context)
        else:
            # Concurrent processing
            return self._process_batches_concurrent(batches, processor_func, context)
    
    def _process_batches_sequential(self,
                                  batches: List[List[T]],
                                  processor_func: Callable[[List[T]], List[R]],
                                  context: Optional[Dict[str, Any]] = None) -> List[BatchResult[R]]:
        """Process batches sequentially."""
        results = []
        
        for i, batch in enumerate(batches, 1):
            with self._lock:
                self._progress.current_batch = i
            
            batch_result = self.process_batch(batch, i, processor_func, context)
            results.append(batch_result)
            
            # Update progress
            with self._lock:
                self._batch_results.append(batch_result)
                if batch_result.status == BatchStatus.COMPLETED:
                    self._progress.completed_batches += 1
                    self._progress.processed_items += len(batch)
                elif batch_result.status == BatchStatus.FAILED:
                    self._progress.failed_batches += 1
                    self._progress.failed_items += len(batch)
                
                self.progress_callback.on_progress_update(self._progress)
        
        return results
    
    def _process_batches_concurrent(self,
                                  batches: List[List[T]],
                                  processor_func: Callable[[List[T]], List[R]],
                                  context: Optional[Dict[str, Any]] = None) -> List[BatchResult[R]]:
        """Process batches concurrently using ThreadPoolExecutor."""
        results = [None] * len(batches)  # Pre-allocate to maintain order
        
        with ThreadPoolExecutor(max_workers=self.max_concurrent_batches) as executor:
            # Submit all batches
            future_to_index = {}
            for i, batch in enumerate(batches):
                future = executor.submit(self.process_batch, batch, i + 1, processor_func, context)
                future_to_index[future] = i
            
            # Collect results as they complete
            for future in as_completed(future_to_index):
                index = future_to_index[future]
                batch_result = future.result()
                results[index] = batch_result
                
                # Update progress
                with self._lock:
                    self._batch_results.append(batch_result)
                    if batch_result.status == BatchStatus.COMPLETED:
                        self._progress.completed_batches += 1
                        self._progress.processed_items += len(batch_result.items)
                    elif batch_result.status == BatchStatus.FAILED:
                        self._progress.failed_batches += 1
                        self._progress.failed_items += len(batch_result.items)
                    
                    self.progress_callback.on_progress_update(self._progress)
        
        return results
    
    def get_progress(self) -> Optional[BatchProgress]:
        """Get current progress information."""
        with self._lock:
            return self._progress
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics for the last batch processing run."""
        with self._lock:
            if not self._progress:
                return {}
            
            successful_batches = [r for r in self._batch_results if r.status == BatchStatus.COMPLETED]
            failed_batches = [r for r in self._batch_results if r.status == BatchStatus.FAILED]
            
            total_processing_time = sum(r.processing_time or 0 for r in self._batch_results)
            avg_batch_time = total_processing_time / len(self._batch_results) if self._batch_results else 0
            
            return {
                "total_batches": self._progress.total_batches,
                "completed_batches": self._progress.completed_batches,
                "failed_batches": self._progress.failed_batches,
                "total_items": self._progress.total_items,
                "processed_items": self._progress.processed_items,
                "failed_items": self._progress.failed_items,
                "completion_percentage": self._progress.completion_percentage,
                "total_processing_time": total_processing_time,
                "average_batch_time": avg_batch_time,
                "successful_batch_count": len(successful_batches),
                "failed_batch_count": len(failed_batches)
            }


# Utility functions for common batch processing patterns

def create_protein_batch_processor(batch_size: int = 10, 
                                 max_retries: int = 3,
                                 max_concurrent: int = 1) -> BatchManager[str, Any]:
    """
    Create a BatchManager configured for protein processing.
    
    Args:
        batch_size: Number of proteins per batch
        max_retries: Maximum retry attempts
        max_concurrent: Maximum concurrent batches
        
    Returns:
        Configured BatchManager instance
    """
    retry_config = RetryConfig(
        max_retries=max_retries,
        base_delay=1.0,
        max_delay=30.0,
        exponential_base=2.0,
        jitter=True
    )
    
    return BatchManager(
        batch_size=batch_size,
        retry_config=retry_config,
        max_concurrent_batches=max_concurrent,
        progress_callback=LoggingProgressCallback()
    )


def batch_process_with_context(items: List[T],
                             processor_func: Callable[[List[T], Dict[str, Any]], List[R]],
                             context: Dict[str, Any],
                             batch_size: int = 10) -> List[R]:
    """
    Convenience function for batch processing with context.
    
    Args:
        items: Items to process
        processor_func: Function that takes (batch, context) and returns results
        context: Context data to pass to processor
        batch_size: Batch size
        
    Returns:
        Flattened list of all results
    """
    batch_manager = BatchManager(batch_size=batch_size)
    
    # Wrapper to adapt the processor function
    def adapted_processor(batch: List[T]) -> List[R]:
        return processor_func(batch, context)
    
    batch_results = batch_manager.process_all_batches(items, adapted_processor)
    
    # Flatten results
    all_results = []
    for batch_result in batch_results:
        if batch_result.status == BatchStatus.COMPLETED:
            all_results.extend(batch_result.results)
    
    return all_results