ZIPFILE_NAME=lambda.zip

.PHONY: test
test:
	pip3 install .
	pytest

.PHONY: build-zipped-lambda
build-zipped-lambda:
	rm -rf packages \
 		&& rm -rf dist && echo -e "Installing pip packages\n"
	pip3 install -q . -t packages
	cd packages && echo -e "Creating Zip..." && \
		zip -qr "../${ZIPFILE_NAME}" *
	echo -e "Zipped file located at : $(realpath ${ZIPFILE_NAME})" && rm -rf packages