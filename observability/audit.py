"""Audit logging for compliance and accountability."""

import json
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, Any, Optional


@dataclass
class AuditEntry:
    """Single audit log entry."""
    timestamp: str
    action: str
    peer_name: str
    user: str
    status: str
    details: Dict[str, Any]


class AuditLog:
    """Audit trail for VPN infrastructure operations."""

    def __init__(self, peer_name: str):
        """
        Initialize audit log for a peer.

        Args:
            peer_name: Peer name
        """
        self.peer_name = peer_name
        self.log_file = Path(f".pulumi/peer-states/{peer_name}/audit.jsonl")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        action: str,
        status: str,
        user: str = "system",
        details: Dict[str, Any] = None,
    ) -> None:
        """Log an action.

        Args:
            action: Action name (e.g., 'deploy', 'destroy', 'validate')
            status: Result (success, failure, in_progress)
            user: User performing action
            details: Additional details
        """
        entry = AuditEntry(
            timestamp=datetime.utcnow().isoformat(),
            action=action,
            peer_name=self.peer_name,
            user=user,
            status=status,
            details=details or {},
        )

        # Append to JSONL file (one entry per line)
        with open(self.log_file, 'a') as f:
            f.write(json.dumps({
                'timestamp': entry.timestamp,
                'action': entry.action,
                'peer_name': entry.peer_name,
                'user': entry.user,
                'status': entry.status,
                'details': entry.details,
            }) + '\n')

    def get_entries(self, limit: int = None) -> list:
        """Get audit log entries.

        Args:
            limit: Maximum number of entries to return (most recent first)

        Returns:
            List of audit entries
        """
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file) as f:
            for line in f:
                if line.strip():
                    entries.append(json.loads(line))

        # Return most recent first
        entries.reverse()

        if limit:
            entries = entries[:limit]

        return entries

    def export(self, export_file: Path) -> None:
        """Export audit log to file.

        Args:
            export_file: Destination file path
        """
        entries = self.get_entries()

        with open(export_file, 'w') as f:
            json.dump(entries, f, indent=2)


class GlobalAuditLog:
    """Global audit log for all VPN operations."""

    def __init__(self):
        """Initialize global audit log."""
        self.log_file = Path(".pulumi/global-audit.jsonl")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        action: str,
        peer_name: str,
        status: str,
        user: str = "system",
        details: Dict[str, Any] = None,
    ) -> None:
        """Log a global action.

        Args:
            action: Action name
            peer_name: Peer being operated on
            status: Result status
            user: User performing action
            details: Additional details
        """
        entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'action': action,
            'peer_name': peer_name,
            'user': user,
            'status': status,
            'details': details or {},
        }

        with open(self.log_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def get_peer_history(self, peer_name: str, limit: int = None) -> list:
        """Get audit history for a peer.

        Args:
            peer_name: Peer name
            limit: Maximum entries

        Returns:
            List of audit entries
        """
        if not self.log_file.exists():
            return []

        entries = []
        with open(self.log_file) as f:
            for line in f:
                if line.strip():
                    entry = json.loads(line)
                    if entry['peer_name'] == peer_name:
                        entries.append(entry)

        # Return most recent first
        entries.reverse()

        if limit:
            entries = entries[:limit]

        return entries
