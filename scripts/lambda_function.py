#!/usr/bin/env python3
"""Can y
AWS Lambda Function for Medical PDF Report Generation

Enhanced Lambda function for generating precision medicine reports with:
- Robust error handling and validation
- Multiple trigger support (S3, API Gateway, EventBridge)
- Memory optimization for serverless environment
- Comprehensive logging and monitoring
- Template-driven report generation
- Secure file handling and cleanup
"""

import json
import os
import boto3
import logging
from datetime import datetime
import tempfile
import traceback
from typing import Dict, Any, Optional, List
from lambda_pdf_generator import LambdaPDFGenerator

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize AWS clients with error handling
try:
    s3 = boto3.client('s3')
    logger.info("AWS S3 client initialized successfully")
except Exception as e:
    logger.error(f"Failed to initialize S3 client: {e}")
    s3 = None

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """
    Enhanced AWS Lambda handler for PDF generation with comprehensive error handling.
    
    Args:
        event: Lambda event data
        context: Lambda context object
        
    Returns:
        Dict containing status code and response body
        
    Event sources supported:
    - S3 event notification (automatic processing)
    - API Gateway request (on-demand generation)
    - EventBridge scheduled event (batch processing)
    - Direct invocation (testing/manual)
    """
    start_time = datetime.now()
    request_id = context.aws_request_id if hasattr(context, 'aws_request_id') else 'local-test'
    
    logger.info(f"[{request_id}] Lambda invocation started")
    logger.info(f"[{request_id}] Memory limit: {getattr(context, 'memory_limit_in_mb', 'unknown')} MB")
    logger.info(f"[{request_id}] Remaining time: {getattr(context, 'get_remaining_time_in_millis', lambda: 'unknown')()}")
    
    try:
        # Validate S3 client availability
        if s3 is None:
            raise Exception("S3 client not available - check AWS credentials and permissions")
        
        # Log sanitized event (remove sensitive data)
        sanitized_event = _sanitize_event_for_logging(event)
        logger.info(f"[{request_id}] Event type: {_determine_event_type(event)}")
        logger.debug(f"[{request_id}] Sanitized event: {json.dumps(sanitized_event, default=str)}")
        
        # Route to appropriate handler based on event source
        if _is_s3_event(event):
            result = handle_s3_event(event, context, request_id)
        elif _is_api_gateway_event(event):
            result = handle_api_event(event, context, request_id)
        elif _is_eventbridge_event(event):
            result = handle_scheduled_event(event, context, request_id)
        else:
            result = handle_direct_invocation(event, context, request_id)
        
        # Log execution metrics
        execution_time = (datetime.now() - start_time).total_seconds()
        logger.info(f"[{request_id}] Execution completed in {execution_time:.2f}s")
        
        return result
        
    except Exception as e:
        execution_time = (datetime.now() - start_time).total_seconds()
        error_msg = str(e)
        
        logger.error(f"[{request_id}] Lambda execution failed after {execution_time:.2f}s: {error_msg}")
        logger.error(f"[{request_id}] Full traceback: {traceback.format_exc()}")
        
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'X-Request-ID': request_id
            },
            'body': json.dumps({
                'error': error_msg,
                'message': 'PDF generation failed',
                'request_id': request_id,
                'execution_time': execution_time
            })
        }

# Helper functions for event detection and sanitization
def _is_s3_event(event: Dict[str, Any]) -> bool:
    """Check if event is from S3."""
    return ('Records' in event and 
            len(event['Records']) > 0 and 
            event['Records'][0].get('eventSource') == 'aws:s3')

def _is_api_gateway_event(event: Dict[str, Any]) -> bool:
    """Check if event is from API Gateway."""
    return 'body' in event and ('httpMethod' in event or 'requestContext' in event)

def _is_eventbridge_event(event: Dict[str, Any]) -> bool:
    """Check if event is from EventBridge."""
    return 'source' in event and event['source'] == 'aws.events'

def _determine_event_type(event: Dict[str, Any]) -> str:
    """Determine the type of event for logging."""
    if _is_s3_event(event):
        return "S3"
    elif _is_api_gateway_event(event):
        return "API Gateway"
    elif _is_eventbridge_event(event):
        return "EventBridge"
    else:
        return "Direct Invocation"

