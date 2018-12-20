import boto3
import jinja2
import os
import subprocess
import sys

def handler(event, context):
    s3 = boto3.resource('s3')

    if event['packer_template_bucket'] and event['packer_template_key']:
        s3.meta.client.download_file(event['provision_script_bucket'],
                                     event['provision_script_key'],
                                     '/tmp/packer_template.json.j2')
    else:
        print("Missing required configuration")
        raise Exception

    with open('/tmp/packer_template.json.j2') as in_template:
        template = jinja2.Template(in_template.read())
    with open('/tmp/packer.json', 'w') as packer_file:
        packer_file.write(template.render(event=event))

    if event['provision_script_bucket'] and event['provision_script_keys']:
        for script in event['provision_script_keys']:
            s3.meta.client.download_file(event['provision_script_bucket'],
                                         event['provision_script_key'],
                                         f'/tmp/{script}')

    try:
        command = ['./package/packer', 'validate', '/tmp/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print("Error validating packer template")
        raise

    try:
        command = ['./package/packer', 'build', '/tmp/packer.json']
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError:
        print("Error building AMI")
        raise
