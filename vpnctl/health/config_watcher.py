"""Configuration File Watcher.

Monitors config/vpn-peers.yaml for changes and triggers health refresh.
"""

import os
import time
import hashlib
import logging
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class ConfigWatcher:
    """Watches config file for changes using file hash comparison."""

    def __init__(self, config_file: str, on_change: Optional[Callable] = None, check_interval: int = 2):
        """
        Initialize config watcher.

        Args:
            config_file: Path to config file to watch
            on_change: Callback function to call when config changes
            check_interval: Seconds between checks (default 2)
        """
        self.config_file = config_file
        self.on_change = on_change
        self.check_interval = check_interval
        self.last_hash: Optional[str] = None
        self._running = False

    def _get_file_hash(self) -> Optional[str]:
        """Calculate SHA256 hash of config file."""
        try:
            if not os.path.exists(self.config_file):
                return None

            with open(self.config_file, 'rb') as f:
                return hashlib.sha256(f.read()).hexdigest()
        except Exception as e:
            logger.error(f"Failed to hash config file: {e}")
            return None

    def _check_for_changes(self) -> bool:
        """Check if config file has changed."""
        current_hash = self._get_file_hash()

        if current_hash is None:
            return False

        if self.last_hash is None:
            # First check
            self.last_hash = current_hash
            return False

        if current_hash != self.last_hash:
            logger.info(f"Config change detected: {self.config_file}")
            self.last_hash = current_hash
            return True

        return False

    def watch(self) -> None:
        """Watch config file for changes (blocking)."""
        self._running = True
        logger.info(f"Config watcher started for {self.config_file}")

        try:
            while self._running:
                if self._check_for_changes():
                    if self.on_change:
                        logger.info("Config changed, triggering callback...")
                        try:
                            self.on_change()
                        except Exception as e:
                            logger.error(f"Error in change callback: {e}")

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("Config watcher stopped by user")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        logger.info("Config watcher stopped")


class FastConfigWatcher:
    """Lightweight config watcher using file modification time (faster for rapid changes)."""

    def __init__(self, config_file: str, on_change: Optional[Callable] = None, check_interval: int = 1):
        """
        Initialize fast config watcher.

        Args:
            config_file: Path to config file to watch
            on_change: Callback function to call when config changes
            check_interval: Seconds between checks (default 1)
        """
        self.config_file = config_file
        self.on_change = on_change
        self.check_interval = check_interval
        self.last_mtime: Optional[float] = None
        self._running = False

    def _get_mtime(self) -> Optional[float]:
        """Get file modification time."""
        try:
            if os.path.exists(self.config_file):
                return os.path.getmtime(self.config_file)
        except Exception as e:
            logger.error(f"Failed to get mtime: {e}")
        return None

    def _check_for_changes(self) -> bool:
        """Check if config file has been modified."""
        current_mtime = self._get_mtime()

        if current_mtime is None:
            return False

        if self.last_mtime is None:
            # First check
            self.last_mtime = current_mtime
            return False

        if current_mtime != self.last_mtime:
            logger.info(f"Config modification detected: {self.config_file}")
            self.last_mtime = current_mtime
            return True

        return False

    def watch(self) -> None:
        """Watch config file for modifications (blocking)."""
        self._running = True
        logger.info(f"Fast config watcher started for {self.config_file}")

        try:
            while self._running:
                if self._check_for_changes():
                    if self.on_change:
                        logger.info("Config modified, triggering callback...")
                        try:
                            self.on_change()
                        except Exception as e:
                            logger.error(f"Error in change callback: {e}")

                time.sleep(self.check_interval)

        except KeyboardInterrupt:
            logger.info("Config watcher stopped by user")
        finally:
            self._running = False

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        logger.info("Config watcher stopped")
