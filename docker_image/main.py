import boto3
import botocore
from botocore.exceptions import ClientError
import tensorflow as tf
import numpy as np
import cv2
import sklearn
import skimage
import json
import argparse
import os
import time
import uuid
from datetime import datetime
import re

class CloudWatchLogger:
    def __init__(self, log_group, log_stream, region='eu-north-1'):
        self.logs_client = boto3.client('logs', region_name=region)
        self.log_group = log_group
        self.log_stream = log_stream
        self.sequence_token = None
        self._ensure_log_group_exists()
        self._create_log_stream()
    
    def _ensure_log_group_exists(self):
        """Ensure the log group exists."""
        try:
            self.logs_client.describe_log_groups(logGroupNamePrefix=self.log_group)
        except ClientError:
            self.logs_client.create_log_group(logGroupName=self.log_group)
    
    def _create_log_stream(self):
        """Create the log stream."""
        try:
            self.logs_client.create_log_stream(
                logGroupName=self.log_group,
                logStreamName=self.log_stream
            )
        except ClientError:
            pass  # Stream might already exist
    
    def log(self, message, level='INFO'):
        """Send a log message to CloudWatch."""
        timestamp = int(time.time() * 1000)
        log_event = {
            'timestamp': timestamp,
            'message': f"[{level}] {message}"
        }
        
        try:
            if self.sequence_token:
                response = self.logs_client.put_log_events(
                    logGroupName=self.log_group,
                    logStreamName=self.log_stream,
                    logEvents=[log_event],
                    sequenceToken=self.sequence_token
                )
            else:
                response = self.logs_client.put_log_events(
                    logGroupName=self.log_group,
                    logStreamName=self.log_stream,
                    logEvents=[log_event]
                )
            self.sequence_token = response.get('nextSequenceToken')
        except ClientError as e:
            print(f"Failed to log to CloudWatch: {e}")


def _is_image_file(key):
    """Check if the file is an image based on its extension."""
    return key.lower().endswith(('.png', '.jpg', '.jpeg'))


def _process_single_image(s3_client, bucket, key, logger=None):
    """Process a single image file from S3."""
    if logger:
        logger.log(f"Processing image: {key}")
    
    try:
        # Read image file from S3
        image_obj = s3_client.get_object(Bucket=bucket, Key=key)
        image_data = image_obj['Body'].read()
        
        # Decode image using OpenCV
        np_array = np.frombuffer(image_data, np.uint8)
        img = cv2.imdecode(np_array, cv2.IMREAD_COLOR)

        if img is not None:
            height, width, channels = img.shape
            result = {
                'key': key,
                'status': 'success',
                'height': height,
                'width': width,
                'channels': channels
            }
            if logger:
                logger.log(f"Successfully processed: {key} ({width}x{height})")
            return result, 'success'
        else:
            result = {'key': key, 'status': 'error', 'reason': 'Could not decode image'}
            if logger:
                logger.log(f"Failed to decode image: {key}", 'ERROR')
            return result, 'error'

    except ClientError as e:
        result = {'key': key, 'status': 'error', 'reason': str(e)}
        if logger:
            logger.log(f"Error processing {key}: {str(e)}", 'ERROR')
        return result, 'error'


def process_images_from_s3(s3_client, bucket, prefix, logger=None):
    """
    Lists, reads, and processes images from a given S3 prefix.
    """
    processed_images = []
    if not prefix:
        if logger:
            logger.log("No prefix provided, skipping image processing")
        return processed_images

    if logger:
        logger.log(f"Starting image processing from bucket: {bucket}, prefix: {prefix}")

    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)

    total_files = 0
    processed_count = 0
    error_count = 0

    for page in pages:
        if 'Contents' in page:
            for obj in page['Contents']:
                key = obj['Key']
                total_files += 1
                
                # Filter for image files
                if _is_image_file(key):
                    result, status = _process_single_image(s3_client, bucket, key, logger)
                    processed_images.append(result)
                    
                    if status == 'success':
                        processed_count += 1
                    else:
                        error_count += 1
    
    if logger:
        logger.log(f"Image processing complete. Total: {total_files}, Processed: {processed_count}, Errors: {error_count}")
    
    return processed_images

