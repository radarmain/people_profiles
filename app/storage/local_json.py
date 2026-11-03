import json
from pathlib import Path

from app.models.domain import AgencyProfile, CoreProfile, UserProfile
from app.storage.base import ProfileStore


class LocalJsonStore(ProfileStore):
    def __init__(self, data_dir: str) -> None:
        self.root = Path(data_dir)
        self.users_dir = self.root / "users"
        self.agencies_dir = self.root / "agencies"
        self.core_profiles_dir = self.root / "core_profiles"
        self.users_dir.mkdir(parents=True, exist_ok=True)
        self.agencies_dir.mkdir(parents=True, exist_ok=True)
        self.core_profiles_dir.mkdir(parents=True, exist_ok=True)

    def _core_profile_path(self, core_id: str) -> Path:
        safe = core_id.replace("/", "_")
        return self.core_profiles_dir / f"{safe}.json"

    def get_core_profile_by_email(self, email: str) -> CoreProfile | None:
        normalized = email.strip().lower()
        for path in self.core_profiles_dir.glob("*.json"):
            profile = CoreProfile.model_validate_json(path.read_text())
            if profile.email.lower() == normalized:
                return profile
        return None

    def save_core_profile(self, profile: CoreProfile) -> CoreProfile:
        profile.touch()
        self._core_profile_path(profile.core_id).write_text(profile.model_dump_json(indent=2))
        return profile

    def list_core_profiles(self, query: str = "") -> list[CoreProfile]:
        needle = query.strip().lower()
        profiles = [
            CoreProfile.model_validate_json(path.read_text())
            for path in self.core_profiles_dir.glob("*.json")
        ]
        if needle:
            profiles = [
                p for p in profiles
                if needle in " ".join(
                    str(v or "")
                    for v in (p.email, p.display_name, p.title, p.department, p.site)
                ).lower()
            ]
        return sorted(profiles, key=lambda p: (p.display_name or p.email).lower())

    def _user_path(self, user_id: str) -> Path:
        safe = user_id.replace("/", "_")
        return self.users_dir / f"{safe}.json"

    def _agency_path(self, agency_id: str) -> Path:
        safe = agency_id.replace("/", "_")
        return self.agencies_dir / f"{safe}.json"

    def get_user(self, user_id: str) -> UserProfile | None:
        path = self._user_path(user_id)
        if not path.exists():
            return None
        return UserProfile.model_validate_json(path.read_text())

    def get_user_by_email(self, email: str) -> UserProfile | None:
        normalized = email.strip().lower()
        for path in self.users_dir.glob("*.json"):
            user = UserProfile.model_validate_json(path.read_text())
            if user.email.lower() == normalized:
                return user
        return None

    def save_user(self, user: UserProfile) -> UserProfile:
        user.touch()
        self._user_path(user.user_id).write_text(user.model_dump_json(indent=2))
        return user

    def get_agency(self, agency_id: str) -> AgencyProfile | None:
        path = self._agency_path(agency_id)
        if not path.exists():
            return None
        return AgencyProfile.model_validate_json(path.read_text())

    def save_agency(self, agency: AgencyProfile) -> AgencyProfile:
        agency.touch()
        self._agency_path(agency.agency_id).write_text(agency.model_dump_json(indent=2))
        return agency

    def list_users(self) -> list[UserProfile]:
        users: list[UserProfile] = []
        for path in self.users_dir.glob("*.json"):
            users.append(UserProfile.model_validate_json(path.read_text()))
        return sorted(users, key=lambda u: (u.email or "").lower())

    def list_agencies(self) -> list[AgencyProfile]:
        agencies: list[AgencyProfile] = []
        for path in self.agencies_dir.glob("*.json"):
            agencies.append(AgencyProfile.model_validate_json(path.read_text()))
        return sorted(agencies, key=lambda a: (a.domain or "").lower())

    def delete_user(self, user_id: str) -> None:
        path = self._user_path(user_id)
        if path.exists():
            path.unlink()
