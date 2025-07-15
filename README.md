# AWS Integration Sample for Earbox analysis: Image Analysis Pipeline with Instance Control

This project provides a sample framework for running a containerized image analysis pipeline on AWS EC2 for Earbox session images, with instance lifecycle control, logging, and automation. It demonstrates how to orchestrate jobs using EC2, Docker, S3, and CloudWatch, with all infrastructure and job parameters externalized for easy configuration and reproducibility.

**Basic Usage:**

This program expects:
- An **input S3 bucket** and an **input_prefix** (S3 prefix) containing Earbox session images to be processed.
- An **output S3 bucket** where the program will write a `.json` file containing some arbitrary information for test purposes.

You must configure these values in your `config.json` file before running the pipeline.

## Project Structure

```
README.md                # This file
LICENSE                  # License file
.gitignore               # Git ignore rules
orchestration/           # Orchestration scripts and templates
  config.json            # Main configuration file (Edit from config.json.example) 
  config.json.example    # Configuration file example
  run_ec2_instance.py    # Main script to launch and control EC2 jobs
  setup_instance_role.py # Script to create/update the EC2 instance IAM role
  setup_automation_role.py # Script to create/update the automation IAM role
  user_data_template.sh.j2 # Jinja2 template for EC2 user data
  requirements.txt       # Python requirements for orchestration scripts
  util_scripts/          # Helper scripts (CloudWatch, ECR, etc.)
docker_image/            # Docker image source for the analysis job
  Dockerfile
  requirements.txt
  main.py                # Main entrypoint for the container
```

## Setup Guide

### 1. Build and Push the Docker Image to ECR

1. **Build your Docker image:**
   ```
   cd docker_image
   docker build -t <your-ecr-repo>:latest .
   ```
2. **Authenticate Docker to ECR:**
   ```
   aws ecr get-login-password --region <region> | docker login --username AWS --password-stdin <aws_account_id>.dkr.ecr.<region>.amazonaws.com
   ```
3. **Push the image:**
   ```
   docker push <your-ecr-repo>:latest
   ```
4. **Update `config.json`** with the full ECR image URI under `docker.image`.

### 2. Set Up `config.json`

- Copy `config.json.example` to `config.json` and fill in the required fields:
  - `test_instance` / `production_instance`: AMI ID and instance type
  - `docker.image`: Full ECR URI of your pushed Docker image
  - `docker.ecr_auth`: Set to `true` if using ECR
  - `environment.region`: AWS region for all resources
  - `environment.input_bucket` / `output_bucket`: S3 buckets for input and output data
  - `environment.input_prefix`: S3 prefix that should be an Earbox session directory for input images
  - `iam.role_name`: Name of the instance profile role (see setup scripts below)
  - `iam.automation_role_arn`: ARN of the automation role (see setup scripts below)
  - `iam.base_profile`: AWS CLI profile for initial role assumption
  - `cloudwatch.log_group`: CloudWatch log group for all job logs
  - `cloudwatch.log_stream_prefix`: Prefix for log streams (each job gets a unique stream)
  - `cloudwatch.retention_days`: Log retention in days

### 3. Setup IAM Roles Using the Provided Scripts

From the `orchestration` directory:

```
# Create the instance role (edit --role-name as needed)
python setup_instance_role.py --role-name EarboxEC2InstanceRole --update-config

# Note the output: use the role name in config.json

# Create the automation role (replace <INSTANCE_ROLE_ARN> with the role ARN from above)
python setup_automation_role.py --role-name EarboxAutomationRole --instance-profile-role-arn <INSTANCE_ROLE_ARN> --update-config
```

### 4. Run the EC2 Instance

From the `orchestration` directory:

```
python run_ec2_instance.py
```

- Use `--mode test` for test settings (default) and `--mode production` for production settings (uses a different EC2 instance type and AMI, set this up in config.json).
- You can override image_prefix, buckets, config file, or AWS profile with command-line arguments:
  ```
  python run_ec2_instance.py --mode test --image-prefix my/custom/prefix/
  python run_ec2_instance.py --mode test --input-bucket mybucket --output-bucket myoutbucket --base-profile myawsprofile
  ```
- The script will launch an EC2 instance, run your container, and automatically terminate the instance when done.
- CloudWatch log links will be printed for monitoring job progress.

---

## Annex: Utility Scripts in `orchestration/util_scripts/`

Below is a summary of the helper scripts available in `orchestration/util_scripts/`:

- **fetch_console_output.py**: Fetch EC2 instance console output by instance ID, with optional polling until output is available.
- **get_ecr_uri.py**: Helper script to get the correct ECR URI for your account and repository.
- **view_logs.py**: Simple script to view CloudWatch logs from batch processing jobs.
- **test_cloudwatch.py**: Simple test script to verify CloudWatch logging and create log group.
- **create_cloudwatch_alarm.py**: Script to create a CloudWatch Logs metric filter and alarm for error detection, using log group from config.json. Chains SNS topic creation, email subscription, and alarm setup. User only needs to supply an email address.
- **check_ami_ids.py**: Script to print the latest Amazon Linux 2023 AMI ID and the latest TensorFlow DLAMI with NVIDIA GPU support.
- **test_all_util_scripts.py**: Test runner for all utility scripts in this directory. Runs each script with safe or dummy parameters, skips tests that require unavailable environment variables, and prints a summary.

See each script's `--help` for usage details and options.
