import sys
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings


class SidecarConfig(BaseSettings):
    # Port zero asks the sidecar's own loopback listener to choose an ephemeral port.
    # Desktop clients learn the chosen port from the readiness handshake.
    port: int = 0
    token: str = "dev"
    data_dir: Path = Path.home() / ".local" / "share" / "BhayanakLegends"
    pack_dir: Path | None = None
    # Optional local replay seams; production defaults retain normal discovery.
    lcu_lockfile: Path | None = None
    live_client_data_url: str = "https://127.0.0.1:2999/liveclientdata/allgamedata"
    # Development-only local import capability. A non-empty approved-root list
    # is required in addition to this flag before the endpoint is enabled.
    allow_import: bool = False
    import_roots: list[Path] = Field(default_factory=list)

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
