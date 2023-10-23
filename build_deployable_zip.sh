#!/bin/bash

ZIPFILE_NAME="lambda.zip"
rm -rf packages && mkdir -p packages
echo -e "Installing pip packages\n"
pip3 install -qr requirements.txt -t packages
pushd packages
echo -e "Creating Zip..."
zip -qr "../${ZIPFILE_NAME}" *
popd
zip -u "${ZIPFILE_NAME}" ./codeBuildHandler.py
echo -e "Zipped file located at : $(realpath ${ZIPFILE_NAME})"