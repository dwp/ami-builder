# ami-builder
Build AMIs using a Lambda function

## How to Use This Code

### Deploy the Lambda Code
1. Grab a [release zip file](releases/)
2. Create an AWS Lambda function, e.g.:

```
aws lambda create-function --function-name amibuilder \
--zip-file fileb://ami-builder-0.0.1.zip --handler handler --runtime python3.7 \
--role arn:aws:iam::123456789012:role/lambda-cli-role
```

### Create a Lambda Payload File

In order to configure the behaviour of the Lambda function, e.g. what source AMI to use,
you will need to provide it with a payload file.  An example is given below:

```
{
    "packer_template_bucket":      "my-bucket-name",
    "packer_template_key":         "packer_template.json.j2",
    "provision_script_bucket":     "my-bucket-name",
    "provision_script_keys":     ["provision.sh"],
    "source_ami_virt_type":        "hvm",
    "source_ami_name":             "CentOS Linux 7 x86_64*",
    "source_ami_root_device_type": "ebs",
    "source_ami_owner":            "679593333241",
    "instance_type":               "t2.micro",
    "ssh_username":                "centos",
    "subnet_id":                   "subnet-0a00aaa0",
    "ami_name":                    "my-first-ami"
}
```

### Create an S3 Bucket for Configuration Items
As you can see from the payload file above, the Lambda function expects you to
have an S3 bucket that contains the packer configuration template file and
(optionally) an S3 bucket containing any provisioning scripts and associated
deployable artifacts that those scripts reference (the same bucket can be used
for both, of course)

This allows the Lambda itself to be completely generic, and to be used to
generate arbitrarily complex AMIs, providing, of course, that the build can
complete within the Lambda's defined execution time.

An example packer configuration template file is available:
[packer_template.json.j2](packer_template.json.j2).

This shows how the packer configuration file can be created by referencing
the payload file that is supplied to the Lambda function.

### Invoke the Lambda function
So, having deployed the Lambda function, created a payload file, and uploaded
your packer configuration template file and provisioning scripts to an S3
bucket, you can now invoke the Lambda:

```aws lambda invoke --function-name amibuilder --payload payload.json```
