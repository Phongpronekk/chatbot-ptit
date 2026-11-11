"""Fixtures and result metadata for the additional offline QA suite."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SAFE_SETTINGS = {
    "ANTHROPIC_API_KEY": "", "GOOGLE_API_KEY": "", "GEMINI_API_KEY": "",
    "OPENAI_API_KEY": "", "MONGODB_URI": "", "ADMIN_TOKEN": "",
    "LLM_PROVIDER": "anthropic", "MODEL_NAME": "", "RETRIEVAL_BACKEND": "lexical",
    "DIRECT_OLLAMA_CHAT": "false", "RAG_TOP_K": "4", "RAG_MIN_SCORE": "0.35",
    "CHUNK_SIZE": "400", "CHUNK_OVERLAP": "60", "RETRIEVAL_HYBRID": "true",
    "COOKIE_SECURE": "false", "CORS_ORIGINS": "http://localhost:5173",
    "PYTHON_DOTENV_DISABLED": "1", "ANONYMIZED_TELEMETRY": "False",
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false",
}


def isolated_environment():
    # Copy only OS/runtime settings. Never copy inherited credentials.
    allowed = ("SystemRoot", "WINDIR", "PATH", "TEMP", "TMP", "COMSPEC", "PATHEXT",
               "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMDRIVE", "NUMBER_OF_PROCESSORS",
               "PYTHONPATH", "PYTHONUTF8", "PYTHONIOENCODING", "PTIT_QA_OUTPUT")
    return {**{k: os.environ[k] for k in allowed if k in os.environ}, **SAFE_SETTINGS}


def case(identifier, description, inputs, expected):
    def decorate(fn):
        fn.qa = dict(id=identifier, description=description, inputs=inputs, expected=expected)
        return fn
    return decorate


class OfflineCase(unittest.TestCase):
    def setUp(self):
        environment = patch.dict(os.environ, isolated_environment(), clear=True)
        environment.start()
        self.addCleanup(environment.stop)
        self.temporary = tempfile.TemporaryDirectory(prefix="ptit-qa-")
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name)

