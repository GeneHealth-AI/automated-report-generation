"""
Performance Optimization System for Risk/Protective Variant Reporting

This module provides performance optimization features including:
- Classification result caching
- Performance monitoring and metrics collection
- Algorithm optimization for large datasets
- Memory usage optimization

Requirements: 4.2, 4.3, 5.1
"""

import time
import logging
import hashlib
import json
import threading
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from functools import wraps, lru_cache
from collections import defaultdict, deque
import psutil
import os
from datetime import datetime, timedelta

# Import existing modules
from variant_classifier import VariantClassifier, VariantClassification, EffectDirection, ConfidenceLevel
from enhanced_data_models import EnhancedVariant, SectionConfig
from section_manager import SectionManager

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics for monitoring system performance."""
    operation_name: str
    start_time: float
    end_time: float
    duration: float
    memory_usage_mb: float
    cpu_usage_percent: float
    items_processed: int
    cache_hits: int = 0
    cache_misses: int = 0
    error_count: int = 0
    
    @property
    def throughput(self) -> float:
        """Calculate throughput (items per second)."""
        return self.items_processed / self.duration if self.duration > 0 else 0.0
    
    @property
    def cache_hit_rate(self) -> float:
        """Calculate cache hit rate."""
        total_requests = self.cache_hits + self.cache_misses
        return self.cache_hits / total_requests if total_requests > 0 else 0.0


@dataclass
class CacheStats:
    """Statistics for cache performance."""
    total_requests: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    cache_size: int = 0
    max_cache_size: int = 0
    evictions: int = 0
    
    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate."""
        return self.cache_hits / self.total_requests if self.total_requests > 0 else 0.0


