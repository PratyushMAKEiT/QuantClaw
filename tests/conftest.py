import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Create a temporary directory for the duration of the test session
tmp_dir = tempfile.TemporaryDirectory()
tmp_path = Path(tmp_dir.name)

# Patch get_app_data_dir to return the temporary directory
patcher = patch("quantclaw.config.get_app_data_dir", return_value=tmp_path)
patcher.start()

@pytest.fixture(scope="session", autouse=True)
def cleanup_temp_dir():
    yield
    import logging
    # Shutdown logging to release lock on files
    logging.shutdown()
    try:
        tmp_dir.cleanup()
    except Exception:
        pass
