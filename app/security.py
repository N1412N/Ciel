"""Small, dependency-free security helpers shared by Ciel backend routes and tools."""
from __future__ import annotations
import ipaddress
import os
import socket
from pathlib import Path
from urllib.parse import urlparse

class SecurityError(ValueError):
    """Raised when an input crosses a backend safety boundary."""

def safe_int(value, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, parsed))

def workspace_path(raw_path: str, workspace: str) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise SecurityError("A path is required.")
    candidate = Path(os.path.expanduser(raw_path.strip())).resolve(strict=False)
    root = Path(os.path.expanduser(workspace)).resolve(strict=False)
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise SecurityError(f"Path must remain inside the workspace: {root}") from exc
    return candidate

def validate_http_url(raw_url: str) -> str:
    if not isinstance(raw_url, str):
        raise SecurityError("URL must be text.")
    parsed = urlparse(raw_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SecurityError("Only http:// and https:// URLs are supported.")
    host = parsed.hostname.lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise SecurityError("Local URLs are not allowed.")
    try:
        addresses = {ipaddress.ip_address(host)}
    except ValueError:
        try:
            addresses = {ipaddress.ip_address(item[4][0]) for item in socket.getaddrinfo(host, None)}
        except socket.gaierror as exc:
            raise SecurityError("Could not resolve URL host.") from exc
    if any(a.is_private or a.is_loopback or a.is_link_local or a.is_reserved for a in addresses):
        raise SecurityError("Private or local network URLs are not allowed.")
    return raw_url.strip()
