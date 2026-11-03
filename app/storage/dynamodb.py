import json
from decimal import Decimal
from typing import Any

import boto3
from botocore.exceptions import ClientError

from app.models.domain import AgencyProfile, CoreProfile, UserProfile
from app.storage.base import ProfileStore


def _serialize(obj: Any) -> Any:
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _serialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialize(v) for v in obj]
    return obj


def _deserialize(obj: Any) -> Any:
    if isinstance(obj, Decimal):
        if obj % 1 == 0:
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: _deserialize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_deserialize(v) for v in obj]
    return obj


class DynamoDBStore(ProfileStore):
    def __init__(
        self,
        *,
        users_table: str,
        agencies_table: str,
        core_profiles_table: str,
        region: str,
        endpoint_url: str | None,
        profile_name: str | None,
    ) -> None:
        session_kwargs: dict[str, Any] = {"region_name": region}
        if profile_name:
            session_kwargs["profile_name"] = profile_name
        session = boto3.Session(**session_kwargs)
        self.dynamodb = session.resource("dynamodb", endpoint_url=endpoint_url)
        self.users = self.dynamodb.Table(users_table)
        self.agencies = self.dynamodb.Table(agencies_table)
        self.core_profiles = self.dynamodb.Table(core_profiles_table)

    def get_core_profile_by_email(self, email: str) -> CoreProfile | None:
        resp = self.core_profiles.query(
            IndexName="email-index",
            KeyConditionExpression="email = :e",
            ExpressionAttributeValues={":e": email.strip().lower()},
            Limit=1,
        )
        items = resp.get("Items") or []
        return CoreProfile.model_validate(_deserialize(items[0])) if items else None

    def save_core_profile(self, profile: CoreProfile) -> CoreProfile:
        profile.touch()
        payload = json.loads(profile.model_dump_json())
        self.core_profiles.put_item(Item=_serialize(payload))
        return profile

    def list_core_profiles(self, query: str = "") -> list[CoreProfile]:
        profiles: list[CoreProfile] = []
        scan_kwargs: dict[str, Any] = {}
        while True:
            resp = self.core_profiles.scan(**scan_kwargs)
            for item in resp.get("Items") or []:
                profiles.append(CoreProfile.model_validate(_deserialize(item)))
            token = resp.get("LastEvaluatedKey")
            if not token:
                break
            scan_kwargs["ExclusiveStartKey"] = token
        needle = query.strip().lower()
        if needle:
            profiles = [
                p for p in profiles
                if needle in " ".join(
                    str(v or "")
                    for v in (p.email, p.display_name, p.title, p.department, p.site)
                ).lower()
            ]
        return sorted(profiles, key=lambda p: (p.display_name or p.email).lower())

    def get_user(self, user_id: str) -> UserProfile | None:
        resp = self.users.get_item(Key={"user_id": user_id})
        item = resp.get("Item")
        if not item:
            return None
        return UserProfile.model_validate(_deserialize(item))

    def get_user_by_email(self, email: str) -> UserProfile | None:
        normalized = email.strip().lower()
        try:
            resp = self.users.query(
                IndexName="email-index",
                KeyConditionExpression="email = :e",
                ExpressionAttributeValues={":e": normalized},
                Limit=1,
            )
        except ClientError:
            return None
        items = resp.get("Items") or []
        if not items:
            return None
        return UserProfile.model_validate(_deserialize(items[0]))

    def save_user(self, user: UserProfile) -> UserProfile:
        user.touch()
        payload = json.loads(user.model_dump_json())
        self.users.put_item(Item=_serialize(payload))
        return user

    def get_agency(self, agency_id: str) -> AgencyProfile | None:
        resp = self.agencies.get_item(Key={"agency_id": agency_id})
        item = resp.get("Item")
        if not item:
            return None
        return AgencyProfile.model_validate(_deserialize(item))

    def save_agency(self, agency: AgencyProfile) -> AgencyProfile:
        agency.touch()
        payload = json.loads(agency.model_dump_json())
        self.agencies.put_item(Item=_serialize(payload))
        return agency

    def list_users(self) -> list[UserProfile]:
        users: list[UserProfile] = []
        scan_kwargs: dict[str, Any] = {}
        while True:
            resp = self.users.scan(**scan_kwargs)
            for item in resp.get("Items") or []:
                users.append(UserProfile.model_validate(_deserialize(item)))
            token = resp.get("LastEvaluatedKey")
            if not token:
                break
            scan_kwargs["ExclusiveStartKey"] = token
        return sorted(users, key=lambda u: (u.email or "").lower())

    def list_agencies(self) -> list[AgencyProfile]:
        agencies: list[AgencyProfile] = []
        scan_kwargs: dict[str, Any] = {}
        while True:
            resp = self.agencies.scan(**scan_kwargs)
            for item in resp.get("Items") or []:
                agencies.append(AgencyProfile.model_validate(_deserialize(item)))
            token = resp.get("LastEvaluatedKey")
            if not token:
                break
            scan_kwargs["ExclusiveStartKey"] = token
        return sorted(agencies, key=lambda a: (a.domain or "").lower())

    def delete_user(self, user_id: str) -> None:
        self.users.delete_item(Key={"user_id": user_id})
