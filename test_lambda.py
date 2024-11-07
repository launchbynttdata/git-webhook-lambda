import json
import pdb
from pdb import set_trace

import codeBuildHandler

class TestSignature:
    payload_body='test'.encode('utf-8')
    secret_token='123'
    signature_header='sha256=a7f5c8c626f994482813230854f66700e626208f52d913b9bd6b4e039aab0f41'

    def test_verify_signature_true(self):
        assert codeBuildHandler.verify_signature(self.payload_body, self.secret_token, self.signature_header) == True

    def test_verify_signature_false(self):
        assert codeBuildHandler.verify_signature(self.payload_body, self.secret_token[0:-1] + '2', self.signature_header) == False

class TestLambdaVars:
    mandatory_environment_vars = {
        'CODEPIPELINE_ENV_VARS_MAP': 1,
        'CODEBUILD_URL': 2,
        'GIT_SERVER_URL': 3,
        'GIT_USERNAME_SM_ARN': 4,
        'GIT_TOKEN_SM_ARN': 5,
        'WEBHOOK_EVENT_TYPE': 6,
        'VALIDATE_DIGITAL_SIGNATURE': 7,
        'GITHUB_ENABLED_EVENTS': 8
    }
    error_keys = [
        'GITHUB_ENABLED_EVENTS',
        'VALIDATE_DIGITAL_SIGNATURE'
    ]

    def test_validate_lambda_env_vars_true(self):
        valid, validation_errors = codeBuildHandler.validate_lambda_env_vars(self.mandatory_environment_vars)
        assert  valid == True

    def test_validate_lambda_env_vars_false(self):
        override_temp = {k: None for k in self.error_keys}
        valid, validation_errors = codeBuildHandler.validate_lambda_env_vars({**self.mandatory_environment_vars, **override_temp})
        assert  valid == False
        assert validation_errors == 'Variable: VALIDATE_DIGITAL_SIGNATURE must not be empty Variable: GITHUB_ENABLED_EVENTS must not be empty'

class TestResponsePreparation:
    response_headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, GET',
        'Access-Control-Allow-Headers': 'Origin, X-Requested-With, Content-Type, Accept'
    }

    def test_response_prepared_200(self):
        response = codeBuildHandler.prepare_response(200, 'Operation completed successfully.')
        assert response is not None

    def test_response_prepared_500(self):
        response = codeBuildHandler.prepare_response(500, 'Server error.')
        assert response.get('headers') == self.response_headers

class TestPrepareInputs:
    codepipeline_env_vars_map = {
        'SOURCE_REPO_URL': 'repository.clone_url',
        'FROM_BRANCH': 'pull_request.head.ref',
        'TO_BRANCH': 'pull_request.base.ref',
        'MERGE_COMMIT_ID': 'pull_request.head.sha'
    }
    github_pr_open_payload =  json.load(open('./sample_payloads/github/pr_open.json'))
    lambda_env_vars = {
        'CODEPIPELINE_ENV_VARS_MAP': json.dumps(codepipeline_env_vars_map),
    }
    extra_git_env_vars = {
        'GIT_USERNAME_SM_ARN': 'TestUser',
        'GIT_TOKEN_SM_ARN': 'TestToken'
    }
    extra_user_env_vars = {
        'USERVAR_KEY1': 'VALUE1',
        'USERVAR_KEY2': 'VALUE2',
    }

    # @pytest.fixture
    # def mock_env_codepipeline(self, monkeypatch):
    #     monkeypatch.setenv('CODEPIPELINE_ENV_VARS_MAP', json.dumps(self.codepipeline_env_vars_map))

    def test_prepare_codepipeline_inputs(self):
        code_pipeline_env_vars = codeBuildHandler.prepare_codepipeline_inputs(self.github_pr_open_payload, self.lambda_env_vars)
        assert code_pipeline_env_vars.keys() == self.codepipeline_env_vars_map.keys()

    def test_prepare_codepipeline_inputs_with_git_vars(self, monkeypatch):
        for key, val in self.extra_git_env_vars.items():
            monkeypatch.setenv(key, val)
        code_pipeline_env_vars = codeBuildHandler.prepare_codepipeline_inputs(self.github_pr_open_payload, self.lambda_env_vars)
        assert list(code_pipeline_env_vars.keys()) == list(self.codepipeline_env_vars_map.keys()) + list(self.extra_git_env_vars.keys())

    def test_prepare_codepipeline_inputs_with_user_vars(self, monkeypatch):
        for key, val in self.extra_user_env_vars.items():
            monkeypatch.setenv(key, val)
        code_pipeline_env_vars = codeBuildHandler.prepare_codepipeline_inputs(self.github_pr_open_payload, self.lambda_env_vars)
        assert list(code_pipeline_env_vars.keys()) == list(self.codepipeline_env_vars_map.keys()) + list(self.extra_user_env_vars.keys())

class TestBotoCalls:
    codepipeline_variables = {'key1': 'value1', 'key2': 'value2'}
    code_pipeline_env_vars = [
        {
            'name': key,
            'value': value
        } for key, value in codepipeline_variables.items()
    ]
    codepipeline_execution_id = '123'

    def test_start_codepipeline_job(self, codepipeline_stub):
        codepipeline_stub.add_response(
            'start_pipeline_execution',
            expected_params={'name': 'mock-pipeline', 'variables': self.code_pipeline_env_vars},
            service_response={
                'pipelineExecutionId': self.codepipeline_execution_id
                },
        )

        result = codeBuildHandler.start_codepipeline_job(codepipeline_name='mock-pipeline', env_vars=self.codepipeline_variables)
        assert result == self.codepipeline_execution_id