import hashlib
import hmac
import json
import logging
import os
import re
import traceback

import boto3
import requests

# Initialize logger
logger = logging.getLogger()
if os.environ.get("LOGGING_LEVEL") not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    logging_level = "INFO"
else:
    logging_level = os.environ.get("LOGGING_LEVEL")

logger.setLevel(logging.getLevelName(logging_level))

# Initialize boto3
s3 = boto3.client('s3')
code_build = boto3.client('codebuild')
secrets_manager = boto3.client('secretsmanager')


def validate_lambda_env_vars(env_vars: dict):
    mandatory_environment_vars = [
        'CODEBUILD_PROJECT_NAME',
        'CODEBUILD_ENV_VARS_MAP',
        'CODEBUILD_URL',
        'GIT_SERVER_URL',
        'GIT_USERNAME_SM_ARN',
        'GIT_TOKEN_SM_ARN',
        'WEBHOOK_EVENT_TYPE',
        'VALIDATE_DIGITAL_SIGNATURE'
    ]
    validation_errors = []
    valid = True
    for key, val in env_vars.items():
        if key in mandatory_environment_vars and not val:
            validation_errors.append(f"Variable: {key} must not be empty")
            valid = False
    return valid, " ".join(validation_errors)


def lambda_handler(event, context):
    try:
        lambda_env_vars = {key: value for key, value in os.environ.items()}
        valid, validation_message = validate_lambda_env_vars(lambda_env_vars)
        if not valid:
            return prepare_response(500, f"Following mandatory lambda vars not set: {validation_message}")
        logger.debug(f"Incoming event: {json.dumps(event)}")
        event_body = json.loads(event['body'])
        logger.debug(f"Incoming Body: {json.dumps(event_body)}")

        # Normalize headers
        normalized_headers = {k.lower(): v for k, v in event['headers'].items()}
        logger.debug(f"Headers: {normalized_headers}")

        if 'x-event-key' in normalized_headers:
            event_type = normalized_headers['x-event-key']
            if event_type == "diagnostics:ping":
                return prepare_response(200, 'Webhook configured successfully')
        elif 'x-github-event' in normalized_headers:
            if normalized_headers["x-github-event"] == "ping":
                return prepare_response(200, 'Webhook configured successfully')
            event_type = event_body['action']
        else:
            logger.error(f"Event type not found in headers {normalized_headers}")
        logger.info(f"Event type: {event_type}")

        # Verify if the lambda is configured for correct event_type
        if str(event_type).lower() != str(lambda_env_vars.get('WEBHOOK_EVENT_TYPE')).lower():
            return prepare_response(500, f"The webhook event_type: {event_type} "
                                         f"doesn't match lambda function's event type:"
                                         f" {lambda_env_vars.get('WEBHOOK_EVENT_TYPE')}")

        # Validate message digital signature
        if str(lambda_env_vars.get('VALIDATE_DIGITAL_SIGNATURE', 'FALSE').lower()) == 'true':
            git_secret = secrets_manager.get_secret_value(SecretId=str(lambda_env_vars.get('GIT_SECRET_SM_ARN'))).get('SecretString')
            lambda_env_vars['GIT_SECRET'] = str(git_secret)
            if not check_signature(git_secret, normalized_headers['x-hub-signature'], event['body']):
                logger.error('Invalid webhook message signature')
                return prepare_response(401, 'Signature is not valid')
        env_vars = prepare_codebuild_inputs(event_body, lambda_env_vars)
        if not env_vars:
            return prepare_response(500, "Unable to parse webhook payload, "
                                         "Please verify the env var: CODEBUILD_ENV_VARS_MAP")

        # Invoke the CodeBuild Job
        codebuild_id = start_codebuild_job(lambda_env_vars.get('CODEBUILD_PROJECT_NAME'), env_vars)

        # Authentication
        git_username = secrets_manager.get_secret_value(SecretId=str(lambda_env_vars.get('GIT_USERNAME_SM_ARN'))).get('SecretString')
        git_token = secrets_manager.get_secret_value(SecretId=str(lambda_env_vars.get('GIT_TOKEN_SM_ARN'))).get('SecretString')
        auth = (str(git_username), str(git_token))

        # Merging both dictionaries are required for the logic in invoking callback method
        merged_env_vars = {**env_vars, **lambda_env_vars}
        merged_env_vars['GIT_USERNAME'] = str(git_username)
        merged_env_vars['GIT_TOKEN'] = str(git_token)
        merged_env_vars['LATEST_SHORT_HASH'] = merged_env_vars.get('LATEST_COMMIT_HASH', "")[:7]
        merged_env_vars["CODEBUILD_STATUS"] = "INPROGRESS"
        merged_env_vars["CALLBACK_DESCRIPTION"] = f"CodeBuild job with id: {codebuild_id} is submitted successfully."
        # Invoke the Git callback and update the build as "INPROGRESS"
        status = invoke_git_callback(merged_env_vars, auth)
        # Respond to the webhook request
        return prepare_response(status, f"Codebuild stated with an id: {codebuild_id}")

    except Exception as e:
        logger.error(e)
        traceback.print_exc()
        try:
            merged_env_vars["CALLBACK_DESCRIPTION"] = f"Build job submission has failed: {e}"
            merged_env_vars["CODEBUILD_STATUS"] = "FAILED"
            invoke_git_callback(merged_env_vars)
        except Exception as e:
            logger.error(f"Unable to update Git webhook to FAILED. Resulted in error: {e}")
        return prepare_response(500, e)


