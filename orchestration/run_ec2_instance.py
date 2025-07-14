#!/usr/bin/env python3
"""
Simple test script to launch EC2 instance and run Docker container.
"""
import argparse
import json
import boto3
import time
from typing import Any
import os
from jinja2 import Template
import urllib.parse
from botocore.credentials import RefreshableCredentials
from botocore.session import get_session


def load_config(config_file):
    """Load configuration from JSON file."""
    with open(config_file, 'r') as f:
        return json.load(f)


def render_user_data_jinja(config, input_bucket=None, output_bucket=None, log_stream=None, output_key=None):
    """Render user data from Jinja2 template file."""
    template_path = os.path.join(os.path.dirname(__file__), 'user_data_template.sh.j2')
    with open(template_path) as f:
        template = Template(f.read())
    # Prepare variables
    variables = {
        'AWS_REGION': config['environment']['region'],
        'INPUT_BUCKET': input_bucket or config['environment']['input_bucket'],
        'OUTPUT_BUCKET': output_bucket or config['environment']['output_bucket'],
        'INPUT_PREFIX': config['environment']['input_prefix'],
        'OUTPUT_KEY': output_key,
        'LOG_GROUP': config['cloudwatch']['log_group'],
        'LOG_STREAM': log_stream,
        'DOCKER_IMAGE': config['docker']['image'],
        'ECR_AUTH': config['docker'].get('ecr_auth', False),
    }
    return template.render(**variables)


def generate_log_stream(config):
    import datetime
    import uuid
    log_stream_prefix = config['cloudwatch']['log_stream_prefix']
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    log_stream = f"{log_stream_prefix}{timestamp}-{uuid.uuid4().hex[:8]}"
    return log_stream


def generate_output_key(config):
    import datetime
    import uuid
    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    output_key = f"results/output_{timestamp}-{uuid.uuid4().hex[:8]}.json"
    return output_key


def generate_user_data(config, input_bucket=None, output_bucket=None, log_stream=None, output_key=None):
    """Generate user data script to run Docker container."""
    return render_user_data_jinja(config, input_bucket, output_bucket, log_stream, output_key)


def assume_role(role_arn, session_name, base_profile=None, region=None):
    """Assume the given role and return a boto3.Session using the temporary credentials."""
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


def get_existing_instance(instance_id, region, session):
    """Get details of an existing running instance."""
    ec2: Any = session.resource('ec2')
    
    try:
        instance = ec2.Instance(instance_id)
        instance.load()
        
        if instance.state['Name'] != 'running':
            print(f"[ERROR] Instance {instance_id} is not running (state: {instance.state['Name']})")
            return None, None
        
        print(f"[INFO] Using existing instance {instance_id}")
        print(f"  State: {instance.state['Name']}")
        print(f"  Type: {instance.instance_type}")
        print(f"  Public DNS: {instance.public_dns_name}")
        
        return instance.id, instance.public_dns_name
        
    except Exception as e:
        print(f"[ERROR] Failed to get instance {instance_id}: {e}")
        return None, None


def launch_instance(config, mode, input_bucket=None, output_bucket=None, session=None, log_stream=None, output_key=None):
    """Launch EC2 instance and return instance details."""  
    mode_config = config[f'{mode}_instance']
    region = config['environment']['region']
    print(f"[INFO] Launching {mode} instance...")
    print(f"  AMI: {mode_config['ami_id']}")
    print(f"  Type: {mode_config['instance_type']}")
    print(f"  Region: {region}")
    
    ec2: Any = session.resource('ec2')
    
    # Generate user data
    user_data = generate_user_data(config, input_bucket=input_bucket, output_bucket=output_bucket, log_stream=log_stream, output_key=output_key)
    
    # Launch instance
    instance_params = {
        'ImageId': mode_config['ami_id'],
        'InstanceType': mode_config['instance_type'],
        'MinCount': 1,
        'MaxCount': 1,
        'UserData': user_data,
        'InstanceInitiatedShutdownBehavior': 'terminate',
    }
    
    # Add IAM role if specified
    if config['iam']['role_name']:
        instance_params['IamInstanceProfile'] = {'Name': config['iam']['role_name']}
    
    instances = ec2.create_instances(**instance_params)
    instance = instances[0]
    
    print(f"[INFO] Waiting for instance {instance.id} to start...")
    instance.wait_until_running()
    instance.reload()
    
    print(f"[INFO] Instance {instance.id} is running at {instance.public_dns_name}")
    return instance.id, instance.public_dns_name


