import os
import tempfile

# CRITICAL: Set environment variables BEFORE any app imports
# These must be set before app.config.settings is loaded
_TEST_DB_PATH = os.path.join(tempfile.gettempdir(), "test_alcast.db")
os.environ["SECRET_KEY"] = "test-secret-key-1234567890"
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{_TEST_DB_PATH}"
os.environ["ENVIRONMENT"] = "test"
os.environ["API_V1_STR"] = "/api"  # Ensure /api prefix is used in tests
os.environ["INGEST_TOKEN"] = "test-ingest-token"

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

# Now import app modules - they will use the test DATABASE_URL
from app.database import Base, get_db, engine as app_engine
from app.main import app

# Use the same engine that the app uses
TEST_ENGINE = app_engine

TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=TEST_ENGINE, future=True
)


def override_get_db():
    """Test database session that uses the test engine."""
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


# Apply override at module load - this needs to happen before tests run
# The key is to override the ORIGINAL function from database module
app.dependency_overrides[get_db] = override_get_db


@pytest.fixture(scope="function", autouse=True)
def setup_test_database():
    """
    Create all tables before each test and clean up after.
    This ensures a fresh database state for each test.
    Also cleans up dependency overrides to ensure test isolation.
    """
    # Save original overrides (just get_db is set at module level)
    original_overrides = dict(app.dependency_overrides)
    
    # Create all tables
    Base.metadata.drop_all(bind=TEST_ENGINE)
    Base.metadata.create_all(bind=TEST_ENGINE)
    
    yield
    
    # Restore only original overrides, removing any test-specific ones
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)
    
    # Clean up - drop tables after each test
    Base.metadata.drop_all(bind=TEST_ENGINE)


@pytest.fixture
def db_session():
    """
    Provide a transactional scope around a test.
    Returns a database session for direct use in tests.
    """
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