class ClassificationCache:
    """
    High-performance cache for variant classification results.
    
    Implements LRU eviction with thread-safe operations and performance monitoring.
    """
    
    def __init__(self, max_size: int = 10000, ttl_seconds: int = 3600):
        """
        Initialize classification cache.
        
        Args:
            max_size: Maximum number of cached classifications
            ttl_seconds: Time-to-live for cached entries in seconds
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._cache: Dict[str, Tuple[VariantClassification, float]] = {}
        self._access_order: deque = deque()
        self._lock = threading.RLock()
        self._stats = CacheStats(max_cache_size=max_size)
        
        logger.info(f"Initialized classification cache with max_size={max_size}, ttl={ttl_seconds}s")
    
    def _generate_cache_key(self, variant_data: Dict[str, Any]) -> str:
        """Generate a unique cache key for variant data."""
        # Create a stable hash of the variant data
        variant_str = json.dumps(variant_data, sort_keys=True, default=str)
        return hashlib.md5(variant_str.encode()).hexdigest()
    
    def get(self, variant_data: Dict[str, Any]) -> Optional[VariantClassification]:
        """
        Get cached classification result.
        
        Args:
            variant_data: Variant data dictionary
            
        Returns:
            Cached VariantClassification or None if not found/expired
        """
        cache_key = self._generate_cache_key(variant_data)
        
        with self._lock:
            self._stats.total_requests += 1
            
            if cache_key in self._cache:
                classification, timestamp = self._cache[cache_key]
                
                # Check if entry has expired
                if time.time() - timestamp > self.ttl_seconds:
                    del self._cache[cache_key]
                    self._access_order.remove(cache_key)
                    self._stats.cache_misses += 1
                    return None
                
                # Move to end (most recently used)
                self._access_order.remove(cache_key)
                self._access_order.append(cache_key)
                
                self._stats.cache_hits += 1
                return classification
            
            self._stats.cache_misses += 1
            return None
    
    def put(self, variant_data: Dict[str, Any], classification: VariantClassification) -> None:
        """
        Cache a classification result.
        
        Args:
            variant_data: Variant data dictionary
            classification: Classification result to cache
        """
        cache_key = self._generate_cache_key(variant_data)
        current_time = time.time()
        
        with self._lock:
            # If key already exists, update it
            if cache_key in self._cache:
                self._access_order.remove(cache_key)
            
            # Add new entry
            self._cache[cache_key] = (classification, current_time)
            self._access_order.append(cache_key)
            
            # Evict oldest entries if cache is full
            while len(self._cache) > self.max_size:
                oldest_key = self._access_order.popleft()
                del self._cache[oldest_key]
                self._stats.evictions += 1
            
            self._stats.cache_size = len(self._cache)
    
    def clear(self) -> None:
        """Clear all cached entries."""
        with self._lock:
            self._cache.clear()
            self._access_order.clear()
            self._stats.cache_size = 0
            logger.info("Classification cache cleared")
    
    def get_stats(self) -> CacheStats:
        """Get cache performance statistics."""
        with self._lock:
            return CacheStats(
                total_requests=self._stats.total_requests,
                cache_hits=self._stats.cache_hits,
                cache_misses=self._stats.cache_misses,
                cache_size=len(self._cache),
                max_cache_size=self.max_size,
                evictions=self._stats.evictions
            )


class PerformanceMonitor:
    """
    Performance monitoring system for tracking system performance metrics.
    """
    
    def __init__(self, max_history: int = 1000):
        """
        Initialize performance monitor.
        
        Args:
            max_history: Maximum number of metrics to keep in history
        """
        self.max_history = max_history
        self._metrics_history: deque = deque(maxlen=max_history)
        self._operation_stats: Dict[str, List[PerformanceMetrics]] = defaultdict(list)
        self._lock = threading.RLock()
        
        logger.info(f"Initialized performance monitor with max_history={max_history}")
    
    def start_operation(self, operation_name: str) -> 'OperationContext':
        """
        Start monitoring an operation.
        
        Args:
            operation_name: Name of the operation being monitored
            
        Returns:
            OperationContext for tracking the operation
        """
        return OperationContext(self, operation_name)
    
    def record_metrics(self, metrics: PerformanceMetrics) -> None:
        """
        Record performance metrics.
        
        Args:
            metrics: PerformanceMetrics object to record
        """
        with self._lock:
            self._metrics_history.append(metrics)
            self._operation_stats[metrics.operation_name].append(metrics)
            
            # Keep only recent metrics per operation
            if len(self._operation_stats[metrics.operation_name]) > 100:
                self._operation_stats[metrics.operation_name] = \
                    self._operation_stats[metrics.operation_name][-100:]
        
        logger.debug(f"Recorded metrics for {metrics.operation_name}: "
                    f"duration={metrics.duration:.3f}s, "
                    f"throughput={metrics.throughput:.1f} items/s")
    
    def get_operation_stats(self, operation_name: str) -> Dict[str, Any]:
        """
        Get statistics for a specific operation.
        
        Args:
            operation_name: Name of the operation
            
        Returns:
            Dictionary with operation statistics
        """
        with self._lock:
            if operation_name not in self._operation_stats:
                return {}
            
            metrics_list = self._operation_stats[operation_name]
            if not metrics_list:
                return {}
            
            durations = [m.duration for m in metrics_list]
            throughputs = [m.throughput for m in metrics_list]
            memory_usage = [m.memory_usage_mb for m in metrics_list]
            
            return {
                'operation_name': operation_name,
                'total_executions': len(metrics_list),
                'avg_duration': sum(durations) / len(durations),
                'min_duration': min(durations),
                'max_duration': max(durations),
                'avg_throughput': sum(throughputs) / len(throughputs),
                'max_throughput': max(throughputs),
                'avg_memory_mb': sum(memory_usage) / len(memory_usage),
                'max_memory_mb': max(memory_usage),
                'total_items_processed': sum(m.items_processed for m in metrics_list),
                'total_errors': sum(m.error_count for m in metrics_list)
            }
    
    def get_system_summary(self) -> Dict[str, Any]:
        """
        Get overall system performance summary.
        
        Returns:
            Dictionary with system performance summary
        """
        with self._lock:
            if not self._metrics_history:
                return {}
            
            recent_metrics = list(self._metrics_history)[-100:]  # Last 100 operations
            
            total_duration = sum(m.duration for m in recent_metrics)
            total_items = sum(m.items_processed for m in recent_metrics)
            total_errors = sum(m.error_count for m in recent_metrics)
            
            return {
                'total_operations': len(recent_metrics),
                'total_duration': total_duration,
                'total_items_processed': total_items,
                'overall_throughput': total_items / total_duration if total_duration > 0 else 0,
                'error_rate': total_errors / len(recent_metrics) if recent_metrics else 0,
                'operations_tracked': list(self._operation_stats.keys()),
                'avg_memory_usage_mb': sum(m.memory_usage_mb for m in recent_metrics) / len(recent_metrics)
            }


class OperationContext:
    """Context manager for tracking operation performance."""
    
    def __init__(self, monitor: PerformanceMonitor, operation_name: str):
        """
        Initialize operation context.
        
        Args:
            monitor: PerformanceMonitor instance
            operation_name: Name of the operation
        """
        self.monitor = monitor
        self.operation_name = operation_name
        self.start_time = 0.0
        self.items_processed = 0
        self.cache_hits = 0
        self.cache_misses = 0
        self.error_count = 0
        self._process = psutil.Process()
    
    def __enter__(self) -> 'OperationContext':
        """Start monitoring the operation."""
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Finish monitoring and record metrics."""
        end_time = time.time()
        duration = end_time - self.start_time
        
        # Get memory usage
        try:
            memory_info = self._process.memory_info()
            memory_usage_mb = memory_info.rss / 1024 / 1024
        except Exception:
            memory_usage_mb = 0.0
        
        # Get CPU usage (approximate)
        try:
            cpu_usage = self._process.cpu_percent()
        except Exception:
            cpu_usage = 0.0
        
        # Count errors
        if exc_type is not None:
            self.error_count += 1
        
        # Create metrics object
        metrics = PerformanceMetrics(
            operation_name=self.operation_name,
            start_time=self.start_time,
            end_time=end_time,
            duration=duration,
            memory_usage_mb=memory_usage_mb,
            cpu_usage_percent=cpu_usage,
            items_processed=self.items_processed,
            cache_hits=self.cache_hits,
            cache_misses=self.cache_misses,
            error_count=self.error_count
        )
        
        self.monitor.record_metrics(metrics)
    
    def add_items_processed(self, count: int) -> None:
        """Add to the count of items processed."""
        self.items_processed += count
    
    def add_cache_hit(self) -> None:
        """Record a cache hit."""
        self.cache_hits += 1
    
    def add_cache_miss(self) -> None:
        """Record a cache miss."""
        self.cache_misses += 1


