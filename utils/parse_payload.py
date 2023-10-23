import json
import re


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


event_file_map = {
    "push": "../sample_payloads/bitbucket/push.json",
    "pr_open": "../sample_payloads/bitbucket/pr_open.json",
    "pr_updated": "../sample_payloads/bitbucket/pr_source_updated.json",
    "pr_merged": ""
}

push_key_map = {
    "REPOSITORY_URL": "repository.links.clone[name=http].href",
    "GIT_REF_ID": "changes[type=UPDATE].refId",
    "LATEST_COMMIT_HASH": "changes[type=UPDATE].toHash",
    "GIT_PROJECT": "repository.project.key",
    "GIT_REPO": "repository.slug",
    "BRANCH": "changes[type=UPDATE].ref.displayId",
    "EVENT_TYPE": "eventKey",
    "FROM_HASH": "changes[type=UPDATE].fromHash",
    "TO_HASH": "changes[type=UPDATE].toHash"
}

pr_opened_map = {
    "REPOSITORY_URL": "pullRequest.fromRef.repository.links.clone[name=http].href",
    "GIT_FROM_REF_ID": "pullRequest.fromRef.id",
    "GIT_TO_REF_ID": "pullRequest.toRef.id",
    "LATEST_COMMIT_HASH": "pullRequest.fromRef.latestCommit",
    "GIT_PROJECT": "pullRequest.fromRef.repository.project.key",
    "GIT_REPO": "pullRequest.fromRef.repository.slug",
    "FROM_BRANCH": "pullRequest.fromRef.displayId",
    "TO_BRANCH": "pullRequest.toRef.displayId",
    "EVENT_TYPE": "eventKey"
}

print("Push Event\n")
with open(event_file_map["push"], "r") as f:
    json_dict = json.loads(f.read())

for key, value in push_key_map.items():
    print(f"{key}={get_value_from_dict(json_dict, value)}")

print("\nPR Open Event\n")
with open(event_file_map["pr_open"], "r") as f:
    json_dict = json.loads(f.read())

for key, value in pr_opened_map.items():
    print(f"{key}={get_value_from_dict(json_dict, value)}")
