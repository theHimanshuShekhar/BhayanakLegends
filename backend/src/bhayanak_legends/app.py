import asyncio
import logging
import os
import sys
import time
import urllib.parse
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ValidationError
from starlette.middleware.cors import CORSMiddleware

from .auth import HostValidationMiddleware, RequestLoggingMiddleware, TokenAuthMiddleware
from .config import SidecarConfig
from .credentials import CredentialBackend, CredentialError, CredentialStore
from .import_paths import (
    ImportPathNotApprovedError,
    InvalidImportDirectoryError,
    canonical_import_directory,
    canonical_import_roots,
)
from .live import ChampSelectSnapshot, InGameSnapshot
from .models import (
    ChampSelectStatus,
    Health,
    HistorySummary,
    InGameStatus,
    LiveStatus,
    Settings,
    SettingsPatch,
    SyncStatus,
)
from .inference import InferenceRuntime
from .pack import PackError, PackStore
from .pack_v2 import FindingsPackV2
from .routers_data import router as data_router
from .routers_events import build_events_router
from .sse import Hub
from .store import Store
from .release_channel import DEFAULT_MANIFEST_URL, ReleaseChannel, ReleaseResult
from .version import APP_VERSION

log = logging.getLogger("bhayanak_legends")

PACK_VALIDATION_ERROR_DETAIL = "Findings Pack validation failed"
PACK_UNAVAILABLE_DETAIL = "Findings Pack unavailable"


def _allow_loopback_http(manifest_url: str) -> bool:
    """Permit HTTP only for the exact credential-free IPv4 loopback host."""
    try:
        parsed = urllib.parse.urlparse(manifest_url)
    except ValueError:
        return False
    return (
        parsed.scheme == "http"
        and parsed.hostname == "127.0.0.1"
        and parsed.username is None
        and parsed.password is None
    )

class DevImportRequest(BaseModel):
    dir: str

async def _run_release_channel_check(app: FastAPI, channel: ReleaseChannel) -> None:
    try:
        result: ReleaseResult = await channel.check_and_activate(
            app.state.pack_version,
            defer_finalize=True,
        )
        if not result.activated:
            return
        try:
            app.state.pack.reload()
            app.state.inference_runtime.clear()
            app.state.pack_error = None
            app.state.pack_version = app.state.pack.version()
            if result.activation is not None:
                result.activation.finalize()
        except Exception:
            if result.activation is not None:
                try:
                    result.activation.rollback()
                except Exception:
                    log.exception("Findings Pack release rollback failed")
            try:
                app.state.pack.reload()
            except Exception:
                log.exception("Findings Pack previous release reload failed")
            raise
        await app.state.hub.publish(
            "pack.updated",
            {
                "schema_version": result.schema_version,
                "pack_version": app.state.pack_version,
            },
        )
    except Exception:
        # Release updates are opportunistic. The bundled/current pack remains
        # the source of truth if activation or reload unexpectedly fails.
        log.exception("Findings Pack release activation failed")
def _startup_release_channel_check(app: FastAPI) -> None:
    manifest_url = os.environ.get("BHAYANAK_PACK_RELEASE_MANIFEST_URL", DEFAULT_MANIFEST_URL)
    channel = ReleaseChannel(
        app.state.pack.pack_dir,
        manifest_url=manifest_url,
        app_version=app.state.app_version,
        allow_loopback_http=_allow_loopback_http(manifest_url),
        pack_store=app.state.pack,
    )
    app.state.release_channel = channel
    app.state.release_channel_task = asyncio.create_task(
        _run_release_channel_check(app, channel),
        name="findings-pack-release-check",
    )



