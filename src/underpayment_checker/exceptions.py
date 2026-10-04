"""Exceptions for this package. Each message tells the reader what to do."""


class UnderpaymentCheckerError(Exception):
    """Base class for all errors in this package."""


class UploadError(UnderpaymentCheckerError):
    """The check rejected a customer file. The message tells the customer what to correct."""


class IngestionError(UnderpaymentCheckerError):
    """The package cannot read a rate file or a reference source."""


class DownloadError(IngestionError):
    """A download failed, or the downloaded file is not complete."""
