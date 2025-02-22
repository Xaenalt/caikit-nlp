"""Helpful fixtures for configuring individual unit tests.
"""
# Standard
from typing import Iterable, Optional
from unittest import mock
import os
import random
import tempfile

# Third Party
from datasets import load_dataset
import numpy as np
import pytest
import torch
import transformers

# First Party
from caikit.interfaces.nlp.data_model import GeneratedTextResult
from caikit_tgis_backend import TGISBackend
from caikit_tgis_backend.tgis_connection import TGISConnection
import caikit

# Local
from caikit_nlp.resources.pretrained_model import HFAutoCausalLM, HFAutoSeq2SeqLM
import caikit_nlp

### Constants used in fixtures
FIXTURES_DIR = os.path.join(os.path.dirname(__file__))
TINY_MODELS_DIR = os.path.join(FIXTURES_DIR, "tiny_models")
SEQ_CLASS_MODEL = os.path.join(TINY_MODELS_DIR, "BertForSequenceClassification")
CAUSAL_LM_MODEL = os.path.join(TINY_MODELS_DIR, "BloomForCausalLM")
SEQ2SEQ_LM_MODEL = os.path.join(TINY_MODELS_DIR, "T5ForConditionalGeneration")


@pytest.fixture
def disable_wip(request):
    """Fixture to temporarily disable wip decorator"""
    previous_state = caikit.core.toolkit.wip_decorator._ENABLE_DECORATOR
    caikit.core.toolkit.wip_decorator.disable_wip()
    yield
    caikit.core.toolkit.wip_decorator._ENABLE_DECORATOR = previous_state


### Fixtures for downloading objects needed to run tests via public internet
@pytest.fixture
def downloaded_dataset(request):
    """Download a dataset via datasets; this should be called via indirect parameterization.

    Example:
    @pytest.mark.parametrize(
        'download_dataset',
        [{"dataset_path": "ought/raft", "dataset_name": "twitter_complaints"}],
        indirect=True
    )
    def test_download_data(downloaded_dataset):
        # downloaded_dataset is a reference to the loaded dataset

    NOTE: Currently this is unused, but we keep it here in case we get some tiny
    models that we want to run quick regression tests on in the future.
    """
    dataset_path = request.param["dataset_path"]
    dataset_name = request.param["dataset_name"]
    return load_dataset(dataset_path, dataset_name)


@pytest.fixture
def temp_cache_dir(request):
    """Use a temporary directory as our transformers / huggingface cache dir. We have permission
    to do things in this directory, but we don't have anything downloaded in it.
    """
    old_cache_path = transformers.utils.hub.TRANSFORMERS_CACHE
    # Create a new tempdir & cache it
    temp_dir = tempfile.TemporaryDirectory()
    transformers.utils.hub.TRANSFORMERS_CACHE = temp_dir.name
    yield
    temp_dir.cleanup()
    if old_cache_path is not None:
        transformers.utils.hub.TRANSFORMERS_CACHE = old_cache_path


@pytest.fixture
def models_cache_dir(request):
    """Use the tiny models directory as the HuggingFace Cache."""
    old_cache_path = transformers.utils.hub.TRANSFORMERS_CACHE
    transformers.utils.hub.TRANSFORMERS_CACHE = TINY_MODELS_DIR
    yield
    if old_cache_path is not None:
        transformers.utils.hub.TRANSFORMERS_CACHE = old_cache_path


### Fixtures for grabbing a randomly initialized model to test interfaces against
## Causal LM
@pytest.fixture
def causal_lm_train_kwargs():
    """Get the kwargs for a valid train call to a Causal LM."""
    model_kwargs = {
        "base_model": HFAutoCausalLM.bootstrap(
            model_name=CAUSAL_LM_MODEL, tokenizer_name=CAUSAL_LM_MODEL
        ),
        "train_stream": caikit.core.data_model.DataStream.from_iterable([]),
        "num_epochs": 0,
        "tuning_config": caikit_nlp.data_model.TuningConfig(
            num_virtual_tokens=8, prompt_tuning_init_text="hello world"
        ),
    }
    return model_kwargs


@pytest.fixture
def causal_lm_dummy_model(causal_lm_train_kwargs):
    """Train a Causal LM dummy model."""
    return caikit_nlp.modules.text_generation.PeftPromptTuning.train(
        **causal_lm_train_kwargs
    )


