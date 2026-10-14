"""Opt-in reader for one application-owned, synthetic development fixture.

This is not a production source catalog or an authorization service. Its sole
entry is explicitly classified as unprotected development data. Callers provide
only the catalog source ID; storage paths are fixed in this module and never
accepted from requests.
"""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import TextIO

from evidence_layer.source_access import (
    SourceReadDenial,
    SourceReadDenialReason,
    SourceReadIntent,
    SourceReadLease,
    SourceReadResult,
    SourceRequestContext,
    context_is_expired,
)

SYNTHETIC_SOURCE_ID = "synthetic-development-notes-v1"
_FIXTURE_FILENAME = "synthetic_evidence.jsonl"
_FIXTURE_DIRECTORY = Path(__file__).parent / "_fixtures"
_UNPROTECTED_DEVELOPMENT = "unprotected-development"
_SOURCE_VERSION = "synthetic-fixture-v1"
_MAX_FIXTURE_BYTES = 64 * 1024


@dataclass(frozen=True)
class _CatalogEntry:
    filename: str
    classification: str
    version: str
    expires_at: datetime | None = None


# This immutable application catalog intentionally contains one synthetic
# source. Adding real or protected sources requires a separate trusted-host
# design and is not supported by this reader.
_SYNTHETIC_SOURCE_CATALOG = MappingProxyType(
    {
        SYNTHETIC_SOURCE_ID: _CatalogEntry(
            filename=_FIXTURE_FILENAME,
            classification=_UNPROTECTED_DEVELOPMENT,
            version=_SOURCE_VERSION,
        )
    }
)


class _JsonlFixtureReader:
    def __init__(self, descriptor: int, lease: SourceReadLease) -> None:
        self._descriptor: int | None = descriptor
        self._stream: TextIO | None = None
        self._iteration_started = False
        self._closed = False
        self.lease = lease

    def iter_records(self) -> Iterable[Mapping[str, object]]:
        if self._closed or self._iteration_started:
            raise OSError("fixture reader is closed")
        descriptor = self._descriptor
        if descriptor is None:
            raise OSError("fixture reader is closed")
        self._iteration_started = True
        self._descriptor = None
        try:
            stream = os.fdopen(descriptor, "r", encoding="utf-8")
        except BaseException:
            self._closed = True
            try:
                os.close(descriptor)
            except OSError:
                pass
            raise
        self._stream = stream
        try:
            while True:
                if self._closed:
                    raise OSError("fixture reader is closed")
                line = stream.readline()
                if not line:
                    return
                if line.strip():
                    yield json.loads(line)
        finally:
            self._close_stream(stream)

    def close(self) -> None:
        self._closed = True
        stream = self._stream
        self._stream = None
        if stream is not None and not stream.closed:
            stream.close()

        descriptor = self._descriptor
        self._descriptor = None
        if descriptor is not None:
            os.close(descriptor)

    def _close_stream(self, stream: TextIO) -> None:
        self._closed = True
        if self._stream is stream:
            self._stream = None
        if not stream.closed:
            stream.close()