def _sanitize_event_for_logging(event: Dict[str, Any]) -> Dict[str, Any]:
    """Remove sensitive data from event for safe logging."""
    sanitized = {}
    
    # Copy safe keys
    safe_keys = ['source', 'httpMethod', 'path', 'requestContext', 'Records']
    for key in safe_keys:
        if key in event:
            if key == 'Records' and isinstance(event[key], list):
                # Sanitize S3 records
                sanitized[key] = []
                for record in event[key]:
                    if isinstance(record, dict):
                        sanitized_record = {
                            'eventSource': record.get('eventSource'),
                            'eventName': record.get('eventName'),
                            's3': {
                                'bucket': {'name': record.get('s3', {}).get('bucket', {}).get('name', 'unknown')},
                                'object': {'key': record.get('s3', {}).get('object', {}).get('key', 'unknown')}
                            } if 's3' in record else {}
                        }
                        sanitized[key].append(sanitized_record)
            else:
                sanitized[key] = event[key]
    
    # Add metadata without sensitive content
    if 'body' in event:
        sanitized['has_body'] = True
        sanitized['body_type'] = type(event['body']).__name__
    
    return sanitized

def _validate_environment_variables() -> Dict[str, str]:
    """Validate and return required environment variables."""
    env_vars = {}
    
    # Optional environment variables with defaults
    env_vars['OUTPUT_BUCKET'] = os.environ.get('OUTPUT_BUCKET', 'precision-medicine-reports')
    env_vars['INPUT_BUCKET'] = os.environ.get('INPUT_BUCKET', 'precision-medicine-reports-input')
    env_vars['MAX_FILE_SIZE_MB'] = int(os.environ.get('MAX_FILE_SIZE_MB', '50'))
    env_vars['PRESIGNED_URL_EXPIRY'] = int(os.environ.get('PRESIGNED_URL_EXPIRY', '3600'))
    
    return env_vars