def run_userdata_on_instance(config, instance_id, input_bucket=None, output_bucket=None, session=None, log_stream=None, output_key=None, input_prefix=None):
    """Re-run user data script on an existing instance using SSM."""
    region = config['environment']['region']
    instance_id, public_dns = get_existing_instance(instance_id, region, session)
    if not instance_id:
        return None, None
    
    print(f"[INFO] Re-running user data on existing instance {instance_id}")
    
    # Generate user data script
    user_data = generate_user_data(config, input_bucket=input_bucket, output_bucket=output_bucket, log_stream=log_stream, output_key=output_key)
    
    # Remove the shebang and make it executable
    user_data_script = user_data.replace('#!/bin/bash\n', '')
    
    # Create a temporary script file on the instance
    setup_commands = [
        '#!/bin/bash',
        'set -e',
        'echo "=== Re-running user data script ==="',
        'echo "Timestamp: $(date)"',
        '',
        '# Create temporary script file',
        'cat > /tmp/rerun_userdata.sh << \'EOF\'',
        user_data_script,
        'EOF',
        '',
        '# Make it executable and run it',
        'chmod +x /tmp/rerun_userdata.sh',
        'echo "=== Executing user data script ==="',
        '/tmp/rerun_userdata.sh',
        '',
        '# Clean up',
        'rm -f /tmp/rerun_userdata.sh',
        'echo "=== User data script completed ==="'
    ]
    
    # Run commands via SSM
    try:
        ssm = session.client('ssm')
        
        print(f"[INFO] Sending user data script to instance {instance_id}...")
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={'commands': setup_commands}
        )
        
        command_id = response['Command']['CommandId']
        print(f"[INFO] User data script sent with ID: {command_id}")
        print(f"[INFO] This will reinstall Docker and run the batch job")
        
        return instance_id, public_dns
        
    except Exception as e:
        print(f"[ERROR] Failed to run user data on instance: {e}")
        print("[INFO] Make sure the instance has SSM agent installed and proper IAM permissions")
        return None, None


def run_job_on_instance(config, instance_id, input_bucket=None, output_bucket=None, session=None, log_stream=None, output_key=None, input_prefix=None):
    """Run the batch processing job on an existing instance using SSM."""
    region = config['environment']['region']
    instance_id, public_dns = get_existing_instance(instance_id, region, session)
    if not instance_id:
        return None, None
    
    print(f"[INFO] Running job on existing instance {instance_id}")
    
    # Generate the Docker run command
    docker_image = config['docker']['image']
    input_prefix = input_prefix or config['environment']['input_prefix']
    log_group = config['cloudwatch']['log_group']

    
    # Build Docker command
    docker_cmd = f'''docker run --rm \
    -e AWS_REGION={region} \
    -e INPUT_BUCKET={input_bucket} \
    -e OUTPUT_BUCKET={output_bucket} \
    -e INPUT_PREFIX={input_prefix} \
    -e OUTPUT_KEY={output_key} \
    -e LOG_GROUP={log_group} \
    -e LOG_STREAM={log_stream} \
    {docker_image} \
    --input-bucket {input_bucket} \
    --output-bucket {output_bucket} \
    --input-prefix {input_prefix} \
    --output-key {output_key} \
    --log-group {log_group} \
    --log-stream {log_stream}'''
    
    # Run command via SSM
    try:
        ssm = session.client('ssm')
        
        print(f"[INFO] Sending command to instance {instance_id}...")
        response = ssm.send_command(
            InstanceIds=[instance_id],
            DocumentName="AWS-RunShellScript",
            Parameters={'commands': [docker_cmd]}
        )
        
        command_id = response['Command']['CommandId']
        print(f"[INFO] Command sent with ID: {command_id}")
        print(f"[INFO] You can monitor logs with: python view_logs.py --log-stream {log_stream}")
        
        return instance_id, public_dns
        
    except Exception as e:
        print(f"[ERROR] Failed to run command on instance: {e}")
        print("[INFO] Make sure the instance has SSM agent installed and proper IAM permissions")
        return None, None


