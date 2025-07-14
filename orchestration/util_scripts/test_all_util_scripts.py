"""
Test runner for all utility scripts in this directory.

This script will:
- Run each utility script with safe or dummy parameters.
- Skip tests that require unavailable environment variables (like TEST_INSTANCE_ID or TEST_ALARM_EMAIL).
- Print the output and a summary of all test results.

Usage:
    python test_all_util_scripts.py

Optional environment variables:
    TEST_INSTANCE_ID   Set to a valid EC2 instance ID to test fetch_console_output.py
    TEST_ALARM_EMAIL   Set to a valid email address to test create_cloudwatch_alarm.py (requires email confirmation)

All scripts are run with ../config.json as the config file where applicable.
"""
import subprocess
import os
import sys

UTIL_SCRIPTS = [
    'check_ami_ids.py',
    'test_cloudwatch.py',
    'view_logs.py',
    'get_ecr_uri.py',
    'fetch_console_output.py',
    'create_cloudwatch_alarm.py',
]

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(SCRIPT_DIR, '../config.json')

results = {}

def run_script(script, args=None):
    cmd = [sys.executable, os.path.join(SCRIPT_DIR, script)]
    if args:
        cmd += args
    try:
        print(f"\n[TEST] Running: {' '.join(cmd)}")
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT, timeout=60)
        print(output.decode())
        results[script] = 'SUCCESS'
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] {script} failed with exit code {e.returncode}")
        print(e.output.decode())
        results[script] = 'FAIL'
    except Exception as e:
        print(f"[ERROR] {script} exception: {e}")
        results[script] = 'FAIL'

# 1. check_ami_ids.py (no args)
run_script('check_ami_ids.py')

# 2. test_cloudwatch.py (uses config)
run_script('test_cloudwatch.py', ['--config', CONFIG_PATH])

# 3. view_logs.py (uses config, just list log groups)
run_script('view_logs.py', ['--config', CONFIG_PATH, '--hours', '0'])

# 4. get_ecr_uri.py (dummy image/repo)
run_script('get_ecr_uri.py', [
    '--image-name', 'dummy-image',
    '--repository-name', 'dummy-repo',
    '--config-file', CONFIG_PATH
])

# 5. fetch_console_output.py (needs instance ID)
instance_id = os.environ.get('TEST_INSTANCE_ID')
if instance_id:
    run_script('fetch_console_output.py', [
        '--instance-id', instance_id,
        '--config', CONFIG_PATH
    ])
else:
    print('[SKIP] fetch_console_output.py (TEST_INSTANCE_ID not set)')
    results['fetch_console_output.py'] = 'SKIP'

# 6. create_cloudwatch_alarm.py (needs email)
email = os.environ.get('TEST_ALARM_EMAIL')
if email:
    run_script('create_cloudwatch_alarm.py', [
        '--email', email,
        '--config', CONFIG_PATH
    ])
else:
    print('[SKIP] create_cloudwatch_alarm.py (TEST_ALARM_EMAIL not set)')
    results['create_cloudwatch_alarm.py'] = 'SKIP'

print('\n=== Test Summary ===')
for script, result in results.items():
    print(f"{script}: {result}") 