def handle_s3_event(event: Dict[str, Any], context: Any, request_id: str) -> Dict[str, Any]:
    """Handle S3 event notification when JSON files are uploaded."""
    logger.info(f"[{request_id}] Processing S3 event notification")
    
    try:
        # Validate environment variables
        env_vars = _validate_environment_variables()
        
        # Extract bucket and key from S3 event
        record = event['Records'][0]
        bucket = record['s3']['bucket']['name']
        key = record['s3']['object']['key']
        file_size = record['s3']['object'].get('size', 0)
        
        logger.info(f"[{request_id}] Processing file {key} from bucket {bucket} (size: {file_size:,} bytes)")
        
        # Validate file type
        if not key.endswith('.json'):
            logger.warning(f"[{request_id}] Skipping non-JSON file: {key}")
            return {
                'statusCode': 200,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'message': 'Skipped non-JSON file',
                    'file': key,
                    'request_id': request_id
                })
            }
        
        # Validate file size
        max_size_bytes = env_vars['MAX_FILE_SIZE_MB'] * 1024 * 1024
        if file_size > max_size_bytes:
            logger.error(f"[{request_id}] File too large: {file_size:,} bytes (max: {max_size_bytes:,})")
            return {
                'statusCode': 413,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'error': 'File too large',
                    'message': f'File size {file_size:,} bytes exceeds limit of {max_size_bytes:,} bytes',
                    'file': key,
                    'request_id': request_id
                })
            }
        
        # Download JSON file to temporary location
        temp_json_path = f"/tmp/{os.path.basename(key)}"
        s3.download_file(bucket, key, temp_json_path)
        logger.info(f"[{request_id}] Downloaded {key} to {temp_json_path}")
        
        # Load and validate JSON data
        try:
            with open(temp_json_path, 'r') as f:
                json_data = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"[{request_id}] Invalid JSON in file {key}: {e}")
            cleanup_temp_files([temp_json_path], request_id)
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'error': 'Invalid JSON format',
                    'message': f'File {key} contains invalid JSON: {str(e)}',
                    'request_id': request_id
                })
            }
        
        # Validate JSON structure
        validation_result = _validate_json_structure(json_data, request_id)
        if not validation_result['valid']:
            logger.error(f"[{request_id}] Invalid JSON structure: {validation_result['error']}")
            cleanup_temp_files([temp_json_path], request_id)
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'error': 'Invalid JSON structure',
                    'message': validation_result['error'],
                    'file': key,
                    'request_id': request_id
                })
            }
        
        # Extract template path if specified in metadata
        template_path = None
        metadata = json_data.get('report_metadata', {})
        template_key = metadata.get('template_key')
        
        if template_key:
            template_path = f"/tmp/template.json"
            try:
                s3.download_file(bucket, template_key, template_path)
                logger.info(f"Downloaded template {template_key}")
            except Exception as e:
                logger.warning(f"Could not download template {template_key}: {e}")
                template_path = None
        
        # Load template data if available
        template_data = None
        if template_path and os.path.exists(template_path):
            with open(template_path, 'r') as f:
                template_data = json.load(f)
        
        # Generate PDF using Lambda-optimized generator
        generator = LambdaPDFGenerator()
        try:
            base_name = os.path.splitext(os.path.basename(key))[0]
            pdf_filename = f"{base_name}_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
            
            result = generator.generate_pdf_from_json(json_data, pdf_filename, template_data)
            
            if not result['success']:
                raise Exception(f"PDF generation failed: {result['error']}")
            
            pdf_path = result['file_path']
            pdf_size = result['file_size']
            
            # Upload PDF to S3
            output_bucket = os.environ.get('OUTPUT_BUCKET', bucket)
            output_key = f"pdfs/{pdf_filename}"
            
            s3.upload_file(pdf_path, output_bucket, output_key)
            logger.info(f"Uploaded PDF to s3://{output_bucket}/{output_key}")
            
        finally:
            # Clean up temporary files
            generator.cleanup()
            cleanup_temp_files([temp_json_path, template_path])
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'PDF generated successfully',
                'source_file': f"s3://{bucket}/{key}",
                'output_file': f"s3://{output_bucket}/{output_key}",
                'pdf_size': pdf_size
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing S3 event: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def handle_api_event(event: Dict[str, Any], context: Any, request_id: str) -> Dict[str, Any]:
    """Handle API Gateway event for on-demand PDF generation."""
    logger.info(f"[{request_id}] Processing API Gateway event")
    
    try:
        # Validate environment variables
        env_vars = _validate_environment_variables()
        
        # Parse request body with error handling
        try:
            if isinstance(event['body'], str):
                body = json.loads(event['body'])
            else:
                body = event['body']
        except json.JSONDecodeError as e:
            logger.error(f"[{request_id}] Invalid JSON in request body: {e}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'error': 'Invalid JSON in request body',
                    'message': f'Request body contains invalid JSON: {str(e)}',
                    'request_id': request_id
                })
            }
        
        # Extract report data and metadata
        json_data = body.get('report_data', {})
        metadata = body.get('metadata', {})
        template_data = body.get('template', {})
        
        if not json_data:
            logger.error(f"[{request_id}] No report data provided in request")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'error': 'No report data provided',
                    'message': 'Request must include report_data field',
                    'request_id': request_id,
                    'received_keys': list(body.keys())
                })
            }
        
        # Validate JSON structure
        validation_result = _validate_json_structure(json_data, request_id)
        if not validation_result['valid']:
            logger.error(f"[{request_id}] Invalid JSON structure in API request: {validation_result['error']}")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'error': 'Invalid JSON structure',
                    'message': validation_result['error'],
                    'request_id': request_id
                })
            }
        
        # Merge metadata into report data if provided
        if metadata:
            if 'report_metadata' not in json_data:
                json_data['report_metadata'] = {}
            json_data['report_metadata'].update(metadata)
        
        # Generate PDF using Lambda-optimized generator
        generator = LambdaPDFGenerator()
        try:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            patient_name = json_data.get('report_metadata', {}).get('patient_name', 'unknown')
            safe_patient_name = "".join(c for c in patient_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            pdf_filename = f"report_{safe_patient_name}_{timestamp}.pdf"
            
            result = generator.generate_pdf_from_json(json_data, pdf_filename, template_data)
            
            if not result['success']:
                raise Exception(f"PDF generation failed: {result['error']}")
            
            pdf_path = result['file_path']
            file_size = result['file_size']
            
            # Upload PDF to S3
            output_bucket = os.environ.get('OUTPUT_BUCKET', 'precision-medicine-reports')
            output_key = f"api-generated/{pdf_filename}"
            
            s3.upload_file(pdf_path, output_bucket, output_key)
            logger.info(f"Uploaded PDF to s3://{output_bucket}/{output_key}")
            
            # Generate pre-signed URL for download
            download_url = s3.generate_presigned_url(
                'get_object',
                Params={'Bucket': output_bucket, 'Key': output_key},
                ExpiresIn=3600  # URL valid for 1 hour
            )
            
        finally:
            # Clean up temporary files
            generator.cleanup()
        
        return {
            'statusCode': 200,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'message': 'PDF generated successfully',
                'download_url': download_url,
                'file_size': file_size,
                's3_location': f"s3://{output_bucket}/{output_key}",
                'expires_in': 3600
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing API event: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            'body': json.dumps({
                'error': str(e),
                'message': 'PDF generation failed'
            })
        }

def handle_scheduled_event(event: Dict[str, Any], context: Any, request_id: str) -> Dict[str, Any]:
    """Handle EventBridge scheduled event for batch processing."""
    logger.info(f"[{request_id}] Processing scheduled event for batch processing")
    
    try:
        input_bucket = os.environ.get('INPUT_BUCKET', 'precision-medicine-reports-input')
        output_bucket = os.environ.get('OUTPUT_BUCKET', 'precision-medicine-reports')
        
        # List objects in the pending folder
        response = s3.list_objects_v2(Bucket=input_bucket, Prefix='pending/')
        
        if 'Contents' not in response:
            logger.info("No pending reports found")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'No pending reports found',
                    'processed_count': 0
                })
            }
        
        processed_files = []
        failed_files = []
        
        for obj in response['Contents']:
            key = obj['Key']
            if not key.endswith('.json'):
                continue
                
            try:
                logger.info(f"Processing batch file: {key}")
                
                # Download JSON file
                temp_json_path = f"/tmp/{os.path.basename(key)}"
                s3.download_file(input_bucket, key, temp_json_path)
                
                # Load JSON data
                with open(temp_json_path, 'r') as f:
                    json_data = json.load(f)
                
                # Generate PDF using Lambda-optimized generator
                generator = LambdaPDFGenerator()
                try:
                    base_name = os.path.splitext(os.path.basename(key))[0]
                    pdf_filename = f"{base_name}_batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
                    
                    result = generator.generate_pdf_from_json(json_data, pdf_filename)
                    
                    if not result['success']:
                        raise Exception(f"PDF generation failed: {result['error']}")
                    
                    pdf_path = result['file_path']
                    
                    # Upload PDF to output bucket
                    output_key = f"batch-generated/{pdf_filename}"
                    s3.upload_file(pdf_path, output_bucket, output_key)
                    
                finally:
                    # Clean up temporary files
                    generator.cleanup()
                    cleanup_temp_files([temp_json_path])
                
                # Move processed JSON to 'processed' folder
                processed_key = key.replace('pending/', 'processed/')
                s3.copy_object(
                    Bucket=input_bucket,
                    CopySource={'Bucket': input_bucket, 'Key': key},
                    Key=processed_key
                )
                s3.delete_object(Bucket=input_bucket, Key=key)
                
                processed_files.append({
                    'source': key,
                    'output': f"s3://{output_bucket}/{output_key}"
                })
                
                logger.info(f"Successfully processed {key}")
                    
            except Exception as e:
                logger.error(f"Error processing file {key}: {str(e)}")
                
                # Move failed JSON to 'failed' folder
                try:
                    failed_key = key.replace('pending/', 'failed/')
                    s3.copy_object(
                        Bucket=input_bucket,
                        CopySource={'Bucket': input_bucket, 'Key': key},
                        Key=failed_key
                    )
                    s3.delete_object(Bucket=input_bucket, Key=key)
                    
                    failed_files.append({
                        'source': key,
                        'error': str(e)
                    })
                except Exception as move_error:
                    logger.error(f"Error moving failed file {key}: {str(move_error)}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': f'Batch processing completed',
                'processed_count': len(processed_files),
                'failed_count': len(failed_files),
                'processed_files': processed_files,
                'failed_files': failed_files
            })
        }
        
    except Exception as e:
        logger.error(f"Error in batch processing: {str(e)}")
        logger.error(traceback.format_exc())
        raise