def create_app(
    config: SidecarConfig | None = None,
    *,
    credential_store: CredentialBackend | None = None,
    live_feature_provider=None,
) -> FastAPI:
    config = config or SidecarConfig()
    data_dir = config.resolved_data_dir()

    store = Store(data_dir / "app.db")
    credentials = credential_store or CredentialStore(store)
    pack = PackStore(
        config.resolved_active_pack_dir(),
        bundled_dir=config.resolved_bundled_pack_dir(),
    )
    pack_error: str | None = None
    try:
        pack.initialize()
        pack.load()
    except PackError:
        log.warning("%s", PACK_VALIDATION_ERROR_DETAIL)
        pack_error = PACK_VALIDATION_ERROR_DETAIL
    try:
        from .live import LiveService
        from .sync import SyncService
    except ImportError:
        LiveService = None  # type: ignore[assignment, misc]
        SyncService = None  # type: ignore[assignment, misc]
        log.warning("sync/live optional deps missing; services disabled")
    def settings_for_sync() -> dict:
        scope = store.capture_owner_scope()
        return {
            "riot_key": credentials.load(),
            "riot_id": store.get_setting("riot_id"),
            "region_route": store.get_setting("region_route") or "sea",
            "owner_key": scope["owner_key"],
            "generation": scope["generation"],
            "owner_state": scope["owner_state"],
        }

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        loop = asyncio.get_running_loop()
        if app.state.sync_service is not None:
            app.state.sync_service.attach_loop(loop)
        # Release channel startup: network check runs in the background.
        _startup_release_channel_check(app)
        if app.state.live_service is not None:
            await app.state.live_service.start()
        # Auto-sync is intentionally scheduled after the readiness-critical hooks.
        _schedule_auto_sync_startup(app)
        yield
        release_task = getattr(app.state, "release_channel_task", None)
        if release_task is not None:
            release_task.cancel()
        if app.state.sync_service is not None:
            app.state.sync_service.shutdown()
        if app.state.live_service is not None:
            await app.state.live_service.stop()

    hub = Hub()
    app = FastAPI(title="Bhayanak Legends sidecar", version=APP_VERSION, lifespan=lifespan)
    app.state.config = config
    app.state.listener_port = config.port
    app.state.store = store
    app.state.credential_store = credentials
    app.state.pack = pack
    app.state.hub = hub
    app.state.app_version = APP_VERSION
    app.state.pack_error = pack_error
    app.state.inference_runtime = InferenceRuntime(pack)
    app.state.pack_version = None if pack_error else pack.version()
    app.state.sync_service = (
        None
        if SyncService is None
        else SyncService(
            store,
            hub,
            settings_for_sync,
            import_roots=config.import_roots,
        )
    )
    if LiveService is None:
        app.state.live_feature_provider = None
        app.state.live_service = None
    else:
        from .lcu import (
            ChampionDirectory,
            DataDragonCatalogProvider,
            HttpxIngameTransport,
            HttpxLcuConnection,
        )
        from .live_features import LiveWpFeatureProvider

        champions = ChampionDirectory(data_dir / "ddragon")
        item_catalogs = DataDragonCatalogProvider()
        resolved_feature_provider = live_feature_provider or LiveWpFeatureProvider(item_catalogs)
        app.state.live_feature_provider = resolved_feature_provider
        app.state.live_service = LiveService(
            HttpxLcuConnection(config.lcu_lockfile),
            HttpxIngameTransport(config.live_client_data_url),
            hub,
            champion_names=champions.get,
            inference=app.state.inference_runtime,
            feature_provider=resolved_feature_provider,
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
    app.add_middleware(HostValidationMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/health", response_model=Health)
    def health() -> Health:
        if app.state.pack_error is None:
            try:
                validated = FindingsPackV2.model_validate(pack.load())
                pack_version = validated.pack_version
            except (PackError, ValidationError):
                pack_version = None
        else:
            pack_version = None
        return Health(
            status="ok" if pack_version is not None else "degraded",
            app_version=APP_VERSION,
            pack_version=pack_version,
        )

    @app.get("/pack", response_model=FindingsPackV2, response_model_exclude_none=True)
    def get_pack() -> dict:
        try:
            validated = FindingsPackV2.model_validate(pack.load())
        except PackError as exc:
            log.warning("Findings Pack validation failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=PACK_UNAVAILABLE_DETAIL,
            ) from None
        except ValidationError as exc:
            log.warning("Findings Pack validation failed: %s", exc)
            raise HTTPException(
                status_code=503,
                detail=PACK_UNAVAILABLE_DETAIL,
            ) from None
        return validated.model_dump(mode="json", exclude_none=True)



    @app.get("/settings", response_model=Settings)
    def get_settings() -> Settings:
        return Settings.model_validate(_settings_view(store, credentials))

    @app.put("/settings", response_model=Settings)
    def put_settings(patch: SettingsPatch) -> Settings:
        current_riot_id = store.get_setting("riot_id")
        current_region = store.get_setting("region_route") or "sea"
        current_scope = store.capture_owner_scope()
        next_riot_id = (
            patch.riot_id.strip() if patch.riot_id is not None else None
        ) if "riot_id" in patch.model_fields_set else current_riot_id
        next_region = (
            patch.region_route
            if "region_route" in patch.model_fields_set and patch.region_route is not None
            else current_region
        )
        identity_changed = (
            ("riot_id" in patch.model_fields_set and current_riot_id != next_riot_id)
            or ("region_route" in patch.model_fields_set and current_region != next_region)
            or ("riot_id" in patch.model_fields_set and next_riot_id is None)
            or (
                current_scope["owner_state"] == "error"
                and _is_valid_riot_id(next_riot_id)
                and bool(
                    {"riot_id", "region_route", "riot_key"}
                    & patch.model_fields_set
                )
            )
        )
        credential_changed = "riot_key" in patch.model_fields_set
        transition_generation: int | None = None
        if identity_changed or credential_changed:
            svc = app.state.sync_service
            if svc is not None and not svc.quiesce():
                raise HTTPException(
                    status_code=409,
                    detail="Backfill is still stopping; retry settings",
                )
            if next_riot_id is None:
                transition_state = "unassigned"
                transition_error = None
            elif _is_valid_riot_id(next_riot_id):
                transition_state = "resolving"
                transition_error = None
            else:
                transition_state = "error"
                transition_error = "valid Riot ID required (GameName#TAG)"
            transition_generation = store.begin_owner_transition(
                transition_state, transition_error
            )
        if "riot_id" in patch.model_fields_set:
            if next_riot_id is None:
                store.delete_raw_setting("riot_id")
            else:
                store.set_setting("riot_id", next_riot_id)
        if "region_route" in patch.model_fields_set and patch.region_route is not None:
            store.set_setting("region_route", patch.region_route)
        if "riot_key" in patch.model_fields_set:
            try:
                if patch.riot_key is None:
                    credentials.delete()
                else:
                    credentials.save(patch.riot_key)
            except CredentialError as exc:
                if transition_generation is not None:
                    store.set_owner_error(
                        transition_generation, "Riot API key could not be saved"
                    )
                raise HTTPException(status_code=503, detail=str(exc)) from None
            if (
                transition_generation is not None
                and patch.riot_key is None
                and next_riot_id is not None
            ):
                store.set_owner_error(transition_generation, "Riot API key required")
        if "auto_sync" in patch.model_fields_set and patch.auto_sync is not None:
            store.set_setting("auto_sync", "1" if patch.auto_sync else "0")
        if (
            transition_generation is not None
            and _is_valid_riot_id(next_riot_id)
            and not (
                "riot_key" in patch.model_fields_set and patch.riot_key is None
            )
        ):
            svc = app.state.sync_service
            if svc is not None:
                svc.resolve_owner(transition_generation)
        return Settings.model_validate(_settings_view(store, credentials))

    @app.get("/sync/status", response_model=SyncStatus)
    def sync_status() -> SyncStatus:
        scope = store.capture_owner_scope()
        svc = app.state.sync_service
        payload = svc.status() if svc is not None else {}
        payload = {**payload, **_owner_status_fields(scope)}
        return SyncStatus.model_validate(payload)

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
            return SyncStatus.model_validate(svc.start())
        except CredentialError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from None

    @app.post("/sync/cancel", response_model=SyncStatus)
    def sync_cancel() -> SyncStatus:
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        return SyncStatus.model_validate(svc.cancel(wait=True))

    @app.post("/dev/import", response_model=SyncStatus)
    async def dev_import(body: DevImportRequest) -> SyncStatus:
        if getattr(sys, "frozen", False) or not config.allow_import or not config.import_roots:
            raise HTTPException(status_code=403, detail="dev import disabled")
        canonical_roots = canonical_import_roots(config.import_roots)
        if not canonical_roots:
            raise HTTPException(status_code=403, detail="dev import disabled")
        try:
            canonical_dir = canonical_import_directory(
                Path(body.dir), canonical_roots
            )
        except InvalidImportDirectoryError as exc:
            raise HTTPException(status_code=400, detail=exc.detail) from None
        except ImportPathNotApprovedError as exc:
            raise HTTPException(status_code=403, detail=exc.detail) from None
        svc = app.state.sync_service
        if svc is None:
            raise HTTPException(status_code=503, detail="sync service not wired yet")
        loop = asyncio.get_running_loop()
        try:
            result = await asyncio.to_thread(svc.import_from_dir, canonical_dir, loop)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from None
        except RuntimeError:
            raise HTTPException(
                status_code=409,
                detail="Backfill is still stopping; retry import",
            ) from None
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


def _owner_status_fields(scope: dict) -> dict:
    return {
        "owner_key": scope.get("owner_key"),
        "generation": int(scope.get("generation") or 0),
        "owner_state": scope.get("owner_state") or "unassigned",
        "owner_error": scope.get("owner_error"),
    }


def _settings_view(
    store: Store, credentials: CredentialBackend | None = None
) -> dict:
    scope = store.capture_owner_scope()
    return {
        "riot_id": store.get_setting("riot_id"),
        "region_route": store.get_setting("region_route") or "sea",
        "has_key": credentials.has_key() if credentials is not None else store.has_setting("riot_key"),
        "auto_sync": (store.get_setting("auto_sync") or "0") == "1",
        **_owner_status_fields(scope),
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
