from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "db" / "studio.db"
CONTACT_PATH = BASE_DIR / "contact.json"

SECRET_KEY = "studio-os-dev-secret-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_HOURS = 72
COOKIE_NAME = "studio_token"

DEFAULT_ADMIN_EMAIL = "admin@studio.local"
DEFAULT_ADMIN_PASSWORD = "admin123"
