"""Per-peer isolated state storage."""

import json
from collections import deque
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List


class PeerStateStore:
    """Isolated state store per peer for tracking deployment metadata and audit trail."""

    def __init__(self, peer_name: str, base_dir: str = ".vpnctl"):
        """Initialize state store for a peer.

        Args:
            peer_name: Name of the peer
            base_dir: Base directory for all state (default: .vpnctl)
        """
        self.peer_name = peer_name
        self.state_dir = Path(base_dir) / "peers" / peer_name
        self.state_dir.mkdir(parents=True, exist_ok=True)

        self.deployment_dir = self.state_dir / "deployments"
        self.deployment_dir.mkdir(parents=True, exist_ok=True)

        self.audit_file = self.state_dir / "audit.jsonl"
        self.status_file = self.state_dir / "status.json"

    def save_deployment(self, deployment_id: str, result: Dict[str, Any]) -> None:
        """Save deployment result with metadata.

        Args:
            deployment_id: Unique deployment identifier
            result: Deployment result dictionary
        """
        deployment_file = self.deployment_dir / f"{deployment_id}.json"

        metadata = {
            "timestamp": datetime.utcnow().isoformat(),
            "peer_name": self.peer_name,
            "deployment_id": deployment_id,
            **result
        }

        with open(deployment_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        self._log_audit("deployment_saved", {
            "deployment_id": deployment_id,
            "status": result.get("status", "unknown"),
        })

    def get_latest_deployment(self) -> Optional[Dict[str, Any]]:
        """Get most recent deployment metadata.

        Returns:
            Deployment metadata dict or None if no deployments
        """
        deployments = sorted(self.deployment_dir.glob("*.json"))

        if not deployments:
            return None

        with open(deployments[-1]) as f:
            return json.load(f)

    def get_deployment_history(self, limit: Optional[int] = 10) -> List[Dict[str, Any]]:
        """Get deployment history (most recent first).

        Args:
            limit: Maximum number of deployments to return, or None for all

        Returns:
            List of deployment metadata dicts
        """
        deployments = sorted(self.deployment_dir.glob("*.json"), reverse=True)[:limit]

        history = []
        for dep_file in deployments:
            with open(dep_file) as f:
                history.append(json.load(f))

        return history

    def save_tunnel_status(self, tunnel_status: Dict[str, Any]) -> None:
        """Save current tunnel status snapshot.

        Args:
            tunnel_status: Tunnel status dictionary
        """
        status_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "peer_name": self.peer_name,
            "tunnels": tunnel_status,
        }

        with open(self.status_file, 'w') as f:
            json.dump(status_data, f, indent=2)

        self._log_audit("tunnel_status_updated", tunnel_status)

    def get_latest_tunnel_status(self) -> Optional[Dict[str, Any]]:
        """Get latest tunnel status snapshot.

        Returns:
            Tunnel status dict or None
        """
        if not self.status_file.exists():
            return None

        with open(self.status_file) as f:
            data = json.load(f)
            return data.get("tunnels")

    def get_audit_log(self, limit: Optional[int] = 100) -> List[Dict[str, Any]]:
        """Get audit log entries (most recent first).

        Args:
            limit: Maximum number of entries to return, or None for all entries

        Returns:
            List of audit log entries
        """
        if not self.audit_file.exists():
            return []

        with open(self.audit_file) as f:
            # deque(maxlen=limit) keeps the *last* `limit` lines, so the newest
            # entries survive truncation; maxlen=None keeps every line.
            recent_lines = deque(f, maxlen=limit)

        entries = []
        for line in recent_lines:
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                pass

        return list(reversed(entries))

    def _log_audit(self, event_type: str, details: Optional[Dict[str, Any]] = None) -> None:
        """Log audit trail entry.

        Args:
            event_type: Type of event (e.g., deployment_saved, tunnel_status_updated)
            details: Event details
        """
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "peer_name": self.peer_name,
            "event_type": event_type,
            "details": details or {},
        }

        with open(self.audit_file, 'a') as f:
            f.write(json.dumps(entry) + '\n')

    def get_peer_status(self) -> Dict[str, Any]:
        """Get overall peer status.

        Returns:
            Status dictionary with deployment and tunnel info
        """
        latest_deployment = self.get_latest_deployment()
        latest_tunnel_status = self.get_latest_tunnel_status()

        return {
            "peer_name": self.peer_name,
            "state_dir": str(self.state_dir),
            "last_deployment": latest_deployment,
            "tunnel_status": latest_tunnel_status,
            "deployments_count": len(list(self.deployment_dir.glob("*.json"))),
            "audit_events_count": sum(1 for _ in self.audit_file.read_text().splitlines()) if self.audit_file.exists() else 0,
        }

    def export_state_backup(self, backup_dir: str = ".vpnctl-backups") -> Path:
        """Export complete peer state to backup file.

        Args:
            backup_dir: Directory for backups

        Returns:
            Path to backup file
        """
        backup_path = Path(backup_dir) / self.peer_name
        backup_path.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        backup_file = backup_path / f"state_{timestamp}.json"

        backup_data = {
            "timestamp": datetime.utcnow().isoformat(),
            "peer_name": self.peer_name,
            "deployments": self.get_deployment_history(limit=None),
            "tunnel_status": self.get_latest_tunnel_status(),
            "audit_log": self.get_audit_log(limit=None),
        }

        with open(backup_file, 'w') as f:
            json.dump(backup_data, f, indent=2)

        self._log_audit("state_backed_up", {"backup_file": str(backup_file)})

        return backup_file

    def clear_state(self) -> None:
        """Clear all peer state (use with caution).

        This does NOT delete the peer spec or infrastructure - only local state tracking.
        """
        self._log_audit("state_cleared", {"warning": "Local state cleared"})

        import shutil
        if self.state_dir.exists():
            shutil.rmtree(self.state_dir)

        self.state_dir.mkdir(parents=True, exist_ok=True)
