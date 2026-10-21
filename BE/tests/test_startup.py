import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


class StartupTests(unittest.TestCase):
    def check_import(self, cwd: Path, target: str):
        result = subprocess.run(
            [sys.executable, "-c", "from uvicorn.importer import import_from_string; "
             f"app = import_from_string({target!r}); assert app.title == 'PTIT Chatbot API'"],
            cwd=cwd, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_uvicorn_import_from_project_root(self):
        self.check_import(ROOT, "BE.main:app")

    def test_uvicorn_import_from_backend_directory(self):
        self.check_import(ROOT / "BE", "main:app")


if __name__ == "__main__":
    unittest.main()
