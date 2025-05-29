#!/usr/bin/env bash
set -e

mkdir -p ~/.aws
if [ ! -f ~/.aws/credentials ]; then
cat <<EOT >> ~/.aws/credentials
[PillCityDevTerraform]
aws_access_key_id=<Access key ID>
aws_secret_access_key=<Secret access key>
region=us-west-2
EOT
fi

pip install -U pip==24.0
pip install -r requirements.txt
pushd web
yarn install
popd
