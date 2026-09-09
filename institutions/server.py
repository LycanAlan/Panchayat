"""A2A server, profile-driven. Adversarial by calibration, not by mood.

Owner: Alakshendra
Lane: institutions
"""

from __future__ import annotations

from core.types import InstitutionProfile


def load_profile(name: str) -> InstitutionProfile:
    """institutions/profiles/<name>.yaml. Every rate needs a calibration_note."""
    raise NotImplementedError


def build_agent_factory(profile: InstitutionProfile):
    """Return a callable(context_id) -> Agent for A2AServer(agent_factory=...)."""
    raise NotImplementedError


def serve(name: str) -> None:
    """A2AServer(agent_factory=..., host='0.0.0.0', port=profile.port).serve()

    This process owns its own state. It must NEVER touch the panchayat table --
    shared state would make the trust boundary decorative.
    """
    raise NotImplementedError
