"""Configuration settings for the Smart Manufacturing Platform."""

import os

from dotenv import load_dotenv

load_dotenv()

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_RAW_DIR = os.path.join(BASE_DIR, "data", "raw")
DATA_PROCESSED_DIR = os.path.join(BASE_DIR, "data", "processed")
DATA_EXPORTS_DIR = os.path.join(BASE_DIR, "data", "exports")

# AI / LLM — using local Qwen via Ollama (zero API costs)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "local")  # "local" (Qwen/Ollama), "gemini", or "openai"
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

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
