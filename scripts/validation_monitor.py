"""
Validation Monitoring Dashboard

This module provides real-time monitoring and alerting for variant classification
quality assurance and performance metrics.
"""

import json
import time
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional
from pathlib import Path
import statistics
from dataclasses import dataclass

from variant_validation import VariantValidationSystem, ValidationSeverity, QualityMetric


@dataclass
class AlertRule:
    """Configuration for monitoring alerts"""
    metric: str
    threshold: float
    comparison: str  # 'less_than', 'greater_than', 'equals'
    severity: str
    message_template: str
    cooldown_minutes: int = 60


@dataclass
class MonitoringAlert:
    """Represents a monitoring alert"""
    rule_id: str
    severity: str
    message: str
    metric_value: float
    threshold: float
    timestamp: str
    acknowledged: bool = False


class ValidationMonitor:
    """
    Real-time monitoring system for variant classification validation
    """
    
    def __init__(self, validation_system: VariantValidationSystem, 
                 config_path: str = "validation_config.json"):
        """
        Initialize the validation monitor
        
        Args:
            validation_system: VariantValidationSystem instance to monitor
            config_path: Path to monitoring configuration file
        """
        self.validation_system = validation_system
        self.config_path = Path(config_path)
        self.logger = logging.getLogger(__name__)
        
        # Load configuration
        self.config = self._load_config()
        
        # Initialize alert tracking
        self.active_alerts: List[MonitoringAlert] = []
        self.alert_history: List[MonitoringAlert] = []
        self.last_alert_times: Dict[str, datetime] = {}
        
        # Initialize metrics tracking
        self.metrics_history: List[Dict[str, Any]] = []
        
        # Set up alert rules
        self.alert_rules = self._setup_alert_rules()
    
    def _load_config(self) -> Dict[str, Any]:
        """Load monitoring configuration from file"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r') as f:
                    return json.load(f)
            else:
                self.logger.warning(f"Config file {self.config_path} not found, using defaults")
                return self._get_default_config()
        except Exception as e:
            self.logger.error(f"Failed to load config: {str(e)}, using defaults")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default monitoring configuration"""
        return {
            "quality_thresholds": {
                "consistency": 0.8,
                "completeness": 0.7,
                "confidence": 0.6,
                "evidence_quality": 0.7,
                "performance": 0.9
            },
            "monitoring_settings": {
                "performance_alert_threshold": 0.8,
                "critical_issue_alert_threshold": 5,
                "report_generation_interval_hours": 24,
                "trend_analysis_window_days": 7
            }
        }
    
    def _setup_alert_rules(self) -> List[AlertRule]:
        """Set up monitoring alert rules"""
        rules = []
        
        # Quality threshold alerts
        quality_thresholds = self.config.get("quality_thresholds", {})
        for metric, threshold in quality_thresholds.items():
            rules.append(AlertRule(
                metric=f"quality_score_{metric}",
                threshold=threshold,
                comparison="less_than",
                severity="warning",
                message_template=f"{metric.title()} quality score ({{value:.3f}}) below threshold ({{threshold:.3f}})",
                cooldown_minutes=30
            ))
        
        # Performance alerts
        monitoring_settings = self.config.get("monitoring_settings", {})
        
        rules.append(AlertRule(
            metric="success_rate",
            threshold=monitoring_settings.get("performance_alert_threshold", 0.8),
            comparison="less_than",
            severity="error",
            message_template="Classification success rate ({value:.1%}) below threshold ({threshold:.1%})",
            cooldown_minutes=15
        ))
        
        rules.append(AlertRule(
            metric="critical_issues_count",
            threshold=monitoring_settings.get("critical_issue_alert_threshold", 5),
            comparison="greater_than",
            severity="critical",
            message_template="Critical validation issues count ({value}) exceeds threshold ({threshold})",
            cooldown_minutes=5
        ))
        
        rules.append(AlertRule(
            metric="average_processing_time_ms",
            threshold=1000.0,  # 1 second
            comparison="greater_than",
            severity="warning",
            message_template="Average processing time ({value:.0f}ms) exceeds threshold ({threshold:.0f}ms)",
            cooldown_minutes=60
        ))
        
        return rules
    
    def collect_current_metrics(self, variants: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Collect current validation and performance metrics
        
        Args:
            variants: List of variants to analyze
            
        Returns:
            Dictionary with current metrics
        """
        if not variants:
            return {}
        
        try:
            # Generate quality assessment report
            report = self.validation_system.generate_quality_assessment_report(variants)
            
            # Extract key metrics
            metrics = {
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'total_variants': report.total_variants,
                'quality_scores': {metric.value: score for metric, score in report.quality_scores.items()},
                'performance_metrics': report.performance_metrics,
                'validation_issues_count': len(report.validation_issues),
                'critical_issues_count': sum(1 for issue in report.validation_issues 
                                           if issue.severity == ValidationSeverity.CRITICAL),
                'error_issues_count': sum(1 for issue in report.validation_issues 
                                        if issue.severity == ValidationSeverity.ERROR),
                'warning_issues_count': sum(1 for issue in report.validation_issues 
                                          if issue.severity == ValidationSeverity.WARNING)
            }
            
            # Add individual quality scores for alerting
            for metric, score in report.quality_scores.items():
                metrics[f'quality_score_{metric.value}'] = score
            
            # Add performance metrics for alerting
            perf_metrics = report.performance_metrics
            metrics.update({
                'success_rate': perf_metrics.get('success_rate', 0.0),
                'average_processing_time_ms': perf_metrics.get('average_processing_time_ms', 0.0),
                'failed_classifications': perf_metrics.get('failed_classifications', 0),
                'timeout_count': perf_metrics.get('timeout_count', 0)
            })
            
            # Store in history
            self.metrics_history.append(metrics)
            
            # Keep only recent history (last 24 hours worth of data)
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=24)
            self.metrics_history = [
                m for m in self.metrics_history 
                if datetime.fromisoformat(m['timestamp']) > cutoff_time
            ]
            
            return metrics
            
        except Exception as e:
            self.logger.error(f"Failed to collect metrics: {str(e)}")
            return {}
    
    def check_alerts(self, current_metrics: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Check current metrics against alert rules
        
        Args:
            current_metrics: Current metrics dictionary
            
        Returns:
            List of triggered alerts
        """
        triggered_alerts = []
        current_time = datetime.now(timezone.utc)
        
        for rule in self.alert_rules:
            try:
                # Check if metric exists in current data
                if rule.metric not in current_metrics:
                    continue
                
                metric_value = current_metrics[rule.metric]
                
                # Check cooldown period
                last_alert_time = self.last_alert_times.get(rule.metric)
                if last_alert_time:
                    time_since_last = current_time - last_alert_time
                    if time_since_last.total_seconds() < (rule.cooldown_minutes * 60):
                        continue  # Still in cooldown period
                
                # Check if alert condition is met
                alert_triggered = False
                
                if rule.comparison == "less_than" and metric_value < rule.threshold:
                    alert_triggered = True
                elif rule.comparison == "greater_than" and metric_value > rule.threshold:
                    alert_triggered = True
                elif rule.comparison == "equals" and metric_value == rule.threshold:
                    alert_triggered = True
                
                if alert_triggered:
                    # Create alert
                    alert = MonitoringAlert(
                        rule_id=rule.metric,
                        severity=rule.severity,
                        message=rule.message_template.format(
                            value=metric_value,
                            threshold=rule.threshold
                        ),
                        metric_value=metric_value,
                        threshold=rule.threshold,
                        timestamp=current_time.isoformat()
                    )
                    
                    triggered_alerts.append(alert)
                    self.last_alert_times[rule.metric] = current_time
                    
                    # Log alert
                    log_level = {
                        'info': logging.INFO,
                        'warning': logging.WARNING,
                        'error': logging.ERROR,
                        'critical': logging.CRITICAL
                    }.get(rule.severity, logging.WARNING)
                    
                    self.logger.log(log_level, f"ALERT: {alert.message}")
            
            except Exception as e:
                self.logger.error(f"Error checking alert rule {rule.metric}: {str(e)}")
        
        # Add to active alerts and history
        self.active_alerts.extend(triggered_alerts)
        self.alert_history.extend(triggered_alerts)
        
        return triggered_alerts
    
    def get_trend_analysis(self, metric_name: str, hours: int = 24) -> Dict[str, Any]:
        """
        Analyze trends for a specific metric over time
        
        Args:
            metric_name: Name of metric to analyze
            hours: Number of hours to look back
            
        Returns:
            Dictionary with trend analysis
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Filter relevant metrics
        relevant_metrics = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m['timestamp']) > cutoff_time
            and metric_name in m
        ]
        
        if len(relevant_metrics) < 2:
            return {
                'metric': metric_name,
                'trend': 'insufficient_data',
                'data_points': len(relevant_metrics),
                'message': f'Insufficient data points ({len(relevant_metrics)}) for trend analysis'
            }
        
        # Extract values and timestamps
        values = [m[metric_name] for m in relevant_metrics]
        timestamps = [datetime.fromisoformat(m['timestamp']) for m in relevant_metrics]
        
        # Calculate trend statistics
        first_value = values[0]
        last_value = values[-1]
        min_value = min(values)
        max_value = max(values)
        avg_value = statistics.mean(values)
        
        # Determine trend direction
        if len(values) >= 3:
            # Simple linear trend calculation
            recent_avg = statistics.mean(values[-3:])
            earlier_avg = statistics.mean(values[:3])
            
            if recent_avg > earlier_avg * 1.05:  # 5% increase
                trend = 'improving'
            elif recent_avg < earlier_avg * 0.95:  # 5% decrease
                trend = 'declining'
            else:
                trend = 'stable'
        else:
            if last_value > first_value:
                trend = 'improving'
            elif last_value < first_value:
                trend = 'declining'
            else:
                trend = 'stable'
        
        return {
            'metric': metric_name,
            'trend': trend,
            'data_points': len(values),
            'time_range_hours': hours,
            'first_value': first_value,
            'last_value': last_value,
            'min_value': min_value,
            'max_value': max_value,
            'average_value': avg_value,
            'change_percent': ((last_value - first_value) / first_value * 100) if first_value != 0 else 0,
            'timestamps': [ts.isoformat() for ts in timestamps],
            'values': values
        }
    
    def generate_monitoring_report(self, hours: int = 24) -> Dict[str, Any]:
        """
        Generate comprehensive monitoring report
        
        Args:
            hours: Number of hours to include in report
            
        Returns:
            Dictionary with monitoring report
        """
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
        
        # Get recent metrics
        recent_metrics = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m['timestamp']) > cutoff_time
        ]
        
        # Get recent alerts
        recent_alerts = [
            alert for alert in self.alert_history
            if datetime.fromisoformat(alert.timestamp) > cutoff_time
        ]
        
        # Calculate summary statistics
        if recent_metrics:
            latest_metrics = recent_metrics[-1]
            
            # Quality score trends
            quality_trends = {}
            for metric in QualityMetric:
                metric_name = f'quality_score_{metric.value}'
                quality_trends[metric.value] = self.get_trend_analysis(metric_name, hours)
            
            # Performance trends
            performance_trends = {
                'success_rate': self.get_trend_analysis('success_rate', hours),
                'processing_time': self.get_trend_analysis('average_processing_time_ms', hours),
                'critical_issues': self.get_trend_analysis('critical_issues_count', hours)
            }
        else:
            latest_metrics = {}
            quality_trends = {}
            performance_trends = {}
        
        # Alert summary
        alert_summary = {
            'total_alerts': len(recent_alerts),
            'critical_alerts': sum(1 for a in recent_alerts if a.severity == 'critical'),
            'error_alerts': sum(1 for a in recent_alerts if a.severity == 'error'),
            'warning_alerts': sum(1 for a in recent_alerts if a.severity == 'warning'),
            'active_alerts': len(self.active_alerts),
            'acknowledged_alerts': sum(1 for a in recent_alerts if a.acknowledged)
        }
        
        report = {
            'report_timestamp': datetime.now(timezone.utc).isoformat(),
            'time_range_hours': hours,
            'data_points': len(recent_metrics),
            'latest_metrics': latest_metrics,
            'quality_trends': quality_trends,
            'performance_trends': performance_trends,
            'alert_summary': alert_summary,
            'recent_alerts': [
                {
                    'rule_id': alert.rule_id,
                    'severity': alert.severity,
                    'message': alert.message,
                    'timestamp': alert.timestamp,
                    'acknowledged': alert.acknowledged
                }
                for alert in recent_alerts
            ],
            'recommendations': self._generate_monitoring_recommendations(
                latest_metrics, quality_trends, performance_trends, alert_summary
            )
        }
        
        return report
    
    def _generate_monitoring_recommendations(self, latest_metrics: Dict[str, Any],
                                           quality_trends: Dict[str, Any],
                                           performance_trends: Dict[str, Any],
                                           alert_summary: Dict[str, Any]) -> List[str]:
        """Generate monitoring recommendations based on current state"""
        recommendations = []
        
        # Check for critical alerts
        if alert_summary['critical_alerts'] > 0:
            recommendations.append(
                f"URGENT: {alert_summary['critical_alerts']} critical alerts require immediate attention"
            )
        
        # Check quality trends
        for metric, trend_data in quality_trends.items():
            if trend_data.get('trend') == 'declining':
                recommendations.append(
                    f"Quality metric '{metric}' is declining. "
                    f"Current: {trend_data.get('last_value', 0):.3f}, "
                    f"Change: {trend_data.get('change_percent', 0):.1f}%"
                )
        
        # Check performance trends
        if performance_trends.get('success_rate', {}).get('trend') == 'declining':
            recommendations.append(
                "Classification success rate is declining. Review failed classifications and error patterns."
            )
        
        if performance_trends.get('processing_time', {}).get('trend') == 'declining':  # Higher time = declining performance
            recommendations.append(
                "Processing time is increasing. Consider performance optimization."
            )
        
        # Check for high error rates
        if latest_metrics.get('failed_classifications', 0) > 0:
            failure_rate = latest_metrics['failed_classifications'] / latest_metrics.get('total_variants', 1)
            if failure_rate > 0.1:  # More than 10% failures
                recommendations.append(
                    f"High failure rate ({failure_rate:.1%}). Investigate classification errors."
                )
        
        # Check for validation issues
        critical_issues = latest_metrics.get('critical_issues_count', 0)
        if critical_issues > 0:
            recommendations.append(
                f"{critical_issues} critical validation issues detected. Review data quality."
            )
        
        if not recommendations:
            recommendations.append("System is operating within normal parameters.")
        
        return recommendations
    
    def acknowledge_alert(self, rule_id: str) -> bool:
        """
        Acknowledge an active alert
        
        Args:
            rule_id: ID of the alert rule to acknowledge
            
        Returns:
            True if alert was acknowledged, False otherwise
        """
        for alert in self.active_alerts:
            if alert.rule_id == rule_id and not alert.acknowledged:
                alert.acknowledged = True
                self.logger.info(f"Alert acknowledged: {rule_id}")
                return True
        
        return False
    
    def clear_acknowledged_alerts(self) -> int:
        """
        Clear acknowledged alerts from active list
        
        Returns:
            Number of alerts cleared
        """
        initial_count = len(self.active_alerts)
        self.active_alerts = [alert for alert in self.active_alerts if not alert.acknowledged]
        cleared_count = initial_count - len(self.active_alerts)
        
        if cleared_count > 0:
            self.logger.info(f"Cleared {cleared_count} acknowledged alerts")
        
        return cleared_count
    
    def export_metrics_history(self, filepath: str, hours: int = 24) -> bool:
        """
        Export metrics history to JSON file
        
        Args:
            filepath: Path to export file
            hours: Number of hours of history to export
            
        Returns:
            True if export successful, False otherwise
        """
        try:
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours)
            
            export_data = {
                'export_timestamp': datetime.now(timezone.utc).isoformat(),
                'time_range_hours': hours,
                'metrics_history': [
                    m for m in self.metrics_history
                    if datetime.fromisoformat(m['timestamp']) > cutoff_time
                ],
                'alert_history': [
                    {
                        'rule_id': alert.rule_id,
                        'severity': alert.severity,
                        'message': alert.message,
                        'metric_value': alert.metric_value,
                        'threshold': alert.threshold,
                        'timestamp': alert.timestamp,
                        'acknowledged': alert.acknowledged
                    }
                    for alert in self.alert_history
                    if datetime.fromisoformat(alert.timestamp) > cutoff_time
                ]
            }
            
            with open(filepath, 'w') as f:
                json.dump(export_data, f, indent=2)
            
            self.logger.info(f"Metrics history exported to {filepath}")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to export metrics history: {str(e)}")
            return False


def main():
    """Example usage of ValidationMonitor"""
    import sys
    from variant_classifier import VariantClassifier, ClassificationConfig
    from variant_validation import VariantValidationSystem
    
    # Set up logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Initialize components
    config = ClassificationConfig.get_default_config()
    classifier = VariantClassifier(config)
    validation_system = VariantValidationSystem(classifier)
    monitor = ValidationMonitor(validation_system)
    
    # Sample variants for monitoring
    sample_variants = [
        {
            'rsid': 'rs1234',
            'gene': 'APOE',
            'clinvar_significance': 'pathogenic',
            'population_frequency': 0.01
        },
        {
            'rsid': 'rs5678',
            'gene': 'BRCA1',
            'clinvar_significance': 'benign',
            'population_frequency': 0.3
        }
    ]
    
    print("Starting validation monitoring...")
    
    # Collect metrics
    metrics = monitor.collect_current_metrics(sample_variants)
    print(f"Collected metrics for {metrics.get('total_variants', 0)} variants")
    
    # Check for alerts
    alerts = monitor.check_alerts(metrics)
    if alerts:
        print(f"Triggered {len(alerts)} alerts:")
        for alert in alerts:
            print(f"  - {alert.severity.upper()}: {alert.message}")
    else:
        print("No alerts triggered")
    
    # Generate monitoring report
    report = monitor.generate_monitoring_report(hours=1)
    print(f"\nMonitoring Report:")
    print(f"  Data points: {report['data_points']}")
    print(f"  Active alerts: {report['alert_summary']['active_alerts']}")
    print(f"  Recommendations: {len(report['recommendations'])}")
    
    for rec in report['recommendations']:
        print(f"    - {rec}")


if __name__ == '__main__':
    main()