def fetch_s3_object(bucket, key):
    """
    Fetches an object from S3 and prints its content.
    """
    s3 = boto3.client('s3')
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        content = response['Body'].read().decode('utf-8')
        print("--- File Content ---")
        print(content)
        print("--------------------")
    except ClientError as e:
        print(f"Error fetching object from S3: {e}")

def list_and_group_images(input_bucket, input_prefix, region):
    s3 = boto3.client('s3', region_name=region)
    paginator = s3.get_paginator('list_objects_v2')
    regex = re.compile(r'(V|I)[1-6](xM|\dU)@.*\.jpg$')
    grouped = {}
    found_any = False
    for page in paginator.paginate(Bucket=input_bucket, Prefix=input_prefix):
        for obj in page.get('Contents', []):
            key = obj['Key']
            filename = os.path.basename(key)
            m = regex.match(filename)
            if m:
                found_any = True
                prefix = filename[2:]  # part after first two chars
                vi = m.group(1)
                grouped.setdefault(prefix, {'V': [], 'I': []})
                grouped[prefix][vi].append(key)
    return grouped, found_any

def validate_and_log_groups(grouped, found_any, logger):
    valid = {}
    if not found_any:
        logger.log('No images matched the regex in the input folder.', level='ERROR')
        return valid
    all_valid = True
    for prefix, vi_dict in grouped.items():
        v_count = len(vi_dict['V'])
        i_count = len(vi_dict['I'])
        if v_count == 6 and i_count == 6:
            valid[prefix] = vi_dict
        else:
            logger.log(f"Entry '{prefix}' does not have required count: V={v_count}, I={i_count}", level='WARNING')
            all_valid = False
    if valid and all_valid:
        logger.log('All entries have 6 V-images and 6 I-images.', level='INFO')
    elif valid:
        logger.log('Some entries are valid, some are missing images.', level='INFO')
    else:
        logger.log('No entry has the required count of V and I images.', level='ERROR')
    return valid

def _parse_arguments():
    """Parse command line arguments and environment variables."""
    parser = argparse.ArgumentParser(description='A test script for AWS earbox image processing.')
    parser.add_argument('--input-bucket', required=False, help='S3 bucket for input files.')
    parser.add_argument('--output-bucket', required=False, help='S3 bucket for output files.')
    parser.add_argument('--input-prefix', required=False, help='S3 prefix for input images to process.')
    parser.add_argument('--output-key', required=False, help='S3 key for the output JSON file.')
    parser.add_argument('--log-group', required=False, help='CloudWatch log group name.')
    parser.add_argument('--log-stream', required=False, help='CloudWatch log stream name.')

    args = parser.parse_args()

    # S3 buckets from args or environment
    input_bucket = args.input_bucket or os.getenv('INPUT_BUCKET')
    output_bucket = args.output_bucket or os.getenv('OUTPUT_BUCKET')
    input_prefix = args.input_prefix or os.getenv('INPUT_PREFIX', 'input_folder/')
    output_key = args.output_key or os.getenv('OUTPUT_KEY', 'test_output.json')
    log_group = args.log_group or os.getenv('LOG_GROUP', '/aws/ec2/earbox-processing')
    log_stream = args.log_stream or os.getenv('LOG_STREAM', f'earbox-job-{datetime.now().strftime("%Y%m%d-%H%M%S")}-{uuid.uuid4().hex[:8]}')

    if not input_bucket or not output_bucket:
        parser.error('You must specify --input-bucket and --output-bucket (or set INPUT_BUCKET and OUTPUT_BUCKET env vars)')

    return {
        'input_bucket': input_bucket,
        'output_bucket': output_bucket,
        'input_prefix': input_prefix,
        'output_key': output_key,
        'log_group': log_group,
        'log_stream': log_stream
    }


def _setup_logging(config):
    """Setup CloudWatch logging."""
    region = os.getenv('AWS_REGION', 'eu-north-1')
    logger = CloudWatchLogger(config['log_group'], config['log_stream'], region)
    
    logger.log(f"Starting batch processing job")
    logger.log(f"Input bucket: {config['input_bucket']}, Output bucket: {config['output_bucket']}")
    logger.log(f"Input prefix: {config['input_prefix']}, Output key: {config['output_key']}")
    
    return logger


