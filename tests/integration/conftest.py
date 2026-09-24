"""Session-scoped real backends for controller integration coverage."""

import pytest


class _SharedBackendLease:
    """Keep a session-owned backend alive when a controller closes its lease."""

    def __init__(self, backend):
        self._backend = backend

    def __getattr__(self, name):
        return getattr(self._backend, name)

    def close(self):
        # The real backend is retained until the session fixture is released.
        pass


@pytest.fixture(scope="session")
def shared_opencc_backend_factory():
    from opencc_backend.backend import OpenCCBackend

    backends = {}
    leases = {}
    probe = None

    def factory(config, *_args, **_kwargs):
        nonlocal probe
        if probe is None:
            bootstrap = OpenCCBackend("s2t")
            probe = bootstrap.jieba_probe
            probe.probe()
            backends["s2t"] = bootstrap
        if config not in backends:
            backends[config] = OpenCCBackend(config, jieba_probe=probe)
        if config not in leases:
            leases[config] = _SharedBackendLease(backends[config])
        return leases[config]

    yield factory
    for backend in backends.values():
        backend.close()


@pytest.fixture(autouse=True)
def use_shared_controller_backends(request, monkeypatch):
    # This module exercises probe startup and pending UI behavior directly.
    if request.module.__name__.endswith("test_jieba_probe_flow"):
        return
    factory = request.getfixturevalue("shared_opencc_backend_factory")
    monkeypatch.setattr("app.controller.OpenCCBackend", factory)
