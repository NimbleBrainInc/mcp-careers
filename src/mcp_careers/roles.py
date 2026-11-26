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
    pay_range: str
    summary: str

    def public(self) -> dict[str, str]:
        return {
            "id": self.id,
            "title": self.title,
            "location": self.location,
            "pay_range": self.pay_range,
            "summary": self.summary,
        }


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
            pay_range=entry["pay_range"],
            summary=entry["summary"],
        )
        roles[role.id] = role
    return roles
