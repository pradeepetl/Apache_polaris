import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 16 — Credential Vending")


@app.cell(hide_code=True)
def _():
    import os
    from datetime import date, datetime, timezone

    import boto3
    import marimo as mo
    import pandas as pd
    import pyarrow as pa
    import requests
    from botocore.exceptions import ClientError
    from pyiceberg.catalog import load_catalog
    from pyiceberg.exceptions import ForbiddenError

    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_HEALTH = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182/q/health"
    S3_ENDPOINT = f"http://{os.environ.get('S3_HOST', 'localhost')}:4566"
    REALM = "POLARIS"
    REGION = "us-east-1"
    BUCKET = "warehouse"
    CATALOG_NAME = "polaris_warehouse"
    ROLE_ARN = "arn:aws:iam::000000000000:role/polaris-s3-role"
    NAMESPACE = "lab16"
    return (
        BUCKET,
        CATALOG_NAME,
        ClientError,
        ForbiddenError,
        NAMESPACE,
        POLARIS,
        POLARIS_HEALTH,
        REALM,
        REGION,
        ROLE_ARN,
        S3_ENDPOINT,
        boto3,
        date,
        datetime,
        load_catalog,
        mo,
        pa,
        pd,
        requests,
        timezone,
    )


@app.cell(hide_code=True)
def _(CATALOG_NAME, NAMESPACE, POLARIS, REALM, datetime, pd, requests, timezone):
    def get_token(client_id, client_secret):
        resp = requests.post(
            f"{POLARIS}/api/catalog/v1/oauth/tokens",
            headers={"Polaris-Realm": REALM},
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "PRINCIPAL_ROLE:ALL",
            },
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()["access_token"]

    def polaris(method, path, token, body=None, headers=None):
        return requests.request(
            method,
            f"{POLARIS}{path}",
            headers={"Authorization": f"Bearer {token}", "Polaris-Realm": REALM, **(headers or {})},
            json=body,
            timeout=10,
        )

    def load_table_rest(token, table, vended=True):
        headers = {"X-Iceberg-Access-Delegation": "vended-credentials"} if vended else {}
        return polaris(
            "GET",
            f"/api/catalog/v1/{CATALOG_NAME}/namespaces/{NAMESPACE}/tables/{table}",
            token,
            headers=headers,
        )

    def vended_credentials(load_response):
        body = load_response.json()
        creds = {k: v for k, v in body.get("config", {}).items() if k.startswith(("s3.", "client."))}
        for entry in body.get("storage-credentials", []):
            creds.update(entry.get("config", {}))
        return creds

    def mask(value, keep=8):
        value = str(value)
        return value if len(value) <= keep else f"{value[:keep]}…"

    def creds_frame(creds):
        rows = []
        for key, value in sorted(creds.items()):
            if key.endswith("expires-at-ms"):
                value = datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            elif any(s in key for s in ("secret", "token", "key-id")):
                value = mask(value)
            rows.append({"Key": key, "Value": value})
        return pd.DataFrame(rows)

    return creds_frame, get_token, load_table_rest, mask, polaris, vended_credentials


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar(
        [
            mo.md("### Lab 16\n**Credential Vending**"),
            mo.outline(),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 16 — Credential Vending

                **Level:** 4 (Advanced) &nbsp;|&nbsp; **Time:** 30 minutes

                Polaris can hand each engine **short-lived S3 credentials scoped to one table**,
                instead of every engine sharing a static key for the whole bucket.
                In this lab you will create two Iceberg tables, one ordinary and one sensitive,
                and watch Polaris turn catalog-role grants into storage credentials.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Create the `lab16.sales` and `lab16.salaries` tables and load sample data
                    2. See how STS `AssumeRole` mints temporary, scoped credentials
                    3. Ask Polaris for vended credentials through the Iceberg REST API
                    4. Create an analyst who may read `sales` only, and prove they can't get credentials for `salaries`
                    5. Read the table from PyIceberg with **no S3 keys in its config**
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(CATALOG_NAME, POLARIS_HEALTH, S3_ENDPOINT, get_token, mo, polaris, requests):
    def _reachable(url):
        try:
            return requests.get(url, timeout=5).ok
        except requests.RequestException:
            return False

    _polaris_ok = _reachable(POLARIS_HEALTH)
    _s3_ok = _reachable(f"{S3_ENDPOINT}/_localstack/health")
    mo.stop(
        not (_polaris_ok and _s3_ok),
        mo.callout(
            mo.md(
                f"""
                **The lab stack isn't reachable.**
                Polaris: {"up" if _polaris_ok else "**down**"} &nbsp;·&nbsp; LocalStack S3: {"up" if _s3_ok else "**down**"}

                Start it with `podman compose --profile marimo up -d`, then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )

    ADMIN_TOKEN = get_token("root", "s3cr3t")
    storage_config = polaris("GET", f"/api/management/v1/catalogs/{CATALOG_NAME}", ADMIN_TOKEN).json()[
        "storageConfigInfo"
    ]

    mo.hstack(
        [
            mo.stat("Healthy", label="Polaris", caption="REST catalog", bordered=True),
            mo.stat("Healthy", label="LocalStack", caption="S3 + STS", bordered=True),
            mo.stat(CATALOG_NAME, label="Catalog", caption=storage_config.get("storageType", "?"), bordered=True),
        ],
        widths="equal",
    )
    return ADMIN_TOKEN, storage_config


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Why credential vending?
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "Static keys (today)": mo.md(
                """
                Trino, Spark and PyIceberg all hold the same long-lived keys (`test / test`):

                ```properties
                # etc/catalog/iceberg.properties
                iceberg.rest-catalog.vended-credentials-enabled=false
                s3.aws-access-key=test
                s3.aws-secret-key=test
                ```

                - Any engine can read **and write** every path in the bucket
                - Keys never expire, so a leaked key is a permanent breach
                - Nothing ties S3 access to a particular table or namespace
                - Every request looks identical in the S3 audit log
                """
            ),
            "Vended credentials": mo.md(
                """
                The engine holds no S3 keys. When it loads a table, Polaris:

                1. Checks the caller's catalog-role grants
                2. Calls STS `AssumeRole` with an inline policy limited to **that table's S3 prefix**
                3. Returns read-only credentials for `TABLE_READ_DATA` and read-write credentials for `TABLE_WRITE_DATA`
                4. The credentials expire after minutes or hours

                Only Polaris holds the IAM role.
                """
            ),
            "Aren't catalog roles enough?": mo.md(
                """
                Catalog roles control what **Polaris** will do for you: list tables, load metadata, commit writes.

                But once an engine has the metadata, it reads the Parquet files **straight from S3**.
                S3 never asks Polaris; it checks only the S3 credential.

                | | Catalog roles only | Catalog roles + vending |
                |---|---|---|
                | Polaris API | Enforced | Enforced |
                | S3 data files | Whatever the static key allows (whole bucket) | Only the granted table, only the granted access level |
                | Where access is defined | Catalog roles **and** hand-written IAM policies | Catalog roles only |

                **Roles decide; vending enforces that decision at the storage layer.**
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        sequenceDiagram
            autonumber
            participant E as Engine (Trino / Spark / PyIceberg)
            participant P as Polaris
            participant S as AWS STS
            participant B as S3 bucket
            E->>P: loadTable(lab16.sales) + X-Iceberg-Access-Delegation
            P->>P: Check catalog-role grants
            P->>S: AssumeRole(roleArn, inline policy for the table prefix)
            S-->>P: Temporary key + secret + session token
            P-->>E: Table metadata + temporary credentials
            E->>B: Read Parquet files with the temporary credentials
        """
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 1 — Create tables and load sample data

    We create a `lab16` namespace with two tables:

    | Table | Contents | Who should read it |
    |-------|----------|--------------------|
    | `lab16.sales` | Orders by region | Analysts |
    | `lab16.salaries` | Employee pay | HR only |

    The code connects to Polaris as `root` through PyIceberg. Note that **the config has no S3 keys**:
    `root` has `CATALOG_MANAGE_CONTENT`, so Polaris vends it read-write credentials for the writes.
    Re-running the cell overwrites the data, so it's safe to run more than once.
    """)
    return


@app.cell
def _(CATALOG_NAME, NAMESPACE, POLARIS, S3_ENDPOINT, date, load_catalog, mo, pa):
    admin_catalog = load_catalog(
        "polaris_admin",
        **{
            "type": "rest",
            "uri": f"{POLARIS}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": "root:s3cr3t",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": "POLARIS",
            "header.X-Iceberg-Access-Delegation": "vended-credentials",
            "s3.endpoint": S3_ENDPOINT,
            "s3.path-style-access": "true",
            "s3.region": "us-east-1",
        },
    )

    sales_data = pa.table(
        {
            "order_id": pa.array(range(1001, 1013), pa.int64()),
            "region": ["EMEA", "APAC", "AMER", "EMEA", "AMER", "APAC",
                       "EMEA", "AMER", "APAC", "EMEA", "AMER", "APAC"],
            "product": ["Laptop", "Monitor", "Keyboard", "Laptop", "Dock", "Headset",
                        "Monitor", "Laptop", "Keyboard", "Dock", "Headset", "Laptop"],
            "quantity": pa.array([2, 5, 10, 1, 4, 8, 3, 2, 12, 6, 7, 1], pa.int32()),
            "amount": [2598.0, 1245.0, 790.0, 1299.0, 716.0, 632.0,
                       747.0, 2598.0, 948.0, 1074.0, 553.0, 1299.0],
            "order_date": pa.array(
                [date(2026, 10, d) for d in (1, 2, 3, 5, 8, 9, 12, 15, 18, 21, 24, 28)],
                pa.date32(),
            ),
        }
    )

    salaries_data = pa.table(
        {
            "employee_id": pa.array([501, 502, 503, 504, 505, 506], pa.int64()),
            "name": ["Asha Rao", "Ben Clarke", "Chen Wei", "Dana Kim", "Elif Demir", "Femi Adeyemi"],
            "department": ["Engineering", "Sales", "Engineering", "Finance", "HR", "Sales"],
            "salary": [142000.0, 98000.0, 155000.0, 121000.0, 87000.0, 104000.0],
            "bonus_pct": [12.5, 18.0, 15.0, 10.0, 8.0, 20.0],
        }
    )

    with mo.status.spinner(title="Creating tables and loading sample data…"):
        admin_catalog.create_namespace_if_not_exists(NAMESPACE)

        sales_table = admin_catalog.create_table_if_not_exists(f"{NAMESPACE}.sales", schema=sales_data.schema)
        sales_table.overwrite(sales_data)

        salaries_table = admin_catalog.create_table_if_not_exists(f"{NAMESPACE}.salaries", schema=salaries_data.schema)
        salaries_table.overwrite(salaries_data)
    return admin_catalog, sales_table, salaries_table


@app.cell(hide_code=True)
def _(mo, sales_table, salaries_table):
    def _preview(table):
        df = table.scan().to_pandas()
        return mo.vstack(
            [
                mo.hstack(
                    [
                        mo.stat(len(df), label="Rows", bordered=True),
                        mo.stat(len(table.history()), label="Snapshots", bordered=True),
                        mo.stat(len(df.columns), label="Columns", bordered=True),
                    ],
                    widths="equal",
                ),
                mo.md(f"**Location:** `{table.location()}`"),
                mo.ui.table(df, selection=None, show_column_summaries=False),
            ]
        )

    mo.ui.tabs({"lab16.sales": _preview(sales_table), "lab16.salaries": _preview(salaries_table)})
    return


@app.cell(hide_code=True)
def _(mo, pd, storage_config):
    mo.vstack(
        [
            mo.md("""
            ---
            ## Step 2 — The catalog's storage configuration

            Every Polaris catalog carries a `storageConfigInfo`. The **`roleArn`** is the IAM role
            Polaris assumes when it vends credentials, and **`allowedLocations`** limits where tables may live.
            The role was created in LocalStack by `localstack-setup`, and the catalog by `init/polaris/setup.sh`.
            """),
            mo.ui.table(
                pd.DataFrame(
                    [{"Field": k, "Value": ", ".join(v) if isinstance(v, list) else str(v)} for k, v in storage_config.items()]
                ),
                selection=None,
                show_column_summaries=False,
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 3 — Under the hood: STS AssumeRole

    This is the call Polaris makes for you. We ask STS for credentials limited to
    **reading the `sales` table's files**, using an inline session policy.
    """)
    return


@app.cell
def _(BUCKET, REGION, ROLE_ARN, S3_ENDPOINT, boto3, sales_table, salaries_table):
    import json

    def _prefix(table):
        return table.location().removeprefix(f"s3://{BUCKET}/").rstrip("/") + "/"

    sales_prefix = _prefix(sales_table)
    salaries_prefix = _prefix(salaries_table)

    read_sales_only = {
        "Version": "2012-10-17",
        "Statement": [
            {"Effect": "Allow", "Action": "s3:GetObject", "Resource": f"arn:aws:s3:::{BUCKET}/{sales_prefix}*"},
            {
                "Effect": "Allow",
                "Action": "s3:ListBucket",
                "Resource": f"arn:aws:s3:::{BUCKET}",
                "Condition": {"StringLike": {"s3:prefix": f"{sales_prefix}*"}},
            },
        ],
    }

    sts = boto3.client(
        "sts",
        endpoint_url=S3_ENDPOINT,
        region_name=REGION,
        aws_access_key_id="test",
        aws_secret_access_key="test",
    )
    scoped_creds = sts.assume_role(
        RoleArn=ROLE_ARN,
        RoleSessionName="lab16-read-sales",
        DurationSeconds=900,
        Policy=json.dumps(read_sales_only),
    )["Credentials"]
    return sales_prefix, salaries_prefix, scoped_creds


@app.cell(hide_code=True)
def _(datetime, mask, mo, scoped_creds, timezone):
    _minutes_left = int((scoped_creds["Expiration"] - datetime.now(timezone.utc)).total_seconds() // 60)
    mo.hstack(
        [
            mo.stat(mask(scoped_creds["AccessKeyId"]), label="Access key", caption="temporary", bordered=True),
            mo.stat(mask(scoped_creds["SessionToken"], 12), label="Session token", caption="required with the key", bordered=True),
            mo.stat(f"{_minutes_left} min", label="Expires in", caption=scoped_creds["Expiration"].strftime("%H:%M:%S UTC"), bordered=True),
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Do the limits hold?

    Use the scoped credentials against S3: read `sales`, read `salaries`, and write into `sales`.
    """)
    return


@app.cell
def _(BUCKET, ClientError, REGION, S3_ENDPOINT, boto3, pd, sales_prefix, salaries_prefix, scoped_creds):
    s3_scoped = boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        region_name=REGION,
        aws_access_key_id=scoped_creds["AccessKeyId"],
        aws_secret_access_key=scoped_creds["SecretAccessKey"],
        aws_session_token=scoped_creds["SessionToken"],
    )

    def _attempt(action):
        try:
            action()
            return "Allowed"
        except ClientError as e:
            return f"Denied ({e.response['Error']['Code']})"

    _probe_key = f"{sales_prefix}lab16-write-probe.txt"
    scope_results = pd.DataFrame(
        [
            {
                "Test": "List sales files",
                "Real AWS": "Allowed",
                "This lab (LocalStack)": _attempt(lambda: s3_scoped.list_objects_v2(Bucket=BUCKET, Prefix=sales_prefix)),
            },
            {
                "Test": "List salaries files",
                "Real AWS": "Denied (AccessDenied)",
                "This lab (LocalStack)": _attempt(lambda: s3_scoped.list_objects_v2(Bucket=BUCKET, Prefix=salaries_prefix)),
            },
            {
                "Test": "Write into sales",
                "Real AWS": "Denied (AccessDenied)",
                "This lab (LocalStack)": _attempt(lambda: s3_scoped.put_object(Bucket=BUCKET, Key=_probe_key, Body=b"x")),
            },
        ]
    )
    _attempt(lambda: s3_scoped.delete_object(Bucket=BUCKET, Key=_probe_key))
    scope_results
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**LocalStack's free tier doesn't enforce IAM or session policies**, so every test above shows *Allowed*. "
            "On real AWS the second and third tests return `AccessDenied`. What matters in this lab is the mechanism: "
            "the policy travels with the credentials, and the engine can't widen it."
        ),
        kind="warn",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 4 — Credential vending through the Iceberg REST API

    Engines don't call STS themselves. They send `loadTable` with the header
    `X-Iceberg-Access-Delegation: vended-credentials`, and Polaris returns the table metadata **plus** temporary credentials.
    Here is the same request with and without the header.
    """)
    return


@app.cell
def _(ADMIN_TOKEN, load_table_rest, vended_credentials):
    without_header = vended_credentials(load_table_rest(ADMIN_TOKEN, "sales", vended=False))
    with_header = vended_credentials(load_table_rest(ADMIN_TOKEN, "sales", vended=True))
    return with_header, without_header


@app.cell(hide_code=True)
def _(creds_frame, mo, with_header, without_header):
    def _panel(title, creds):
        has_keys = "s3.access-key-id" in creds
        return mo.vstack(
            [
                mo.md(f"**{title}**"),
                mo.callout(
                    "Temporary credentials returned" if has_keys else "No credentials returned",
                    kind="success" if has_keys else "neutral",
                ),
                mo.ui.table(creds_frame(creds), selection=None, show_column_summaries=False)
                if creds
                else mo.md("_empty config block_"),
            ]
        )

    mo.hstack(
        [_panel("Without the header", without_header), _panel("With vended-credentials", with_header)],
        widths="equal",
        align="start",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 5 — A restricted analyst

    Create the principal `lab16_analyst` and give it **read access to `lab16.sales` only**,
    plus permission to list the tables in `lab16` (so it can see that `salaries` exists).
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            P["Principal<br/>lab16_analyst"] --> PR["Principal role<br/>lab16_analyst_role"]
            PR --> CR["Catalog role<br/>lab16_sales_reader"]
            CR --> G1["TABLE_READ_DATA<br/>lab16.sales"]
            CR --> G2["TABLE_LIST<br/>namespace lab16"]
        """
    )
    return


@app.cell
def _(ADMIN_TOKEN, CATALOG_NAME, NAMESPACE, get_token, polaris):
    ANALYST = "lab16_analyst"
    _principal_role = "lab16_analyst_role"
    _catalog_role = "lab16_sales_reader"

    # Polaris shows a principal's secret only once; on re-runs, an admin reset issues a new one.
    _created = polaris("POST", "/api/management/v1/principals", ADMIN_TOKEN, {"principal": {"name": ANALYST}})
    if _created.status_code == 409:
        _created = polaris("POST", f"/api/management/v1/principals/{ANALYST}/reset", ADMIN_TOKEN, {})
    _created.raise_for_status()
    _credentials = _created.json()["credentials"]
    analyst_client_id = _credentials["clientId"]
    analyst_secret = _credentials["clientSecret"]

    polaris("POST", "/api/management/v1/principal-roles", ADMIN_TOKEN, {"principalRole": {"name": _principal_role}})
    polaris(
        "PUT",
        f"/api/management/v1/principals/{ANALYST}/principal-roles",
        ADMIN_TOKEN,
        {"principalRole": {"name": _principal_role}},
    )
    polaris(
        "POST",
        f"/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles",
        ADMIN_TOKEN,
        {"catalogRole": {"name": _catalog_role}},
    )
    polaris(
        "PUT",
        f"/api/management/v1/principal-roles/{_principal_role}/catalog-roles/{CATALOG_NAME}",
        ADMIN_TOKEN,
        {"catalogRole": {"name": _catalog_role}},
    )
    for _grant in (
        {"type": "table", "namespace": [NAMESPACE], "tableName": "sales", "privilege": "TABLE_READ_DATA"},
        {"type": "namespace", "namespace": [NAMESPACE], "privilege": "TABLE_LIST"},
    ):
        polaris(
            "PUT",
            f"/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles/{_catalog_role}/grants",
            ADMIN_TOKEN,
            {"grant": _grant},
        ).raise_for_status()

    ANALYST_TOKEN = get_token(analyst_client_id, analyst_secret)
    analyst_grants = polaris(
        "GET", f"/api/management/v1/catalogs/{CATALOG_NAME}/catalog-roles/{_catalog_role}/grants", ADMIN_TOKEN
    ).json()["grants"]
    return ANALYST, ANALYST_TOKEN, analyst_client_id, analyst_grants, analyst_secret


@app.cell(hide_code=True)
def _(ANALYST, analyst_client_id, analyst_grants, mo, pd):
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"Principal **`{ANALYST}`** is ready (clientId `{analyst_client_id}`). "
                    "Its secret stays in the `analyst_secret` variable; Polaris shows it only once."
                ),
                kind="success",
            ),
            mo.ui.table(
                pd.DataFrame(
                    [
                        {
                            "Privilege": g["privilege"],
                            "On": g["type"],
                            "Object": ".".join(g.get("namespace", [])) + (f".{g['tableName']}" if g.get("tableName") else ""),
                        }
                        for g in analyst_grants
                    ]
                ),
                selection=None,
                show_column_summaries=False,
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Try it: who gets credentials for what?

    Pick a principal and a table. Polaris checks the grants first and **only vends credentials when the grant allows it**.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    principal_picker = mo.ui.dropdown(
        {"root (catalog admin)": "root", "lab16_analyst (sales reader)": "analyst"},
        value="lab16_analyst (sales reader)",
        label="Principal",
    )
    table_picker = mo.ui.dropdown(["sales", "salaries"], value="salaries", label="Table")
    mo.hstack([principal_picker, table_picker], justify="start", gap=2)
    return principal_picker, table_picker


@app.cell(hide_code=True)
def _(
    ADMIN_TOKEN,
    ANALYST_TOKEN,
    NAMESPACE,
    creds_frame,
    load_table_rest,
    mo,
    principal_picker,
    table_picker,
    vended_credentials,
):
    _token = {"root": ADMIN_TOKEN, "analyst": ANALYST_TOKEN}[principal_picker.value]
    _resp = load_table_rest(_token, table_picker.value)
    _target = f"`{NAMESPACE}.{table_picker.value}`"

    if _resp.ok:
        _out = mo.vstack(
            [
                mo.callout(mo.md(f"**HTTP {_resp.status_code}.** Polaris returned metadata and temporary credentials for {_target}."), kind="success"),
                mo.ui.table(creds_frame(vended_credentials(_resp)), selection=None, show_column_summaries=False),
            ]
        )
    else:
        _out = mo.callout(
            mo.md(
                f"**HTTP {_resp.status_code}.** Polaris refused to load {_target}, so **no credentials were vended**.\n\n"
                f"> {_resp.json().get('error', {}).get('message', _resp.text)[:300]}"
            ),
            kind="danger",
        )
    _out
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 6 — PyIceberg as the analyst, with no S3 keys

    The config below has **no `s3.access-key-id` or `s3.secret-access-key`**. PyIceberg gets the credentials
    from the `loadTable` response and uses them to read the Parquet files.
    """)
    return


@app.cell
def _(CATALOG_NAME, POLARIS, S3_ENDPOINT, analyst_client_id, analyst_secret, load_catalog):
    analyst_catalog = load_catalog(
        "polaris_analyst",
        **{
            "type": "rest",
            "uri": f"{POLARIS}/api/catalog",
            "warehouse": CATALOG_NAME,
            "credential": f"{analyst_client_id}:{analyst_secret}",
            "scope": "PRINCIPAL_ROLE:ALL",
            "header.Polaris-Realm": "POLARIS",
            "header.X-Iceberg-Access-Delegation": "vended-credentials",
            "s3.endpoint": S3_ENDPOINT,
            "s3.path-style-access": "true",
            "s3.region": "us-east-1",
        },
    )

    analyst_sales = analyst_catalog.load_table("lab16.sales")
    analyst_sales_df = analyst_sales.scan().to_pandas()
    return analyst_catalog, analyst_sales, analyst_sales_df


@app.cell(hide_code=True)
def _(analyst_sales, analyst_sales_df, mask, mo):
    _key = analyst_sales.io.properties.get("s3.access-key-id", "none")
    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"Read **{len(analyst_sales_df)} rows** from `lab16.sales` as `lab16_analyst`. "
                    f"The S3 key PyIceberg used was vended by Polaris: `{mask(_key)}`"
                ),
                kind="success",
            ),
            mo.ui.table(analyst_sales_df, selection=None, show_column_summaries=False),
        ]
    )
    return


@app.cell
def _(ForbiddenError, analyst_catalog):
    try:
        analyst_catalog.load_table("lab16.salaries")
        salaries_outcome = "loaded"
    except ForbiddenError as e:
        salaries_outcome = str(e)
    return (salaries_outcome,)


@app.cell(hide_code=True)
def _(mo, salaries_outcome):
    mo.callout(
        mo.md(
            "**`lab16.salaries` was refused.** The analyst can see the table in a listing, but Polaris won't load it, "
            "and with no static S3 keys there's no other way to reach its files.\n\n"
            f"> {salaries_outcome[:300]}"
        )
        if salaries_outcome != "loaded"
        else mo.md("**`lab16.salaries` loaded.** Check the analyst's grants; they're broader than intended."),
        kind="danger" if salaries_outcome == "loaded" else "success",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Wrap-up
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.accordion(
        {
            "Enable vended credentials in Trino": mo.md(
                """
                Edit `etc/catalog/iceberg.properties`:

                ```properties
                # before
                iceberg.rest-catalog.vended-credentials-enabled=false
                s3.aws-access-key=test
                s3.aws-secret-key=test

                # after
                iceberg.rest-catalog.vended-credentials-enabled=true
                # delete s3.aws-access-key and s3.aws-secret-key
                ```

                Then restart Trino: `podman compose restart trino`.
                Trino now asks Polaris for credentials on every `loadTable`.
                """
            ),
            "Static vs vended credentials": mo.md(
                """
                | | Static credentials | Vended credentials |
                |---|---|---|
                | Lifetime | Never expire | Minutes to hours |
                | Scope | Whole bucket | One table's prefix |
                | Read vs write | No distinction | `TABLE_READ_DATA` → read-only, `TABLE_WRITE_DATA` → read-write |
                | Rotation | Manual | Every request |
                | Blast radius of a leak | Entire data lake | One table, until expiry |
                | Where keys live | Every engine's config | Only Polaris holds the IAM role |
                """
            ),
            "Key takeaways": mo.md(
                """
                1. Catalog roles protect the Polaris API; vending extends the same rules to the S3 files
                2. Polaris uses the catalog's `roleArn` to call STS `AssumeRole` with a per-table inline policy
                3. Engines opt in with the `X-Iceberg-Access-Delegation: vended-credentials` header
                4. A principal without a grant gets HTTP 403 and **no credentials**
                5. PyIceberg, Trino and Spark pick up vended credentials automatically
                """
            ),
            "Exercises": mo.md(
                """
                1. Grant `TABLE_WRITE_DATA` on `lab16.sales` to `lab16_sales_reader` and re-run Step 5. What changes in the vended credentials?
                2. Revoke `TABLE_READ_DATA` on `lab16.sales` and re-run Step 6. What error does PyIceberg raise?
                3. Enable vended credentials in Trino (see above) and query `iceberg.lab16.sales`.
                4. **Challenge:** wait for the credentials from Step 3 to expire (or use `DurationSeconds=900` and come back), then retry the S3 calls.
                """
            ),
        },
        multiple=True,
    )
    return


if __name__ == "__main__":
    app.run()