class OptimizedVariantClassifier(VariantClassifier):
    """
    Optimized variant classifier with caching and performance monitoring.
    
    Extends the base VariantClassifier with performance optimizations
    for large-scale variant classification.
    """
    
    def __init__(self, config=None, cache_size: int = 10000, enable_monitoring: bool = True):
        """
        Initialize optimized variant classifier.
        
        Args:
            config: Classification configuration
            cache_size: Maximum cache size for classifications
            enable_monitoring: Whether to enable performance monitoring
        """
        super().__init__(config)
        
        self.cache = ClassificationCache(max_size=cache_size)
        self.monitor = PerformanceMonitor() if enable_monitoring else None
        self._batch_size = 100  # Optimal batch size for processing
        
        logger.info(f"Initialized optimized classifier with cache_size={cache_size}, "
                   f"monitoring={'enabled' if enable_monitoring else 'disabled'}")
    
    def classify_variant(self, variant_data: Dict[str, Any]) -> VariantClassification:
        """
        Classify a variant with caching and performance monitoring.
        
        Args:
            variant_data: Variant data dictionary
            
        Returns:
            VariantClassification result
        """
        if self.monitor:
            with self.monitor.start_operation("classify_variant") as ctx:
                ctx.add_items_processed(1)
                
                # Check cache first
                cached_result = self.cache.get(variant_data)
                if cached_result:
                    ctx.add_cache_hit()
                    return cached_result
                
                ctx.add_cache_miss()
                
                # Perform classification
                try:
                    result = super().classify_variant(variant_data)
                    self.cache.put(variant_data, result)
                    return result
                except Exception as e:
                    ctx.error_count += 1
                    raise
        else:
            # Check cache without monitoring
            cached_result = self.cache.get(variant_data)
            if cached_result:
                return cached_result
            
            result = super().classify_variant(variant_data)
            self.cache.put(variant_data, result)
            return result
    
    def classify_variants_batch(self, variants_data: List[Dict[str, Any]]) -> List[VariantClassification]:
        """
        Classify multiple variants in optimized batches.
        
        Args:
            variants_data: List of variant data dictionaries
            
        Returns:
            List of VariantClassification results
        """
        if not variants_data:
            return []
        
        operation_name = f"classify_variants_batch_{len(variants_data)}"
        
        if self.monitor:
            with self.monitor.start_operation(operation_name) as ctx:
                ctx.add_items_processed(len(variants_data))
                return self._process_batch_with_monitoring(variants_data, ctx)
        else:
            return self._process_batch_without_monitoring(variants_data)
    
    def _process_batch_with_monitoring(self, variants_data: List[Dict[str, Any]], 
                                     ctx: OperationContext) -> List[VariantClassification]:
        """Process batch with performance monitoring."""
        results = []
        
        # Process in smaller batches for better memory management
        for i in range(0, len(variants_data), self._batch_size):
            batch = variants_data[i:i + self._batch_size]
            batch_results = []
            
            for variant_data in batch:
                try:
                    # Check cache
                    cached_result = self.cache.get(variant_data)
                    if cached_result:
                        ctx.add_cache_hit()
                        batch_results.append(cached_result)
                    else:
                        ctx.add_cache_miss()
                        result = super().classify_variant(variant_data)
                        self.cache.put(variant_data, result)
                        batch_results.append(result)
                        
                except Exception as e:
                    ctx.error_count += 1
                    logger.error(f"Error classifying variant in batch: {e}")
                    # Create fallback classification
                    fallback = self._create_fallback_classification(f"Batch processing error: {e}")
                    batch_results.append(fallback)
            
            results.extend(batch_results)
        
        return results
    
    def _process_batch_without_monitoring(self, variants_data: List[Dict[str, Any]]) -> List[VariantClassification]:
        """Process batch without monitoring for maximum performance."""
        results = []
        
        for variant_data in variants_data:
            try:
                cached_result = self.cache.get(variant_data)
                if cached_result:
                    results.append(cached_result)
                else:
                    result = super().classify_variant(variant_data)
                    self.cache.put(variant_data, result)
                    results.append(result)
            except Exception as e:
                logger.error(f"Error classifying variant in batch: {e}")
                fallback = self._create_fallback_classification(f"Batch processing error: {e}")
                results.append(fallback)
        
        return results
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """
        Get performance statistics for the classifier.
        
        Returns:
            Dictionary with performance statistics
        """
        stats = {
            'cache_stats': self.cache.get_stats().__dict__,
            'batch_size': self._batch_size
        }
        
        if self.monitor:
            stats['operation_stats'] = {
                'classify_variant': self.monitor.get_operation_stats('classify_variant'),
                'system_summary': self.monitor.get_system_summary()
            }
            
            # Add batch operation stats
            for op_name in self.monitor._operation_stats.keys():
                if op_name.startswith('classify_variants_batch_'):
                    stats['operation_stats'][op_name] = self.monitor.get_operation_stats(op_name)
        
        return stats
    
    def optimize_batch_size(self, test_sizes: List[int] = None) -> int:
        """
        Automatically optimize batch size based on performance testing.
        
        Args:
            test_sizes: List of batch sizes to test (default: [50, 100, 200, 500])
            
        Returns:
            Optimal batch size
        """
        if test_sizes is None:
            test_sizes = [50, 100, 200, 500]
        
        logger.info("Starting batch size optimization...")
        
        # Create test data
        test_variants = []
        for i in range(1000):  # Test with 1000 variants
            test_variants.append({
                'rsid': f'rs{i}',
                'gene': f'GENE{i % 100}',
                'clinvar_significance': 'pathogenic' if i % 3 == 0 else 'benign',
                'population_frequency': 0.01 if i % 5 == 0 else 0.1
            })
        
        best_size = self._batch_size
        best_throughput = 0.0
        
        for batch_size in test_sizes:
            # Clear cache for fair testing
            self.cache.clear()
            
            # Test this batch size
            old_batch_size = self._batch_size
            self._batch_size = batch_size
            
            start_time = time.time()
            self.classify_variants_batch(test_variants)
            duration = time.time() - start_time
            
            throughput = len(test_variants) / duration
            
            logger.info(f"Batch size {batch_size}: {throughput:.1f} variants/sec")
            
            if throughput > best_throughput:
                best_throughput = throughput
                best_size = batch_size
            
            # Restore original batch size
            self._batch_size = old_batch_size
        
        # Set optimal batch size
        self._batch_size = best_size
        logger.info(f"Optimal batch size determined: {best_size} (throughput: {best_throughput:.1f} variants/sec)")
        
        return best_size


