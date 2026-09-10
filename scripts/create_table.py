"""Create the single Panchayat table. Idempotent -- safe to re-run.

    python scripts/create_table.py

Reads the same two environment variables core/store.py reads, so pointing this
at DynamoDB Local and pointing the tests at DynamoDB Local are the same
gesture:

    PANCHAYAT_TABLE          table name          (default "panchayat")
    PANCHAYAT_DDB_ENDPOINT   http://localhost:8000 for DynamoDB Local

ONE table, ONE GSI. The access patterns and the key strings live in
core/store.py and nowhere else; this file only declares the shape they need.

    Entity       PK                     SK                        GSI1PK           GSI1SK
    Household    HH#<id>                META                      SEG#<segment>    HH#<id>
    Claim        CLAIM#<id>             META                      SEG#<s>#SVC#<v>  TS#<iso>
    Case         CASE#<id>              META                      STATUS#<s>       TS#<iso>
    Case member  CASE#<id>              HH#<hh>                   --               --
    Consent      HH#<id>                CONSENT#<ts>#<grant_id>   --               --
    Filing       CASE#<id>              FILING#<idem>             --               --
    Disclosure   HH#<id>                DISC#<ts>#<uniq>          --               --
    Case/feeder  FEEDER#<f>#SVC#<v>     TS#<iso>#CASE#<id>        --               --
    Grant ptr    GRANT#<grant_id>       META                      --               --

PAY-PER-REQUEST, not provisioned: a hackathon ward does a few hundred writes a
day and the free tier covers it. Provisioned capacity would need a number we
have no traffic data to defend.

Streams are NEW_IMAGE because the ambient Pattern Watch Lambda is triggered by
a claim row arriving and needs the row's contents -- KEYS_ONLY would make it
read back every record it was just handed.
"""
from __future__ import annotations

import os
import sys

import boto3
from botocore.exceptions import ClientError

TABLE = os.environ.get("PANCHAYAT_TABLE", "panchayat")
ENDPOINT = os.environ.get("PANCHAYAT_DDB_ENDPOINT") or None


def create() -> str:
    ddb = boto3.resource("dynamodb", endpoint_url=ENDPOINT)
    try:
        ddb.create_table(
            TableName=TABLE,
            BillingMode="PAY_PER_REQUEST",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "GSI1PK", "AttributeType": "S"},
                {"AttributeName": "GSI1SK", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "GSI1",
                "KeySchema": [
                    {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                    {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
                ],
                # ALL, not KEYS_ONLY: claims_in_window returns whole Claims, and
                # a projection that forced a GetItem per hit would undo the
                # single-query cost argument the whole design rests on.
                "Projection": {"ProjectionType": "ALL"},
            }],
            StreamSpecification={
                "StreamEnabled": True,
                "StreamViewType": "NEW_IMAGE",
            },
        ).wait_until_exists()
        return "created"
    except ClientError as exc:
        if exc.response["Error"]["Code"] != "ResourceInUseException":
            raise
        return "already exists"


if __name__ == "__main__":
    where = ENDPOINT or "the real AWS endpoint"
    print(f"table '{TABLE}' at {where}: {create()}", file=sys.stderr)
