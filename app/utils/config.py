"""Configuration settings for the Smart Manufacturing Platform."""

import os

from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data", "exports")
# Rows rejected by the Phase-2 data contracts land here instead of being silently
# dropped, so a bad upload stays auditable and replayable (DLQ pattern).
DATA_QUARANTINE_DIR = os.path.join(BASE_DIR, "data", "quarantine")
DATA_QUARANTINE_FILE = os.path.join(DATA_QUARANTINE_DIR, "corrupt_records.csv")

# AI / LLM — using local Qwen via Ollama (zero API costs)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "local")  # "local" (Qwen/Ollama), "gemini", or "openai"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

# Local LAN provider selection: "ollama" (default) or "local_openai"
# (OpenAI-compatible endpoint at LOCAL_LLM_URL — the vLLM server on LAN).
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama")
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://192.168.1.8:1234/v1")
LOCAL_LLM_MODEL = os.getenv("LOCAL_LLM_MODEL", "qwen2.5-vl-3b-instruct")
# Aliases kept for the uncommitted working tree / sibling repos.
LMSTUDIO_BASE_URL = os.getenv("LMSTUDIO_BASE_URL", LOCAL_LLM_URL)
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", LOCAL_LLM_MODEL)

# Database
DATABASE_URL = os.getenv(
    "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'data', 'manufacturing.db')}"
)

# Factory defaults
FACTORY_NAME = "Smart Factory Alpha"
DEFAULT_SHIFTS = ["Morning", "Afternoon", "Night"]
PRODUCTION_LINES = [f"Line_{i}" for i in range(1, 11)]
MACHINES = [f"M-{i:02d}" for i in range(1, 21)]
PRODUCTS = [
    "Running Shoe A1",
    "Running Shoe A2",
    "Casual B1",
    "Casual B2",
    "Formal C1",
    "Sport D1",
    "Boot E1",
    "Sandal F1",
    "Slipper G1",
    "Loafers H1",
]
WORKERS = [f"EMP_{i:04d}" for i in range(1, 201)]

# Alert thresholds
ALERT_REJECT_RATE = 5.0  # %
ALERT_INVENTORY_MIN = 200
ALERT_DOWNTIME_MIN = 30  # minutes

# OEE targets
OEE_TARGET = 0.85
AVAILABILITY_TARGET = 0.90
PERFORMANCE_TARGET = 0.95
QUALITY_TARGET = 0.99
