# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for testbench-ai-service
#
# Build with:
#   pyinstaller testbench-ai-service.spec --clean --noconfirm
#
# Or use the helper script which handles environment setup first:
#   python build_binary.py
#
# Output: dist/testbench-ai-service/  (onedir)

from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_submodules

# Collect everything from packages that use dynamic internal imports or
# have data files / lazy-loaded sub-packages.
uvicorn_datas, uvicorn_binaries, uvicorn_hiddenimports = collect_all("uvicorn")
fastapi_datas, fastapi_binaries, fastapi_hiddenimports = collect_all("fastapi")

# Package data files (prompts YAML/schema, locale JSON files)
pkg_datas = collect_data_files("testbench_ai_service")

datas = (
    pkg_datas
    + uvicorn_datas
    + fastapi_datas
)
binaries = uvicorn_binaries + fastapi_binaries
hiddenimports = (
    uvicorn_hiddenimports
    + fastapi_hiddenimports
    + collect_submodules("testbench_ai_service")
    + collect_submodules("testbench_cli_reporter")
    + collect_submodules("testbench2robotframework")
    + collect_submodules("azure.identity")
    + collect_submodules("msal")
    + [
        # uvicorn server implementation modules loaded by string at runtime
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.protocols.websockets.websockets_impl",
        "uvicorn.logging",
        # anyio backend loaded by name at runtime by starlette/fastapi
        "anyio._backends._asyncio",
        "anyio._backends._trio",
        # httpx used internally by openai client
        "httpx",
        # pydantic v2 core
        "pydantic.v1",
        # jsonschema validators loaded via importlib
        "jsonschema.validators",
        "jsonschema._format",
        # yaml (PyYAML)
        "yaml",
        # tomli / tomli-w for config parsing
        "tomli",
        "tomli_w",
        # jinja2 template engine
        "jinja2",
        # python-dotenv
        "dotenv",
        # multiprocessing spawn support (needed for freeze_support on all platforms)
        "multiprocessing.resource_tracker",
        "multiprocessing.spawn",
    ]
)

a = Analysis(
    ["testbench_ai_service/__main__.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Dev / test tooling — not needed at runtime
        "pytest",
        "mypy",
        "ruff",
        "robotframework",
        "IPython",
        "ipykernel",
        "notebook",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,  # onedir: binaries live in COLLECT
    name="testbench-ai-service",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX can cause false-positive AV alerts; disable by default
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="lib",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="testbench-ai-service",
    contents_directory="lib",
)
