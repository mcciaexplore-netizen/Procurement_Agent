from __future__ import annotations

from urllib.parse import urlparse

from .models import Source, SourceStatus


class PolicyViolation(ValueError):
    """Raised when an acquisition or outbound action is not policy-approved."""


def assert_source_can_run(source: Source, requested_scope: str) -> None:
    if source.status is not SourceStatus.ACTIVE:
        raise PolicyViolation(f"source {source.id} is {source.status}; it cannot run")
    if not source.policy or not source.policy.approved:
        raise PolicyViolation(f"source {source.id} has no approved policy")
    if not any(requested_scope.startswith(scope) for scope in source.policy.allowed_scopes):
        raise PolicyViolation("requested scope is not approved for this source")


def assert_outbound_url_allowed(source: Source, destination: str) -> None:
    if not source.policy or not source.policy.approved:
        raise PolicyViolation("source has no approved policy")
    parsed = urlparse(destination)
    if parsed.scheme != "https" or not parsed.hostname:
        raise PolicyViolation("outbound destination must be an absolute HTTPS URL")
    host = parsed.hostname.lower()
    approved = {domain.lower() for domain in source.policy.allowed_domains}
    if host not in approved:
        raise PolicyViolation("outbound destination is not in the source allow-list")
