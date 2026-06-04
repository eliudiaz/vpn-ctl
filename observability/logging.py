"""Structured logging for vpn-ctl operations."""

import logging
import json
from pathlib import Path
from datetime import datetime


def get_logger(name: str) -> logging.Logger:
    """Get a configured logger instance.

    Args:
        name: Logger name (typically __name__)

    Returns:
        Configured logger
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        # Configure once per logger
        logger.setLevel(logging.DEBUG)

        # Console handler (INFO level)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            '[%(name)s] %(levelname)s: %(message)s'
        )
        console_handler.setFormatter(console_formatter)

        # File handler (DEBUG level) - logs/vpn-ctl.log
        logs_dir = Path("logs")
        logs_dir.mkdir(exist_ok=True)
        file_handler = logging.FileHandler(logs_dir / "vpn-ctl.log")
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            '%(asctime)s [%(name)s] %(levelname)s: %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_formatter)

        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    return logger


def log_operation(operation: str, peer_name: str, status: str, metadata: dict = None):
    """Log an operation event (deployment, validation, etc).

    Args:
        operation: Operation name (e.g., 'deploy', 'validate', 'destroy')
        peer_name: Peer being operated on
        status: Status (success, failure, in_progress)
        metadata: Additional metadata dict
    """
    logger = get_logger('vpn-ctl.operations')

    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'operation': operation,
        'peer_name': peer_name,
        'status': status,
        'metadata': metadata or {},
    }

    logger.info(json.dumps(log_entry))


def log_peer_event(peer_name: str, event: str, details: dict = None):
    """Log a peer-specific event.

    Args:
        peer_name: Peer name
        event: Event description (e.g., 'tunnel_up', 'spec_changed')
        details: Event details
    """
    logger = get_logger('vpn-ctl.peers')

    log_entry = {
        'timestamp': datetime.utcnow().isoformat(),
        'peer_name': peer_name,
        'event': event,
        'details': details or {},
    }

    logger.info(json.dumps(log_entry))
