#   configure_bitbucket_webhooks.py: A helper script for configuring Webhooks in Bitbucket
#
#   This script will quickly retrieve details of Webhook Lambda functions from AWS 
#   and associate them with a chosen Bitbucket repository, avoiding the toil and 
#   errors associated with manual configuration.
#
#   This script performs its task well, but could be improved upon if desired. 
# 
#   TODO in no particular order:
#       - Handle the -properties repo if present
#       - Error handling, idempotence (re-running if it fails on webhook #3 won't work)
#       - Automatically grab secret value out of SecretsManager rather than accepting as input
#       - Better parsing of arguments via argparse (stdlib) or Click (3rd party)
#       - Explore option to feed a path to a repo rather than discrete inputs, auto-detect 
#         webhook names and perform any necessary configuration
#       - Better outputs, current version is extremely bare-bones

import requests
import sys

import boto3

lambda_session = boto3.Session(profile_name="launch", region_name="us-east-2")
lambda_client = lambda_session.client("lambda")

BITBUCKET_BASE_URL = "https://bitbucket.example.com/rest/api"

EVENT_MAP = {
    "pr_merge": "pr:merged",
    "pr_updated": "pr:from_ref_updated",
    "pr_modified": "pr:modified",
    "pr_open": "pr:opened"
}


def get_events_from_function_definition(definition: dict) -> list[str]:
    name = definition["FunctionName"]

    for name_match, event in EVENT_MAP.items():
        if name_match in name:
            return [event]
    return []


def add_webhook(project: str, repo: str, hook_name: str, hook_url: str, hook_secret: str, hook_events: list[str]):
    url = f"{BITBUCKET_BASE_URL}/latest/projects/{project}/repos/{repo}/webhooks"
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    payload = {
        "name": hook_name,
        "events": hook_events,
        "url": hook_url,
        "configuration": {
            "secret": hook_secret,
            "createdBy": "python"
        }
    }
    response = requests.post(url=url, headers=headers, json=payload)
    print()
    print(response.status_code)
    print(response.content)


def get_lambda_functions(prefix: str) -> list[dict]:
    found_functions: list[dict] = []
    more = True
    next_marker = None
    while more:
        if next_marker is None:
            list_response = lambda_client.list_functions()
        else:
            list_response = lambda_client.list_functions(Marker=next_marker)
        
        for function_definition in list_response["Functions"]:
            if function_definition["FunctionName"].startswith(prefix):
                found_functions.append(function_definition)
        
        if 'NextMarker' in list_response.keys():
            next_marker = list_response["NextMarker"]
        else:
            more = False
    return found_functions


def get_function_url(function_definition: dict) -> str:
    url_response = lambda_client.get_function_url_config(FunctionName=function_definition["FunctionName"])
    return url_response["FunctionUrl"]


def create_webhooks(function_definitions: list[dict], project: str, repo: str, secret: str):
    for definition in function_definitions:
        function_name = definition["FunctionName"]
        function_url = get_function_url(definition)
        add_webhook(
            project=project,
            repo=repo,
            hook_name=function_name,
            hook_url=function_url, 
            hook_secret=secret, 
            hook_events=get_events_from_function_definition(definition=definition)
        )


def usage():
    print("""
python3 configure_bitbucket_webhooks.py {PROJECT} {REPOSITORY} {PREFIX} {SECRET}

    Provide a Bitbucket PROJECT and REPOSITORY, plus a PREFIX to detect and associate webhooks, 
    and a SECRET matching the one created in SecretsManager. Four standard webhooks will be 
    configured for your repository. If your SECRET value contains special characters, you 
    should enclose it in quotes to prevent your shell from truncating the configured 
    secret in Bitbucket.
          
    NOTE: You must have configured your .netrc file with credentials for Bitbucket!""")


if __name__ == "__main__":
    args = sys.argv[1:]

    if not len(args) == 4:
        usage()
        exit(-1)
    
    project = args[0]
    repo = args[1]
    prefix = args[2]
    secret = args[3]
    
    lambda_functions = get_lambda_functions(prefix=prefix)
    if not len(lambda_functions) == 4:
        print(f"Expected 4 lambda functions, got {len(lambda_functions)}!")
        if len(lambda_functions) > 0:
            print([f["FunctionName"] for f in lambda_functions])

    create_webhooks(function_definitions=lambda_functions, project=project, repo=repo, secret=secret)
