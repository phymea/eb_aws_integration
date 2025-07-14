#!/usr/bin/env python3
"""
Script to create a CloudWatch Logs metric filter and alarm for error detection, using log group from config.json.
Chains SNS topic creation, email subscription, and alarm setup. User only needs to supply an email address.
"""
import boto3
import json
import argparse
import sys
import time

ERROR_PATTERN = '[BOOT] ERROR: Could not retrieve instance ID from metadata service.'
METRIC_NAME = 'InstanceTerminationErrorCount'
METRIC_NAMESPACE = 'EC2Batch/Errors'
ALARM_NAME = 'EC2Batch-InstanceTerminationError'
DEFAULT_TOPIC_NAME = 'ec2batch-alerts'


def load_config(config_file):
    with open(config_file, 'r') as f:
        return json.load(f)

def get_log_group(config):
    return config['cloudwatch']['log_group']

def create_metric_filter(log_group, region):
    logs = boto3.client('logs', region_name=region)
    print(f"[INFO] Creating metric filter on log group: {log_group}")
    try:
        logs.put_metric_filter(
            logGroupName=log_group,
            filterName='InstanceTerminationError',
            filterPattern=f'\"{ERROR_PATTERN}\"',
            metricTransformations=[{
                'metricName': METRIC_NAME,
                'metricNamespace': METRIC_NAMESPACE,
                'metricValue': '1',
                'defaultValue': 0
            }]
        )
        print(f"[SUCCESS] Metric filter created.")
    except logs.exceptions.ResourceAlreadyExistsException:
        print(f"[INFO] Metric filter already exists.")
    except Exception as e:
        print(f"[ERROR] Failed to create metric filter: {e}")
        sys.exit(1)

def create_alarm(region, sns_topic_arn):
    cloudwatch = boto3.client('cloudwatch', region_name=region)
    print(f"[INFO] Creating CloudWatch alarm: {ALARM_NAME}")
    try:
        cloudwatch.put_metric_alarm(
            AlarmName=ALARM_NAME,
            MetricName=METRIC_NAME,
            Namespace=METRIC_NAMESPACE,
            Statistic='Sum',
            Period=300,
            Threshold=1,
            ComparisonOperator='GreaterThanOrEqualToThreshold',
            EvaluationPeriods=1,
            AlarmActions=[sns_topic_arn],
            TreatMissingData='notBreaching',
            ActionsEnabled=True,
            AlarmDescription='Alarm for EC2 instance termination errors detected in user data logs.'
        )
        print(f"[SUCCESS] Alarm created and will notify SNS topic: {sns_topic_arn}")
    except Exception as e:
        print(f"[ERROR] Failed to create alarm: {e}")
        sys.exit(1)

def create_or_get_sns_topic(region, topic_name):
    sns = boto3.client('sns', region_name=region)
    print(f"[INFO] Creating or getting SNS topic: {topic_name}")
    response = sns.create_topic(Name=topic_name)
    topic_arn = response['TopicArn']
    print(f"[SUCCESS] SNS topic ARN: {topic_arn}")
    return topic_arn

def subscribe_email_to_topic(region, topic_arn, email):
    sns = boto3.client('sns', region_name=region)
    print(f"[INFO] Subscribing {email} to SNS topic {topic_arn}")
    response = sns.subscribe(
        TopicArn=topic_arn,
        Protocol='email',
        Endpoint=email,
        ReturnSubscriptionArn=True
    )
    subscription_arn = response['SubscriptionArn']
    if subscription_arn == 'pending confirmation':
        print(f"[ACTION REQUIRED] Check your email ({email}) and confirm the SNS subscription.")
    else:
        print(f"[SUCCESS] Email already subscribed: {subscription_arn}")
    return subscription_arn

def wait_for_subscription_confirmation(region, topic_arn, email, timeout=300):
    sns = boto3.client('sns', region_name=region)
    print(f"[INFO] Waiting for email subscription confirmation...")
    waited = 0
    while waited < timeout:
        subs = sns.list_subscriptions_by_topic(TopicArn=topic_arn)['Subscriptions']
        for sub in subs:
            if sub['Endpoint'].lower() == email.lower() and sub['Protocol'] == 'email':
                if sub['SubscriptionArn'] != 'PendingConfirmation':
                    print(f"[SUCCESS] Email subscription confirmed: {sub['SubscriptionArn']}")
                    return True
        time.sleep(5)
        waited += 5
        print(f"[INFO] Still waiting for confirmation... ({waited}s elapsed)")
    print(f"[ERROR] Subscription not confirmed after {timeout} seconds. Please confirm the email and re-run the script.")
    return False

def main():
    parser = argparse.ArgumentParser(description='Create CloudWatch metric filter and alarm for instance termination errors, with SNS email notification.')
    parser.add_argument('--config', default='../config.json', help='Path to config.json (default: ../config.json)')
    parser.add_argument('--email', required=True, help='Email address to notify')
    parser.add_argument('--region', help='AWS region (overrides config)')
    parser.add_argument('--topic-name', default=DEFAULT_TOPIC_NAME, help='SNS topic name (default: ec2batch-alerts)')
    args = parser.parse_args()

    config = load_config(args.config)
    log_group = get_log_group(config)
    region = args.region or config['environment']['region']

    print("\n[INFO] === Step 1: Create or get SNS topic ===")
    topic_arn = create_or_get_sns_topic(region, args.topic_name)

    print("\n[INFO] === Step 2: Subscribe email to SNS topic ===")
    subscribe_email_to_topic(region, topic_arn, args.email)

    print("\n[INFO] === Step 3: Confirm email subscription ===")
    print(f"[ACTION REQUIRED] Please check your email ({args.email}) and confirm the SNS subscription.")
    print("Waiting for confirmation (up to 5 minutes)...")
    if not wait_for_subscription_confirmation(region, topic_arn, args.email):
        sys.exit(1)

    print("\n[INFO] === Step 4: Create metric filter ===")
    create_metric_filter(log_group, region)

    print("\n[INFO] === Step 5: Create alarm ===")
    create_alarm(region, topic_arn)

    print("\n[INFO] Setup complete. You will receive email alerts if the error is detected in CloudWatch logs.")

if __name__ == "__main__":
    main() 