def handle_direct_invocation(event: Dict[str, Any], context: Any, request_id: str) -> Dict[str, Any]:
    """Handle direct Lambda invocation with enhanced validation."""
    logger.info(f"[{request_id}] Processing direct invocation")
    
    try:
        # Validate environment variables
        env_vars = _validate_environment_variables()
        logger.info(f"[{request_id}] Environment validated - Output bucket: {env_vars['OUTPUT_BUCKET']}")
        
        # Check if event contains report data
        if 'report_data' in event:
            # Treat as API-like event but add request_id to body
            api_event = {
                'body': {
                    **event,
                    'request_id': request_id
                }
            }
            return handle_api_event(api_event, context, request_id)
        else:
            logger.warning(f"[{request_id}] Invalid direct invocation format")
            return {
                'statusCode': 400,
                'headers': {
                    'Content-Type': 'application/json',
                    'X-Request-ID': request_id
                },
                'body': json.dumps({
                    'error': 'Invalid event format',
                    'message': 'Event must contain report_data or be from S3/API Gateway',
                    'received_keys': list(event.keys()),
                    'request_id': request_id,
                    'expected_format': {
                        'report_data': {
                            'report_metadata': {'patient_name': 'string', 'patient_id': 'string'},
                            'blocks': {'block_name': {'content': 'string'}}
                        }
                    }
                })
            }
    except Exception as e:
        logger.error(f"[{request_id}] Error in direct invocation: {str(e)}")
        return {
            'statusCode': 500,
            'headers': {
                'Content-Type': 'application/json',
                'X-Request-ID': request_id
            },
            'body': json.dumps({
                'error': str(e),
                'message': 'Direct invocation failed',
                'request_id': request_id
            })
        }

