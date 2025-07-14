#!/usr/bin/env python3
"""
Fetch EC2 instance console output by instance ID, with optional polling until output is available.
"""
import boto3
import time
import argparse
from typing import Any
import json


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


def fetch_console_output(instance_id, session, region, wait=False, poll_interval=10, timeout=300):
    ec2: Any = session.resource("ec2")
    instance = ec2.Instance(instance_id)
    elapsed = 0
    while True:
        console_output = instance.console_output()
        output = console_output.get('Output', '')
        if output:
            print("[INFO] Console output from instance:")
            print(output)
            return output
        if not wait:
            print("[INFO] No console output available yet.")
            return None
        if elapsed >= timeout:
            print(f"[ERROR] Timeout reached ({timeout}s), no console output available.")
            return None
        print(f"[INFO] Waiting for console output... ({elapsed}/{timeout}s)")
        time.sleep(poll_interval)
        elapsed += poll_interval


def main():
    parser = argparse.ArgumentParser(description="Fetch EC2 instance console output by instance ID.")
    parser.add_argument('--instance-id', required=True, help='EC2 instance ID')
    parser.add_argument('--base-profile', help='AWS base profile for initial STS call (overrides config)')
    parser.add_argument('--region', default='eu-north-1', help='AWS region')
    parser.add_argument('--wait', action='store_true', help='Wait and poll until output is available')
    parser.add_argument('--poll-interval', type=int, default=10, help='Polling interval in seconds (default: 10)')
    parser.add_argument('--timeout', type=int, default=300, help='Timeout in seconds (default: 300)')
    parser.add_argument('--config', default='../config.json', help='Configuration file (default: ../config.json)')
    args = parser.parse_args()
    # Load config for automation_role_arn and base_profile
    try:
        with open(args.config, 'r') as f:
            config = json.load(f)
    except Exception:
        config = {}
    automation_role_arn = config.get('automation_role_arn') or config.get('iam', {}).get('automation_role_arn')
    base_profile = args.base_profile or config.get('base_profile') or config.get('iam', {}).get('base_profile')
    if not automation_role_arn:
        print('[ERROR] automation_role_arn must be set in config.json')
        return
    session_name = f"automation-session-{int(time.time())}"
    session = assume_role(automation_role_arn, session_name, base_profile, args.region)
    fetch_console_output(
        instance_id=args.instance_id,
        session=session,
        region=args.region,
        wait=args.wait,
        poll_interval=args.poll_interval,
        timeout=args.timeout
    )

if __name__ == "__main__":
    main()