import pytest
from botocore.stub import Stubber

from codeBuildHandler import code_pipeline

@pytest.fixture()
def codepipeline_stub():
    with Stubber(code_pipeline) as stubber:
        yield stubber
        stubber.assert_no_pending_responses()