def cleanup_temp_files(file_paths: List[Optional[str]], request_id: str = "unknown") -> None:
    """Clean up temporary files with enhanced logging."""
    if not file_paths:
        return
        
    cleaned_count = 0
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                file_size = os.path.getsize(file_path)
                os.remove(file_path)
                cleaned_count += 1
                logger.info(f"[{request_id}] Cleaned up temporary file: {file_path} ({file_size:,} bytes)")
            except Exception as e:
                logger.warning(f"[{request_id}] Could not clean up {file_path}: {e}")
    
    logger.info(f"[{request_id}] Cleanup completed: {cleaned_count}/{len([f for f in file_paths if f])} files removed")

def _validate_json_structure(json_data: Dict[str, Any], request_id: str) -> Dict[str, Any]:
    """Validate JSON structure for PDF generation."""
    try:
        if not isinstance(json_data, dict):
            return {'valid': False, 'error': 'JSON data must be a dictionary'}
        
        # Check for required top-level keys
        if 'report_metadata' not in json_data and 'blocks' not in json_data:
            return {'valid': False, 'error': 'JSON must contain either report_metadata or blocks'}
        
        # Validate report_metadata if present
        if 'report_metadata' in json_data:
            metadata = json_data['report_metadata']
            if not isinstance(metadata, dict):
                return {'valid': False, 'error': 'report_metadata must be a dictionary'}
            
            # Check for recommended metadata fields
            recommended_fields = ['patient_name', 'patient_id', 'provider_name', 'report_date']
            missing_fields = [field for field in recommended_fields if field not in metadata]
            if missing_fields:
                logger.warning(f"[{request_id}] Missing recommended metadata fields: {missing_fields}")
        
        # Validate blocks if present
        if 'blocks' in json_data:
            blocks = json_data['blocks']
            if not isinstance(blocks, dict):
                return {'valid': False, 'error': 'blocks must be a dictionary'}
            
            # Check if at least one block has content
            content_blocks = 0
            for block_name, block_data in blocks.items():
                if isinstance(block_data, dict) and 'content' in block_data:
                    if block_data['content']:  # Not empty
                        content_blocks += 1
            
            if content_blocks == 0:
                logger.warning(f"[{request_id}] No blocks with content found")
            else:
                logger.info(f"[{request_id}] Found {content_blocks} blocks with content")
        
        return {'valid': True, 'error': None}
        
    except Exception as e:
        return {'valid': False, 'error': f'Validation error: {str(e)}'}

def _get_lambda_metrics(context: Any) -> Dict[str, Any]:
    """Extract Lambda execution metrics."""
    metrics = {}
    
    try:
        if hasattr(context, 'memory_limit_in_mb'):
            metrics['memory_limit_mb'] = int(context.memory_limit_in_mb)
        
        if hasattr(context, 'get_remaining_time_in_millis'):
            metrics['remaining_time_ms'] = context.get_remaining_time_in_millis()
        
        if hasattr(context, 'function_name'):
            metrics['function_name'] = context.function_name
        
        if hasattr(context, 'function_version'):
            metrics['function_version'] = context.function_version
            
    except Exception as e:
        logger.warning(f"Could not extract Lambda metrics: {e}")
    
    return metrics

# For local testing
if __name__ == "__main__":
    # Test event for local development
    test_event = {
        "report_data": {
            "report_metadata": {
                "patient_name": "Test Patient",
                "patient_id": "TEST001",
                "provider_name": "Dr. Test",
                "report_date": "2025-01-16",
                "focus": "ADHD"
            },
            "blocks": {
                "executive_summary": {
                    "content": '{"executive_summary": {"summary_statement": "Test summary for local development"}}'
                }
            }
        }
    }
    
    test_context = type('Context', (), {
        'function_name': 'test-pdf-generator',
        'function_version': '$LATEST',
        'invoked_function_arn': 'arn:aws:lambda:us-east-1:123456789012:function:test-pdf-generator',
        'memory_limit_in_mb': '1024',
        'remaining_time_in_millis': lambda: 60000
    })()
    
    result = lambda_handler(test_event, test_context)
    print(json.dumps(result, indent=2))