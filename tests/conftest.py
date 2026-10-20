"""Offline test settings: sample day, no AI, a throwaway database."""

import os
import tempfile

os.environ["DATA_DIR"] = tempfile.mkdtemp(prefix="memory-lane-test-")
os.environ["BEE_MODE"] = "demo"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["SESSION_SIZE"] = "6"
