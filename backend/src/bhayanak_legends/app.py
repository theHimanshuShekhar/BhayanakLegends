import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.middleware.cors import CORSMiddleware

from .auth import TokenAuthMiddleware
from .config import SidecarConfig
from .credentials import CredentialBackend, CredentialError, CredentialStore
from .live import ChampSelectSnapshot, InGameSnapshot
from .models import (
    ChampSelectStatus,
    FindingsPack,
    Health,
    HistorySummary,
    InGameStatus,
    LiveStatus,
    Settings,
    LiveState,
    SettingsPatch,
    SyncStatus,
)
from .pack import PackError, PackStore
from .routers_data import router as data_router
from .routers_events import build_events_router
from .sse import Hub
from .store import Store

APP_VERSION = "0.1.0"
log = logging.getLogger("bhayanak_legends")


class DevImportRequest(BaseModel):
    dir: str


def create_app(
    config: SidecarConfig | None = None,
    *,
    credential_store: CredentialBackend | None = None,
) -> FastAPI:
    config = config or SidecarConfig()
    data_dir = config.resolved_data_dir()

    store = Store(data_dir / "app.db")
    credentials = credential_store or CredentialStore(store)
    pack = PackStore(config.resolved_pack_dir())
    pack_error: str | None = None
    try:
        pack.load()
    except PackError as e:
        log.warning("pack load failed: %s", e)
        pack_error = str(e)

    try:
        from .live import LiveService
        from .sync import SyncService
    except ImportError:
        LiveService = None  # type: ignore[assignment, misc]
        SyncService = None  # type: ignore[assignment, misc]
        log.warning("sync/live optional deps missing; services disabled")
    def settings_for_sync() -> dict:
        return {
            "riot_key": credentials.load(),
            "riot_id": store.get_setting("riot_id"),
            "region_route": store.get_setting("region_route") or "sea",
        }

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        if app.state.sync_service is not None:
            app.state.sync_service.attach_loop(loop)
        if app.state.live_service is not None:
            await app.state.live_service.start()
        # Auto-sync is intentionally scheduled after the readiness-critical hooks.
        _schedule_auto_sync_startup(app)
        yield
        if app.state.sync_service is not None:
            app.state.sync_service.shutdown()
        if app.state.live_service is not None:
            await app.state.live_service.stop()

    hub = Hub()
    app = FastAPI(title="Bhayanak Legends sidecar", version=APP_VERSION, lifespan=lifespan)
    app.state.config = config
    app.state.store = store
    app.state.credential_store = credentials
    app.state.pack = pack
    app.state.hub = hub
    app.state.app_version = APP_VERSION
    app.state.pack_error = pack_error
    app.state.pack_version = None if pack_error else pack.version()
    app.state.sync_service = None if SyncService is None else SyncService(store, hub, settings_for_sync)
    if LiveService is None:
        app.state.live_service = None
    else:
        from .lcu import ChampionDirectory, HttpxIngameTransport, HttpxLcuConnection

        champions = ChampionDirectory(data_dir / "ddragon")
        app.state.live_service = LiveService(
            HttpxLcuConnection(),
            HttpxIngameTransport(),
            hub,
            champion_names=champions.get,
        )

    app.add_middleware(TokenAuthMiddleware, token=config.token)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:1420",
            "http://127.0.0.1:1420",
            "tauri://localhost",
            "http://tauri.localhost",
            "https://tauri.localhost",
        ],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=Health)
    def health() -> Health:
        if pack_error is None:
            try:
                pack_version = pack.version()
            except PackError:
                pack_version = None
        else:
            pack_version = None
        return Health(
            status="ok" if pack_version is not None else "degraded",
            app_version=APP_VERSION,
            pack_version=pack_version,
        )

    @app.get("/pack", response_model=FindingsPack)
    def get_pack() -> FindingsPack:
        try:
            return FindingsPack.model_validate(pack.load())
        except PackError as e:
            raise HTTPException(status_code=503, detail=str(e))

    @app.get("/settings", response_model=Settings)
    def get_settings() -> Settings:
        return Settings.model_validate(_settings_view(store, credentials))
    @app.put("/settings", response_model=Settings)
    def put_settings(patch: SettingsPatch) -> Settings:
        if "riot_id" in patch.model_fields_set:
            current_riot_id = store.get_setting("riot_id")
            next_riot_id = patch.riot_id.strip() if patch.riot_id is not None else None
            if current_riot_id != next_riot_id or next_riot_id is None:
                store.delete_raw_setting("puuid")
            if next_riot_id is None:
                store.delete_raw_setting("riot_id")
            else:
                store.set_setting("riot_id", next_riot_id)
        if "region_route" in patch.model_fields_set and patch.region_route is not None:
            current_region = store.get_setting("region_route") or "sea"
            if current_region != patch.region_route:
                store.delete_raw_setting("puuid")
            store.set_setting("region_route", patch.region_route)
        if "riot_key" in patch.model_fields_set:
            try:
                if patch.riot_key is None:
                    credentials.delete()
                else:
                    credentials.save(patch.riot_key)
            except CredentialError as exc:
                raise HTTPException(status_code=503, detail=str(exc)) from None
        if "auto_sync" in patch.model_fields_set and patch.auto_sync is not None:
            store.set_setting("auto_sync", "1" if patch.auto_sync else "0")
        return Settings.model_validate(_settings_view(store, credentials))

    @app.get("/sync/status", response_model=SyncStatus)
    def sync_status() -> SyncStatus:
        svc = app.state.sync_service
        if svc is not None:
            return SyncStatus.model_validate(svc.status())
        return SyncStatus()
    @app.post("/sync/start", response_model=SyncStatus)
    def sync_start() -> SyncStatus:
        settings = _settings_view(store, credentials)
        if not _is_valid_riot_id(settings["riot_id"]):
            raise HTTPException(
                status_code=400,
                detail="valid riot id required (GameName#TAG)",
            )
        if not settings["has_key"]:
            raise HTTPException(status_code=400, detail="riot key required")
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        try:
            return svc.start()
        except CredentialError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None

    @app.post("/sync/cancel", response_model=SyncStatus)
    def sync_cancel() -> SyncStatus:
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        return SyncStatus.model_validate(svc.cancel())

    @app.post("/dev/import", response_model=SyncStatus)
    async def dev_import(body: DevImportRequest) -> SyncStatus:
        allowed = config.token == "dev" or os.environ.get("BHAYANAK_ALLOW_IMPORT") == "1"
        if not allowed:
            raise HTTPException(status_code=403, detail="dev import disabled")
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        loop = asyncio.get_running_loop()
        result = await asyncio.to_thread(svc.import_from_dir, Path(body.dir), loop)
        return SyncStatus.model_validate(result)

    @app.get("/live/status", response_model=LiveStatus)
    def live_status() -> LiveStatus:
        svc = app.state.live_service
        if svc is not None:
            return LiveStatus.model_validate(svc.status())
        return LiveStatus(
            champ_select=ChampSelectStatus(),
            ingame=InGameStatus(),
        )

    @app.get("/live/session", response_model=ChampSelectSnapshot)
    def live_session() -> ChampSelectSnapshot:
        svc = app.state.live_service
        if svc is not None:
            return ChampSelectSnapshot.model_validate(svc.session())
        return ChampSelectSnapshot()

    @app.get("/live/ingame", response_model=InGameSnapshot)
    def live_ingame() -> InGameSnapshot:
        svc = app.state.live_service
        if svc is not None:
            return InGameSnapshot.model_validate(svc.ingame())
        return InGameSnapshot()

    app.include_router(build_events_router())
    app.include_router(data_router)
    return app


