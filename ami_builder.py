import botocore
import boto3
import jinja2
import logging
import os
import subprocess
import sys

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def handler(event, context):
    if 'log_level' in event:
        try:
            logger.setLevel(logging.getLevelName(event['log_level'].upper()))
        except ValueError:
            logger.warning(f"Invalid log level specified: {event['log_level']}; using INFO")

    if event['packer_template_bucket_region'] and event['packer_template_bucket'] and event['packer_template_key']:
        s3_url=f"https://s3.{event['packer_template_bucket_region']}.amazonaws.com"
        logger.info(f"Getting packer template from {s3_url}/{event['packer_template_bucket']}/{event['packer_template_key']}")
        s3 = boto3.resource('s3', event['packer_template_bucket_region'],
                            endpoint_url=s3_url,
                            config=botocore.config.Config(s3={'addressing_style':'path'}))
        s3.Bucket(event['packer_template_bucket']).download_file(event['packer_template_key'], '/tmp/packer_template.json.j2')
    else:
        print("Missing required configuration")
        raise Exception

    with open('/tmp/packer_template.json.j2') as in_template:
        template = jinja2.Template(in_template.read())
    with open('/tmp/packer.json', 'w') as packer_file:
        packer_file.write(template.render(event=event))

    if event['provision_script_bucket_region'] and event['provision_script_bucket'] and event['provision_script_keys']:
        s3_url=f"https://s3.{event['provision_script_bucket_region']}.amazonaws.com"
        s3 = boto3.resource('s3', event['provision_script_bucket_region'],
                            endpoint_url=s3_url,
                            config=botocore.config.Config(s3={'addressing_style':'path'}))
        for script in event['provision_script_keys']:
            s3.Bucket(event['provision_script_bucket']).download_file(script, f'/tmp/{script}')

    try:
        command = ['./packer', 'validate', '/tmp/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print("Error validating packer template")
        raise

    try:
        command = ['./packer', 'build', '/tmp/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print("Error building AMI")
        raise
