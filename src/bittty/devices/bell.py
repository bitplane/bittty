"""Bell device for terminal notifications.

This device handles the BEL character (0x07) and can produce
audio beeps, visual flashes, or system notifications.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..command import Command

from ..device import Device

logger = logging.getLogger(__name__)


class BellDevice(Device):
    """A bell device that handles terminal notifications.

    This device can be configured to produce different types
    of notifications when the BEL character is received.
    """

    def __init__(self, bell_type: str = "none", board=None):
        """Initialize the bell device.

        Args:
            bell_type: Type of bell ("none", "audio", "visual", "system")
            board: Board to plug into
        """
        super().__init__(board)

        self.bell_type = bell_type
        self.bell_count = 0

        logger.debug(f"BellDevice initialized with type: {bell_type}")

    def get_command_handlers(self):
        """Return the commands this bell device handles."""
        return {
            "C0_BEL": self.handle_bell,
        }

    def query(self, feature_name: str) -> Any:
        """Query bell capabilities."""
        if feature_name == "bell_type":
            return self.bell_type
        elif feature_name == "bell_count":
            return self.bell_count
        elif feature_name == "bell_supported":
            return True
        return None

    def handle_bell(self, command: "Command") -> None:
        """Handle the BEL character."""
        self.bell_count += 1

        if self.bell_type == "audio":
            self._audio_bell()
        elif self.bell_type == "visual":
            self._visual_bell()
        elif self.bell_type == "system":
            self._system_bell()
        else:
            # Silent bell - just log
            logger.debug("Bell (silent)")

        return None

    def _audio_bell(self) -> None:
        """Produce an audio beep."""
        try:
            # Try to use system bell
            import os

            os.system('echo -e "\\a"')
        except Exception as e:
            logger.debug(f"Audio bell failed: {e}")

    def _visual_bell(self) -> None:
        """Produce a visual flash (to be implemented by UI layer)."""
        # This would be overridden by UI-specific bell devices
        logger.debug("Visual bell")

    def _system_bell(self) -> None:
        """Produce a system notification."""
        # This would use platform-specific notification systems
        logger.debug("System bell")


class AudioBellDevice(BellDevice):
    """Audio bell device that produces sound."""

    def __init__(self, board=None):
        super().__init__("audio", board)


class VisualBellDevice(BellDevice):
    """Visual bell device that produces visual feedback."""

    def __init__(self, board=None):
        super().__init__("visual", board)


class SystemBellDevice(BellDevice):
    """System bell device that uses OS notifications."""

    def __init__(self, board=None):
        super().__init__("system", board)


class SilentBellDevice(BellDevice):
    """Silent bell device that ignores bell commands."""

    def __init__(self, board=None):
        super().__init__("none", board)
