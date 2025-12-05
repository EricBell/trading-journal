"""Trading Journal - PostgreSQL-based trading data ingestion and analysis."""

# Get version from version manager
import sys
from pathlib import Path

# Add project root to path to import version_manager
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from version_manager import version_manager
    major, minor, patch = version_manager.get_current_version()
    __version__ = f"{major}.{minor}.{patch}"
except ImportError:
    __version__ = "0.2.0"  # fallback