class OptimizedSectionManager(SectionManager):
    """
    Optimized section manager with performance enhancements.
    """
    
    def __init__(self, min_confidence_level=None, enable_monitoring: bool = True):
        """
        Initialize optimized section manager.
        
        Args:
            min_confidence_level: Minimum confidence level for variants
            enable_monitoring: Whether to enable performance monitoring
        """
        super().__init__(min_confidence_level)
        
        self.monitor = PerformanceMonitor() if enable_monitoring else None
        self._section_cache: Dict[str, SectionConfig] = {}
        self._cache_ttl = 300  # 5 minutes cache TTL
        self._cache_timestamps: Dict[str, float] = {}
        
        logger.info(f"Initialized optimized section manager with monitoring={'enabled' if enable_monitoring else 'disabled'}")
    
    def determine_required_sections(self, variants: List[EnhancedVariant], condition: str) -> SectionConfig:
        """
        Determine required sections with caching and performance monitoring.
        
        Args:
            variants: List of enhanced variants
            condition: Condition name
            
        Returns:
            SectionConfig object
        """
        # Generate cache key
        cache_key = self._generate_section_cache_key(variants, condition)
        
        # Check cache
        if self._is_cache_valid(cache_key):
            cached_result = self._section_cache[cache_key]
            if self.monitor:
                with self.monitor.start_operation("determine_required_sections_cached") as ctx:
                    ctx.add_items_processed(len(variants))
                    ctx.add_cache_hit()
            return cached_result
        
        # Process with monitoring
        if self.monitor:
            with self.monitor.start_operation("determine_required_sections") as ctx:
                ctx.add_items_processed(len(variants))
                ctx.add_cache_miss()
                
                result = super().determine_required_sections(variants, condition)
                
                # Cache the result
                self._section_cache[cache_key] = result
                self._cache_timestamps[cache_key] = time.time()
                
                return result
        else:
            result = super().determine_required_sections(variants, condition)
            self._section_cache[cache_key] = result
            self._cache_timestamps[cache_key] = time.time()
            return result
    
    def _generate_section_cache_key(self, variants: List[EnhancedVariant], condition: str) -> str:
        """Generate cache key for section determination."""
        # Create a hash based on variant RSIDs and condition
        variant_ids = sorted([v.rsid for v in variants])
        key_data = f"{condition}:{':'.join(variant_ids)}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """Check if cached entry is still valid."""
        if cache_key not in self._section_cache:
            return False
        
        timestamp = self._cache_timestamps.get(cache_key, 0)
        return time.time() - timestamp < self._cache_ttl
    
    def clear_cache(self) -> None:
        """Clear section determination cache."""
        self._section_cache.clear()
        self._cache_timestamps.clear()
        logger.info("Section manager cache cleared")
    
    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics."""
        stats = {
            'cache_size': len(self._section_cache),
            'cache_ttl_seconds': self._cache_ttl
        }
        
        if self.monitor:
            stats['operation_stats'] = {
                'determine_required_sections': self.monitor.get_operation_stats('determine_required_sections'),
                'determine_required_sections_cached': self.monitor.get_operation_stats('determine_required_sections_cached'),
                'system_summary': self.monitor.get_system_summary()
            }
        
        return stats


