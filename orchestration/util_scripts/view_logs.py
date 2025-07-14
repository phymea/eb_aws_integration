#!/usr/bin/env python3
"""
Simple script to view CloudWatch logs from batch processing jobs.
"""
import argparse
import boto3
import json
from datetime import datetime, timedelta
import time


def assume_role(role_arn, session_name, base_profile=None, region=None):
    base_session = boto3.Session(profile_name=base_profile, region_name=region) if base_profile else boto3.Session(region_name=region)
    sts = base_session.client('sts')
    response = sts.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name
    )
    creds = response['Credentials']
    return boto3.Session(
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
        region_name=region
    )


def view_logs(log_group, log_stream=None, region='eu-north-1', session=None, hours=1):
    """View CloudWatch logs for the specified log group and stream."""
    logs_client = session.client('logs')
    
    # Calculate start time (default: 1 hour ago)
    start_time = int((datetime.now() - timedelta(hours=hours)).timestamp() * 1000)
    
    print(f"[INFO] Fetching logs from {log_group}")
    print(f"[INFO] Start time: {datetime.fromtimestamp(start_time/1000)}")
    
    try:
        # First, check if the log group exists
        try:
            logs_client.describe_log_groups(logGroupNamePrefix=log_group)
        except Exception as e:
            if "ResourceNotFoundException" in str(e) or "does not exist" in str(e):
                print(f"[ERROR] Log group '{log_group}' does not exist.")
                print("[INFO] This usually means:")
                print("  1. No batch processing jobs have been run yet")
                print("  2. The log group name is different")
                print("  3. You're looking in the wrong region")
                print("\n[INFO] Try running a job first, or check available log groups:")
                _list_available_log_groups(logs_client)
                return
            else:
                raise e
        
        if log_stream:
            # Get specific log stream
            response = logs_client.get_log_events(
                logGroupName=log_group,
                logStreamName=log_stream,
                startTime=start_time
            )
            
            print(f"\n=== Log Stream: {log_stream} ===")
            for event in response['events']:
                timestamp = datetime.fromtimestamp(event['timestamp']/1000)
                print(f"[{timestamp}] {event['message']}")
                
        else:
            # List all log streams and get recent events
            response = logs_client.describe_log_streams(
                logGroupName=log_group,
                orderBy='LastEventTime',
                descending=True,
                limit=10
            )
            
            if not response['logStreams']:
                print(f"[INFO] No log streams found in '{log_group}'")
                print("[INFO] This might mean:")
                print("  1. No jobs have completed yet")
                print("  2. Jobs are still running")
                print("  3. Logs are in a different time range")
                return
            
            print(f"\n=== Recent Log Streams ===")
            for stream in response['logStreams']:
                print(f"\n--- Stream: {stream['logStreamName']} ---")
                print(f"Last Event: {datetime.fromtimestamp(stream['lastEventTimestamp']/1000)}")
                
                # Get events from this stream
                events_response = logs_client.get_log_events(
                    logGroupName=log_group,
                    logStreamName=stream['logStreamName'],
                    startTime=start_time,
                    limit=20
                )
                
                for event in events_response['events']:
                    timestamp = datetime.fromtimestamp(event['timestamp']/1000)
                    print(f"[{timestamp}] {event['message']}")
                    
    except Exception as e:
        print(f"Error fetching logs: {e}")


def _list_available_log_groups(logs_client):
    """List available log groups to help user find the correct one."""
    try:
        response = logs_client.describe_log_groups(limit=10)
        if response['logGroups']:
            print("\n[INFO] Available log groups:")
            for group in response['logGroups']:
                print(f"  - {group['logGroupName']}")
        else:
            print("\n[INFO] No log groups found in this region/account")
    except Exception as e:
        print(f"[ERROR] Could not list log groups: {e}")


def load_config(config_file='config.json'):
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[WARNING] Config file '{config_file}' not found, using defaults")
        return {}
    except json.JSONDecodeError as e:
        print(f"[ERROR] Invalid JSON in config file: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(description='View CloudWatch logs from batch processing')
    parser.add_argument('--log-group', help='CloudWatch log group name (overrides config)')
    parser.add_argument('--log-stream', help='Specific log stream name (optional)')
    parser.add_argument('--region', help='AWS region (overrides config)')
    parser.add_argument('--base-profile', help='AWS base profile for initial STS call (overrides config)')
    parser.add_argument('--hours', type=int, default=1, 
                       help='Hours to look back (default: 1)')
    parser.add_argument('--config', default='../config.json', 
                       help='Configuration file (default: ../config.json)')
    
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Get values from config or use defaults
    log_group = args.log_group or config.get('cloudwatch', {}).get('log_group', '/aws/ec2/batch-processing')
    region = args.region or config.get('environment', {}).get('region', 'eu-north-1')
    automation_role_arn = config.get('automation_role_arn') or config.get('iam', {}).get('automation_role_arn')
    base_profile = args.base_profile or config.get('base_profile') or config.get('iam', {}).get('base_profile')
    if not automation_role_arn:
        print('[ERROR] automation_role_arn must be set in config.json')
        return
    session_name = f"automation-session-{int(time.time())}"
    session = assume_role(automation_role_arn, session_name, base_profile, region)
    
    print(f"[INFO] Using configuration:")
    print(f"  Config file: {args.config}")
    print(f"  Log group: {log_group}")
    print(f"  Region: {region}")
    
    view_logs(
        log_group=log_group,
        log_stream=args.log_stream,
        region=region,
        session=session,
        hours=args.hours
    )


if __name__ == "__main__":
    main() 