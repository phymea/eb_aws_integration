#!/usr/bin/env python3
"""
Script to create/update the automation role for launching EC2 with correct PassRole permissions.
"""
import boto3
import argparse
import json

def update_config_file(config_file, automation_role_arn):
    """Update config.json with the automation_role_arn."""
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
        if 'iam' not in config:
            config['iam'] = {}
        config['iam']['automation_role_arn'] = automation_role_arn
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        print(f"✅ Updated {config_file} with automation_role_arn: {automation_role_arn}")
        return True
    except Exception as e:
        print(f"❌ Failed to update config file: {e}")
        return False


def create_or_update_automation_role(role_name, instance_profile_role_arn, profile=None, config_file=None, update_config=False):
    session = boto3.Session(profile_name=profile)
    iam = session.client('iam')
    sts = session.client('sts')
    account_id = sts.get_caller_identity()['Account']

    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"AWS": f"arn:aws:iam::{account_id}:root"},
            "Action": "sts:AssumeRole"
        }]
    }

    # Policy: EC2, S3, CloudWatch, and PassRole for the instance profile role
    automation_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": [
                    "ec2:RunInstances",
                    "ec2:DescribeInstances",
                    "ec2:TerminateInstances",
                    "ec2:DescribeInstanceStatus",
                    "ec2:CreateTags",
                    "ec2:DescribeImages"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "iam:PassRole"
                ],
                "Resource": instance_profile_role_arn
            },
            {
                "Effect": "Allow",
                "Action": [
                    "s3:ListBucket",
                    "s3:GetObject",
                    "s3:PutObject"
                ],
                "Resource": "*"
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "*"
            }
        ]
    }

    try:
        try:
            iam.get_role(RoleName=role_name)
            print(f"[INFO] Role {role_name} already exists, updating trust policy and attaching policy.")
            iam.update_assume_role_policy(
                RoleName=role_name,
                PolicyDocument=json.dumps(trust_policy)
            )
        except iam.exceptions.NoSuchEntityException:
            print(f"[INFO] Creating role {role_name}")
            iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy),
                Description="Automation role for launching EC2 with PassRole"
            )

        # Create or update the inline policy
        policy_name = f"{role_name}-automation-policy"
        iam.put_role_policy(
            RoleName=role_name,
            PolicyName=policy_name,
            PolicyDocument=json.dumps(automation_policy)
        )
        print(f"\n[SUCCESS] Automation role {role_name} is ready.")
        automation_role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
        print(f"[INFO] Automation role ARN: {automation_role_arn}")
        updated = False
        if update_config and config_file:
            updated = update_config_file(config_file, automation_role_arn)
        if update_config and updated:
            pass  # info already printed during the call to update_config_file
        else:
            print(f"[INFO] To use this role in your deployment, set 'automation_role_arn' under the 'iam' section in config.json to the above ARN.")
            print(f"[INFO] To update config.json automatically, run with --update-config")
        return True
    except Exception as e:
        print(f"[ERROR] {e}")
        return False


def main():
    parser = argparse.ArgumentParser(description="Setup automation role for EC2 deployment")
    parser.add_argument('--role-name', default='EarboxAutomationRole', help='Automation role name')
    parser.add_argument('--instance-profile-role-arn', required=True, help='ARN of the EC2 instance profile role')
    parser.add_argument('--profile', default='default', help='AWS profile to use for creation')
    parser.add_argument('--config', default='config.json', help='Configuration file to update')
    parser.add_argument('--update-config', action='store_true', help='Update config.json with automation_role_arn')
    args = parser.parse_args()
    create_or_update_automation_role(args.role_name, args.instance_profile_role_arn, args.profile, args.config, args.update_config)

if __name__ == "__main__":
    main()