def print_log_group_info(config, log_stream=None):
    log_group = config['cloudwatch']['log_group']
    region = config['environment']['region']
    log_group_enc = urllib.parse.quote(log_group, safe='')
    print(f"[INFO] View logs in CloudWatch:")
    print(f"  Log group: {log_group}")
    if log_stream:
        print(f"  Log stream: {log_stream}")
        print(f"  Console link: https://console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group_enc}/log-events/{urllib.parse.quote(log_stream, safe='')}")
    else:
        print(f"  Console link: https://console.aws.amazon.com/cloudwatch/home?region={region}#logsV2:log-groups/log-group/{log_group_enc}")


def main():
    parser = argparse.ArgumentParser(description='Simple EC2 deployment test')
    parser.add_argument('--mode', choices=['test', 'production'], default='test', 
                       help='Deployment mode (default: test)')
    parser.add_argument('--input-bucket', help='S3 input bucket (overrides config)')
    parser.add_argument('--output-bucket', help='S3 output bucket (overrides config)')
    parser.add_argument('--config', default='config.json', 
                       help='Configuration file (default: config.json)')
    parser.add_argument('--instance-id', help='Use existing running instance instead of launching new one')
    parser.add_argument('--rerun-userdata', action='store_true', 
                       help='Re-run user data script on existing instance (for debugging)')
    parser.add_argument('--base-profile', help='AWS base profile for initial STS call (overrides config)')
    parser.add_argument('--image-prefix', help='S3 input prefix (overrides config)')
    args = parser.parse_args()
    
    # Load configuration
    config = load_config(args.config)
    
    # Use command line args if provided, otherwise use config values
    input_bucket = args.input_bucket or config['environment']['input_bucket']
    output_bucket = args.output_bucket or config['environment']['output_bucket']
    input_prefix = args.image_prefix or config['environment']['input_prefix']
    
    # Validate that buckets are available
    if not input_bucket or not output_bucket:
        print("[ERROR] Input and output buckets must be specified either in config.json or via command line arguments")
        print(f"  Config buckets: input={config['environment'].get('input_bucket')}, output={config['environment'].get('output_bucket')}")
        return
    
    print(f"[INFO] Using buckets:")
    print(f"  Input: {input_bucket}")
    print(f"  Output: {output_bucket}")
    print(f"  Input prefix: {input_prefix}")
    
    # Generate a unique log stream name and output key
    log_stream = generate_log_stream(config)
    output_key = generate_output_key(config)
    
    print(f"[INFO] Generated output key: {output_key}")
    
    # Assume role for automation
    automation_role_arn = config.get('iam', {}).get('automation_role_arn')
    base_profile = args.base_profile or config.get('iam', {}).get('base_profile')
    region = config['environment']['region']
    if not automation_role_arn:
        print("[ERROR] automation_role_arn must be set in config.json")
        return
    session_name = f"automation-session-{int(time.time())}"
    session = assume_role(automation_role_arn, session_name, base_profile, region)

    if args.instance_id:
        # Use existing instance
        print(f"[INFO] Using existing instance: {args.instance_id}")
        
        if args.rerun_userdata:
            # Re-run user data script
            instance_id, public_dns = run_userdata_on_instance(
                config, args.instance_id, input_bucket, output_bucket, session, log_stream, output_key, input_prefix=input_prefix
            )
            if instance_id:
                print(f"[INFO] User data script re-executed on existing instance!")
                print(f"  Instance ID: {instance_id}")
                print(f"  Public DNS: {public_dns}")
                print_log_group_info(config, log_stream)
            else:
                print("[ERROR] Failed to re-run user data on existing instance")
        else:
            # Just run the job
            instance_id, public_dns = run_job_on_instance(
                config, args.instance_id, input_bucket, output_bucket, session, log_stream, output_key, input_prefix=input_prefix
            )
            if instance_id:
                print(f"[INFO] Job started on existing instance!")
                print(f"  Instance ID: {instance_id}")
                print(f"  Public DNS: {public_dns}")
                print_log_group_info(config, log_stream)
            else:
                print("[ERROR] Failed to run job on existing instance")
    else:
        # Launch new instance
        instance_id, public_dns = launch_instance(
            config, args.mode, input_bucket, output_bucket, session, log_stream, output_key, input_prefix=input_prefix
        )
        print(f"[INFO] Deployment complete!")
        print(f"  Instance ID: {instance_id}")
        print(f"  Public DNS: {public_dns}")
        print_log_group_info(config, log_stream)


if __name__ == "__main__":
    main() 