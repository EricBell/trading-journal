#!/usr/bin/env python3
"""
Version management system with file hashing
Automatically tracks file changes and manages version numbers (major.minor.patch format)

To bump up the major version, use:
    python version_manager.py major
To bump up the minor version, use:
    python version_manager.py minor
To bump up the patch version, use:
    python version_manager.py patch
To reset the version to v1.0.0, use:
    python version_manager.py reset
To reset to a specific version, use:
    python version_manager.py reset <major> <minor> <patch>
To check for changes and update the version, use:
    python version_manager.py check
To get the current version, use:
    python version_manager.py status    
"""

import os
import json
import hashlib
import logging
from pathlib import Path
from typing import Dict, List, Tuple

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class VersionManager:
    """Manages application versioning based on file hashes"""
    
    def __init__(self, project_root: str = None):
        self.project_root = Path(project_root) if project_root else Path(__file__).parent
        self.version_file = self.project_root / 'version.json'
        self.tracked_files = [
            '*.py',
            'templates/**/*.html',
            'requirements.txt',
            '*.spec'
        ]
        
    def _get_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of a file"""
        try:
            with open(file_path, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.warning(f"Could not hash {file_path}: {e}")
            return ""
    
    def _get_all_tracked_files(self) -> List[Path]:
        """Get all files matching the tracked patterns"""
        all_files = []
        
        for pattern in self.tracked_files:
            if '**' in pattern:
                # Recursive glob
                files = list(self.project_root.glob(pattern))
            else:
                # Simple glob
                files = list(self.project_root.glob(pattern))
            
            # Filter out dist/, build/, __pycache__ directories
            filtered_files = []
            for f in files:
                if f.is_file():
                    rel_path = f.relative_to(self.project_root)
                    if not any(part.startswith('.') or part in ['dist', 'build', '__pycache__', 'instance'] 
                             for part in rel_path.parts):
                        filtered_files.append(f)
            
            all_files.extend(filtered_files)
        
        return sorted(set(all_files))
    
    def _calculate_file_hashes(self) -> Dict[str, str]:
        """Calculate hashes for all tracked files"""
        hashes = {}
        tracked_files = self._get_all_tracked_files()
        
        for file_path in tracked_files:
            rel_path = str(file_path.relative_to(self.project_root))
            hashes[rel_path] = self._get_file_hash(file_path)
        
        return hashes
    
    def _load_version_data(self) -> Dict:
        """Load version data from file"""
        default_data = {
            "major": 1,
            "minor": 0,
            "patch": 0,
            "file_hashes": {}
        }
        
        if not self.version_file.exists():
            return default_data
        
        try:
            with open(self.version_file, 'r') as f:
                data = json.load(f)
                # Ensure all required fields exist
                for key in default_data:
                    if key not in data:
                        data[key] = default_data[key]
                return data
        except Exception as e:
            logger.error(f"Error loading version file: {e}")
            return default_data
    
    def _save_version_data(self, data: Dict) -> None:
        """Save version data to file"""
        try:
            with open(self.version_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving version file: {e}")
    
    def get_current_version(self) -> Tuple[int, int, int]:
        """Get current version without checking for changes"""
        data = self._load_version_data()
        return data["major"], data["minor"], data["patch"]
    
    def check_and_update_version(self) -> Tuple[int, int, int, bool]:
        """Check for file changes and update version if needed"""
        data = self._load_version_data()
        current_hashes = self._calculate_file_hashes()
        previous_hashes = data.get("file_hashes", {})
        
        # Check if any files have changed
        files_changed = False
        changed_files = []
        
        # Check for modified files
        for file_path, current_hash in current_hashes.items():
            if file_path in previous_hashes:
                if previous_hashes[file_path] != current_hash:
                    files_changed = True
                    changed_files.append(f"Modified: {file_path}")
            else:
                files_changed = True
                changed_files.append(f"Added: {file_path}")
        
        # Check for removed files
        for file_path in previous_hashes:
            if file_path not in current_hashes:
                files_changed = True
                changed_files.append(f"Removed: {file_path}")
        
        if files_changed:
            # Increment patch version for file changes
            data["patch"] += 1
            data["file_hashes"] = current_hashes
            self._save_version_data(data)
            
            logger.info(f"Version updated to {data['major']}.{data['minor']}.{data['patch']}")
            for change in changed_files:
                logger.info(f"  {change}")
        
        return data["major"], data["minor"], data["patch"], files_changed
    
    def increment_major_version(self) -> Tuple[int, int, int]:
        """Manually increment major version and reset minor/patch to 0"""
        data = self._load_version_data()
        data["major"] += 1
        data["minor"] = 0
        data["patch"] = 0
        data["file_hashes"] = self._calculate_file_hashes()
        self._save_version_data(data)
        
        logger.info(f"Major version incremented to {data['major']}.{data['minor']}.{data['patch']}")
        return data["major"], data["minor"], data["patch"]
    
    def increment_minor_version(self) -> Tuple[int, int, int]:
        """Manually increment minor version and reset patch to 0"""
        data = self._load_version_data()
        data["minor"] += 1
        data["patch"] = 0
        data["file_hashes"] = self._calculate_file_hashes()
        self._save_version_data(data)
        
        logger.info(f"Minor version incremented to {data['major']}.{data['minor']}.{data['patch']}")
        return data["major"], data["minor"], data["patch"]
    
    def increment_patch_version(self) -> Tuple[int, int, int]:
        """Manually increment patch version"""
        data = self._load_version_data()
        data["patch"] += 1
        data["file_hashes"] = self._calculate_file_hashes()
        self._save_version_data(data)
        
        logger.info(f"Patch version incremented to {data['major']}.{data['minor']}.{data['patch']}")
        return data["major"], data["minor"], data["patch"]
    
    def get_version_string(self) -> str:
        """Get formatted version string"""
        major, minor, patch, _ = self.check_and_update_version()
        return f"v{major}.{minor}.{patch}"
    
    def reset_version(self, major: int = 1, minor: int = 0, patch: int = 0) -> Tuple[int, int, int]:
        """Reset version to specified values"""
        data = {
            "major": major,
            "minor": minor,
            "patch": patch,
            "file_hashes": self._calculate_file_hashes()
        }
        self._save_version_data(data)
        
        logger.info(f"Version reset to {major}.{minor}.{patch}")
        return major, minor, patch

# Global version manager instance
version_manager = VersionManager()

def get_version_string() -> str:
    """Convenience function to get version string"""
    return version_manager.get_version_string()

def increment_major() -> str:
    """Convenience function to increment major version"""
    major, minor, patch = version_manager.increment_major_version()
    return f"v{major}.{minor}.{patch}"

# CLI interface
if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Version Manager Commands:")
        print("  python version_manager.py status      - Show current version")
        print("  python version_manager.py check       - Check for changes and update")
        print("  python version_manager.py major       - Increment major version")
        print("  python version_manager.py minor       - Increment minor version")
        print("  python version_manager.py patch       - Increment patch version")
        print("  python version_manager.py reset       - Reset to v1.0.0")
        print("  python version_manager.py reset X Y Z - Reset to vX.Y.Z")
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == 'status':
        major, minor, patch = version_manager.get_current_version()
        print(f"Current version: v{major}.{minor}.{patch}")
    
    elif command == 'check':
        major, minor, patch, changed = version_manager.check_and_update_version()
        if changed:
            print(f"Version updated to v{major}.{minor}.{patch}")
        else:
            print(f"No changes detected. Version remains v{major}.{minor}.{patch}")
    
    elif command == 'major':
        major, minor, patch = version_manager.increment_major_version()
        print(f"Major version incremented to v{major}.{minor}.{patch}")
    
    elif command == 'minor':
        major, minor, patch = version_manager.increment_minor_version()
        print(f"Minor version incremented to v{major}.{minor}.{patch}")
    
    elif command == 'patch':
        major, minor, patch = version_manager.increment_patch_version()
        print(f"Patch version incremented to v{major}.{minor}.{patch}")
    
    elif command == 'reset':
        if len(sys.argv) == 5:
            try:
                major = int(sys.argv[2])
                minor = int(sys.argv[3])
                patch = int(sys.argv[4])
                major, minor, patch = version_manager.reset_version(major, minor, patch)
                print(f"Version reset to v{major}.{minor}.{patch}")
            except ValueError:
                print("Error: Major, minor, and patch versions must be integers")
                sys.exit(1)
        else:
            major, minor, patch = version_manager.reset_version()
            print(f"Version reset to v{major}.{minor}.{patch}")
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)