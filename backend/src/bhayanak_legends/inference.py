"""Fail-closed local inference for Findings Pack v2 ONNX declarations."""

from __future__ import annotations

import math
from collections.abc import Mapping
from numbers import Real
from pathlib import Path
from typing import Any

from .model_runtime import ModelRuntimeError, load_onnx_session, run_model
from .models import LiveInference, WhatIfResponse
from .pack import PackError, PackStore
from .live_features import FEATURE_ORDER, LIVE_WP_CONTRACT_VERSION, LiveFeatureVector
from .pack_v2 import EXECUTABLE_MODEL_KEYS, FindingsPackV2, WITHHELD_MODEL_KEYS


class InferenceRuntime:
    """Load only active-pack-declared ONNX models with fixed session settings."""

    def __init__(self, pack: PackStore) -> None:
        self._pack_store = pack
        self._sessions: dict[str, tuple[object, object, tuple[str, ...]]] = {}

    @staticmethod
    def _finite(value: object) -> bool:
        if isinstance(value, bool):
            return False
        try:
            return isinstance(value, Real) and math.isfinite(float(value))
        except (TypeError, ValueError, OverflowError):
            return False

    @staticmethod
    def _pack_error_reason(error: object) -> str:
        """Map detailed loader failures to display-safe diagnostics."""
        text = str(error).lower()
        if "runtime" in text and "unavailable" in text:
            return "model runtime is unavailable"
        if "missing" in text or "unavailable" in text:
            return "active Findings Pack is unavailable"
        return "active Findings Pack failed model validation"

    def _pack_v2(self) -> tuple[FindingsPackV2 | None, str | None]:
        try:
            payload = self._pack_store.load()
        except PackError as exc:
            return None, self._pack_error_reason(exc)
        if payload.get("schema_version") != 2:
            return None, "active pack has no v2 model declarations"
        try:
            return FindingsPackV2.model_validate(payload), None
        except Exception:
            return None, "active Findings Pack failed model validation"

    def _declaration(self, model_key: str) -> tuple[FindingsPackV2 | None, Any, str | None]:
        pack, error = self._pack_v2()
        if pack is None:
            return None, None, error
        declaration = (pack.models or {}).get(model_key)
        if declaration is None:
            return pack, None, "model declaration unavailable"
        # This is deliberately checked before release_status and before any
        # artifact access.  It protects the gate even when a caller supplies a
        # malformed object that bypassed FindingsPackV2 validation.
        if model_key in WITHHELD_MODEL_KEYS:
            return pack, None, "Surrender Advisor is unavailable"
        if model_key not in EXECUTABLE_MODEL_KEYS:
            return pack, None, "model declaration unavailable"
        if declaration.release_status != "available":
            return pack, None, declaration.release_reason or "model is not released"
        if declaration.artifact is None or declaration.model_card is None:
            return pack, None, "model artifact or card unavailable"
        expected_contract = (pack.feature_contracts.models or {}).get(model_key)
        if expected_contract != declaration.model_card.feature_contract_version:
            return (
                pack,
                None,
                "model card feature contract is incompatible with the active pack",
            )
        return pack, declaration, None

    @staticmethod
    def _patch_in_scope(patch: str | None, patch_range: Any) -> bool:
        if patch is None:
            return True

        def patch_key(value: object) -> tuple[int, int] | None:
            if not isinstance(value, str):
                return None
            parts = value.strip().split(".")
            if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
                return None
            return int(parts[0]), int(parts[1])

        candidate = patch_key(patch)
        minimum = patch_key(getattr(patch_range, "min", None))
        maximum = patch_key(getattr(patch_range, "max", None))
        return (
            candidate is not None
            and minimum is not None
            and maximum is not None
            and minimum <= candidate <= maximum
        )

    def _session(self, model_key: str, declaration: Any, root: Path) -> tuple[object, object]:
        artifact = declaration.artifact
        card = declaration.model_card
        if artifact is None or card is None:
            raise ModelRuntimeError("model artifact or card unavailable")
        fingerprint = (
            artifact.path,
            artifact.sha256,
            artifact.model_card_sha256,
            card.model_version,
        )
        try:
            resolved_root = root.resolve()
            artifact_path = (root / artifact.path).resolve()
        except OSError as exc:
            raise ModelRuntimeError("model artifact path could not be resolved") from exc
        if resolved_root not in artifact_path.parents or not artifact_path.is_file():
            raise ModelRuntimeError("model artifact is unavailable")
        session = load_onnx_session(artifact_path, card)
        self._sessions[model_key] = (session, card, fingerprint)
        return session, card

    def _features(
        self,
        declaration: Any,
        values: Mapping[str, object],
        *,
        adjustable_only: bool = False,
    ) -> tuple[dict[str, float] | None, list[str], str | None]:
        card = declaration.model_card
        if card is None:
            return None, [], "model card unavailable"
        expected = list(card.feature_order)
        expected_set = set(expected)
        provided = set(values)
        if any(not isinstance(name, str) for name in provided):
            return None, [], "model feature names must be strings"
        rejected = sorted(provided - expected_set)
        if rejected:
            return None, rejected, "input contains undeclared features"
        if provided != expected_set:
            missing = sorted(expected_set - provided)
            return None, missing, "required model features are missing"
        output: dict[str, float] = {}
        for feature in card.features:
            value = values.get(feature.name)
            if not self._finite(value):
                return None, [feature.name], "model features must be finite numbers"
            numeric = float(value)
            if numeric < feature.bounds.min or numeric > feature.bounds.max:
                return None, [feature.name], "model feature is outside its declared domain"
            if adjustable_only and not feature.adjustable:
                return None, [feature.name], "model feature is not adjustable"
            output[feature.name] = numeric
        return output, [], None

    @staticmethod
    def _output_value(raw: object) -> float | None:
        value = raw
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            try:
                value = tolist()
            except Exception:
                return None
        while isinstance(value, (list, tuple)):
            if len(value) != 1:
                return None
            value = value[0]
            tolist = getattr(value, "tolist", None)
            if callable(tolist):
                try:
                    value = tolist()
                except Exception:
                    return None
        if isinstance(value, bool):
            return None
        try:
            result = float(value)
        except (TypeError, ValueError, OverflowError):
            return None
        return result if math.isfinite(result) and 0 <= result <= 1 else None

    def predict(
        self,
        model_key: str,
        values: Mapping[str, object],
        *,
        patch: str | None = None,
        observed_game_time_s: float | None = None,
    ) -> LiveInference:
        with self._pack_store.read_transaction():
            return self._predict_unlocked(
                model_key,
                values,
                patch=patch,
                observed_game_time_s=observed_game_time_s,
            )

    def _predict_unlocked(
        self,
        model_key: str,
        values: Mapping[str, object],
        *,
        patch: str | None = None,
        observed_game_time_s: float | None = None,
    ) -> LiveInference:
        pack, declaration, reason = self._declaration(model_key)
        if pack is None or declaration is None:
            return LiveInference(status="suppressed", reason=reason)
        if not isinstance(values, Mapping):
            return LiveInference(
                status="suppressed",
                reason="model feature vector unavailable",
            )
        card = declaration.model_card
        if card is None:
            return LiveInference(
                status="suppressed",
                pack_version=pack.pack_version,
                reason="model card unavailable",
            )
        if not self._patch_in_scope(patch, card.patch_scope):
            return LiveInference(
                status="unsupported-patch",
                model_version=card.model_version,
                pack_version=pack.pack_version,
                observed_game_time_s=observed_game_time_s,
                reason="patch is outside the model card scope",
            )
        vector, _rejected, error = self._features(declaration, values)
        if vector is None:
            status = "out-of-domain" if error and "domain" in error else "suppressed"
            return LiveInference(
                status=status,
                model_version=card.model_version,
                pack_version=pack.pack_version,
                observed_game_time_s=observed_game_time_s,
                reason=error,
            )
        try:
            session, session_card = self._session(
                model_key,
                declaration,
                self._pack_store.pack_dir,
            )
            probability = run_model(session, session_card, vector)
        except ModelRuntimeError as exc:
            return LiveInference(
                status="error",
                model_version=card.model_version,
                pack_version=pack.pack_version,
                observed_game_time_s=observed_game_time_s,
                reason=str(exc),
            )
        except Exception:
            return LiveInference(
                status="error",
                model_version=card.model_version,
                pack_version=pack.pack_version,
                observed_game_time_s=observed_game_time_s,
                reason="model inference failed",
            )
        return LiveInference(
            status="available",
            probability=probability,
            observed_game_time_s=observed_game_time_s,
            model_version=card.model_version,
            pack_version=pack.pack_version,
        )

    def what_if(
        self,
        adjustments: Mapping[str, object],
        baseline: Mapping[str, object],
        *,
        patch: str | None = None,
    ) -> WhatIfResponse:
        with self._pack_store.read_transaction():
            return self._what_if_unlocked(adjustments, baseline, patch=patch)

    def _what_if_unlocked(
        self,
        adjustments: Mapping[str, object],
        baseline: Mapping[str, object],
        *,
        patch: str | None = None,
    ) -> WhatIfResponse:
        pack, declaration, reason = self._declaration("personal_what_if")
        if pack is None or declaration is None:
            return WhatIfResponse(
                status="suppressed",
                pack_version=pack.pack_version if pack else None,
                reason=reason,
            )
        card = declaration.model_card
        if card is None:
            return WhatIfResponse(
                status="suppressed",
                pack_version=pack.pack_version,
                reason="model card unavailable",
            )
        expected = {feature.name for feature in card.features}
        adjustable = {feature.name for feature in card.features if feature.adjustable}
        rejected = sorted(set(adjustments) - adjustable)
        if rejected:
            return WhatIfResponse(
                status="rejected",
                model_version=card.model_version,
                pack_version=pack.pack_version,
                rejected_fields=rejected,
                reason="only model-card-declared adjustable features may change",
            )
        if set(baseline) != expected:
            return WhatIfResponse(
                status="rejected",
                model_version=card.model_version,
                pack_version=pack.pack_version,
                rejected_fields=sorted(set(baseline) ^ expected),
                reason="Personal History baseline does not match the model feature contract",
            )
        feature_by_name = {feature.name: feature for feature in card.features}
        invalid_adjustments: list[str] = []
        out_of_domain: list[str] = []
        for name, value in adjustments.items():
            feature = feature_by_name[name]
            if not self._finite(value):
                invalid_adjustments.append(name)
                continue
            numeric = float(value)
            if numeric < feature.bounds.min or numeric > feature.bounds.max:
                out_of_domain.append(name)
        if invalid_adjustments:
            return WhatIfResponse(
                status="rejected",
                model_version=card.model_version,
                pack_version=pack.pack_version,
                rejected_fields=sorted(invalid_adjustments),
                reason="adjustments must be finite numbers",
            )
        if out_of_domain:
            return WhatIfResponse(
                status="out-of-domain",
                model_version=card.model_version,
                pack_version=pack.pack_version,
                rejected_fields=sorted(out_of_domain),
                reason="adjustments are outside their declared model domains",
            )
        changed = dict(baseline)
        changed.update(adjustments)
        baseline_result = self.predict("personal_what_if", baseline, patch=patch)
        changed_result = self.predict("personal_what_if", changed, patch=patch)
        if changed_result.status != "available" or baseline_result.status != "available":
            return WhatIfResponse(
                status=changed_result.status,
                baseline_probability=baseline_result.probability,
                model_version=changed_result.model_version or baseline_result.model_version,
                pack_version=changed_result.pack_version or baseline_result.pack_version,
                adjusted_features={
                    key: float(value) for key, value in changed.items() if self._finite(value)
                },
                reason=changed_result.reason or baseline_result.reason,
            )
        return WhatIfResponse(
            status="available",
            probability=changed_result.probability,
            baseline_probability=baseline_result.probability,
            adjusted_features={key: float(value) for key, value in changed.items()},
            model_version=changed_result.model_version,
            pack_version=changed_result.pack_version,
        )

    def predict_live_snapshot(
        self,
        snapshot: Mapping[str, object] | None,
        *,
        observed_game_time_s: float | None = None,
        feature_provider=None,
    ) -> LiveInference:
        with self._pack_store.read_transaction():
            return self._predict_live_snapshot_unlocked(
                snapshot,
                observed_game_time_s=observed_game_time_s,
                feature_provider=feature_provider,
            )

    def _predict_live_snapshot_unlocked(
        self,
        snapshot: Mapping[str, object] | None,
        *,
        observed_game_time_s: float | None = None,
        feature_provider=None,
    ) -> LiveInference:
        """Evaluate one exact, typed Live WP vector from an injected adapter."""
        if feature_provider is None or not isinstance(snapshot, Mapping):
            return LiveInference(
                status="suppressed",
                observed_game_time_s=observed_game_time_s,
                reason="exact live feature adapter unavailable",
            )
        try:
            vector = feature_provider(snapshot)
        except Exception:
            return LiveInference(
                status="suppressed",
                observed_game_time_s=observed_game_time_s,
                reason="live feature extraction failed",
            )
        if vector is None:
            return LiveInference(
                status="suppressed",
                observed_game_time_s=observed_game_time_s,
                reason="live feature vector unavailable",
            )
        if not isinstance(vector, LiveFeatureVector):
            return LiveInference(
                status="suppressed",
                observed_game_time_s=observed_game_time_s,
                reason="live feature vector has no typed contract",
            )
        if vector.contract_version != LIVE_WP_CONTRACT_VERSION:
            return LiveInference(
                status="incompatible",
                observed_game_time_s=observed_game_time_s,
                reason="live feature contract is incompatible",
            )

        def patch_key(value: object) -> tuple[int, int] | None:
            if not isinstance(value, str):
                return None
            parts = value.strip().split(".")
            if len(parts) < 2 or not parts[0].isdigit() or not parts[1].isdigit():
                return None
            return int(parts[0]), int(parts[1])

        if patch_key(vector.patch) != patch_key(vector.data_dragon_version):
            return LiveInference(
                status="incompatible",
                observed_game_time_s=observed_game_time_s,
                reason="live patch and Data Dragon versions are incompatible",
            )
        values = dict(zip(FEATURE_ORDER, vector.values, strict=True))
        return self.predict(
            "live_wp",
            values,
            patch=vector.patch,
            observed_game_time_s=(
                observed_game_time_s
                if observed_game_time_s is not None
                else vector.observed_at_s
            ),
        )

    def what_if_from_personal_features(
        self,
        adjustments: Mapping[str, object],
        features: Mapping[str, object],
        *,
        patch: str | None = None,
    ) -> WhatIfResponse:
        with self._pack_store.read_transaction():
            return self._what_if_from_personal_features_unlocked(
                adjustments,
                features,
                patch=patch,
            )

    def _what_if_from_personal_features_unlocked(
        self,
        adjustments: Mapping[str, object],
        features: Mapping[str, object],
        *,
        patch: str | None = None,
    ) -> WhatIfResponse:
        """Build a model-card-ordered baseline from one v2 personal row."""
        pack, declaration, reason = self._declaration("personal_what_if")
        if pack is None or declaration is None:
            return WhatIfResponse(
                status="suppressed",
                pack_version=pack.pack_version if pack else None,
                reason=reason,
            )
        card = declaration.model_card
        if card is None:
            return WhatIfResponse(
                status="suppressed",
                pack_version=pack.pack_version,
                reason="model card unavailable",
            )
        baseline = {feature.name: features.get(feature.name) for feature in card.features}
        return self.what_if(adjustments, baseline, patch=patch)

    def clear(self) -> None:
        with self._pack_store.read_transaction():
            self._sessions.clear()
