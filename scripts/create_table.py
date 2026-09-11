"""
Create the single DynamoDB table, idempotently.

    python scripts/create_table.py                 # against real AWS
    PANCHAYAT_DDB_ENDPOINT=http://localhost:8000 \\
        python scripts/create_table.py              # against DynamoDB Local

WHY THIS EXISTS HERE AND NOT IN A SCRATCHPAD
Table creation is deploy, which is the platform lane -- but the shape of the
table is downstream of core/types.py's key methods and core/store.py's actual
key patterns, which are Kartik's. Writing it here rather than leaving it in a
personal scratchpad means everyone can create an isolated table for the
PANCHAYAT_BACKEND=dynamodb test run without reconstructing the schema from
memory, and it means the schema is reviewed instead of copy-pasted.

THE SCHEMA
One table, one GSI, overloaded across every entity type -- the standard
single-table pattern, and the one CLAUDE.md and core/types.py already commit
to:

    PK / SK              primary key.       CLAIM#<id> / META
                                             CASE#<id>  / META
    GSI1PK / GSI1SK       one shared index, several key patterns:
        SEG#<segment>#SVC#<service>  / TS#<iso>       the Pattern Watch query
                                                       (core/types.py's
                                                       Claim.gsi1pk/gsi1sk)
        FEEDER#<feeder>#SVC#<service> / CASE#<id>      recurrence_count
                                                       (approved in review,
                                                       docs/review/mesh-day1.md
                                                       D2 -- no new GSI, no
                                                       declared key changed)
        STATUS#<status>              / <whatever Case sorts open_cases on>

No second GSI. A single overloaded index is deliberate: this table serves a
five-day build's query patterns, all of them "give me recent items in one
partition," and a second index is capacity we would be paying for and testing
never.

STREAMS
NEW_AND_OLD_IMAGES, always. agents/pattern_watch.py is a Lambda triggered by
this stream -- the ambient path in the four-execution-paths design. Without
streams enabled here, that Lambda has nothing to trigger it and clustering
never runs, silently, with no error anywhere to point at.

BILLING
PAY_PER_REQUEST. A five-day build has no traffic to provision capacity for,
and the wrong provisioned number either throttles the demo or burns credits
sitting idle. Revisit only if this stops being a hackathon.

Owner: Ali (platform). Schema changes here should follow the same rule as
core/types.py itself -- raise it in the group first, this file is what four
people's tests run against.
"""
from __future__ import annotations

import os
import sys

TABLE_NAME = os.environ.get("PANCHAYAT_TABLE", "panchayat")
ENDPOINT = os.environ.get("PANCHAYAT_DDB_ENDPOINT") or None
REGION = os.environ.get("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))


def _client():
    import boto3

    kwargs = {"region_name": REGION}
    if ENDPOINT:
        # DynamoDB Local ignores real credentials but boto3 still demands the
        # shape of some -- these are the standard placeholder values, not
        # secrets, and matter only when ENDPOINT is set.
        kwargs["endpoint_url"] = ENDPOINT
        kwargs.setdefault("aws_access_key_id", os.environ.get("AWS_ACCESS_KEY_ID", "local"))
        kwargs.setdefault("aws_secret_access_key",
                          os.environ.get("AWS_SECRET_ACCESS_KEY", "local"))
    return boto3.client("dynamodb", **kwargs)


def create_table() -> bool:
    """Returns True if it created the table, False if one already existed.

    Idempotent on purpose: this runs on every dev machine and in CI, and a
    table-already-exists error breaking that would be a worse failure mode
    than a no-op.
    """
    ddb = _client()

    # describe_table, not list_tables: the latter returns at most 100 names
    # per page and was unpaginated here, so on an account with more than 100
    # tables the check false-negatives and the script dies on
    # ResourceInUseException -- an "idempotent" script that is only idempotent
    # on small accounts.
    try:
        ddb.describe_table(TableName=TABLE_NAME)
    except ddb.exceptions.ResourceNotFoundException:
        pass
    else:
        print("Table '" + TABLE_NAME + "' already exists at "
              + (ENDPOINT or "region " + REGION) + " -- nothing to do.")
        return False

    ddb.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
            {"AttributeName": "GSI1PK", "AttributeType": "S"},
            {"AttributeName": "GSI1SK", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        GlobalSecondaryIndexes=[{
            "IndexName": "GSI1",
            "KeySchema": [
                {"AttributeName": "GSI1PK", "KeyType": "HASH"},
                {"AttributeName": "GSI1SK", "KeyType": "RANGE"},
            ],
            # ALL, not KEYS_ONLY: claims_in_window and recurrence_count both
            # need the full item back from the index query, not a second
            # GetItem per result -- that second round trip is exactly the
            # kind of thing that is invisible on 12 test claims and expensive
            # or slow against a real dataset.
            "Projection": {"ProjectionType": "ALL"},
        }],
        StreamSpecification={
            "StreamEnabled": True,
            "StreamViewType": "NEW_AND_OLD_IMAGES",
        },
    )

    ddb.get_waiter("table_exists").wait(TableName=TABLE_NAME)
    print("Created table '" + TABLE_NAME + "' at " + (ENDPOINT or "region " + REGION)
          + ", GSI1 active, streams on (NEW_AND_OLD_IMAGES).")
    return True


if __name__ == "__main__":
    try:
        create_table()
    except Exception as exc:  # noqa: BLE001 -- top-level script, report and exit
        target = ENDPOINT or ("AWS region " + REGION)
        print("Failed to create table '" + TABLE_NAME + "' at " + target + ": "
              + type(exc).__name__ + ": " + str(exc), file=sys.stderr)
        sys.exit(1)
