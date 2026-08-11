"""Replayable raw provider payload storage."""

from __future__ import annotations

import gzip
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import quote

JsonObject = dict[str, Any]


@dataclass(frozen=True)
class RawObjectRef:
    storage_bucket: str
    storage_path: str
    endpoint: str
    request_fingerprint: str
    payload_sha256: str
    byte_size: int
    content_type: str = "application/json"
    content_encoding: str = "gzip"


class LocalRawStore:
    """Filesystem raw store used for development, audit evidence, and tests.

    Production storage is intentionally not coupled to this class. Block 4 can
    implement a Supabase Storage adapter behind the same output contract.
    """

    def __init__(self, root: Path, *, bucket_name: str = "local-audit") -> None:
        self._root = root
        self._bucket_name = bucket_name

    def put(
        self,
        *,
        endpoint: str,
        parameters: dict[str, str | int],
        payload: JsonObject,
    ) -> RawObjectRef:
        canonical_payload = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        payload_sha256 = hashlib.sha256(canonical_payload).hexdigest()
        request_fingerprint = self.fingerprint(endpoint=endpoint, parameters=parameters)
        endpoint_path = quote(endpoint.strip("/").replace("/", "_"), safe="_-")
        relative_path = (
            f"api-football/{endpoint_path}/{request_fingerprint}-{payload_sha256}.json.gz"
        )
        target = self._root / relative_path
        target.parent.mkdir(parents=True, exist_ok=True)

        compressed = gzip.compress(canonical_payload, mtime=0)
        if not target.exists():
            target.write_bytes(compressed)
        elif target.read_bytes() != compressed:
            raise RuntimeError(f"raw object collision at {target}")

        return RawObjectRef(
            storage_bucket=self._bucket_name,
            storage_path=relative_path.replace("\\", "/"),
            endpoint=endpoint.strip("/"),
            request_fingerprint=request_fingerprint,
            payload_sha256=payload_sha256,
            byte_size=len(compressed),
        )

    @staticmethod
    def fingerprint(
        *,
        endpoint: str,
        parameters: dict[str, str | int],
    ) -> str:
        material = json.dumps(
            {
                "endpoint": endpoint.strip("/"),
                "parameters": sorted((str(key), str(value)) for key, value in parameters.items()),
            },
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        return hashlib.sha256(material).hexdigest()
