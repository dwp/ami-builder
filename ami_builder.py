import botocore
import boto3
import jinja2
import logging
import os
import subprocess
import json
import sys
from botocore.exceptions import ClientError

# Initialise logging
logger = logging.getLogger(__name__)
log_level = os.environ["LOG_LEVEL"] if "LOG_LEVEL" in os.environ else "ERROR"
logger.setLevel(logging.getLevelName(log_level.upper()))
logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s %(levelname)s %(module)s "
           "%(process)s[%(thread)s] %(message)s",
)
logger.info("Logging at {} level".format(log_level.upper()))


def handler(event, context):
    download_dir = '/tmp'
    if 'AWS_PROFILE' in os.environ:
        boto3.setup_default_session(profile_name=os.environ['AWS_PROFILE'])

    if logger.isEnabledFor(logging.DEBUG):
        # Log everything from boto3
        boto3.set_stream_logger()
    logger.debug(f"Using boto3 {boto3.__version__}")
    logger.debug(event)

    s3_url = f"https://s3.{event['packer_template_bucket_region']}.amazonaws.com"

    if event['packer_template_bucket'] and event['packer_template_key']:
        logger.info(
            f"Getting packer template from {s3_url}/{event['packer_template_bucket']}/{event['packer_template_key']}")
        s3 = boto3.resource('s3',
                            endpoint_url=s3_url,
                            config=botocore.config.Config(s3={'addressing_style': 'path'}))
        try:
            s3.Bucket(event['packer_template_bucket']).download_file(
                event['packer_template_key'], f'{download_dir}/packer_template.json.j2')
        except ClientError as e:
            logger.error(f"Unable to download packer template file: {e}")
            raise
    else:
        print("Missing required configuration")
        raise Exception

    with open(f'{download_dir}/packer_template.json.j2') as in_template:
        template = jinja2.Template(in_template.read())
    with open(f'{download_dir}/packer.json', 'w+') as packer_file:
        packer_file.write(template.render(
            event=event, download_dir=download_dir))
        logger.debug(packer_file.read())

    if 'provision_script_bucket_region' in event:
        s3_url = f"https://s3.{event['provision_script_bucket_region']}.amazonaws.com"

    if event['provision_script_bucket'] and event['provision_script_keys']:
        s3 = boto3.resource('s3',
                            endpoint_url=s3_url,
                            config=botocore.config.Config(s3={'addressing_style': 'path'}))
        for script in event['provision_script_keys']:
            logger.info(
                f"Getting provision script from {s3_url}/{event['provision_script_bucket']}/{script}")
            if not os.path.exists(f'{download_dir}/{os.path.dirname(script)}'):
                os.makedirs(f'{download_dir}/{os.path.dirname(script)}')
            try:
                s3.Bucket(event['provision_script_bucket']).download_file(
                    script, f'{download_dir}/{script}')
            except ClientError as e:
                logger.error(f"Unable to download provisioning script: {e}")
                raise
        for file_path in event['provision_file_keys']:
            logger.info(
                f"Getting provision files from {s3_url}/{event['provision_script_bucket']}/{file_path}")
            if not os.path.exists(f'{download_dir}/{os.path.dirname(file_path)}'):
                os.makedirs(f'{download_dir}/{os.path.dirname(file_path)}')
            try:
                s3.Bucket(event['provision_script_bucket']).download_file(
                    file_path, f'{download_dir}/{file_path}')
            except ClientError as e:
                logger.error(f"Unable to download provisioning file: {e}")
                raise

    try:
        command = ['./packer', 'validate', f'{download_dir}/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Couldn't validate packer template: {e}")
        with open(f'{download_dir}/packer.json', 'r') as f:
            logger.debug(f.read())
        raise

    try:
        if logger.isEnabledFor(logging.DEBUG):
            command = ['./packer', 'build', '-on-error=abort',
                       f'{download_dir}/packer.json']
        else:
            command = ['./packer', 'build', f'{download_dir}/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as e:
        logger.error(f"Error building AMI: {e}")
        raise


if __name__ == "__main__":
    json_content = json.loads(open('event.json', 'r').read())
    try:
        handler(json_content, None)
    except KeyError as key_name:
        logger.error(f'Key: {key_name} is required in payload')
        sys.exit(1)
    except Exception as e:
        logger.error(e)
        sys.exit(1)
