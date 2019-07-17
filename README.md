# ami-builder-configs
Configuration files for building various AMIs using ami-builder

All our AMI configuration source code is kept in [AMI Builder Config](https://github.com/dwp/ami-builder-configs)

# ami-builder
Building AMIs using a Lambda function

## How to Use This Code

### Deploy the Lambda Code
Step 1: Grab the latest Packer release [release zip file](https://github.com/dwp/ami-builder/blob/master/.circleci/config.yml)
This is done via the CircleCI config.yml file, and then published on GitHub.
Example below:
```
mkdir artifacts
sudo pip install -r requirements.txt -t artifacts
cp -v ami_builder.py LICENSE packer_template.json.j2 README.md artifacts
curl -O https://releases.hashicorp.com/packer/1.3.3/packer_1.3.3_linux_amd64.zip
cd artifacts
unzip ../packer_1.3.3_linux_amd64.zip
LATEST_VERSION=$(curl --silent "https://api.github.com/repos/${CIRCLE_PROJECT_USERNAME}/${CIRCLE_PROJECT_REPONAME}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
VERSION=$(echo $LATEST_VERSION | awk -F. '{$NF = $NF + 1;} 1' | sed 's/ /./g')
VERSION_NUMBER=$(echo $VERSION | sed 's/^v\(.*\)$/\1/')
zip -r ami-builder-$VERSION_NUMBER.zip *
- persist_to_workspace:
root: artifacts
paths:
- ami-builder-*.zip
publish-github-release:
docker:
- image: cibuilds/github:0.10
steps:
 - attach_workspace:
at: ./artifacts
- run:
name: "Publish Release on GitHub"
command: |
LATEST_VERSION=$(curl --silent "https://api.github.com/repos/${CIRCLE_PROJECT_USERNAME}/${CIRCLE_PROJECT_REPONAME}/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/')
VERSION=$(echo $LATEST_VERSION | awk -F. '{$NF = $NF + 1;} 1' | sed 's/ /./g')
echo "ghr -t GITHUB_TOKEN -u ${CIRCLE_PROJECT_USERNAME} -r ${CIRCLE_PROJECT_REPONAME} -c ${CIRCLE_SHA1} -delete ${VERSION} ./artifacts/"
ghr -t ${GITHUB_TOKEN} -u ${CIRCLE_PROJECT_USERNAME} -r ${CIRCLE_PROJECT_REPONAME} -c ${CIRCLE_SHA1} -delete ${VERSION} ./artifacts/

```

Step 2: Create an AWS Lambda function.

[Packer Lambda Code](https://github.ucds.io/dip/aws-management-infrastructure/blob/master/packer.tf)
Creating the Lambda function
The following code is Terraform examples

```
resource "aws_lambda_function" "ami_builder" {
  filename         = "${var.ami_builder_zip["base_path"]}/ami-builder-${var.ami_builder_zip["version"]}.zip"
  function_name    = "ami_builder"
  role             = "${aws_iam_role.lambda_ami_builder.arn}"
  handler          = "ami_builder.handler"
  runtime          = "python3.7"
  source_code_hash = "${base64sha256(file(format("%s/ami-builder-%s.zip",var.ami_builder_zip["base_path"],var.ami_builder_zip["version"])))}"
  publish          = true
  tags             = "${local.common_tags}"
```
This allows Packer EC2 Instance HTTP internet traffic outbound via a NAT
```
resource "aws_security_group_rule" "allow_packer_EC2_internet_http" {
  description       = "Allow Packer EC2 Instance HTTP internet traffic outbound via a NAT"
  type              = "egress"
  from_port         = 80
  to_port           = 80
  protocol          = "tcp"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = "${aws_security_group.packer.id}"
}
```

CloudWatch logs are also configured here
```
resource "aws_cloudwatch_log_group" "ami_builder" {
  name              = "/aws/lambda/ami_builder"
  retention_in_days = 30
  tags              = "${local.common_tags}"
}
```

Step 3: Create a Lambda Payload File
In order to configure the behaviour of the Lambda function, e.g. what source AMI to use,
you will need to provide it with a payload file. This payload file is output as a manifest.json file which is created here.
[payload file creation](https://github.ucds.io/dip/aws-management-infrastructure/blob/master/ci/meta.yml)
Please see link for [Packer docs](https://www.packer.io/docs/builders/amazon.html) for further information.
An example is given below:

```
            cat << EOF > manifest.json
            {
            "log_level":                      "${LOG_LEVEL}",
            "packer_template_bucket_region":  "${PACKER_TEMPLATE_BUCKET_REGION}",
            "packer_template_bucket":         "${PACKER_TEMPLATE_BUCKET}",
            "packer_template_key":            "${PACKER_TEMPLATE_KEY}",
            "provision_script_bucket_region": "${PROVISION_SCRIPT_BUCKET_REGION}",
            "provision_script_bucket":        "${PROVISION_SCRIPT_BUCKET}",
            "provision_script_keys":          ${PROVISION_SCRIPT_KEYS},
            "provision_file_keys":            ${PROVISION_FILE_KEYS},
            "source_ami_virt_type":           "${SOURCE_AMI_VIRT_TYPE}",
            "source_ami_name":                "${SOURCE_AMI_NAME}",
            "source_ami_root_device_type":    "${SOURCE_AMI_ROOT_DEVICE_TYPE}",
            "source_ami_owner":               "${SOURCE_AMI_OWNER}",
            "instance_type":                  "${INSTANCE_TYPE}",
            "ssh_username":                   "${SSH_USERNAME}",
            "subnet_id":                      "${SUBNET_ID}",
            "ami_name":                       "${AMI_NAME}",
            "profile":                        "${PROFILE}",
            "security_group_id":              "${SECURITY_GROUP_ID}",
            "ami_users":                      "${AMI_USERS}",
            "region":                         "${REGION}"
            }
            EOF
```

Step 4: Create an S3 Bucket for Configuration Items
As you can see from the payload file above, the Lambda function expects you to
have an S3 bucket that contains the packer generic configuration template key file and
(optionally) an S3 bucket containing any provisioning scripts and associated
deployable artifacts that those scripts reference (the same bucket can be used
for both, of course)
This allows the Lambda itself to be completely generic, and to be used to
generate arbitrarily complex AMIs, providing, of course, that the build can
complete within the Lambda's defined execution time which is currently set to maximum allowed of 15 minutes.

[S3 bucket creation](https://github.ucds.io/dip/aws-management-infrastructure/blob/master/s3.tf)
```
resource "aws_s3_bucket" "config" {
  bucket = "${random_id.config_bucket.hex}"
  acl    = "private"
  tags   = "${local.common_tags}"
```
An example packer configuration template key file is available:
This shows how the packer configuration file can be created by referencing the payload file that is supplied to the Lambda function.
[packer_template.json.j2](https://github.com/dwp/ami-builder/blob/master/packer_template.json.j2)

Step 5: Uploading the configuration files to S3 bucket
Sync directories and S3 prefixes. Recursively copies new and updated files from the source directory to the destination.
Files that exist in the destination but not in the source are deleted during sync
[Upload config files to S3 bucket](https://github.ucds.io/dip/aws-management-infrastructure/blob/master/ci/meta.yml)

```
aws s3 --endpoint-url=https://s3-eu-west-2.amazonaws.com sync tmp s3://${AMI_BUILDER_CONFIG_BUCKET}/ami-builder --exclude ".*" --exclude "LICENSE" --delete
```
Step 6: Invoke the Lambda function
So, having deployed the Lambda function, created a payload file, and uploaded
your packer configuration template file and provisioning scripts to an S3
bucket, you can now invoke the Lambda:

We overwrite our manifest.json file during the AMI build. This allows for individual AMI build configurations.
Here additional configuration files can be added. The example below is for the DKS host AMI config.
[Overwrite manifest generation file](https://github.ucds.io/dip/aws-management-infrastructure/tree/master/ci/jobs/build_amis)

```
      - .: (( inject meta.plan.generate-manifest ))
        config:
          params:
            LOG_LEVEL: DEBUG
            AMI_NAME: dks-host-ami
            INSTANCE_TYPE: m4.large
            PACKER_TEMPLATE_KEY: ami-builder/dks-host/generic_packer_template.json.j2
            PROVISION_SCRIPT_KEYS: '["ami-builder/dks-host/dks-host-install.sh"]'
            PROVISION_FILE_KEYS: '["ami-builder/dks-host/dks","ami-builder/dks-host/dks.sh","ami-builder/dks-host/server.properties","ami-builder/dks-host/dks.logrotate"]'
      - .: (( inject meta.plan.build-ami ))
```

#CONCOURSE AMI BUILD PIPELINE JOBS:

[AMI Builder Release](https://concourse.service.dw/teams/dataworks/pipelines/management)
[AMI Builder Config Release](https://concourse.service.dw/teams/dataworks/pipelines/management?groups=AMIs)

Below are some fly command line examples to trigger these builds manually from your terminal

```
fly -t concourse check-resource -r management/ami-builder-configs-release
```
```
fly -t concourse check-resource -r aws-crypto/dks-host-ami
```

Eg to trigger a check on a pipeline in concourse, use
```
fly -t concourse check-resource -r pipeline/ami-builder-configs-release
```
