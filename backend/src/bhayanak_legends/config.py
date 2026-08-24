import sys
from pathlib import Path

from pydantic_settings import BaseSettings


class SidecarConfig(BaseSettings):
    # Port zero asks the sidecar's own loopback listener to choose an ephemeral port.
    # Desktop clients learn the chosen port from the readiness handshake.
    port: int = 0
    token: str = "dev"
    data_dir: Path = Path.home() / ".local" / "share" / "BhayanakLegends"
    pack_dir: Path | None = None

    model_config = {"env_prefix": "BHAYANAK_"}

    def resolved_pack_dir(self) -> Path:
        if self.pack_dir:
            return self.pack_dir
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            bundled = Path(meipass) / "pack"
            if bundled.exists():
                return bundled
        repo = Path(__file__).resolve().parents[3]
        return repo / "pack"

    def resolved_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir
