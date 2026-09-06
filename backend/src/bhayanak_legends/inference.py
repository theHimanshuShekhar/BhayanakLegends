"""Fail-closed local inference for Findings Pack v2 ONNX declarations."""

from __future__ import annotations

import math
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .models import LiveInference, WhatIfResponse
from .pack import PackError, PackStore
from .pack_v2 import FindingsPackV2
from .live_features import FEATURE_ORDER, LIVE_WP_CONTRACT_VERSION, LiveFeatureVector


class InferenceRuntime:
    """Load only active-pack-declared ONNX models with fixed session settings."""

    def __init__(self, pack: PackStore) -> None:
        self._pack_store = pack
        self._sessions: dict[str, tuple[object, object]] = {}

    @staticmethod
    def _finite(value: object) -> bool:
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(float(value))
        )

    def _pack_v2(self) -> tuple[FindingsPackV2 | None, str | None]:
        try:
            payload = self._pack_store.load()
        except PackError as exc:
            return None, str(exc)
        if payload.get("schema_version") != 2:
            return None, "active pack has no v2 model declarations"
        try:
            return FindingsPackV2.model_validate(payload), None
        except Exception:
            return None, "active v2 pack model declarations are invalid"

    def _declaration(self, model_key: str) -> tuple[FindingsPackV2 | None, Any, str | None]:
        pack, error = self._pack_v2()
        if pack is None:
            return None, None, error
        declaration = (pack.models or {}).get(model_key)
        if declaration is None:
            return pack, None, "model declaration unavailable"
        if declaration.release_status != "available":
            return pack, declaration, declaration.release_reason or "model is not released"
        if declaration.artifact is None or declaration.model_card is None:
            return pack, declaration, "model artifact or card unavailable"
        expected_contract = (pack.feature_contracts.models or {}).get(model_key)
        if expected_contract != declaration.model_card.feature_contract_version:
            return (
                pack,
                declaration,
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
        cached = self._sessions.get(model_key)
        if cached is not None:
            return cached
        try:
            import onnxruntime as ort  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("ONNX runtime is unavailable") from exc
        artifact = root / declaration.artifact.path
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        session = ort.InferenceSession(
            str(artifact),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )
        self._sessions[model_key] = (session, declaration.model_card)
        return session, declaration.model_card

    def _features(
        self,
        declaration: Any,
        values: Mapping[str, object],
        *,
        adjustable_only: bool = False,
    ) -> tuple[list[float] | None, list[str], str | None]:
        card = declaration.model_card
        if card is None:
            return None, [], "model card unavailable"
        expected = list(card.feature_order)
        provided = set(values)
        expected_set = set(expected)
        rejected = sorted(provided - expected_set)
        if rejected:
            return None, rejected, "input contains undeclared features"
        if set(values) != expected_set:
            missing = sorted(expected_set - provided)
            return None, missing, "required model features are missing"
        output: list[float] = []
        for feature in card.features:
            value = values.get(feature.name)
            if not self._finite(value):
                return None, [feature.name], "model features must be finite numbers"
            numeric = float(value)
            if numeric < feature.bounds.min or numeric > feature.bounds.max:
                return None, [feature.name], "model feature is outside its declared domain"
            if adjustable_only and not feature.adjustable:
                return None, [feature.name], "model feature is not adjustable"
            output.append(numeric)
        return output, [], None

    @staticmethod
    def _output_value(raw: object) -> float | None:
        value = raw
        while isinstance(value, (list, tuple)):
            if len(value) != 1:
                return None
            value = value[0]
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return None
        result = float(value)
        return result if math.isfinite(result) and 0 <= result <= 1 else None

    def predict(
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
        if not self._patch_in_scope(patch, declaration.model_card.patch_scope):
            return LiveInference(
                status="unsupported-patch",
                model_version=declaration.model_card.model_version,
                pack_version=pack.pack_version,
                observed_game_time_s=observed_game_time_s,
                reason="patch is outside the model card scope",
            )
        vector, rejected, error = self._features(declaration, values)
        if vector is None:
            status = "out-of-domain" if error and "domain" in error else "suppressed"
            return LiveInference(
                status=status,
                model_version=declaration.model_card.model_version,
                pack_version=pack.pack_version,
                observed_game_time_s=observed_game_time_s,
                reason=error,
            )
        try:
            root = self._pack_store.pack_dir
            session, card = self._session(model_key, declaration, root)
            inputs = {card.input_names[0]: [vector]}
            output = session.run(list(card.output_names), inputs)
            probability = self._output_value(output[0] if output else None)
            if probability is None:
                raise RuntimeError("model output is not a bounded probability")
        except Exception as exc:
            return LiveInference(
                status="error",
                model_version=declaration.model_card.model_version,
                pack_version=pack.pack_version,
                observed_game_time_s=observed_game_time_s,
                reason=str(exc)[:200],
            )
        return LiveInference(
            status="available",
            probability=probability,
            observed_game_time_s=observed_game_time_s,
            model_version=declaration.model_card.model_version,
            pack_version=pack.pack_version,
        )

    def what_if(
        self,
        adjustments: Mapping[str, object],
        baseline: Mapping[str, object],
        *,
        patch: str | None = None,
    ) -> WhatIfResponse:
        pack, declaration, reason = self._declaration("personal_what_if")
        if pack is None or declaration is None:
            return WhatIfResponse(status="suppressed", pack_version=pack.pack_version if pack else None, reason=reason)
        card = declaration.model_card
        if card is None:
            return WhatIfResponse(status="suppressed", pack_version=pack.pack_version, reason="model card unavailable")
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
                adjusted_features={key: float(value) for key, value in changed.items() if self._finite(value)},
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
        self._sessions.clear()
