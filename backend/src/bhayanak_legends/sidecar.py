"""Sidecar entrypoint with an explicit loopback readiness handshake."""

from __future__ import annotations

import json
import logging
import sys
from typing import TextIO

import uvicorn

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig

READY_EVENT = "ready"


def readiness_line(port: int) -> str:
    """Return the single-line JSON message consumed by the desktop shell."""
    return json.dumps({"type": READY_EVENT, "port": port}, separators=(",", ":"))


def emit_readiness(port: int, output: TextIO = sys.stdout) -> None:
    """Emit readiness only after uvicorn has successfully bound its socket."""
    print(readiness_line(port), file=output, flush=True)


class ReadinessServer(uvicorn.Server):
    """Uvicorn server that reports the actual port after binding."""

    def __init__(self, config: uvicorn.Config, *, readiness_output: TextIO = sys.stdout):
        super().__init__(config)
        self._readiness_output = readiness_output
        self._readiness_emitted = False

    async def startup(self, sockets=None) -> None:
        await super().startup(sockets)
        if self._readiness_emitted or not self.servers:
            return
        listener = self.servers[0].sockets
        if not listener:
            raise RuntimeError("sidecar listener was not created")
        emit_readiness(int(listener[0].getsockname()[1]), self._readiness_output)
        self._readiness_emitted = True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = SidecarConfig()
    app = create_app(config)
    server_config = uvicorn.Config(app, host="127.0.0.1", port=config.port, log_level="info")
    ReadinessServer(server_config).run()


if __name__ == "__main__":
    main()
