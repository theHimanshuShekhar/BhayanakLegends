"""Strict, deterministic ONNX loading shared by pack activation and inference."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from numbers import Real
from pathlib import Path

from .pack_v2 import PackV2ModelCard


class ModelRuntimeError(RuntimeError):
    """An ONNX artifact cannot satisfy its model-card contract."""


_CPU_PROVIDER = "CPUExecutionProvider"
_FLOAT_TYPES = frozenset({"tensor(float)", "tensor(float32)"})


def _shape_is_valid(shape: object, *, feature_count: int, output: bool) -> bool:
    if not isinstance(shape, Sequence) or isinstance(shape, (str, bytes)):
        return False
    dimensions = list(shape)
    if output:
        if len(dimensions) == 1:
            return dimensions[0] in (None, "batch", "N", 1)
        return (
            len(dimensions) == 2
            and dimensions[0] in (None, "batch", "N", 1)
            and dimensions[-1] == 1
        )
    if len(dimensions) != 2:
        return False
    return dimensions[0] in (None, "batch", "N", 1) and dimensions[-1] == feature_count


def _inspect_session(session: object, card: PackV2ModelCard) -> None:
    get_inputs = getattr(session, "get_inputs", None)
    get_outputs = getattr(session, "get_outputs", None)
    get_providers = getattr(session, "get_providers", None)
    if not callable(get_inputs) or not callable(get_outputs) or not callable(get_providers):
        raise ModelRuntimeError("ONNX session does not expose model metadata")
    try:
        inputs = list(get_inputs())
        outputs = list(get_outputs())
        input_names = [item.name for item in inputs]
        output_names = [item.name for item in outputs]
        providers = list(get_providers())
    except Exception as exc:
        raise ModelRuntimeError("ONNX session metadata could not be inspected") from exc
    if not inputs or not outputs:
        raise ModelRuntimeError("ONNX model must expose declared inputs and outputs")
    if len(inputs) != len(card.input_names) or input_names != card.input_names:
        raise ModelRuntimeError("ONNX model inputs do not match the model card")
    if len(outputs) != len(card.output_names) or output_names != card.output_names:
        raise ModelRuntimeError("ONNX model outputs do not match the model card")
    if any(getattr(item, "type", None) not in _FLOAT_TYPES for item in inputs + outputs):
        raise ModelRuntimeError("ONNX model tensors must use float32")
    if not _shape_is_valid(
        getattr(inputs[0], "shape", None), feature_count=len(card.feature_order), output=False
    ):
        raise ModelRuntimeError("ONNX model input shape does not match the model card")
    if not _shape_is_valid(getattr(outputs[0], "shape", None), feature_count=1, output=True):
        raise ModelRuntimeError("ONNX model output shape does not contain one probability")
    if providers != [_CPU_PROVIDER]:
        raise ModelRuntimeError("ONNX model must use the CPU execution provider")


def load_onnx_session(path: Path, card: PackV2ModelCard) -> object:
    """Load one CPU-only ONNX session and inspect its complete I/O contract."""
    try:
        import onnxruntime as ort  # type: ignore[import-not-found]
    except ImportError as exc:
        raise ModelRuntimeError("ONNX runtime is unavailable") from exc
    try:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 1
        options.inter_op_num_threads = 1
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        # Avoid provider- or optimizer-dependent graph rewrites.  The model card
        # and smoke vector are the activation contract, not a best-effort probe.
        if hasattr(ort, "GraphOptimizationLevel"):
            options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_DISABLE_ALL
        session = ort.InferenceSession(
            str(path),
            sess_options=options,
            providers=[_CPU_PROVIDER],
        )
    except Exception as exc:
        raise ModelRuntimeError("ONNX model could not be loaded") from exc
    _inspect_session(session, card)
    return session


def _finite(value: object) -> bool:
    if isinstance(value, bool):
        return False
    try:
        return isinstance(value, Real) and math.isfinite(float(value))
    except (TypeError, ValueError, OverflowError):
        return False


def preprocess_features(card: PackV2ModelCard, values: Mapping[str, object]) -> list[float]:
    """Apply only the model-card-declared deterministic transforms."""
    transformed = {name: float(values[name]) for name in card.feature_order}
    for step in card.preprocessing:
        name = step.feature
        operation = step.operation.strip().lower()
        value = transformed[name]
        parameters = step.parameters or []
        if operation == "identity":
            result = value
        elif operation in {"standardize", "z_score"}:
            result = (value - parameters[0]) / parameters[1]
        elif operation in {"minmax", "min_max"}:
            result = (value - parameters[0]) / (parameters[1] - parameters[0])
        else:
            # This also protects a card object constructed without Pydantic.
            raise ModelRuntimeError("model preprocessing operation is unsupported")
        if not _finite(result):
            raise ModelRuntimeError("model preprocessing produced a non-finite value")
        transformed[name] = float(result)
    return [transformed[name] for name in card.feature_order]


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
    if not _finite(value):
        return None
    result = float(value)
    return result if 0 <= result <= 1 else None


def run_model(
    session: object,
    card: PackV2ModelCard,
    values: Mapping[str, object],
) -> float:
    """Run one exact-card vector and return a finite probability in [0, 1]."""
    vector = preprocess_features(card, values)
    run = getattr(session, "run", None)
    if not callable(run):
        raise ModelRuntimeError("ONNX session cannot execute inference")
    try:
        result = run(card.output_names, {card.input_names[0]: [vector]})
    except Exception as exc:
        raise ModelRuntimeError("ONNX model inference failed") from exc
    if not isinstance(result, Sequence) or isinstance(result, (str, bytes)):
        raise ModelRuntimeError("ONNX model returned an invalid output set")
    if len(result) != len(card.output_names):
        raise ModelRuntimeError("ONNX model returned an unexpected output set")
    probability = _output_value(result[0])
    if probability is None:
        raise ModelRuntimeError("ONNX model output is not a bounded probability")
    return probability


def validate_model_artifact(path: Path, card: PackV2ModelCard) -> None:
    """Load, inspect, and smoke-test an artifact before activation."""
    session = load_onnx_session(path, card)
    try:
        actual = run_model(
            session,
            card,
            dict(zip(card.feature_order, card.smoke_test.features, strict=True)),
        )
    except ModelRuntimeError:
        raise
    except Exception as exc:
        raise ModelRuntimeError("model smoke test failed") from exc
    if abs(actual - card.smoke_test.expected) > card.smoke_test.tolerance:
        raise ModelRuntimeError("model smoke test output is outside its tolerance")


__all__ = [
    "ModelRuntimeError",
    "load_onnx_session",
    "preprocess_features",
    "run_model",
    "validate_model_artifact",
]
