"""Stand-ins for the JSON report's test case sets, with just the attributes the code reads."""
# ruff: noqa: PT028 (test_case_set is a factory despite its name)

from types import SimpleNamespace


def ref(key: str) -> SimpleNamespace:
    return SimpleNamespace(key=key)


def call(name: str, phase: str = "TestStep", check: bool = False, **arguments: str):
    return SimpleNamespace(
        spec=SimpleNamespace(
            name=name,
            sequencePhase=SimpleNamespace(value=phase),
            callType=SimpleNamespace(value="Check" if check else "Flow"),
            callParameters=[SimpleNamespace(name=k, value=v) for k, v in arguments.items()],
        )
    )


def case(uid: str, links=(), sequence=None, **parameters: str) -> SimpleNamespace:
    return SimpleNamespace(
        uniqueID=uid,
        spec=SimpleNamespace(requirements=[ref(key) for key in links]),
        testSequence=sequence or [],
        parameters=[SimpleNamespace(name=k, value=v) for k, v in parameters.items()],
    )


def test_case_set(
    key: str,
    path: str,
    links=(),
    cases=(),
    sequence=None,
    status: str = "Released",
    description: str = "<html><body><p>Checks the login</p></body></html>",
) -> SimpleNamespace:
    return SimpleNamespace(
        details=SimpleNamespace(
            key=key,
            uniqueID=f"U-{key}",
            name=f"Set {key}",
            path=path,
            spec=SimpleNamespace(
                key=f"spec-{key}",
                description=description,
                status=SimpleNamespace(value=status),
                requirements=[ref(k) for k in links],
            ),
            testSequence=sequence or [],
        ),
        test_cases={c.uniqueID: c for c in cases},
    )


test_case_set.__test__ = False  # type: ignore[attr-defined]