## Seq2seq
@pytest.fixture
def seq2seq_lm_train_kwargs():
    """Get the kwargs for a valid train call to a Causal LM."""
    model_kwargs = {
        "base_model": HFAutoSeq2SeqLM.bootstrap(
            model_name=SEQ2SEQ_LM_MODEL, tokenizer_name=SEQ2SEQ_LM_MODEL
        ),
        "train_stream": caikit.core.data_model.DataStream.from_iterable([]),
        "num_epochs": 0,
        "tuning_config": caikit_nlp.data_model.TuningConfig(
            num_virtual_tokens=16, prompt_tuning_init_text="hello world"
        ),
    }
    return model_kwargs


@pytest.fixture
def seq2seq_lm_dummy_model(seq2seq_lm_train_kwargs):
    """Train a Seq2Seq LM dummy model."""
    return caikit_nlp.modules.text_generation.PeftPromptTuning.train(
        **seq2seq_lm_train_kwargs
    )


@pytest.fixture()
def requires_determinism(request):
    """Set all of random seeds for tests expected to be deterministic."""
    # Basically, set the random seed of anything our tests might depend on
    seed = 1
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    transformers.set_seed(seed)


### Common TGIS stub classes

# Helper stubs / mocks; we use these to patch caikit so that we don't actually
# test the TGIS backend directly, and instead stub the client and inspect the
# args that we pass to it.
class StubTGISClient:
    def __init__(self, base_model_name):
        pass

    def Generate(self, request):
        return StubTGISClient.unary_generate(request)

    def GenerateStream(self, request):
        return StubTGISClient.stream_generate(request)

    @staticmethod
    def unary_generate(request):
        fake_response = mock.Mock()
        fake_result = mock.Mock()
        fake_result.stop_reason = 5
        fake_result.generated_token_count = 1
        fake_result.text = "moose"
        fake_response.responses = [fake_result]
        return fake_response

    @staticmethod
    def stream_generate(request):
        fake_stream = mock.Mock()
        fake_stream.stop_reason = 5
        fake_stream.generated_token_count = 1
        fake_stream.seed = 10
        token = mock.Mock()
        token.text = "moose"
        token.logprob = 0.2
        fake_stream.tokens = [token]
        fake_stream.text = "moose"
        for _ in range(3):
            yield fake_stream

    @staticmethod
    def validate_unary_generate_response(result):
        assert isinstance(result, GeneratedTextResult)
        assert result.generated_text == "moose"
        assert result.generated_tokens == 1
        assert result.finish_reason == 5

    @staticmethod
    def validate_stream_generate_response(stream_result):
        assert isinstance(stream_result, Iterable)
        # Convert to list to more easily check outputs
        result_list = list(stream_result)
        assert len(result_list) == 3
        first_result = result_list[0]
        assert first_result.generated_text == "moose"
        assert first_result.tokens[0].text == "moose"
        assert first_result.tokens[0].logprob == 0.2
        assert first_result.details.finish_reason == 5
        assert first_result.details.generated_tokens == 1
        assert first_result.details.seed == 10


class StubTGISBackend(TGISBackend):
    def __init__(
        self,
        config: Optional[dict] = None,
        temp_dir: Optional[str] = None,
        mock_remote: bool = False,
    ):
        self._temp_dir = temp_dir
        if mock_remote:
            config = config or {}
            config.update({"connection": {"hostname": "foo.{model_id}:123"}})
        super().__init__(config)
        self.load_prompt_artifacts = mock.MagicMock()

    def get_client(self, base_model_name):
        self._model_connections[base_model_name] = TGISConnection(
            hostname="foo.bar",
            prompt_dir=self._temp_dir,
        )
        return StubTGISClient(base_model_name)


@pytest.fixture
def stub_tgis_backend():
    with tempfile.TemporaryDirectory() as temp_dir:
        yield StubTGISBackend(temp_dir=temp_dir)


### Args for commonly used datasets that we can use with our fixtures accepting params
TWITTER_DATA_DOWNLOAD_ARGS = [
    {"dataset_path": "ought/raft", "dataset_name": "twitter_complaints"}
]
