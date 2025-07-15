import boto3

region = 'eu-north-1'  # Change to your preferred region
ssm = boto3.client('ssm', region_name=region)

# Get the latest Amazon Linux 2 AMI ID
param = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-6.1-x86_64"
ami_id = ssm.get_parameter(Name=param)['Parameter']['Value']

print(f"Latest Amazon Linux 2023 AMI ID: {ami_id}")

# Find the latest TensorFlow DLAMI with NVIDIA GPU support
filters = [
    {'Name': 'name', 'Values': ['Deep Learning AMI GPU TensorFlow*']},
    {'Name': 'state', 'Values': ['available']},
    {'Name': 'architecture', 'Values': ['x86_64']}
]
ec2 = boto3.client('ec2', region_name=region)
response = ec2.describe_images(Owners=['amazon'], Filters=filters)
images = sorted(response['Images'], key=lambda x: x['CreationDate'], reverse=True)
latest_dlami_id = images[0]['ImageId']

print(f"Latest TensorFlow DLAMI ID: {latest_dlami_id}")