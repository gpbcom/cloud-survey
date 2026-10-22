from __future__ import annotations


class ScriptError(Exception):
    """Base class for every error raised by the install and migration scripts.

    Attributes:
        message (str): Human-readable description of the error.
    """

    def __init__(self, message: str) -> None:
        """Initialize the error.

        Args:
            message (str): Human-readable description of the error.
        """
        self.message = message
        super().__init__(message)


class StackInstallError(ScriptError):
    """Raised when a step of the stack installation fails.

    Attributes:
        step (str): The failed step.
        reason (str): Human-readable explanation of why it failed.
    """

    def __init__(self, step: str, reason: str) -> None:
        """Initialize the error.

        Args:
            step (str): The failed step.
            reason (str): Human-readable explanation of why it failed.
        """
        self.step = step
        self.reason = reason
        super().__init__(f"The stack installation failed at '{step}': {reason}.")


class MigrationError(ScriptError):
    """Raised when a database migration command fails.

    Attributes:
        command (str): The migration command.
        reason (str): Human-readable explanation of why it failed.
    """

    def __init__(self, command: str, reason: str) -> None:
        """Initialize the error.

        Args:
            command (str): The migration command.
            reason (str): Human-readable explanation of why it failed.
        """
        self.command = command
        self.reason = reason
        super().__init__(f"The migration command '{command}' failed: {reason}.")
