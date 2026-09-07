import os
import pytest


def pytest_sessionstart(session):
    if os.environ.get("CALISIFT_REQUIRE_OCR") == "1":
        from xingcheng.ocr import readiness

        state = readiness()
        if not state["ready"]:
            raise pytest.UsageError(
                "Real OCR is required for release checks: " + state["message"]
            )
