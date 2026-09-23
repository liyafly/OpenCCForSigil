"""Production adapter for the vendored official `opencc` package."""

from dataclasses import dataclass
from concurrent.futures import Future, ThreadPoolExecutor
from time import perf_counter
from typing import Dict, Optional, Tuple

from app.errors import DependencyError
from opencc_backend.configs import (
    JIEBA_CONFIGS,
    V1_CONFIGS,
    comparison_configs,
    is_jieba_config,
    validate_config,
)
from opencc_backend.errors import BackendConversionError
from opencc_backend.manifest import NativePluginRecord
from opencc_backend.provenance import BackendProvenance
from opencc_backend.runtime_selector import RuntimeSelector


@dataclass(frozen=True)
class SelfTestResult:
    passed: bool
    checks: Dict[str, bool]
    error: Optional[str] = None


class OpenCCBackend:
    """Official Python Binding adapter with optional native Jieba configs."""

    def __init__(self, config: str, selector: Optional[RuntimeSelector] = None) -> None:
        self._comparisons = {}
        self._config = validate_config(config)
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
        module_configs = _config_stems(self._module)
        self._jieba_plugin = self._selector.manifest.native_plugin(payload, "opencc-jieba")
        standard_configs = tuple(
            config_name for config_name in V1_CONFIGS if config_name in _config_stems(self._module)
        )
        jieba_configs = tuple(
            config_name
            for config_name in JIEBA_CONFIGS
            if self._jieba_plugin is not None
            and config_name in self._jieba_plugin.config_names
            and config_name in module_configs
        )
        self._available_configs = standard_configs + jieba_configs
        self._jieba_checked = False
        self._jieba_error: Optional[str] = None
        self._jieba_future: Future | None = None
        self._jieba_executor: ThreadPoolExecutor | None = None
        self._ensure_config_is_exposed()
        try:
            # This is the public upstream API. The default tofu policy is intentional.
            self._converter = self._module.OpenCC(self.config)
        except Exception as exc:
            raise BackendConversionError(
                f"official OpenCC could not construct config {self.config!r}"
            ) from exc

    def available_configs(self) -> Tuple[str, ...]:
        if self.probe_jieba():
            return self._available_configs
        return tuple(config for config in self._available_configs if not is_jieba_config(config))

    def available_configs_nonblocking(self) -> Tuple[str, ...]:
        """Return verified capabilities without waiting for a background probe."""

        if self.jieba_probe_state()[0] == "available":
            return self._available_configs
        return tuple(config for config in self._available_configs if not is_jieba_config(config))

    def start_jieba_probe(self, on_complete=None) -> None:
        """Start optional native probing without delaying the first settings UI."""

        if self._jieba_checked or self._jieba_future is not None:
            return
        self._jieba_executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="OpenCC-jieba-probe")
        self._jieba_future = self._jieba_executor.submit(self._probe_jieba_payload)
        if callable(on_complete):
            self._jieba_future.add_done_callback(
                lambda future: on_complete(future.result()))

    def jieba_probe_state(self) -> tuple[str, Optional[str], Optional[float]]:
        """Return pending/available/unavailable and consume completed results on caller thread."""

        future = self._jieba_future
        if future is not None:
            if not future.done():
                return "pending", None, None
            self._apply_jieba_probe_result(future.result())
        if not self._jieba_checked:
            return "not_started", None, None
        state = "unavailable" if self._jieba_error else "available"
        elapsed = getattr(self, "_jieba_elapsed_ms", None)
        return state, self._jieba_error, elapsed

    def jieba_available(self) -> bool:
        """Return whether the selected payload exposes verified native Jieba."""

        return self.probe_jieba()

    @property
    def jieba_error(self) -> Optional[str]:
        """Optional capability failure; integrity failures still abort import."""

        return self._jieba_error

    def probe_jieba(self) -> bool:
        """Probe the verified optional plugin once without changing the config.

        This only isolates native loading/construction failures. The selector
        has already verified every shipped byte; hash/provenance failures are
        never downgraded to an optional-capability warning.
        """

        if not self._jieba_checked:
            future = self._jieba_future
            result = future.result() if future is not None else self._probe_jieba_payload()
            self._apply_jieba_probe_result(result)
        return self._jieba_error is None

    def _probe_jieba_payload(self) -> tuple[bool, Optional[str], float]:
        started = perf_counter()
        try:
            if self._jieba_plugin is None:
                raise RuntimeError("official native Jieba is not included in this payload")
            if not set(JIEBA_CONFIGS) <= set(self._available_configs):
                raise RuntimeError("official native Jieba configurations are incomplete")
            for config in JIEBA_CONFIGS:
                value = self._module.OpenCC(config).convert("汉字")
                if not isinstance(value, str):
                    raise TypeError(f"{config} returned a non-text result")
            return True, None, (perf_counter() - started) * 1000
        except Exception as exc:
            return False, str(exc), (perf_counter() - started) * 1000

    def _apply_jieba_probe_result(self, result) -> None:
        ok, error, elapsed_ms = result
        self._jieba_checked = True
        self._jieba_error = None if ok else error
        self._jieba_elapsed_ms = elapsed_ms

    @property
    def config(self) -> str:
        """Return the config frozen into this backend instance."""

        return self._config

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

    def convert_for_config(self, config: str, text: str) -> str:
        """Independent official comparison on this backend's verified payload."""
        config = validate_config(config)
        if config == self.config:
            return self.convert(text)
        if config not in self._available_configs:
            raise BackendConversionError(f"configuration unavailable: {config}")
        if not isinstance(text, str):
            raise TypeError("OpenCC input must be text")
        if config not in self._comparisons:
            self._comparisons[config] = self._module.OpenCC(config)
        value = self._comparisons[config].convert(text)
        if not isinstance(value, str):
            raise BackendConversionError("official OpenCC returned a non-text result")
        return value

    def provenance(self) -> BackendProvenance:
        manifest = self._selector.manifest
        native_plugin = self._native_plugin_for_config()
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
            data_manifest_sha256=_config_data_hash(self._payload.config_data),
            config_sha256=manifest.config_hash(self._payload, self.config),
            config_name=self.config,
            tofu_policy=manifest.tofu_policy,
            segmentation="jieba" if native_plugin is not None else "mmseg",
            native_plugin_name=native_plugin.name if native_plugin is not None else None,
            native_plugin_sha256=(
                native_plugin.library_sha256 if native_plugin is not None else None
            ),
            native_plugin_resource_manifest_sha256=(
                native_plugin.resource_manifest_sha256 if native_plugin is not None else None
            ),
        )

    def self_test(self, *, include_optional: bool = True) -> SelfTestResult:
        error: Optional[str] = None
        checks: Dict[str, bool] = {
            "manifest": True,
            "payload": self._payload_root.is_dir(),
            "import_origin": bool(self._import_origin),
            "version": str(getattr(self._module, "__version__", ""))
            == self._selector.manifest.opencc_version,
            "config": True,
            "s2t_smoke": False,
            "t2s_smoke": False,
            "regional_smoke": False,
            "selected_config_smoke": False,
        }
        try:
            checks["config"] = set(self._available_configs) >= set(V1_CONFIGS)
            checks["s2t_smoke"] = self._module.OpenCC("s2t").convert("汉字") == "漢字"
            checks["t2s_smoke"] = self._module.OpenCC("t2s").convert("漢字") == "汉字"
            checks["regional_smoke"] = isinstance(
                self._module.OpenCC("s2twp").convert("汉字"), str
            )
            checks["selected_config_smoke"] = isinstance(self.convert("汉字"), str)
            if include_optional and self._jieba_plugin is not None:
                checks["native_jieba_payload"] = set(self._jieba_plugin.config_names) <= set(
                    self._available_configs
                )
                checks["native_jieba_smoke"] = self.probe_jieba()
                if not checks["native_jieba_smoke"]:
                    error = self._jieba_error
        except Exception as exc:
            error = f"self-test failed: {exc}"
            checks["config"] = False
            checks["s2t_smoke"] = False
        passed = all(checks.values())
        return SelfTestResult(passed=passed, checks=checks, error=None if passed else error)

    def comparison_configs(self, config: str) -> Tuple[str, ...]:
        return comparison_configs(config)

    def close(self) -> None:
        # The official binding owns native resources; dropping the public object
        # is the only lifecycle operation OpenCCForSigil performs.
        self._converter = None
        self._comparisons.clear()
        if self._jieba_executor is not None:
            self._jieba_executor.shutdown(wait=False, cancel_futures=False)
            self._jieba_executor = None

    def _ensure_config_is_exposed(self) -> None:
        if self.config not in self._available_configs:
            if is_jieba_config(self.config):
                raise DependencyError(
                    f"official native opencc-jieba payload does not expose config {self.config}"
                )
            raise DependencyError(f"selected wheel does not expose OpenCC config {self.config}")

    def _native_plugin_for_config(self) -> Optional[NativePluginRecord]:
        if is_jieba_config(self.config) and self._jieba_plugin is not None:
            return self._jieba_plugin
        return None


def _config_stems(module: object) -> set:
    configs = getattr(module, "CONFIGS", ())
    return {str(value)[:-5] if str(value).endswith(".json") else str(value) for value in configs}


def _config_data_hash(config_data: object) -> Optional[str]:
    if not isinstance(config_data, dict):
        return None
    value = config_data.get("manifest_sha256")
    return str(value) if value else None
