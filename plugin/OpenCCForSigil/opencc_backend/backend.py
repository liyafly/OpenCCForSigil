"""Production adapter for the vendored official `opencc` package."""

from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from app.errors import DependencyError
from opencc_backend.configs import V1_CONFIGS, comparison_configs, validate_config
from opencc_backend.errors import BackendConversionError
from opencc_backend.provenance import BackendProvenance
from opencc_backend.runtime_selector import RuntimeSelector


@dataclass(frozen=True)
class SelfTestResult:
    passed: bool
    checks: Dict[str, bool]
    error: Optional[str] = None


class OpenCCBackend:
    """Only production conversion path allowed by the v1.3 specification."""

    def __init__(self, config: str, selector: Optional[RuntimeSelector] = None) -> None:
        self.config = validate_config(config)
        self._selector = selector or RuntimeSelector()
        try:
            self._module, runtime, payload, root, import_origin = self._selector.import_opencc()
        except Exception as exc:
            if isinstance(exc, DependencyError):
                raise
            raise DependencyError(f"official OpenCC Python Binding is unavailable: {exc}") from exc
        self._runtime = runtime
        self._payload = payload
        self._payload_root = root
        self._import_origin = import_origin
        self._available_configs = tuple(
            config_name for config_name in V1_CONFIGS if config_name in _config_stems(self._module)
        )
        self._ensure_config_is_exposed()
        try:
            # This is the public upstream API. The default tofu policy is intentional.
            self._converter = self._module.OpenCC(self.config)
        except Exception as exc:
            raise BackendConversionError(
                f"official OpenCC could not construct config {self.config!r}"
            ) from exc

    def available_configs(self) -> Tuple[str, ...]:
        return self._available_configs

    def convert(self, text: str) -> str:
        if not isinstance(text, str):
            raise TypeError("OpenCC input must be text")
        try:
            result = self._converter.convert(text)
        except Exception as exc:
            raise BackendConversionError(f"OpenCC conversion failed for {self.config}") from exc
        if not isinstance(result, str):
            raise BackendConversionError("official OpenCC returned a non-text result")
        return result

    def provenance(self) -> BackendProvenance:
        manifest = self._selector.manifest
        return BackendProvenance(
            opencc_version=manifest.opencc_version,
            opencc_python_binding_version=manifest.opencc_version,
            python_implementation=self._runtime.python_implementation,
            python_version=self._runtime.python_version,
            python_abi=self._runtime.python_abi,
            runtime_os=self._runtime.os,
            runtime_architecture=self._runtime.architecture,
            upstream_tag=manifest.upstream_tag,
            upstream_commit=manifest.upstream_commit,
            import_path_id=self._payload.runtime.payload_id,
            wheel_filename=self._payload.wheel_name,
            wheel_sha256=self._payload.wheel_sha256,
            payload_sha256=self._payload.payload_sha256,
            import_origin=self._import_origin,
            data_manifest_sha256=_config_data_hash(manifest.config_data),
            config_sha256=manifest.config_hash(self._payload, self.config),
            config_name=self.config,
            tofu_policy=manifest.tofu_policy,
        )

    def self_test(self) -> SelfTestResult:
        checks: Dict[str, bool] = {
            "manifest": True,
            "payload": self._payload_root.is_dir(),
            "import_origin": bool(self._import_origin),
            "version": str(getattr(self._module, "__version__", ""))
            == self._selector.manifest.opencc_version,
            "config": True,
            "s2t_smoke": False,
        }
        try:
            checks["config"] = set(self._available_configs) >= set(V1_CONFIGS)
            checks["s2t_smoke"] = self._module.OpenCC("s2t").convert("汉字") == "漢字"
        except Exception:
            checks["config"] = False
            checks["s2t_smoke"] = False
        passed = all(checks.values())
        return SelfTestResult(passed=passed, checks=checks, error=None if passed else "self-test failed")

    def comparison_configs(self, config: str) -> Tuple[str, ...]:
        return comparison_configs(config)

    def close(self) -> None:
        # The official binding owns native resources; dropping the public object
        # is the only lifecycle operation OpenCCForSigil performs.
        self._converter = None

    def _ensure_config_is_exposed(self) -> None:
        if _config_stems(self._module) < {self.config}:
            raise DependencyError(f"selected wheel does not expose OpenCC config {self.config}")


def _config_stems(module: object) -> set:
    configs = getattr(module, "CONFIGS", ())
    return {str(value)[:-5] if str(value).endswith(".json") else str(value) for value in configs}


def _config_data_hash(config_data: object) -> Optional[str]:
    if not isinstance(config_data, dict):
        return None
    value = config_data.get("manifest_sha256")
    return str(value) if value else None
