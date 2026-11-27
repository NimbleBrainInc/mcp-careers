"""The open roles, from roles.yaml, filtered to the running environment."""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROLES_FILE = Path(__file__).parent / "roles.yaml"


@dataclass(frozen=True)
class Role:
    id: str
    title: str
    location: str
    summary: str
    type: str | None = None
    pay_range: str | None = None

    def public(self) -> dict[str, str | None]:
        """The role as an agent sees it; a field the role does not set is None."""
        fields = {
            "id": self.id,
            "title": self.title,
            "location": self.location,
            "type": self.type,
            "pay_range": self.pay_range,
            "summary": self.summary,
        }
        return fields


def load_roles(env: str, path: Path = ROLES_FILE) -> dict[str, Role]:
    """The roles that show in `env`, keyed by id, in file order."""
    data = yaml.safe_load(path.read_text())
    roles: dict[str, Role] = {}
    for entry in data.get("roles", []):
        if env not in entry.get("environments", []):
            continue
        role = Role(
            id=entry["id"],
            title=entry["title"],
            location=entry["location"],
            summary=entry["summary"],
            type=entry.get("type"),
            pay_range=entry.get("pay_range"),
        )
        roles[role.id] = role
    return roles
