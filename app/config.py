"""Settings, all from the environment (.env is loaded by run.sh)."""

from __future__ import annotations

import os
import shutil
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))
FIXTURES = ROOT / "fixtures"
WEB = ROOT / "web"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# Where the day comes from.
#   cli   the real Bee data, through the official `bee` CLI (must be logged in)
#   demo  a recorded sample day in fixtures/, so the app runs without a device
#   auto  cli when the `bee` binary is on PATH, demo otherwise
BEE_BIN = _env("BEE_BIN", "bee")


def bee_mode() -> str:
    mode = _env("BEE_MODE", "auto").lower()
    if mode == "auto":
        return "cli" if shutil.which(BEE_BIN) else "demo"
    return mode


# Who is practising, and in which language their questions are asked.
PARENT_NAME = _env("PARENT_NAME", "आमा")
PARENT_NAME_EN = _env("PARENT_NAME_EN", "Mom")      # how English screens address them
PARENT_LANG = _env("PARENT_LANG", "ne")              # BCP-47 code for questions and speech
PARENT_LANG_NAME = _env("PARENT_LANG_NAME", "Nepali")
FAMILY_LANG_NAME = "English"
# The language Bee's speech recognizer is set to. Bee has no Nepali, so for a Nepali speaker it's set to Hindi:
# the words come out in Devanagari, spelled the Hindi way, and the AI rebuilds the Nepali that was meant.
BEE_HEARS = _env("BEE_HEARS", "Hindi" if PARENT_LANG == "ne" else PARENT_LANG_NAME)


def rebuilding() -> bool:
    """True when Bee transcribes the parent's speech with another language's recognizer."""
    return BEE_HEARS.strip().lower() != PARENT_LANG_NAME.strip().lower()
TZ = ZoneInfo(_env("TZ_NAME", "America/Denver"))

# The AI that turns a transcript into practice cards.
#   together   Together AI, open models (TOGETHER_API_KEY)
#   anthropic  Claude API (ANTHROPIC_API_KEY or an `ant auth login` profile)
#   bedrock    Claude on Amazon Bedrock (AWS credentials + AWS_REGION)
#   mock       no network: sample digests for the demo day, a plain card otherwise
TOGETHER_API_KEY = _env("TOGETHER_API_KEY")
TOGETHER_MODEL = _env("TOGETHER_MODEL", "moonshotai/Kimi-K3")             # cards + full translation
TOGETHER_FAST_MODEL = _env("TOGETHER_FAST_MODEL", "deepseek-ai/DeepSeek-V4-Pro-0813")  # live lines, as they're spoken
CLAUDE_MODEL = _env("CLAUDE_MODEL", "claude-opus-5-5")
BEDROCK_MODEL = _env("BEDROCK_MODEL", "anthropic.claude-opus-5-5")
CLAUDE_EFFORT = _env("CLAUDE_EFFORT", "medium")
AWS_REGION = _env("AWS_REGION", "us-west-2")


def llm_provider() -> str:
    p = _env("LLM_PROVIDER").lower()
    if p:
        return p
    if TOGETHER_API_KEY:
        return "together"
    return "anthropic" if (_env("ANTHROPIC_API_KEY") or _env("ANTHROPIC_AUTH_TOKEN")) else "mock"


# Practice settings.
SESSION_SIZE = int(_env("SESSION_SIZE", "6"))        # questions per evening
MIN_WORDS = int(_env("MIN_WORDS", "25"))             # skip conversations shorter than this
LOOKBACK_DAYS = int(_env("LOOKBACK_DAYS", "2"))      # how far back a sync reads
MAX_CARDS_PER_CONVERSATION = int(_env("MAX_CARDS", "3"))

# MCP over Streamable HTTP. Behind nginx the Host header is the public name,
# so list it here (comma separated) or the SDK's DNS-rebinding guard rejects it.
MCP_ALLOWED_HOSTS = [h.strip() for h in _env("MCP_ALLOWED_HOSTS").split(",") if h.strip()]

# Background work.
SYNC_MINUTES = int(_env("SYNC_MINUTES", "10"))       # with the real Bee, also re-check this often
LIVE_TRANSLATE = _env("LIVE_TRANSLATE", "1") == "1"  # English under each live line (needs the AI engine)
LIVE_REMINDERS = _env("LIVE_REMINDERS", "1") == "1"  # a promise said out loud becomes a Bee todo within seconds
PHOTO_CARDS = int(_env("PHOTO_CARDS", "2"))           # "who were you with?" questions from today's photos

# Real transcripts are private. When ACCESS_TOKEN is set, every page, API call
# and the MCP endpoint need it: open /?token=... once (it becomes a cookie),
# or send "Authorization: Bearer ...". Leave it empty only for the sample day.
ACCESS_TOKEN = _env("ACCESS_TOKEN")
