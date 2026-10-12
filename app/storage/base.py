from abc import ABC, abstractmethod

from app.models.domain import AgencyProfile, UserProfile


class ProfileStore(ABC):
    @abstractmethod
    def get_user(self, user_id: str) -> UserProfile | None: ...

    @abstractmethod
    def get_user_by_email(self, email: str) -> UserProfile | None: ...

    @abstractmethod
    def save_user(self, user: UserProfile) -> UserProfile: ...

    @abstractmethod
    def get_agency(self, agency_id: str) -> AgencyProfile | None: ...

    @abstractmethod
    def save_agency(self, agency: AgencyProfile) -> AgencyProfile: ...

    @abstractmethod
    def list_users(self) -> list[UserProfile]: ...

    @abstractmethod
    def list_agencies(self) -> list[AgencyProfile]: ...

    @abstractmethod
    def delete_user(self, user_id: str) -> None: ...