class SyntheticFixtureReadBoundary:
    """Read only the single fixed synthetic fixture after complete preflight.

    A request context is validated for shape and expiry, but its fields are not
    treated as trusted identity. This boundary is safe only because the catalog
    entry is public synthetic development data. It must never be generalized to
    real sources or composed into MCP/customer-data paths. This is not a sandbox
    against arbitrary Python code already running in the same process: Python
    module globals and object state can be changed by such code.
    """

    def open_sources(
        self,
        context: SourceRequestContext,
        intents: Sequence[SourceReadIntent],
    ) -> SourceReadResult:
        denial = self._validate_scope(context, intents)
        if denial is not None:
            return denial

        # Validation above covers the complete scope before this first open.
        intent = intents[0]
        entry = _SYNTHETIC_SOURCE_CATALOG[intent.source_id]
        descriptor: int | None = None
        try:
            descriptor = self._open_fixed_fixture(entry.filename)
            info = os.fstat(descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_size > _MAX_FIXTURE_BYTES:
                os.close(descriptor)
                descriptor = None
                return SourceReadDenial(SourceReadDenialReason.INVALID_SOURCE_DATA)
        except (OSError, TypeError, ValueError):
            if descriptor is not None:
                os.close(descriptor)
            return SourceReadDenial(SourceReadDenialReason.STORAGE_FAILURE)

        lease = SourceReadLease(
            request_id=context.request_id,
            operation_id=context.operation_id,
            principal_id=context.principal_id,
            tenant_id=context.tenant_id,
            source_id=intent.source_id,
            operation=intent.operation,
            source_version=entry.version,
            expires_at=min(
                context.expires_at,
                entry.expires_at if entry.expires_at is not None else context.expires_at,
            ),
        )
        return (_JsonlFixtureReader(descriptor, lease),)

    @staticmethod
    def _validate_scope(
        context: SourceRequestContext,
        intents: Sequence[SourceReadIntent],
    ) -> SourceReadDenial | None:
        if type(context) is not SourceRequestContext:
            return SourceReadDenial(SourceReadDenialReason.MISSING_CONTEXT)
        if not all(
            isinstance(value, str) and value
            for value in (
                context.request_id,
                context.operation_id,
                context.principal_id,
                context.tenant_id,
                context.policy_version,
            )
        ) or not isinstance(context.expires_at, datetime):
            return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
        if context_is_expired(context):
            return SourceReadDenial(SourceReadDenialReason.EXPIRED)
        if not intents:
            return SourceReadDenial(SourceReadDenialReason.UNKNOWN_SOURCE)
        if len(intents) != 1 or type(intents[0]) is not SourceReadIntent:
            return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)

        intent = intents[0]
        if not isinstance(intent.source_id, str) or not intent.source_id:
            return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
        entry = _SYNTHETIC_SOURCE_CATALOG.get(intent.source_id)
        if entry is None:
            return SourceReadDenial(SourceReadDenialReason.UNKNOWN_SOURCE)
        if (
            not isinstance(entry, _CatalogEntry)
            or not isinstance(entry.filename, str)
            or not isinstance(entry.version, str)
            or not entry.version
            or entry.classification != _UNPROTECTED_DEVELOPMENT
        ):
            return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
        if entry.expires_at is not None:
            if not isinstance(entry.expires_at, datetime):
                return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
            if (
                entry.expires_at.tzinfo is None
                or entry.expires_at <= datetime.now(timezone.utc)
            ):
                return SourceReadDenial(SourceReadDenialReason.EXPIRED)
        if (
            intent.operation != "retrieve"
            or (
                intent.expected_version is not None
                and not isinstance(intent.expected_version, str)
            )
            or (intent.expected_version is not None and intent.expected_version != entry.version)
            or entry.filename != _FIXTURE_FILENAME
            or Path(entry.filename).name != entry.filename
        ):
            return SourceReadDenial(SourceReadDenialReason.SCOPE_MISMATCH)
        return None

    @staticmethod
    def _open_fixed_fixture(filename: str) -> int:
        """Open only the fixed file, rejecting symlinks and blocking targets.

        Platforms without the required no-follow, directory, or nonblocking
        flags fail closed before opening the fixture.
        """
        nofollow = getattr(os, "O_NOFOLLOW", None)
        directory_flag = getattr(os, "O_DIRECTORY", None)
        nonblocking = getattr(os, "O_NONBLOCK", None)
        if (
            nofollow is None
            or directory_flag is None
            or nonblocking is None
            or not nonblocking
            or filename != _FIXTURE_FILENAME
        ):
            raise OSError("safe fixture open is unavailable")

        common_flags = os.O_RDONLY | nofollow | getattr(os, "O_CLOEXEC", 0)
        directory_fd = os.open(
            os.fspath(_FIXTURE_DIRECTORY), common_flags | directory_flag
        )
        try:
            return os.open(
                filename, common_flags | nonblocking, dir_fd=directory_fd
            )
        finally:
            os.close(directory_fd)
