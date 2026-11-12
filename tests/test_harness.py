import pytest

from tests.harness import markers

INI = "[pytest]\nasyncio_default_fixture_loop_scope = function\nmarkers =\n    standin\n    real\n"
ADAPTER_TEST = """import pytest

{marker}
def test_uses_adapter():
    from fleet.transport.zenoh import StandInZenoh
"""


def _collect(pytester, **files: str) -> pytest.RunResult:
    pytester.makeini(INI)
    pytester.makepyfile(**files)
    return pytester.runpytest("--collect-only", plugins=[markers])


def test_req132_adapter_test_without_marker_fails_collection(pytester):
    result = _collect(pytester, test_planted=ADAPTER_TEST.format(marker=""))

    assert result.ret != 0
    result.stderr.fnmatch_lines(
        ["*test_planted.py::test_uses_adapter needs @pytest.mark.standin or @pytest.mark.real"]
    )


@pytest.mark.parametrize("marker", ["@pytest.mark.standin", "@pytest.mark.real"])
def test_req132_labelled_adapter_test_collects(pytester, marker):
    result = _collect(pytester, test_planted=ADAPTER_TEST.format(marker=marker))

    assert result.ret == 0


def test_req132_test_without_adapter_needs_no_marker(pytester):
    result = _collect(pytester, test_plain="def test_math():\n    assert 1 + 1 == 2\n")

    assert result.ret == 0


@pytest.mark.parametrize(
    "imports",
    [
        "from fleet.vehicle import twin_kuksa",
        "from fleet.vehicle import twin",
        "import fleet.demo.wiring",
    ],
)
def test_req132_adapter_imported_by_name_or_via_demo_needs_marker(pytester, imports):
    test = f"def test_x():\n    {imports}\n"

    result = _collect(pytester, test_planted=test)

    assert result.ret != 0


def test_req132_verbose_report_shows_the_label(pytester):
    pytester.makeini(INI)
    pytester.makepyfile(
        test_planted=ADAPTER_TEST.format(marker="@pytest.mark.real").replace(
            "from fleet.transport.zenoh import StandInZenoh", "pass  # fleet.transport.zenoh"
        )
        + "\n\nfrom fleet.transport import zenoh  # noqa\n"
    )
    result = pytester.runpytest("-v", plugins=[markers])

    result.stdout.fnmatch_lines(["*test_uses_adapter PASSED [[]real[]]*"])
