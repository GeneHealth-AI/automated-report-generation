import os
import logging
from dotenv import load_dotenv

load_dotenv()

# --- Logging ---
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(level=getattr(logging, LOG_LEVEL))

# --- API Keys ---
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
PUBMED_EMAIL = os.getenv("PUBMED_EMAIL", "sskolusa@gmail.com") # Default from test script
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY", "cc4c8e3a576269291de09db7fb095ea8b008") # Default from test script

# --- Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATE_DIR = os.path.join(BASE_DIR, "ui/templates")
CACHE_DB_PATH = os.path.join(BASE_DIR, "../mutation_cache.db") # Re-use existing cache

# --- Constants ---
DEFAULT_MODEL = "gemini-3-flash-preview"
MAX_TOKENS = 65536
RATE_LIMIT_DELAY = 1.0 # Seconds between API calls