def performance_test_decorator(operation_name: str):
    """
    Decorator for adding performance monitoring to functions.
    
    Args:
        operation_name: Name of the operation for monitoring
        
    Returns:
        Decorated function with performance monitoring
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Try to find a monitor in the arguments
            monitor = None
            for arg in args:
                if hasattr(arg, 'monitor') and isinstance(arg.monitor, PerformanceMonitor):
                    monitor = arg.monitor
                    break
            
            if monitor:
                with monitor.start_operation(operation_name) as ctx:
                    try:
                        result = func(*args, **kwargs)
                        # Try to count items if result is a list
                        if isinstance(result, list):
                            ctx.add_items_processed(len(result))
                        else:
                            ctx.add_items_processed(1)
                        return result
                    except Exception as e:
                        ctx.error_count += 1
                        raise
            else:
                return func(*args, **kwargs)
        
        return wrapper
    return decorator


# Utility functions for performance optimization

def optimize_memory_usage():
    """
    Optimize memory usage by forcing garbage collection and clearing caches.
    """
    import gc
    
    # Force garbage collection
    collected = gc.collect()
    
    # Get memory usage
    process = psutil.Process()
    memory_mb = process.memory_info().rss / 1024 / 1024
    
    logger.info(f"Memory optimization: collected {collected} objects, "
               f"current memory usage: {memory_mb:.1f} MB")
    
    return {
        'objects_collected': collected,
        'memory_usage_mb': memory_mb
    }


def create_performance_report(classifier: OptimizedVariantClassifier, 
                            section_manager: OptimizedSectionManager) -> Dict[str, Any]:
    """
    Create comprehensive performance report.
    
    Args:
        classifier: OptimizedVariantClassifier instance
        section_manager: OptimizedSectionManager instance
        
    Returns:
        Dictionary with comprehensive performance report
    """
    report = {
        'timestamp': datetime.now().isoformat(),
        'classifier_stats': classifier.get_performance_stats(),
        'section_manager_stats': section_manager.get_performance_stats(),
        'system_info': {
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / 1024 / 1024 / 1024,
            'memory_available_gb': psutil.virtual_memory().available / 1024 / 1024 / 1024,
            'python_version': os.sys.version
        }
    }
    
    return report


def benchmark_system_performance(variant_counts: List[int] = None) -> Dict[str, Any]:
    """
    Run comprehensive system performance benchmark.
    
    Args:
        variant_counts: List of variant counts to test (default: [100, 500, 1000])
        
    Returns:
        Dictionary with benchmark results
    """
    if variant_counts is None:
        variant_counts = [100, 500, 1000]
    
    logger.info("Starting system performance benchmark...")
    
    # Initialize optimized components
    classifier = OptimizedVariantClassifier(cache_size=5000, enable_monitoring=True)
    section_manager = OptimizedSectionManager(enable_monitoring=True)
    
    benchmark_results = {
        'timestamp': datetime.now().isoformat(),
        'test_results': {}
    }
    
    for variant_count in variant_counts:
        logger.info(f"Benchmarking with {variant_count} variants...")
        
        # Generate test data
        test_variants = []
        for i in range(variant_count):
            test_variants.append({
                'rsid': f'rs{i}',
                'gene': f'GENE{i % 50}',
                'clinvar_significance': 'pathogenic' if i % 3 == 0 else 'benign',
                'population_frequency': 0.01 if i % 5 == 0 else 0.1,
                'literature_evidence': {'risk_association': i % 4 == 0}
            })
        
        # Benchmark classification
        start_time = time.time()
        classifications = classifier.classify_variants_batch(test_variants)
        classification_time = time.time() - start_time
        
        # Create enhanced variants for section management testing
        enhanced_variants = []
        for i, classification in enumerate(classifications):
            enhanced_variant = EnhancedVariant(
                rsid=f'rs{i}',
                gene=f'GENE{i % 50}',
                effect_direction=classification.effect_direction,
                effect_magnitude=1.0,
                confidence_level=classification.confidence_level,
                confidence_score=classification.confidence_score,
                condition_associations=['Test Condition'],
                evidence_sources=classification.evidence_sources
            )
            enhanced_variants.append(enhanced_variant)
        
        # Benchmark section management
        start_time = time.time()
        section_config = section_manager.determine_required_sections(enhanced_variants, 'Test Condition')
        section_time = time.time() - start_time
        
        # Record results
        benchmark_results['test_results'][f'{variant_count}_variants'] = {
            'variant_count': variant_count,
            'classification_time': classification_time,
            'classification_throughput': variant_count / classification_time,
            'section_management_time': section_time,
            'total_time': classification_time + section_time,
            'memory_usage_mb': psutil.Process().memory_info().rss / 1024 / 1024
        }
    
    # Add performance statistics
    benchmark_results['classifier_stats'] = classifier.get_performance_stats()
    benchmark_results['section_manager_stats'] = section_manager.get_performance_stats()
    
    logger.info("System performance benchmark completed")
    return benchmark_results