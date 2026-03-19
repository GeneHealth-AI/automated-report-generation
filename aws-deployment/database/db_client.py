"""
Database client for Genetic Report Generation System.
Handles connections to PostgreSQL RDS and provides helper methods for database operations.
"""

import os
import json
import logging
import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from typing import Dict, List, Optional, Any
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class DatabaseClient:
    """PostgreSQL database client with AWS Secrets Manager integration."""

    def __init__(self, secret_arn: Optional[str] = None):
        """
        Initialize database client.

        Args:
            secret_arn: ARN of the AWS Secrets Manager secret containing DB credentials.
                       If not provided, will try to get from environment variable DB_SECRET_ARN.
        """
        self.secret_arn = secret_arn or os.environ.get('DB_SECRET_ARN')
        self._connection = None
        self._credentials = None

    def _get_db_credentials(self) -> Dict[str, str]:
        """Fetch database credentials from AWS Secrets Manager."""
        if self._credentials:
            return self._credentials

        if not self.secret_arn:
            # Fallback to environment variables
            self._credentials = {
                'host': os.environ.get('DB_HOST'),
                'port': int(os.environ.get('DB_PORT', 5432)),
                'dbname': os.environ.get('DB_NAME'),
                'username': os.environ.get('DB_USERNAME'),
                'password': os.environ.get('DB_PASSWORD')
            }
            logger.info("Using database credentials from environment variables")
            return self._credentials

        try:
            secrets_client = boto3.client('secretsmanager')
            response = secrets_client.get_secret_value(SecretId=self.secret_arn)
            secret = json.loads(response['SecretString'])

            self._credentials = {
                'host': secret['host'],
                'port': int(secret.get('port', 5432)),
                'dbname': secret['dbname'],
                'username': secret['username'],
                'password': secret['password']
            }
            logger.info(f"Retrieved database credentials from Secrets Manager: {self.secret_arn}")
            return self._credentials

        except ClientError as e:
            logger.error(f"Error retrieving database credentials: {e}")
            raise

    @contextmanager
    def get_connection(self):
        """
        Context manager for database connections.

        Usage:
            with db_client.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM table")
        """
        credentials = self._get_db_credentials()

        conn = psycopg2.connect(
            host=credentials['host'],
            port=credentials['port'],
            dbname=credentials['dbname'],
            user=credentials['username'],
            password=credentials['password'],
            connect_timeout=10
        )

        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()

    def create_patient(self, external_id: str, patient_name: str = None, **kwargs) -> str:
        """
        Create a new patient record.

        Args:
            external_id: External patient ID
            patient_name: Patient name
            **kwargs: Additional patient fields (email, phone, etc.)

        Returns:
            UUID of the created patient
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            metadata = {k: v for k, v in kwargs.items()
                       if k not in ['external_id', 'patient_name', 'date_of_birth', 'gender', 'email', 'phone']}

            cursor.execute("""
                INSERT INTO reports.patients (
                    external_id, patient_name, date_of_birth, gender, email, phone, metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (external_id) DO UPDATE
                SET patient_name = EXCLUDED.patient_name,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING patient_id
            """, (
                external_id,
                patient_name,
                kwargs.get('date_of_birth'),
                kwargs.get('gender'),
                kwargs.get('email'),
                kwargs.get('phone'),
                json.dumps(metadata)
            ))

            patient_id = cursor.fetchone()[0]
            logger.info(f"Created/updated patient: {patient_id}")
            return str(patient_id)

    def create_provider(self, provider_name: str, **kwargs) -> str:
        """
        Create a new provider record.

        Args:
            provider_name: Provider name
            **kwargs: Additional provider fields

        Returns:
            UUID of the created provider
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO reports.providers (
                    provider_name, organization, email, phone, license_number, specialization
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING provider_id
            """, (
                provider_name,
                kwargs.get('organization'),
                kwargs.get('email'),
                kwargs.get('phone'),
                kwargs.get('license_number'),
                kwargs.get('specialization')
            ))

            provider_id = cursor.fetchone()[0]
            logger.info(f"Created provider: {provider_id}")
            return str(provider_id)

    def create_report_request(
        self,
        patient_id: str,
        vcf_s3_path: str,
        annotated_vcf_s3_path: str = None,
        provider_id: str = None,
        focus: str = None,
        **kwargs
    ) -> str:
        """
        Create a new report request.

        Args:
            patient_id: UUID of the patient
            vcf_s3_path: S3 path to VCF file
            annotated_vcf_s3_path: S3 path to annotated VCF file
            provider_id: UUID of the provider (optional)
            focus: Report focus (e.g., "ADHD", "Cardiovascular")
            **kwargs: Additional request fields

        Returns:
            UUID of the created request
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO reports.report_requests (
                    patient_id, provider_id, vcf_s3_path, annotated_vcf_s3_path,
                    focus, family_history, template_s3_path, request_type, request_metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING request_id
            """, (
                patient_id,
                provider_id,
                vcf_s3_path,
                annotated_vcf_s3_path,
                focus,
                kwargs.get('family_history'),
                kwargs.get('template_s3_path'),
                kwargs.get('request_type', 'full_report'),
                json.dumps(kwargs.get('request_metadata', {}))
            ))

            request_id = cursor.fetchone()[0]
            logger.info(f"Created report request: {request_id}")
            return str(request_id)

    def update_report_status(
        self,
        request_id: str,
        status: str,
        ecs_task_arn: str = None,
        error_message: str = None
    ):
        """
        Update the status of a report request.

        Args:
            request_id: UUID of the request
            status: New status (pending, processing, completed, failed)
            ecs_task_arn: ECS task ARN (for processing status)
            error_message: Error message (for failed status)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            update_fields = ['status = %s']
            params = [status]

            if status == 'processing':
                update_fields.append('started_at = CURRENT_TIMESTAMP')
                if ecs_task_arn:
                    update_fields.append('ecs_task_arn = %s')
                    params.append(ecs_task_arn)

            elif status == 'completed':
                update_fields.append('completed_at = CURRENT_TIMESTAMP')

            elif status == 'failed':
                if error_message:
                    update_fields.append('error_message = %s')
                    params.append(error_message)
                update_fields.append('retry_count = retry_count + 1')

            params.append(request_id)

            query = f"""
                UPDATE reports.report_requests
                SET {', '.join(update_fields)}
                WHERE request_id = %s
            """

            cursor.execute(query, params)
            logger.info(f"Updated request {request_id} status to {status}")

    def save_generated_report(
        self,
        request_id: str,
        report_type: str,
        s3_bucket: str,
        s3_key: str,
        file_size_bytes: int = None,
        generation_time_seconds: float = None
    ) -> str:
        """
        Save metadata about a generated report.

        Args:
            request_id: UUID of the request
            report_type: Type of report (pdf, json, html)
            s3_bucket: S3 bucket name
            s3_key: S3 object key
            file_size_bytes: Size of the generated file
            generation_time_seconds: Time taken to generate the report

        Returns:
            UUID of the report record
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            s3_uri = f"s3://{s3_bucket}/{s3_key}"

            cursor.execute("""
                INSERT INTO reports.generated_reports (
                    request_id, report_type, report_format, s3_bucket, s3_key, s3_uri,
                    file_size_bytes, generation_time_seconds
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING report_id
            """, (
                request_id,
                report_type,
                'standard',  # Can be made configurable
                s3_bucket,
                s3_key,
                s3_uri,
                file_size_bytes,
                generation_time_seconds
            ))

            report_id = cursor.fetchone()[0]
            logger.info(f"Saved generated report: {report_id}")
            return str(report_id)

    def log_api_usage(
        self,
        request_id: str,
        api_provider: str,
        tokens_input: int = None,
        tokens_output: int = None,
        estimated_cost: float = None,
        **kwargs
    ):
        """
        Log API usage for cost tracking.

        Args:
            request_id: UUID of the request
            api_provider: API provider name (anthropic, gemini)
            tokens_input: Number of input tokens
            tokens_output: Number of output tokens
            estimated_cost: Estimated cost in USD
            **kwargs: Additional fields (api_model, status, etc.)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                INSERT INTO reports.api_usage (
                    request_id, api_provider, api_model, tokens_input, tokens_output,
                    tokens_total, estimated_cost_usd, status, usage_metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                request_id,
                api_provider,
                kwargs.get('api_model'),
                tokens_input,
                tokens_output,
                (tokens_input or 0) + (tokens_output or 0),
                estimated_cost,
                kwargs.get('status', 'success'),
                json.dumps(kwargs.get('metadata', {}))
            ))

            logger.info(f"Logged API usage for request {request_id}: {api_provider}")

    def get_report_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a report request by ID.

        Args:
            request_id: UUID of the request

        Returns:
            Dictionary with request details or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

            cursor.execute("""
                SELECT
                    rr.*,
                    p.external_id as patient_external_id,
                    p.patient_name,
                    pr.provider_name
                FROM reports.report_requests rr
                LEFT JOIN reports.patients p ON rr.patient_id = p.patient_id
                LEFT JOIN reports.providers pr ON rr.provider_id = pr.provider_id
                WHERE rr.request_id = %s
            """, (request_id,))

            result = cursor.fetchone()
            return dict(result) if result else None


# Example usage
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    # Initialize client
    db = DatabaseClient()

    # Example: Create a patient and report request
    patient_id = db.create_patient(
        external_id="PATIENT-12345",
        patient_name="John Doe",
        email="john.doe@example.com"
    )

    request_id = db.create_report_request(
        patient_id=patient_id,
        vcf_s3_path="s3://bucket/vcf/patient-12345.vcf",
        annotated_vcf_s3_path="s3://bucket/vcf/patient-12345-annotated.vcf",
        focus="ADHD"
    )

    print(f"Created request: {request_id}")