def _is_valid_riot_id(riot_id: object) -> bool:
    if not isinstance(riot_id, str):
        return False
    game_name, separator, tag_line = riot_id.strip().partition("#")
    return bool(separator and game_name.strip() and tag_line.strip() and "#" not in tag_line)


def _settings_view(
    store: Store, credentials: CredentialBackend | None = None
) -> dict:
    return {
        "riot_id": store.get_setting("riot_id"),
        "region_route": store.get_setting("region_route") or "sea",
        "has_key": credentials.has_key() if credentials is not None else store.has_setting("riot_key"),
        "auto_sync": (store.get_setting("auto_sync") or "0") == "1",
    }


async def _start_auto_sync(app: FastAPI) -> None:
    """Start the eligible startup Backfill after the app yields readiness."""
    await asyncio.sleep(0)
    settings = _settings_view(app.state.store, app.state.credential_store)
    if not settings["auto_sync"]:
        return
    if not _is_valid_riot_id(settings["riot_id"]):
        log.info("auto-sync skipped: valid Riot ID required")
        return
    if settings["region_route"] not in {"sea", "americas", "europe", "asia"}:
        log.info("auto-sync skipped: valid region route required")
        return
    try:
        riot_key = await asyncio.to_thread(app.state.credential_store.load)
    except CredentialError as exc:
        log.info("auto-sync skipped: Riot key unavailable: %s", exc)
        return
    if not isinstance(riot_key, str) or not riot_key.strip():
        log.info("auto-sync skipped: Riot key required")
        return
    service = app.state.sync_service
    if service is None:
        return
    try:
        await asyncio.to_thread(service.start)
    except CredentialError as exc:
        # Credential state can change between eligibility and worker start.
        log.warning("auto-sync skipped: %s", exc)


def _schedule_auto_sync_startup(app: FastAPI) -> None:
    """Schedule at most one startup Backfill for an eligible installation."""
    if getattr(app.state, "auto_sync_startup_scheduled", False):
        return
    app.state.auto_sync_startup_scheduled = True

    settings = _settings_view(app.state.store, app.state.credential_store)
    if not settings["auto_sync"]:
        return
    if not _is_valid_riot_id(settings["riot_id"]):
        log.info("auto-sync skipped: valid Riot ID required")
        return
    if settings["region_route"] not in {"sea", "americas", "europe", "asia"}:
        log.info("auto-sync skipped: valid region route required")
        return
    app.state.auto_sync_startup_task = asyncio.create_task(_start_auto_sync(app))
