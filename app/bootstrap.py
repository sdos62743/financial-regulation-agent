"""Load .env before any config-dependent imports. Import this first in entry points."""

from dotenv import load_dotenv

load_dotenv(override=True)
