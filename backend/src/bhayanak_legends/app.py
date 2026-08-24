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
from .models import LiveState, LiveStatus, SettingsPatch
from .pack import PackError, PackStore
from .routers_data import router as data_router
from .routers_events import build_events_router
from .sse import Hub
from .store import Store

APP_VERSION = "0.1.0"
log = logging.getLogger("bhayanak_legends")


class DevImportRequest(BaseModel):
    dir: str


def create_app(config: SidecarConfig | None = None) -> FastAPI:
    config = config or SidecarConfig()
    data_dir = config.resolved_data_dir()

    store = Store(data_dir / "app.db")
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
            "riot_key": store.get_setting("riot_key"),
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
        yield
        if app.state.sync_service is not None:
            app.state.sync_service.shutdown()
        if app.state.live_service is not None:
            await app.state.live_service.stop()

    hub = Hub()
    app = FastAPI(title="Bhayanak Legends sidecar", version=APP_VERSION, lifespan=lifespan)
    app.state.config = config
    app.state.store = store
    app.state.pack = pack
    app.state.hub = hub
    app.state.app_version = APP_VERSION
    app.state.pack_error = pack_error
    app.state.sync_service = None if SyncService is None else SyncService(store, hub, settings_for_sync)
    app.state.live_service = None if LiveService is None else LiveService(hub)

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

    @app.get("/health")
    def health():
        return {
            "status": "ok",
            "app_version": APP_VERSION,
            "pack_version": None if pack_error else f"v{pack.load()['schema_version']}",
        }

    @app.get("/pack")
    def get_pack():
        try:
            return pack.load()
        except PackError as e:
            raise HTTPException(status_code=503, detail=str(e))

    @app.get("/settings")
    def get_settings():
        return _settings_view(store)

    @app.put("/settings")
    def put_settings(patch: SettingsPatch):
        if patch.riot_id is not None:
            store.set_setting("riot_id", patch.riot_id)
        if patch.region_route is not None:
            store.set_setting("region_route", patch.region_route)
        if patch.riot_key is not None:
            store.set_setting("riot_key", patch.riot_key)
        if patch.auto_sync is not None:
            store.set_setting("auto_sync", "1" if patch.auto_sync else "0")
        return _settings_view(store)

    @app.get("/sync/status")
    def sync_status():
        svc = app.state.sync_service
        if svc is not None:
            return svc.status()
        return {
            "state": "idle",
            "mode": "era_first",
            "total_queued": 0,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "current_match_id": None,
            "started_at": None,
        }

    @app.post("/sync/start")
    def sync_start():
        if not _settings_view(store)["has_key"]:
            raise HTTPException(status_code=400, detail="riot key required")
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        return svc.start()

    @app.post("/sync/cancel")
    def sync_cancel():
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        return svc.cancel()

    @app.post("/dev/import")
    async def dev_import(body: DevImportRequest):
        allowed = config.token == "dev" or os.environ.get("BHAYANAK_ALLOW_IMPORT") == "1"
        if not allowed:
            raise HTTPException(status_code=403, detail="dev import disabled")
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        loop = asyncio.get_running_loop()
        return await asyncio.to_thread(svc.import_from_dir, Path(body.dir), loop)

    @app.get("/live/status")
    def live_status():
        svc = app.state.live_service
        if svc is not None:
            return svc.status()
        return LiveStatus(champ_select=LiveState(), ingame=LiveState()).model_dump()

    app.include_router(build_events_router())
    app.include_router(data_router)

    return app


def _settings_view(store: Store) -> dict:
    return {
        "riot_id": store.get_setting("riot_id"),
        "region_route": store.get_setting("region_route") or "sea",
        "has_key": bool(store.get_setting("riot_key")),
        "auto_sync": (store.get_setting("auto_sync") or "0") == "1",
    }
