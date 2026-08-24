import io
import json

from bhayanak_legends.config import SidecarConfig
from bhayanak_legends.sidecar import emit_readiness, readiness_line


def test_sidecar_defaults_to_ephemeral_port():
    assert SidecarConfig().port == 0


def test_readiness_line_contains_actual_port_once():
    output = io.StringIO()
    emit_readiness(43127, output)

    lines = output.getvalue().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == {"type": "ready", "port": 43127}
    assert readiness_line(43127) == lines[0]
