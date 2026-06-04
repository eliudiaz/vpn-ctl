"""VPN Health Monitoring Web Application.

Serves VPN health status via REST API, watches config for changes.
"""

import threading
import logging
from pathlib import Path
from flask import Flask, jsonify
from vpnctl.health.state import VPNHealthState
from vpnctl.health.config_watcher import FastConfigWatcher

logger = logging.getLogger(__name__)


class VPNHealthApp:
    """VPN Health Monitoring Application."""

    def __init__(self, config_file: str = "config/vpn-peers.yaml", infra_config_file: str = "infra-config.json",
                 aws_profile: str = "affinity", region: str = "us-east-2"):
        """
        Initialize health app.

        Args:
            config_file: Path to VPN peers config file (vpn-peers.yaml)
            infra_config_file: Path to infrastructure config file (infra-config.json with resource IDs)
            aws_profile: AWS profile to use
            region: AWS region
        """
        self.config_file = config_file
        self.infra_config_file = infra_config_file
        self.aws_profile = aws_profile
        self.region = region

        # State management
        self.state = VPNHealthState(aws_profile=aws_profile, region=region)

        # Config watching
        self.watcher: FastConfigWatcher = None
        self.infra_watcher: FastConfigWatcher = None
        self.watcher_thread: threading.Thread = None
        self.infra_watcher_thread: threading.Thread = None

        # Flask app
        self.flask_app = Flask(__name__)
        self._setup_routes()

    def _setup_routes(self) -> None:
        """Setup Flask routes."""

        @self.flask_app.route('/health', methods=['GET'])
        def health():
            """Return overall health status."""
            summary = self.state.get_summary()
            return jsonify({
                "status": "ok",
                "summary": summary,
            })

        @self.flask_app.route('/health/peers', methods=['GET'])
        def peers():
            """Return detailed peer health."""
            return jsonify(self.state.to_dict())

        @self.flask_app.route('/health/peers/<peer_name>', methods=['GET'])
        def peer_health(peer_name):
            """Return health for specific peer."""
            peer = self.state.peers.get(peer_name)
            if not peer:
                return jsonify({"error": f"Peer not found: {peer_name}"}), 404

            return jsonify(peer.to_dict())

        @self.flask_app.route('/health/refresh', methods=['POST'])
        def refresh():
            """Force refresh health status from AWS."""
            try:
                self.state.refresh(self.config_file)
                summary = self.state.get_summary()
                return jsonify({
                    "status": "refreshed",
                    "summary": summary,
                })
            except Exception as e:
                logger.error(f"Refresh failed: {e}")
                return jsonify({"error": str(e)}), 500

        @self.flask_app.route('/health/liveness', methods=['GET'])
        def liveness():
            """Kubernetes liveness probe."""
            return jsonify({"status": "alive"}), 200

        @self.flask_app.route('/health/readiness', methods=['GET'])
        def readiness():
            """Kubernetes readiness probe."""
            if self.state.last_update:
                return jsonify({"status": "ready"}), 200
            return jsonify({"status": "not ready"}), 503

    def _on_config_change(self) -> None:
        """Callback when vpn-peers.yaml changes."""
        logger.info("Peers config changed, refreshing health state...")
        try:
            self.state.refresh(self.config_file, self.infra_config_file)
            summary = self.state.get_summary()
            logger.info(f"Health updated: {summary}")
        except Exception as e:
            logger.error(f"Failed to refresh health: {e}")

    def _on_infra_config_change(self) -> None:
        """Callback when infra-config.json changes (AWS resource IDs updated)."""
        logger.info("Infrastructure config changed, refreshing health state...")
        try:
            self.state.refresh(self.config_file, self.infra_config_file)
            summary = self.state.get_summary()
            logger.info(f"Health updated: {summary}")
        except Exception as e:
            logger.error(f"Failed to refresh health: {e}")

    def start_watcher(self) -> None:
        """Start config file watchers in background threads."""
        # Start peers config watcher
        if not (self.watcher_thread and self.watcher_thread.is_alive()):
            self.watcher = FastConfigWatcher(
                config_file=self.config_file,
                on_change=self._on_config_change,
                check_interval=2
            )
            self.watcher_thread = threading.Thread(target=self.watcher.watch, daemon=True)
            self.watcher_thread.start()
            logger.info("Peers config watcher started")

        # Start infra config watcher if file exists
        if not (self.infra_watcher_thread and self.infra_watcher_thread.is_alive()):
            from pathlib import Path
            if Path(self.infra_config_file).exists():
                self.infra_watcher = FastConfigWatcher(
                    config_file=self.infra_config_file,
                    on_change=self._on_infra_config_change,
                    check_interval=2
                )
                self.infra_watcher_thread = threading.Thread(target=self.infra_watcher.watch, daemon=True)
                self.infra_watcher_thread.start()
                logger.info("Infrastructure config watcher started")
            else:
                logger.warning(f"Infra config file not found: {self.infra_config_file}")

    def stop_watcher(self) -> None:
        """Stop config file watchers."""
        if self.watcher:
            self.watcher.stop()
            if self.watcher_thread:
                self.watcher_thread.join(timeout=5)
            logger.info("Peers config watcher stopped")

        if self.infra_watcher:
            self.infra_watcher.stop()
            if self.infra_watcher_thread:
                self.infra_watcher_thread.join(timeout=5)
            logger.info("Infrastructure config watcher stopped")

    def run(self, host: str = "0.0.0.0", port: int = 8080, debug: bool = False) -> None:
        """Run Flask app with config watchers."""
        # Initial health refresh
        logger.info(f"Initial health check from {self.config_file} and {self.infra_config_file}...")
        self.state.refresh(self.config_file, self.infra_config_file)

        # Start config watchers
        self.start_watcher()

        # Run Flask app
        logger.info(f"Starting VPN Health App on {host}:{port}")
        try:
            self.flask_app.run(host=host, port=port, debug=debug, use_reloader=False)
        finally:
            self.stop_watcher()


def create_app(config_file: str = "config/vpn-peers.yaml", infra_config_file: str = "infra-config.json",
               aws_profile: str = "affinity", region: str = "us-east-2") -> Flask:
    """Factory function for WSGI deployment."""
    app = VPNHealthApp(config_file=config_file, infra_config_file=infra_config_file,
                       aws_profile=aws_profile, region=region)
    app.state.refresh(config_file, infra_config_file)
    app.start_watcher()
    return app.flask_app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app = VPNHealthApp()
    app.run(debug=True)
