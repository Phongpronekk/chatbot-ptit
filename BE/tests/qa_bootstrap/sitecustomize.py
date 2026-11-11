"""Opt-in offline harness for `python -m unittest discover -s BE/tests -v`.

Activate by adding BE/tests/qa_bootstrap to PYTHONPATH. It does not load .env,
connect to MongoDB/LLMs, or replace any application function under test.
"""
import json
import os
from pathlib import Path
import socket
import sys
import time
import unittest
from unittest.mock import patch
import httpx

TESTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TESTS))
from qa_support import isolated_environment

_environment = patch.dict(os.environ, isolated_environment(), clear=True)
_environment.start()


_connect = socket.socket.connect


def offline_connect(sock, address):
    # Windows asyncio may create a loopback socket pair for its wake-up pipe.
    if isinstance(address, tuple) and address[0] in ("127.0.0.1", "::1", "localhost"):
        return _connect(sock, address)
    raise OSError("QA offline: real socket connections are disabled")


_network = patch.object(socket.socket, "connect", offline_connect)
_network.start()
_http = patch.object(httpx.HTTPTransport, "handle_request", side_effect=OSError("QA offline: real HTTP disabled"))
_http.start()

# This one legacy test explicitly reads the real BE/.env and requires its values
# to be imported into child-process os.environ. Leave it unexecuted under the
# user's prohibition on real credentials; all other legacy tests run unchanged.
_load_case = unittest.TestLoader.loadTestsFromTestCase


def load_offline(self, cls):
    suite = _load_case(self, cls)
    for test in suite:
        if cls.__name__ == "StartupTests" and test._testMethodName == "test_backend_env_overrides_inherited_provider":
            def unsafe_environment_test():
                pass
            setattr(test, test._testMethodName, unittest.skip(
                "Chưa chạy: test cũ yêu cầu nạp BE/.env thật; QA cách ly toàn bộ khóa và cấu hình thật."
            )(unsafe_environment_test))
    return suite


unittest.TestLoader.loadTestsFromTestCase = load_offline


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = []

    def startTest(self, test):
        super().startTest(test)
        method = getattr(test, test._testMethodName)
        metadata = getattr(method, "qa", {})
        self.current = {"test": test.id(), "module": test.__class__.__module__,
                        "id": metadata.get("id", test.id()),
                        "description": metadata.get("description", test._testMethodName.removeprefix("test_").replace("_", " ")),
                        "inputs": metadata.get("inputs", "Fixture và dữ liệu trong " + test.__class__.__module__ + ".py"),
                        "expected": metadata.get("expected", "Toàn bộ assertion của testcase phải đạt"),
                        "status": "Pass", "actual": [], "started": time.perf_counter()}

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.current["status"] = "Fail"
        self.current["actual"].append(self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self.current["status"] = "Fail"
        self.current["actual"].append(self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.current["status"] = "Chưa chạy"
        self.current["actual"].append(reason)

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err:
            self.current["status"] = "Fail"
            self.current["actual"].append(str(subtest) + "\n" + self._exc_info_to_string(err, test))

    def stopTest(self, test):
        self.current["duration"] = round(time.perf_counter() - self.current.pop("started"), 5)
        if not self.current["actual"]:
            self.current["actual"] = [getattr(test, "observed", "Đã chạy; toàn bộ assertion đạt.")]
        self.rows.append(self.current)
        super().stopTest(test)

    def stopTestRun(self):
        super().stopTestRun()
        if os.environ.get("PTIT_QA_OUTPUT"):
            Path(os.environ["PTIT_QA_OUTPUT"]).write_text(json.dumps({
                "testsRun": self.testsRun, "failures": len(self.failures), "errors": len(self.errors),
                "skipped": len(self.skipped), "rows": self.rows,
            }, ensure_ascii=False, indent=2), encoding="utf-8")


unittest.TextTestRunner.resultclass = RecordedResult