def _read_input_file(s3_client, input_bucket, file_key, logger):
    """Read input file from S3."""
    logger.log(f"Reading input file: {file_key}")
    try:
        response = s3_client.get_object(Bucket=input_bucket, Key=file_key)
        testfile_content = response['Body'].read().decode('utf-8')
        logger.log(f"Successfully read input file: {file_key} ({len(testfile_content)} characters)")
        return testfile_content
    except ClientError as e:
        testfile_content = f'Error reading input file: {str(e)}'
        logger.log(f"Error reading input file {file_key}: {str(e)}", 'ERROR')
        return testfile_content


def _collect_module_versions(logger):
    """Collect and log module version information."""
    logger.log("Checking module versions...")
    try:
        skimage_version = getattr(skimage, "__version__", None)
        if skimage_version is None:
            import pkg_resources
            skimage_version = pkg_resources.get_distribution("scikit-image").version
    except Exception:
        skimage_version = 'unknown'
        logger.log("Could not determine scikit-image version", 'WARNING')
    
    module_versions = {
        "tensorflow": tf.__version__,
        "numpy": np.__version__,
        "opencv-python": cv2.__version__,
        "scikit-learn": sklearn.__version__,
        "scikit-image": skimage_version,
        "boto3": boto3.__version__,
        "botocore": botocore.__version__
    }
    
    logger.log(f"Module versions collected: TensorFlow={tf.__version__}, NumPy={np.__version__}")
    return module_versions


def _check_gpu_availability(logger):
    """Check and log GPU availability."""
    logger.log("Checking GPU availability...")
    try:
        gpus = tf.config.list_physical_devices('GPU')
        gpu_info = [str(gpu) for gpu in gpus]
        logger.log(f"GPUs available: {len(gpus)} - {gpu_info}")
        return gpu_info
    except Exception as e:
        error_msg = f"Error checking GPUs: {e}"
        logger.log(error_msg, 'ERROR')
        return error_msg


def _write_results_to_s3(s3_client, output_bucket, output_key, module_versions, testfile_content, processed_images, logger, valid_groups=None):
    """Write results to S3."""
    logger.log(f"Writing results to S3: {output_bucket}/{output_key}")
    
    # Add additional data to module_versions
    module_versions.update({
        "testfile_content": testfile_content,
        "processed_images": processed_images
    })
    if valid_groups is not None:
        module_versions["valid_groups"] = valid_groups
    
    try:
        s3_client.put_object(
            Bucket=output_bucket, 
            Key=output_key, 
            Body=json.dumps(module_versions, indent=4)
        )
        logger.log(f"Successfully wrote results to S3: {output_bucket}/{output_key}")
        print('Successfully wrote module versions to output bucket')
    except ClientError as e:
        logger.log(f"Error writing output file: {str(e)}", 'ERROR')
        print(f'Error writing output file: {str(e)}')


def main():
    # Parse arguments and setup
    config = _parse_arguments()
    logger = _setup_logging(config)
    s3_client = boto3.client('s3')

    # Read input file
    testfile_content = _read_input_file(s3_client, config['input_bucket'], config['input_prefix'] + 'session_para', logger)

    # Collect system information
    module_versions = _collect_module_versions(logger)
    gpu_info = _check_gpu_availability(logger)
    module_versions["GPUs_available"] = gpu_info

    grouped, found_any = list_and_group_images(config['input_bucket'], config['input_prefix'], os.getenv('AWS_REGION', 'eu-north-1'))
    valid_groups = validate_and_log_groups(grouped, found_any, logger)

    # Process images
    logger.log("Starting image processing...")
    processed_images = process_images_from_s3(s3_client, config['input_bucket'], config['input_prefix'], logger)

    # Write results
    _write_results_to_s3(s3_client, config['output_bucket'], config['output_key'], 
                        module_versions, testfile_content, processed_images, logger, valid_groups)

    # Log the output file URL
    s3_url = f"s3://{config['output_bucket']}/{config['output_key']}"
    console_url = f"https://console.aws.amazon.com/s3/object/{config['output_bucket']}/{config['output_key']}"
    logger.log(f"Results written to: {s3_url}")
    logger.log(f"View in AWS Console: {console_url}")

    logger.log("Job completed successfully")
    fetch_s3_object(config['output_bucket'], config['output_key'])

if __name__ == "__main__":
    main()
