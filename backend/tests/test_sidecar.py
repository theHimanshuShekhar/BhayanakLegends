import io
import json

import pytest
from pydantic import ValidationError

from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.sidecar import emit_readiness, readiness_line


VALID_TOKEN = "test-sidecar-token-with-at-least-32-chars"


@pytest.mark.parametrize(
    "token",
    [None, "", " " * 32, "short", "dev", "a" + " " * 31, "dev" + " " * 29],
)
def test_sidecar_rejects_weak_tokens_before_startup(token):
    with pytest.raises(ValidationError):
        if token is None:
            SidecarConfig()
        else:
            SidecarConfig(token=token)


def test_sidecar_accepts_explicit_strong_token():
    config = SidecarConfig(token=VALID_TOKEN)
    assert config.port == 0


def test_sidecar_defaults_to_ephemeral_port():
    assert SidecarConfig(token=VALID_TOKEN).port == 0


def test_readiness_line_contains_actual_port_once():
    output = io.StringIO()
    emit_readiness(43127, output)

    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"type": "ready", "port": 43127}
    assert readiness_line(43127) == lines[0]
