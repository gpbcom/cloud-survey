from __future__ import annotations

from pathlib import Path

from logger.exception import LoggerError, LoggingConfigFileError


class TestLoggerError:
    def test_is_an_exception(self) -> None:
        assert issubclass(LoggerError, Exception)

    def test_keeps_its_message(self) -> None:
        error = LoggerError("Something went wrong.")

        assert error.message == "Something went wrong."
        assert str(error) == "Something went wrong."


class TestLoggingConfigFileError:
    def test_hierarchy(self) -> None:
        assert issubclass(LoggingConfigFileError, LoggerError)

    def test_attributes_and_message(self) -> None:
        error = LoggingConfigFileError(Path("conf/logger.yaml"), "the file is not valid YAML.")

        assert error.path == Path("conf/logger.yaml")
        assert error.reason == "the file is not valid YAML."
        assert error.message == str(error)
        assert str(error) == "Cannot load the logging configuration 'conf/logger.yaml': the file is not valid YAML."
