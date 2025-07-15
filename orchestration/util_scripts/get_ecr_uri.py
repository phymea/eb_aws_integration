#!/usr/bin/env python3
"""
Helper script to get the correct ECR URI for your account and repository.
"""
import boto3
import argparse
import json
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


def get_account_id(session):
    """Get AWS account ID."""
    sts = session.client('sts')
    
    try:
        response = sts.get_caller_identity()
        return response['Account']
    except Exception as e:
        print(f"[ERROR] Failed to get account ID: {e}")
        return None


def get_ecr_uri(image_name, repository_name, region, session):
    """Generate the full ECR URI for an image."""
    account_id = get_account_id(session)
    if not account_id:
        return None
    
    ecr_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repository_name}/{image_name}"
    return ecr_uri


def update_config_file(config_file, image_name, repository_name, session, region):
    """Update config.json with the correct ECR URI."""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        ecr_uri = get_ecr_uri(image_name, repository_name, region, session)
        
        if not ecr_uri:
            print("[ERROR] Could not generate ECR URI")
            return False
        
        # Update the config
        config['docker']['image'] = f"{ecr_uri}:latest"
        config['docker']['ecr_auth'] = True
        
        # Write back to file
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"[SUCCESS] Updated {config_file}")
        print(f"[INFO] Docker image: {config['docker']['image']}")
        return True
        
    except Exception as e:
        print(f"[ERROR] Failed to update config file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Get ECR URI for Docker image')
    parser.add_argument('--image-name', required=True, help='Docker image name (e.g., dummy-app)')
    parser.add_argument('--repository-name', required=True, help='ECR repository name')
    parser.add_argument('--region', default='eu-north-1', help='AWS region')
    parser.add_argument('--base-profile', help='AWS base profile for initial STS call (overrides config)')
    parser.add_argument('--update-config', action='store_true', help='Update config.json with the ECR URI')
    parser.add_argument('--config-file', default='../config.json', help='Config file to update (default: ../config.json)')
    
    args = parser.parse_args()
    
    # Load config for automation_role_arn and base_profile
    try:
        with open(args.config_file, 'r') as f:
            config = json.load(f)
    except Exception:
        config = {}
    automation_role_arn = config.get('automation_role_arn') or config.get('iam', {}).get('automation_role_arn')
    base_profile = args.base_profile or config.get('base_profile') or config.get('iam', {}).get('base_profile')
    if not automation_role_arn:
        print('[ERROR] automation_role_arn must be set in config.json')
        return 1
    session_name = f"automation-session-{int(time.time())}"
    session = assume_role(automation_role_arn, session_name, base_profile, args.region)
    # Get ECR URI
    ecr_uri = get_ecr_uri(args.image_name, args.repository_name, args.region, session)
    
    if not ecr_uri:
        print("[ERROR] Could not generate ECR URI")
        return 1
    
    print(f"[INFO] ECR URI: {ecr_uri}:latest")
    print(f"[INFO] Full image name: {ecr_uri}:latest")
    
    # Update config if requested
    if args.update_config:
        success = update_config_file(args.config_file, args.image_name, args.repository_name, session, args.region)
        if not success:
            return 1
    
    print(f"\n[INFO] You can now use this image in your deployment scripts")
    print(f"[INFO] Make sure your EC2 instance has ECR pull permissions")
    
    return 0


if __name__ == "__main__":
    exit(main()) 