def check_signature(signing_secret, signature, body):
    logger.info("Checking signature")
    # Create a digital signature by signing the body with the provided secret (pass in as env var)
    digest = hmac.new(signing_secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()
    logger.debug(f"Digest = {digest}")

    signature_hash = signature.split('=')
    # Compare the created signature against the one passed in as the webhook header
    if signature_hash[1] == digest:
        return True

    return False


def prepare_response(status_code, detail="An unknown error has occurred."):
    if not status_code:
        raise TypeError('response_to_api_gw() expects at least argument status_code')
    if status_code != 200 and not detail:
        raise TypeError('response_to_api_gw() expects at least arguments status_code and detail')

    body = {}
    if 200 <= status_code < 300:
        body = {
            'statusCode': status_code,
            'message': detail
        }
    else:
        body = {
            'statusCode': status_code,
            'fault': detail
        }
    response = {
        'statusCode': status_code,
        'body': json.dumps(body),
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'POST, GET',
            'Access-Control-Allow-Headers': 'Origin, X-Requested-With, Content-Type, Accept'
        }
    }
    return response


def prepare_codebuild_inputs(body: dict, lambda_env_vars: dict):
    code_build_env_vars = {}

    try:
        logger.debug(f"CODEBUILD_ENV_VARS_MAP={lambda_env_vars.get('CODEBUILD_ENV_VARS_MAP')}")
        env_vars_dict = json.loads(lambda_env_vars.get('CODEBUILD_ENV_VARS_MAP'))
        logger.debug(f"env_vars_dict={env_vars_dict}")
        logger.debug(f"type of env_vars_dict: {type(env_vars_dict)}")
        for env_var, json_path in env_vars_dict.items():
            code_build_env_vars[env_var] = get_value_from_dict(body, json_path)
        # Add any other Env Vars we want to pass to CodeBuild.
        for key, value in os.environ.items():
            if key.startswith("USERVAR_") or key.startswith("GIT_"):
                code_build_env_vars[key] = value
    except Exception as e:
        logger.error(f"Error in parsing the webhook payload: {e}")
        traceback.print_exc()

    logger.info(f"Environment variables to be passed to CodeBuild: {code_build_env_vars}")

    return code_build_env_vars


def start_codebuild_job(project_name, env_vars: dict):

    logger.info(f"Starting CodeBuild job for project: {project_name}")
    try:
        code_build_env_vars = [
            {
                'name': key,
                'value': value
            } for key, value in env_vars.items()
        ]
        response = code_build. \
            start_build(projectName=project_name,
                        environmentVariablesOverride=code_build_env_vars)
    except Exception as e:
        raise e
    return response["build"]["id"]


def invoke_git_callback(merged_env_vars, auth):
    # Create URL object for the HTTP endpoint
    pattern = r"\{\{(\w+)\}\}"
    url = merged_env_vars.get('GIT_CALLBACK_URI', None)
    if not url:
        logger.info(f"Did not find callback url to set build status: {url}")
        return 200

    try:
        payload = merged_env_vars['GIT_CALLBACK_PAYLOAD']
    except KeyError:
        logger.error(f"GIT_CALLBACK_PAYLOAD must be set if GIT_CALLBACK_URI is set: {e}")
        raise e

    # Create request headers
    headers = {
        'Content-Type': 'application/json'
    }
    try:
        # Render the url and the payload
        post_url = re.sub(pattern, lambda match: str(merged_env_vars.get(match.group(1))), url).rstrip()
        post_payload = json.loads(re.sub(pattern, lambda match: str(merged_env_vars.get(match.group(1))), payload))
        logger.debug(f"POST Payload: {post_payload}")
        logger.debug(f"POST Headers: {headers}")

        logger.info(f"Invoking Git Callback: {post_url}")
        response = requests.post(post_url, json=post_payload, headers=headers, auth=auth)

        logger.info(f"Git Callback response Code: {response.status_code}")
        logger.debug(f"Response Body: {response.content}")
    except Exception as e:
        logger.error(f"Error while invoking Git callback: {e}")
        raise e

    return response.status_code


def parse_filter_condition(filter_condition):
    # pattern to find string with square brackets []
    pattern = r'\[(.*?)\]'

    matches = re.findall(pattern, filter_condition)

    if len(matches) == 1:
        filter_key = matches[0]
        search_key, search_value = filter_key.split('=')
        return search_key, search_value
    else:
        raise TypeError(f"Invalid key: {filter_condition}")


def get_value_from_dict(dictionary: dict, json_path: str):
    """
    Given a JSON document as a python dictionary and a dot-separated string path,
    returns the value of the corresponding key in the JSON document.
    """
    # Split the path into a list of keys and indices
    keys = json_path.split('.')
    # Traverse the JSON document using the keys and indices
    current_dictionary = dictionary
    for key in keys:
        if "[" in key:
            current_key = key.split('[')[0]
            # The json element must be a list
            if not isinstance(current_dictionary[current_key], list):
                raise TypeError(f"No object of type list found in the json for the key: {key} in path: {json_path}")
            else:
                search_key, search_value = parse_filter_condition(key)
                for index, obj in enumerate(current_dictionary[current_key]):
                    if obj[search_key] == search_value:
                        current_dictionary = current_dictionary[current_key][index]
        elif isinstance(current_dictionary, dict):
            # If the current object is a dictionary, use the key as a string
            if key in current_dictionary:
                current_dictionary = current_dictionary[key]
            else:
                raise TypeError(f"Key: {key} in path: {json_path} not found in the dictionary")
        else:
            raise TypeError(f"No object/value found for the key: {key} in path: {json_path}")

    return current_dictionary
