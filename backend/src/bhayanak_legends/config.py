import sys
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings


def _validate_sidecar_token(token: str) -> str:
    normalized = token.strip()
    if (
        not normalized
        or normalized != token
        or len(normalized) < 32
        or normalized.lower() == "dev"
    ):
        raise ValueError("BHAYANAK_TOKEN must be a non-blank token of at least 32 characters")
    return token


class SidecarConfig(BaseSettings):
    # Port zero asks the sidecar's own loopback listener to choose an ephemeral port.
    # Desktop clients learn the chosen port from the readiness handshake.
    port: int = 0
    token: str
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

    @model_validator(mode="after")
    def validate_startup(self) -> "SidecarConfig":
        _validate_sidecar_token(self.token)
        return self

    def resolved_bundled_pack_dir(self) -> Path:
        """Return the read-only Findings Pack seed shipped with the app."""
        if self.pack_dir:
            return self.pack_dir
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            return Path(meipass) / "pack"
        repo = Path(__file__).resolve().parents[3]
        return repo / "pack"

    def resolved_active_pack_dir(self) -> Path:
        """Return the durable Findings Pack activation directory."""
        if self.pack_dir:
            return self.pack_dir
        return self.resolved_data_dir() / "findings-pack" / "active"

    def resolved_pack_dir(self) -> Path:
        """Return the pack directory used by the sidecar at runtime."""
        return self.resolved_active_pack_dir()

    def resolved_data_dir(self) -> Path:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        return self.data_dir
