# Git Webhook for CodeBuild

The lambda function acts as a webhook to invoke a CodePipeline job. 


## Setup your lambda
These settings are necessary on your lambda function:

### Upload your code as a zip file to your lambda
```shell
chmod +x build_deployable_zip.sh
./build_deployable_zip.sh
```
### IAM Permissions
The lambda function need the following permissions in order to fetch the keyvault secrets as well as trigger a CodePipeline run:
```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "VisualEditor0",
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "codepipeline:StartPipelineExecution"
      ],
      "Resource": "*"
    }
  ]
}
```
### Handler
The name of the handler for this lambda is `codeBuildHandler.lambda_handler`
### Lambda Environment variables
This lambda function requires that a few mandatory environment variables are passed in to the lambda function. Below are the list of environment variables
```shell
# A valid json parsable string
# This example is for push event (repo:refs_changed)
CODEPIPELINE_ENV_VARS_MAP={ "REPOSITORY_URL": "repository.links.clone[name=http].href", "GIT_REF_ID": "changes[type=UPDATE].refId", "LATEST_COMMIT_HASH": "changes[type=UPDATE].toHash", "GIT_PROJECT": "repository.project.key", "GIT_REPO": "repository.slug", "BRANCH": "changes[type=UPDATE].ref.displayId", "EVENT_TYPE": "eventKey", "FROM_HASH": "changes[type=UPDATE].fromHash", "TO_HASH": "changes[type=UPDATE].toHash" }
# CodeBuild job to trigger
CODEBUILD_PROJECT_NAME=bitbucket-codebuild-webhook
# URL of the CodeBuild for the correct region
CODEBUILD_URL=https://us-east-2.console.aws.amazon.com/codesuite/codebuild/projects?region=us-east-2
# Git Callback payload (to update the status of the webhook)
# Below example is for BitBucket payload
GIT_SECRET=<git_secret>
# URL of the Git provider URL
GIT_SERVER_URL=https://bitbucket.example.com
# Token/password to connect to git provider
GIT_TOKEN=<git_token>
# Username to connect to git provider
GIT_USERNAME=example
# Logging level of lambda function (Optional). Default=INFO. Valid values (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOGGING_LEVEL=DEBUG
# Whether to validate the digital signature of the payload body. Default=false Header `x-hub-signature` contains the sha-256 signature to match
VALIDATE_DIGITAL_SIGNATURE=true
# Webhook Event type this lambda function will listen to (Valid values for BitBucket: repo:refs_changed, pr:opened, pr:updated, pr:merged)
# Bitbucket event details: https://confluence.atlassian.com/bitbucketserver0721/event-payload-1115665959.html
WEBHOOK_EVENT_TYPE=repo:refs_changed
```

The following environment variables are optional if you wish to enable the codebuild build status callback feature. This does not work for github.
```shell
GIT_CALLBACK_PAYLOAD={"state": "{{CODEBUILD_STATUS}}", "key": "{{CODEBUILD_PROJECT_NAME}}-{{LATEST_SHORT_HASH}}", "name": "{{CODEBUILD_PROJECT_NAME}}", "url": "{{CODEBUILD_URL}}", "description": "{{CALLBACK_DESCRIPTION}}" }
# Git Callback URI (to update the status of the webhook)
# LATEST_COMMIT_HASH must be a key in CODEPIPELINE_ENV_VARS_MAP
# Below example is for BitBucket callback URI
GIT_CALLBACK_URI={{GIT_SERVER_URL}}/rest/build-status/1.0/commits/{{LATEST_COMMIT_HASH}}
# Salt used to create digital signature. Required if VALIDATE_DIGITAL_SIGNATURE=true
# For Bitbucket, this is configured while creating the webhook
```

#### CODEPIPELINE_ENV_VARS_MAP
For each Git event the webhook would respond to, the lambda function has to be configured with a `dictionary/map` environment variable. The key of the map would be the environment variable to be passed to the `CodeBuild job` and the value would be the path in the webhook payload where the value be fetched.

Listed below are examples of the `CODEPIPELINE_ENV_VARS_MAP` for BitBucket events that will be supported in our project

##### [Bitbucket] Push
```shell
{
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
```

##### [Bitbucket] PR Opened
```shell
{
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
```

##### [Bitbucket] PR Updated
```shell
{
    "REPOSITORY_URL": "pullRequest.fromRef.repository.links.clone[name=http].href",
    "GIT_FROM_REF_ID": "pullRequest.fromRef.id",
    "GIT_TO_REF_ID": "pullRequest.toRef.id",
    "LATEST_COMMIT_HASH": "pullRequest.fromRef.latestCommit",
    "GIT_PROJECT": "pullRequest.fromRef.repository.project.key",
    "GIT_REPO": "pullRequest.fromRef.repository.slug",
    "FROM_BRANCH": "pullRequest.fromRef.displayId",
    "TO_BRANCH": "pullRequest.toRef.displayId",
    "EVENT_TYPE": "eventKey"
    "PREVIOUS_FROM_HASH": "previousFromHash"
}
```

##### [Bitbucket] PR Merged
```shell
TBD. Dont have one yet
```

##### [Github] Pull request
```shell
{
    "SOURCE_REPO_URL": "repository.clone_url",
    "FROM_BRANCH": "pull_request.head.ref",
    "TO_BRANCH": "pull_request.base.ref",
    "MERGE_COMMIT_ID": "pull_request.head.sha"
}
```


### Map Webhook events to CodePipeline projects
The way to specify which events trigger which CodePipeline events is by providing an environment variable called **GITHUB_ENABLED_EVENTS** on your lambda with the following format:
```json
{
  "opened": "CodePipeline-Project-1",
  "edited": "CodePipeline-Project-1",
  "closed": "CodePipeline-Project-1",
  "reopened": "CodePipeline-Project-1",
  "assigned": "CodePipeline-Project-1",
  "unassigned": "CodePipeline-Project-1",
  "review_requested": "CodePipeline-Project-1",
  "review_request_removed": "CodePipeline-Project-1",
  "labeled": "CodePipeline-Project-2",
  "unlabeled": "CodePipeline-Project-2",
  "synchronize": "CodePipeline-Project-3"
}
```
You can use this command to populate the env var in your lambda:
```shell
cat << EOF | tr '\n' ' ' | pbcopy
{
    "opened": "CodePipeline-Project-1",
    "edited": "CodePipeline-Project-1",
    "closed": "CodePipeline-Project-1",
    "reopened": "CodePipeline-Project-1",
    "assigned": "CodePipeline-Project-1",
    "unassigned": "CodePipeline-Project-1",
    "review_requested": "CodePipeline-Project-1",
    "review_request_removed": "CodePipeline-Project-1",
    "labeled": "CodePipeline-Project-2",
    "unlabeled": "CodePipeline-Project-2",
    "synchronize": "CodePipeline-Project-3"
}
EOF
```

## [Bitbucket] Webhook Events
Our current plan supports the following webhook events
- Push
  - Event Type `repo:refs_changed`
- PR Created
  - Event Type `pr:opened`
- PR Updated (source branch updated)
  - Event Type `pr:from_ref_updated`
- PR Merged
  - Event Type `pr:merged`

## [Github] Webhook Events
Our current plan supports the following webhook events
- Pull request
  - Event Type `pull_request`
- PR Merged
  - Event Type `closed`
- PR Updated (source branch updated)
  - Event Type `synchronize`
- PR Opened
  - Event Type `opened`

