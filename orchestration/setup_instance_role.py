#!/usr/bin/env python3
"""
Script to create IAM role with correct permissions for EC2 instances.
"""
import boto3
import argparse
import json


def load_config(config_file='config.json'):
    """Load configuration from JSON file."""
    try:
        with open(config_file, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"[ERROR] Config file '{config_file}' not found")
        return None


def create_ecr_role(role_name, profile=None):
    """Create IAM role with correct permissions."""
    session = boto3.Session(profile_name=profile)
    iam = session.client('iam')
    
    print(f"[INFO] Creating IAM role: {role_name}")
    
    # Trust policy for EC2
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "ec2.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }
    
    # ECR permissions policy
    ecr_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogGroups",
                    "logs:DescribeLogStreams"
                ],
                "Resource": "arn:aws:logs:*:*:log-group:*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket"
                ],
                "Resource": [
                    "arn:aws:s3:::boxinputtest",
                    "arn:aws:s3:::boxinputtest/*",
                    "arn:aws:s3:::boxoutputtest",
                    "arn:aws:s3:::boxoutputtest/*"
                ]
            },
        ]
    }
    
    try:
        # Create role
        iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Role for EC2 instances to access ECR, CloudWatch, and S3"
        )
        print(f"✅ Created IAM role: {role_name}")
        
        # Create policy
        policy_name = f"{role_name}-policy"
        iam.create_policy(
            PolicyName=policy_name,
            PolicyDocument=json.dumps(ecr_policy),
            Description="Policy for ECR, CloudWatch, and S3 access"
        )
        print(f"✅ Created policy: {policy_name}")
        
        # Attach policy to role
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn=f"arn:aws:iam::{session.client('sts').get_caller_identity()['Account']}:policy/{policy_name}"
        )
        print(f"✅ Attached policy to role: {role_name}")
        
        # Create instance profile
        iam.create_instance_profile(InstanceProfileName=role_name)
        print(f"✅ Created instance profile: {role_name}")
        
        # Add role to instance profile
        iam.add_role_to_instance_profile(
            InstanceProfileName=role_name,
            RoleName=role_name
        )
        print(f"✅ Added role to instance profile: {role_name}")
        
        # Fetch and print the instance profile ARN and role ARN
        instance_profile = iam.get_instance_profile(InstanceProfileName=role_name)
        instance_profile_arn = instance_profile['InstanceProfile']['Arn']
        # Fetch the role ARN
        role = iam.get_role(RoleName=role_name)
        role_arn = role['Role']['Arn']
        print(f"[OUTPUT] Instance profile ARN: {instance_profile_arn}")
        print(f"[OUTPUT] Role ARN: {role_arn}")
        print(f"[INFO] Use the instance profile NAME ('{role_name}') in EC2 launch (IamInstanceProfile)")
        print(f"[INFO] Use the ROLE ARN for iam:PassRole policy in automation role setup")
        return instance_profile_arn, role_arn
        
    except iam.exceptions.EntityAlreadyExistsException:
        print(f"⚠️  Role {role_name} already exists")
        # Fetch and print the instance profile ARN and role ARN if they exist
        try:
            instance_profile = iam.get_instance_profile(InstanceProfileName=role_name)
            instance_profile_arn = instance_profile['InstanceProfile']['Arn']
            role = iam.get_role(RoleName=role_name)
            role_arn = role['Role']['Arn']
            print(f"[OUTPUT] Instance profile ARN: {instance_profile_arn}")
            print(f"[OUTPUT] Role ARN: {role_arn}")
            print(f"[INFO] Use the instance profile NAME ('{role_name}') in EC2 launch (IamInstanceProfile)")
            print(f"[INFO] Use the ROLE ARN for iam:PassRole policy in automation role setup")
            return instance_profile_arn, role_arn
        except Exception as e:
            print(f"[ERROR] Could not fetch instance profile or role ARN: {e}")
            return None, None
    except Exception as e:
        print(f"❌ Failed to create role: {e}")
        return None, None


def update_config_file(config_file, role_name):
    """Update config.json with the role name."""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        
        config['iam']['role_name'] = role_name
        
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print(f"✅ Updated {config_file} with role name: {role_name}")
        return True
        
    except Exception as e:
        print(f"❌ Failed to update config file: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Create IAM role with ECR permissions')
    parser.add_argument('--role-name', default='EarboxEC2InstanceRole', help='IAM role name to create')
    parser.add_argument('--profile', default='default', help='AWS profile to use for creation')
    parser.add_argument('--config', default='config.json', help='Configuration file to update')
    parser.add_argument('--update-config', action='store_true', help='Update config.json with role name')
    args = parser.parse_args()
    
    # Create IAM role
    instance_profile_arn, role_arn = create_ecr_role(args.role_name, args.profile)
    
    if not instance_profile_arn or not role_arn:
        print("[ERROR] Failed to create IAM role or fetch ARNs")
        return 1
    
    # Update config if requested
    updated = False
    if args.update_config:
        updated = update_config_file(args.config, args.role_name)
    
    print(f"\n[SUCCESS] IAM role setup complete!")
    print(f"[INFO] Role name: {args.role_name}")
    print(f"[INFO] Role ARN: {role_arn}")
    if args.update_config and updated:
        pass  # info already printed during the call to update_config_file
    else:
        print(f"[INFO] To use this role in your deployment, set 'role_name' under the 'iam' section in config.json to '{args.role_name}'")
        print(f"[INFO] To update config.json automatically, run with --update-config")
    print(f"[INFO] To grant automation permissions, run:")
    print(f"  python setup_automation_role.py --instance-profile-role-arn {role_arn} [--update-config]")
    
    return 0


if __name__ == "__main__":
    exit(main()) 