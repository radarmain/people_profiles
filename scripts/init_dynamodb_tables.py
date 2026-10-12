#!/usr/bin/env python3
"""Create DynamoDB tables for local or AWS (profile: concrete)."""

import argparse
import sys

import boto3
from botocore.exceptions import ClientError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", default="us-east-1")
    parser.add_argument("--profile", default="concrete")
    parser.add_argument("--endpoint", default="http://127.0.0.1:8000")
    parser.add_argument("--users-table", default="_user_profiles_users")
    parser.add_argument("--agencies-table", default="_user_profiles_agencies")
    args = parser.parse_args()

    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    dynamodb = session.client("dynamodb", endpoint_url=args.endpoint)

    users_def = {
        "TableName": args.users_table,
        "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [
            {"AttributeName": "user_id", "AttributeType": "S"},
            {"AttributeName": "email", "AttributeType": "S"},
        ],
        "GlobalSecondaryIndexes": [
            {
                "IndexName": "email-index",
                "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "ALL"},
            }
        ],
        "BillingMode": "PAY_PER_REQUEST",
    }

    agencies_def = {
        "TableName": args.agencies_table,
        "KeySchema": [{"AttributeName": "agency_id", "KeyType": "HASH"}],
        "AttributeDefinitions": [{"AttributeName": "agency_id", "AttributeType": "S"}],
        "BillingMode": "PAY_PER_REQUEST",
    }

    for table_def in (users_def, agencies_def):
        name = table_def["TableName"]
        try:
            dynamodb.create_table(**table_def)
            print(f"Created table {name}")
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "ResourceInUseException":
                print(f"Table {name} already exists")
            else:
                raise

    return 0


if __name__ == "__main__":
    sys.exit(main())
