"""Pre-Shared Key Domain Service."""

from domain.models.value_objects import PSK
from domain.exceptions import PSKGenerationError


class PskService:
    """PSK generation and validation service."""

    @staticmethod
    def generate_psk(length: int = 64) -> PSK:
        """
        Generate a cryptographically secure PSK.

        Args:
            length: PSK length (default 64)

        Returns:
            Generated PSK

        Raises:
            PSKGenerationError: If generation fails
        """
        return PSK.generate(length)

    @staticmethod
    def validate_psk(psk: str) -> tuple[bool, str]:
        """
        Validate a PSK.

        Args:
            psk: PSK to validate

        Returns:
            (is_valid, error_message)
        """
        if not psk:
            return False, "PSK cannot be empty"

        if len(psk) < PSK.MIN_LENGTH:
            return False, f"PSK too short: {len(psk)} chars (minimum {PSK.MIN_LENGTH})"

        return True, ""

    @staticmethod
    def generate_paired_psks(length: int = 64) -> tuple[PSK, PSK]:
        """
        Generate a pair of PSKs for dual tunnels.

        Args:
            length: PSK length

        Returns:
            (psk1, psk2)

        Raises:
            PSKGenerationError: If generation fails
        """
        return PSK.generate(length), PSK.generate(length)
