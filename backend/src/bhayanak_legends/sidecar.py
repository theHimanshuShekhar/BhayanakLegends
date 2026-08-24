"""Sidecar entrypoint: uvicorn bound to loopback with the Tauri-negotiated port/token."""

import logging

import uvicorn

from bhayanak_legends.app import create_app
from bhayanak_legends.config import SidecarConfig


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    config = SidecarConfig()
    app = create_app(config)
    uvicorn.run(app, host="127.0.0.1", port=config.port, log_level="info")


if __name__ == "__main__":
    main()
