"""Shared fixtures: isolate mutable module state so tests never leak
into each other (job postings created, tokens issued, pending previews)."""

import pytest

from fieldglass_agent import tools
from mock_fieldglass import app as mock_app
from mock_fieldglass import data


@pytest.fixture(autouse=True)
def isolated_state():
    postings_before = list(data.JOB_POSTINGS)
    tokens_before = dict(mock_app._tokens)
    pending_before = set(tools._pending_confirmations)
    yield
    data.JOB_POSTINGS[:] = postings_before
    mock_app._tokens.clear()
    mock_app._tokens.update(tokens_before)
    tools._pending_confirmations.clear()
    tools._pending_confirmations.update(pending_before)
