#!/usr/bin/env python3
"""
Simple test script to verify CloudWatch logging and create log group.
"""
import boto3
import json
import time
from datetime import datetime
import argparse


def load_config(config_file='../config.json'):
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Config file '{config_file}' not found")
        return None


def test_cloudwatch_logging(region=None, log_group=None, log_stream_prefix=None, config_file=None):
    """Test CloudWatch logging functionality."""
    config = load_config(config_file) if config_file else load_config()
    if not config:
        return
    
    # Get CloudWatch configuration, with CLI args overriding config
    log_group = log_group or config['cloudwatch']['log_group']
    log_stream_prefix = log_stream_prefix or config['cloudwatch']['log_stream_prefix']
    region = region or config['environment']['region']
    
    # Create unique log stream name
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_stream = f"{log_stream_prefix}{timestamp}-test"
    
    print(f"[INFO] Testing CloudWatch logging:")
    print(f"  Log group: {log_group}")
    print(f"  Log stream: {log_stream}")
    print(f"  Region: {region}")
    
    try:
        # Create CloudWatch logs client
        logs_client = boto3.client('logs', region_name=region)
        
        # Create log group if it doesn't exist
        try:
            logs_client.create_log_group(logGroupName=log_group)
            print(f"[INFO] Created log group: {log_group}")
        except logs_client.exceptions.ResourceAlreadyExistsException:
            print(f"[INFO] Log group already exists: {log_group}")
        except Exception as e:
            print(f"[ERROR] Failed to create log group: {e}")
            return
        
        # Create log stream
        try:
            logs_client.create_log_stream(
                logGroupName=log_group,
                logStreamName=log_stream
            )
            print(f"[INFO] Created log stream: {log_stream}")
        except Exception as e:
            print(f"[ERROR] Failed to create log stream: {e}")
            return
        
        # Send test log messages
        test_messages = [
            "CloudWatch logging test started",
            "This is a test message from the batch processing system",
            "Testing log group and stream creation",
            "CloudWatch logging test completed successfully"
        ]
        
        sequence_token = None
        for i, message in enumerate(test_messages):
            timestamp = int(time.time() * 1000)
            log_event = {
                'timestamp': timestamp,
                'message': f"[TEST] {message}"
            }
            
            try:
                if sequence_token:
                    response = logs_client.put_log_events(
                        logGroupName=log_group,
                        logStreamName=log_stream,
                        logEvents=[log_event],
                        sequenceToken=sequence_token
                    )
                else:
                    response = logs_client.put_log_events(
                        logGroupName=log_group,
                        logStreamName=log_stream,
                        logEvents=[log_event]
                    )
                sequence_token = response.get('nextSequenceToken')
                print(f"[INFO] Sent log message {i+1}/{len(test_messages)}")
                
            except Exception as e:
                print(f"[ERROR] Failed to send log message: {e}")
                return
        
        print(f"[SUCCESS] CloudWatch logging test completed!")
        print(f"[INFO] You can now view logs with:")
        print(f"  python view_logs.py --log-stream {log_stream}")
        
    except Exception as e:
        print(f"[ERROR] CloudWatch test failed: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Test CloudWatch logging functionality.')
    parser.add_argument('--config', default='../config.json', help='Configuration file (default: ../config.json)')
    parser.add_argument('--region', help='AWS region (overrides config)')
    parser.add_argument('--log-group', help='CloudWatch log group name (overrides config)')
    parser.add_argument('--log-stream-prefix', help='CloudWatch log stream prefix (overrides config)')
    args = parser.parse_args()
    test_cloudwatch_logging(
        region=args.region,
        log_group=args.log_group,
        log_stream_prefix=args.log_stream_prefix,
        config_file=args.config
    ) 