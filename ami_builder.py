import botocore
import boto3
import jinja2
import logging
import os
import subprocess
import sys
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    if 'log_level' in event:
        try:
            logger.setLevel(logging.getLevelName(event['log_level'].upper()))
        except ValueError:
            logger.warning(f"Invalid log level specified: {event['log_level']}; using INFO")

    if logger.isEnabledFor(logging.DEBUG):
        # Log everything from boto3
        boto3.set_stream_logger()
        logger.debug(f"Using boto3 {boto3.__version__}")

    if 'packer_template_bucket_region' in event:
        s3_url = f"https://s3.{event['packer_template_bucket_region']}.amazonaws.com"

    if event['packer_template_bucket'] and event['packer_template_key']:
        logger.info(f"Getting packer template from {s3_url}/{event['packer_template_bucket']}/{event['packer_template_key']}")
        s3 = boto3.resource('s3',
                            endpoint_url=s3_url,
                            config=botocore.config.Config(s3={'addressing_style':'path'}))
        try:
            s3.Bucket(event['packer_template_bucket']).download_file(event['packer_template_key'], '/tmp/packer_template.json.j2')
        except ClientError as e:
            logger.error(f"Unable to download packer template file: {e}")
            raise
    else:
        print("Missing required configuration")
        raise Exception

    with open('/tmp/packer_template.json.j2') as in_template:
        template = jinja2.Template(in_template.read())
    with open('/tmp/packer.json', 'w') as packer_file:
        packer_file.write(template.render(event=event))

    if 'provision_script_bucket_region' in event:
        s3_url = f"https://s3.{event['provision_script_bucket_region']}.amazonaws.com"

    if event['provision_script_bucket'] and event['provision_script_keys']:
        s3 = boto3.resource('s3',
                            endpoint_url=s3_url,
                            config=botocore.config.Config(s3={'addressing_style':'path'}))
        for script in event['provision_script_keys']:
            logger.info(f"Getting provision script from {s3_url}/{event['provision_script_bucket']}/{script}")
            try:
                s3.Bucket(event['provision_script_bucket']).download_file(script, f'/tmp/{script}')
            except ClientError as e:
                logger.error(f"Unable to download provisioning script: {e}")
                raise

    try:
        command = ['./packer', 'validate', '/tmp/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Couldn't validate packer template: {e}")
        with open('/tmp/packer.json', 'r') as f:
            logger.debug(f.read())
        raise

    try:
        command = ['./packer', 'build', '/tmp/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error building AMI: {e}")
        raise
