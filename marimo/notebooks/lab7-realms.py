import marimo

__generated_with = "0.25.2"
app = marimo.App(width="medium", app_title="Lab 7 — Realms (Multi-Tenant Isolation)")


@app.cell(hide_code=True)
def _():
    import base64
    import json
    import os

    import marimo as mo
    import pandas as pd
    import requests

    POLARIS = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8181"
    POLARIS_HEALTH = f"http://{os.environ.get('POLARIS_HOST', 'localhost')}:8182/q/health"

    # Bootstrap credentials from docker-compose.yml:
    #   POLARIS_BOOTSTRAP_CREDENTIALS: "POLARIS,root,s3cr3t;TRAINING,trainadmin,train123"
    REALM_CREDS = {"POLARIS": ("root", "s3cr3t"), "TRAINING": ("trainadmin", "train123")}

    # Objects this lab creates in the TRAINING realm (prefixed: the stack is shared by every lab).
    TRAINING_CATALOG = "lab7_training_catalog"
    STUDENT_ROLE = "lab7_student_role"
    SANDBOX_READER = "lab7_sandbox_reader"
    return (
        POLARIS,
        POLARIS_HEALTH,
        REALM_CREDS,
        SANDBOX_READER,
        STUDENT_ROLE,
        TRAINING_CATALOG,
        base64,
        json,
        mo,
        pd,
        requests,
    )


@app.cell(hide_code=True)
def _(POLARIS, REALM_CREDS, base64, json, mo, requests):
    def request_token(realm, client_id, client_secret):
        """Return the raw token response so failures can be shown, not just raised."""
        return requests.post(
            f"{POLARIS}/api/catalog/v1/oauth/tokens",
            headers={"Polaris-Realm": realm},
            data={
                "grant_type": "client_credentials",
                "client_id": client_id,
                "client_secret": client_secret,
                "scope": "PRINCIPAL_ROLE:ALL",
            },
            timeout=10,
        )

    def realm_admin_token(realm):
        _resp = request_token(realm, *REALM_CREDS[realm])
        _resp.raise_for_status()
        return _resp.json()["access_token"]

    def mask(value, keep=8):
        value = str(value)
        return value if len(value) <= keep else f"{value[:keep]}…"

    def jwt_claims(token):
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload))

    def error_message(resp):
        try:
            _body = resp.json()
        except ValueError:
            return resp.text
        _err = _body.get("error")
        if isinstance(_err, dict):
            return _err.get("message", resp.text)
        return _body.get("error_description") or str(_err or resp.text)

    def status_kind(code):
        if 200 <= code < 300:
            return "success"
        return "neutral" if code == 409 else "danger"

    def status_note(code):
        if 200 <= code < 300:
            return "OK"
        return {409: "already exists (expected on a re-run)", 401: "unauthorized", 403: "forbidden"}.get(code, "failed")

    def show_status(label, resp):
        return mo.callout(
            mo.md(f"**{label}** → HTTP **{resp.status_code}** — {status_note(resp.status_code)}"),
            kind=status_kind(resp.status_code),
        )

    return error_message, jwt_claims, mask, realm_admin_token, request_token, show_status, status_note


@app.cell(hide_code=True)
def _(mo):
    mo.sidebar([mo.md("### Lab 7\n**Realms**"), mo.outline()])
    return


@app.cell(hide_code=True)
def _(mo):
    mo.vstack(
        [
            mo.md(
                """
                # Lab 7 — Realms (Multi-Tenant Isolation)

                **Level:** 5 (Advanced) &nbsp;|&nbsp; **Time:** 30 minutes

                A **realm** is the top-level logical partition in Polaris. Everything — catalogs, principals,
                roles, grants — lives inside a realm, and two realms on the same Polaris server are completely
                isolated from each other. In this lab you use a second realm, `TRAINING`, and prove that
                catalogs, principals and roles in one realm are invisible from the other.
                """
            ),
            mo.callout(
                mo.md(
                    """
                    **What you'll do**

                    1. Check how the stack bootstraps two realms
                    2. Get a token for each realm, and try the wrong credentials in the wrong realm
                    3. Compare the catalogs each realm can see
                    4. Create a catalog and a namespace in `TRAINING`
                    5. Prove cross-realm isolation: tokens and objects don't cross the boundary
                    6. Build a small RBAC setup in `TRAINING` and compare both realms side by side
                    """
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(POLARIS_HEALTH, mo, request_token, requests):
    try:
        _polaris_ok = requests.get(POLARIS_HEALTH, timeout=5).ok
    except requests.RequestException:
        _polaris_ok = False
    mo.stop(
        not _polaris_ok,
        mo.callout(
            mo.md(
                """
                **Polaris isn't reachable.** Start the stack with `podman compose --profile marimo up -d`
                (or `docker compose --profile marimo up -d`), then re-run this cell.
                """
            ),
            kind="danger",
        ),
    )

    _polaris_login = request_token("POLARIS", "root", "s3cr3t").status_code
    _training_login = request_token("TRAINING", "trainadmin", "train123").status_code
    mo.stop(
        _training_login != 200,
        mo.callout(
            mo.md(
                f"""
                **The `TRAINING` realm isn't available** (login as `trainadmin` returned HTTP {_training_login}).

                Make sure the `polaris` service in `docker-compose.yml` has:

                ```yaml
                POLARIS_BOOTSTRAP_CREDENTIALS: "POLARIS,root,s3cr3t;TRAINING,trainadmin,train123"
                POLARIS_REALM_CONTEXT_REALMS: "POLARIS,TRAINING"
                ```

                then recreate Polaris: `podman compose up -d polaris` (or `docker compose up -d polaris`).
                Realms are bootstrapped on first start; with Postgres persistence, an existing realm keeps its original credentials.
                """
            ),
            kind="danger",
        ),
    )

    mo.hstack(
        [
            mo.stat("Healthy", label="Polaris", caption="REST catalog :8181", bordered=True),
            mo.stat(f"HTTP {_polaris_login}", label="Realm POLARIS", caption="root / s3cr3t", bordered=True),
            mo.stat(f"HTTP {_training_login}", label="Realm TRAINING", caption="trainadmin / train123", bordered=True),
        ],
        widths="equal",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ## Concepts
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "One server, two realms": mo.mermaid(
                """
                flowchart LR
                    subgraph S["Polaris server"]
                        direction LR
                        subgraph R1["Realm: POLARIS"]
                            C1[("polaris_warehouse")] --> N1["shop"]
                            C1 --> N2["earthquakes"]
                            P1["Principals: root, eng_alice, ..."]
                            PR1["Roles: trino_role, ..."]
                        end
                        subgraph R2["Realm: TRAINING"]
                            C2[("training_catalog")] --> N3["sandbox"]
                            P2["Principals: root (separate!)"]
                            PR2["Roles: student_role, ..."]
                        end
                    end
                    R1 -. "no cross-realm visibility<br/>separate tokens, credentials, everything" .- R2
                """
            ),
            "Use cases": mo.md(
                """
                - **SaaS multi-tenancy** — each customer gets their own realm
                - **Environment isolation** — separate dev, staging and prod realms
                - **Team boundaries** — engineering, data science and compliance each in their own realm
                """
            ),
            "Key rule": mo.md(
                """
                The **`Polaris-Realm` HTTP header** decides which realm a request targets.
                **Tokens are scoped to the realm they were issued in**: a token from one realm fails
                signature verification in another, even on the same server.
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 1 — The realm configuration

    Realms are declared on the `polaris` service in `docker-compose.yml`. Check it with:

    ```bash
    grep -i "realm" docker-compose.yml
    ```

    Out of the box, a single-realm stack looks like this:

    ```yaml
    POLARIS_BOOTSTRAP_CREDENTIALS: POLARIS,root,s3cr3t
    polaris.realm-context.realms: POLARIS
    ```

    The bootstrap format is `REALM_NAME,client_id,client_secret`, with one entry per realm.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.ui.tabs(
        {
            "This stack (already two realms)": mo.md(
                """
                The training stack already bootstraps both realms, so **no edit or restart is needed**:

                ```yaml
                POLARIS_BOOTSTRAP_CREDENTIALS: "POLARIS,root,s3cr3t;TRAINING,trainadmin,train123"
                POLARIS_REALM_CONTEXT_REALMS: "POLARIS,TRAINING"
                ```

                `POLARIS_REALM_CONTEXT_REALMS` is the environment-variable form of `polaris.realm-context.realms`.
                """
            ),
            "Step 2 — adding a realm yourself": mo.md(
                """
                On a single-realm stack, edit the `polaris` service environment. Two changes:

                1. `polaris.realm-context.realms` now includes `TRAINING`
                2. `POLARIS_BOOTSTRAP_CREDENTIALS` bootstraps both realms (semicolon-separated)

                ```yaml
                  polaris:
                    image: apache/polaris:latest
                    container_name: polaris
                    ports:
                      - "8181:8181"
                      - "8182:8182"
                    environment:
                      AWS_REGION: us-east-1
                      AWS_ACCESS_KEY_ID: test
                      AWS_SECRET_ACCESS_KEY: test
                      AWS_ENDPOINT_URL: http://localstack:4566
                      POLARIS_BOOTSTRAP_CREDENTIALS: POLARIS,root,s3cr3t;TRAINING,trainadmin,train123
                      polaris.realm-context.realms: POLARIS,TRAINING
                ```
                """
            ),
            "Step 3 — restart Polaris": mo.md(
                """
                ```bash
                podman compose up -d polaris        # or: docker compose up -d polaris
                podman compose ps polaris           # wait until healthy
                podman logs polaris 2>&1 | grep -i "realm\\|bootstrap"   # both realms bootstrapped?
                ```

                With Postgres persistence, realms are bootstrapped on **first** start only; later starts find them and skip.
                """
            ),
        }
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 4 — Get tokens for both realms

    The same token endpoint, but a different `Polaris-Realm` header and that realm's own credentials.
    """)
    return


@app.cell
def _(POLARIS, requests):
    polaristoken_resp = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": "POLARIS"},
        data={"grant_type": "client_credentials", "client_id": "root", "client_secret": "s3cr3t", "scope": "PRINCIPAL_ROLE:ALL"},
    ).json()
    POLARIS_TOKEN = polaristoken_resp["access_token"]
    POLARIS_AUTH = {"Authorization": f"Bearer {POLARIS_TOKEN}", "Polaris-Realm": "POLARIS"}
    return POLARIS_AUTH, POLARIS_TOKEN


@app.cell
def _(POLARIS, requests):
    trainingtoken_resp = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": "TRAINING"},
        data={"grant_type": "client_credentials", "client_id": "trainadmin", "client_secret": "train123", "scope": "PRINCIPAL_ROLE:ALL"},
    ).json()
    TRAINING_TOKEN = trainingtoken_resp["access_token"]
    TRAINING_AUTH = {"Authorization": f"Bearer {TRAINING_TOKEN}", "Polaris-Realm": "TRAINING"}
    return TRAINING_AUTH, TRAINING_TOKEN


@app.cell(hide_code=True)
def _(POLARIS_TOKEN, TRAINING_TOKEN, jwt_claims, mask, mo, pd):
    _p, _t = jwt_claims(POLARIS_TOKEN), jwt_claims(TRAINING_TOKEN)
    _keys = [k for k in ("sub", "client_id", "principal_id", "scope", "iss") if k in _p or k in _t]
    mo.vstack(
        [
            mo.hstack(
                [
                    mo.stat(mask(POLARIS_TOKEN, 16), label="POLARIS token", caption="client root", bordered=True),
                    mo.stat(mask(TRAINING_TOKEN, 16), label="TRAINING token", caption="client trainadmin", bordered=True),
                ],
                widths="equal",
            ),
            mo.ui.table(
                pd.DataFrame([{"Claim": k, "POLARIS": str(_p.get(k, "")), "TRAINING": str(_t.get(k, ""))} for k in _keys]),
                selection=None,
                show_column_summaries=False,
            ),
            mo.callout(
                mo.md(
                    "Both admins are principals **named `root`** (look at `sub`), yet they are different principals: "
                    "each realm has its own `root`, with its own client ID and secret."
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Question: the wrong credentials in the wrong realm

    What happens if you try the POLARIS realm's credentials (`root` / `s3cr3t`) with `Polaris-Realm: TRAINING`? Try it:
    """)
    return


@app.cell
def _(POLARIS, requests):
    cross_resp = requests.post(
        f"{POLARIS}/api/catalog/v1/oauth/tokens",
        headers={"Polaris-Realm": "TRAINING"},
        data={"grant_type": "client_credentials", "client_id": "root", "client_secret": "s3cr3t", "scope": "PRINCIPAL_ROLE:ALL"},
    )
    return (cross_resp,)


@app.cell(hide_code=True)
def _(cross_resp, error_message, mo):
    mo.callout(
        mo.md(
            f"**Cross-realm login attempt** → HTTP **{cross_resp.status_code}**\n\n"
            f"> {error_message(cross_resp)[:200]}\n\n"
            "The client ID `root` simply doesn't exist in `TRAINING` (its admin's client ID is `trainadmin`)."
        ),
        kind="success" if cross_resp.status_code in (400, 401) else "danger",
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 5 — Realm isolation: catalogs

    List catalogs in each realm with that realm's token.
    """)
    return


@app.cell
def _(POLARIS, POLARIS_AUTH, TRAINING_AUTH, requests):
    polaris_catalogs = requests.get(f"{POLARIS}/api/management/v1/catalogs", headers=POLARIS_AUTH).json()
    training_catalogs_before = requests.get(f"{POLARIS}/api/management/v1/catalogs", headers=TRAINING_AUTH).json()
    return polaris_catalogs, training_catalogs_before


@app.cell(hide_code=True)
def _(TRAINING_CATALOG, mo, polaris_catalogs, training_catalogs_before):
    def _panel(realm, body, note):
        _names = [c["name"] for c in body.get("catalogs", [])]
        return mo.vstack(
            [
                mo.stat(len(_names), label=f"{realm} realm — catalogs", caption=note, bordered=True),
                mo.md("\n".join(f"- `{n}`" for n in _names) or "_(no catalogs)_"),
            ]
        )

    _training_names = [c["name"] for c in training_catalogs_before.get("catalogs", [])]
    mo.vstack(
        [
            mo.hstack(
                [
                    _panel("POLARIS", polaris_catalogs, "expect polaris_warehouse"),
                    _panel("TRAINING", training_catalogs_before, "empty on a fresh stack"),
                ],
                widths="equal",
                align="start",
            ),
            mo.callout(
                mo.md(
                    "**Key insight:** `polaris_warehouse` exists only in the POLARIS realm. The TRAINING realm can't see it, "
                    "even though both realms run on the same server."
                    + (
                        f"\n\n`{TRAINING_CATALOG}` is already listed because this notebook ran before. Use the reset button "
                        "at the end of the lab to start from an empty TRAINING realm."
                        if TRAINING_CATALOG in _training_names
                        else ""
                    )
                ),
                kind="info",
            ),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 6 — Create a catalog in the TRAINING realm

    `POST /api/management/v1/catalogs` with the **TRAINING** token. The storage config mirrors `polaris_warehouse`,
    but tables land under `s3://warehouse/training/`.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.callout(
        mo.md(
            "**Naming note:** the exercise guide uses `training_catalog`, `student_role` and `sandbox_reader`. "
            "Because several labs share this stack, the notebook prefixes them: "
            "**`lab7_training_catalog`**, **`lab7_student_role`**, **`lab7_sandbox_reader`**."
        ),
        kind="neutral",
    )
    return


@app.cell
def _(POLARIS, TRAINING_AUTH, TRAINING_CATALOG, requests, show_status, training_catalogs_before):
    _resp = requests.post(
        f"{POLARIS}/api/management/v1/catalogs",
        headers=TRAINING_AUTH,
        json={
            "catalog": {
                "name": TRAINING_CATALOG,
                "type": "INTERNAL",
                "readOnly": False,
                "properties": {"default-base-location": "s3://warehouse/training"},
                "storageConfigInfo": {
                    "storageType": "S3",
                    "allowedLocations": ["s3://warehouse/training/"],
                    "roleArn": "arn:aws:iam::000000000000:role/polaris-s3-role",
                    "endpoint": "http://localhost:4566",  # S3 endpoint handed to clients
                    "endpointInternal": "http://localstack:4566",  # S3 endpoint Polaris itself uses
                    "stsEndpoint": "http://localstack:4566",  # for credential vending
                    "pathStyleAccess": True,
                    "region": "us-east-1",
                },
            }
        },
    )
    catalog_status = _resp.status_code
    show_status(f"Create {TRAINING_CATALOG} in TRAINING", _resp)
    return (catalog_status,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 7 — Create a namespace in the TRAINING realm

    Namespaces belong to the **Catalog API** (`/api/catalog/v1/{catalog}/namespaces`), still with the TRAINING token.
    """)
    return


@app.cell
def _(POLARIS, TRAINING_AUTH, TRAINING_CATALOG, catalog_status, requests, show_status):
    _resp = requests.post(
        f"{POLARIS}/api/catalog/v1/{TRAINING_CATALOG}/namespaces",
        headers=TRAINING_AUTH,
        json={"namespace": ["sandbox"]},
    )
    namespace_status = _resp.status_code
    show_status("Create namespace sandbox", _resp)
    return (namespace_status,)


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 8 — Verify cross-realm isolation

    Three probes, each crossing the realm boundary in a different way.
    """)
    return


@app.cell
def _(POLARIS, POLARIS_AUTH, TRAINING_AUTH, namespace_status, requests):
    # 1. Can the POLARIS realm see the new TRAINING catalog?
    polaris_view = requests.get(f"{POLARIS}/api/management/v1/catalogs", headers=POLARIS_AUTH).json()

    # 2. POLARIS token, but the TRAINING realm header
    polaris_token_in_training = requests.get(
        f"{POLARIS}/api/management/v1/catalogs",
        headers={**POLARIS_AUTH, "Polaris-Realm": "TRAINING"},
    )

    # 3. TRAINING token, but listing POLARIS principals
    training_token_in_polaris = requests.get(
        f"{POLARIS}/api/management/v1/principals",
        headers={**TRAINING_AUTH, "Polaris-Realm": "POLARIS"},
    )
    return polaris_token_in_training, polaris_view, training_token_in_polaris


@app.cell(hide_code=True)
def _(
    TRAINING_CATALOG,
    error_message,
    mo,
    polaris_token_in_training,
    polaris_view,
    training_token_in_polaris,
):
    _names = [c["name"] for c in polaris_view.get("catalogs", [])]
    _hidden = TRAINING_CATALOG not in _names

    def _denied(title, resp):
        return mo.callout(
            mo.md(f"**{title}** → HTTP **{resp.status_code}**\n\n> {error_message(resp)[:160]}"),
            kind="success" if resp.status_code in (401, 403) else "danger",
        )

    mo.vstack(
        [
            mo.callout(
                mo.md(
                    f"**1 · POLARIS realm lists:** {', '.join(f'`{n}`' for n in _names)} — "
                    f"`{TRAINING_CATALOG}` visible: **{not _hidden}**"
                ),
                kind="success" if _hidden else "danger",
            ),
            mo.hstack(
                [
                    _denied("2 · POLARIS token + `Polaris-Realm: TRAINING`", polaris_token_in_training),
                    _denied("3 · TRAINING token + `Polaris-Realm: POLARIS`", training_token_in_polaris),
                ],
                widths="equal",
                align="start",
            ),
            mo.md("Tokens are realm-scoped: a token from one realm fails verification in the other, so both calls are rejected with an authentication error."),
        ]
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ### Every token × every realm header

    The full matrix: which combinations of token and `Polaris-Realm` header can list catalogs?
    """)
    return


@app.cell(hide_code=True)
def _(POLARIS, POLARIS_TOKEN, TRAINING_TOKEN, mo, pd, requests):
    _rows = []
    for _tname, _tok in (("POLARIS token", POLARIS_TOKEN), ("TRAINING token", TRAINING_TOKEN)):
        _row = {"Token": _tname}
        for _realm in ("POLARIS", "TRAINING"):
            _code = requests.get(
                f"{POLARIS}/api/management/v1/catalogs",
                headers={"Authorization": f"Bearer {_tok}", "Polaris-Realm": _realm},
            ).status_code
            _row[f"Header: {_realm}"] = f"allowed ({_code})" if _code == 200 else f"REJECTED ({_code})"
        _rows.append(_row)
    mo.ui.table(pd.DataFrame(_rows), selection=None, show_column_summaries=False)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 9 — Build RBAC in the TRAINING realm

    A minimal role structure, built exactly like Labs 5 and 6 but entirely inside `TRAINING`:
    a principal role, a catalog role, a namespace-level `TABLE_LIST` grant, and the link between them.
    """)
    return


@app.cell(hide_code=True)
def _(mo):
    mo.mermaid(
        """
        flowchart LR
            PR["Principal role<br/>lab7_student_role"] --> CR["Catalog role<br/>lab7_sandbox_reader"]
            CR --> G["TABLE_LIST<br/>namespace sandbox"]
            G --> C[("lab7_training_catalog<br/>realm TRAINING")]
        """
    )
    return


@app.cell
def _(
    POLARIS,
    SANDBOX_READER,
    STUDENT_ROLE,
    TRAINING_AUTH,
    TRAINING_CATALOG,
    namespace_status,
    requests,
):
    # Create a principal role
    _r1 = requests.post(
        f"{POLARIS}/api/management/v1/principal-roles",
        headers=TRAINING_AUTH,
        json={"principalRole": {"name": STUDENT_ROLE, "properties": {}}},
    )

    # Create a catalog role with read access
    _r2 = requests.post(
        f"{POLARIS}/api/management/v1/catalogs/{TRAINING_CATALOG}/catalog-roles",
        headers=TRAINING_AUTH,
        json={"catalogRole": {"name": SANDBOX_READER, "properties": {}}},
    )

    # Grant namespace-level TABLE_LIST on sandbox
    _r3 = requests.put(
        f"{POLARIS}/api/management/v1/catalogs/{TRAINING_CATALOG}/catalog-roles/{SANDBOX_READER}/grants",
        headers=TRAINING_AUTH,
        json={"grant": {"type": "namespace", "privilege": "TABLE_LIST", "namespace": ["sandbox"]}},
    )

    # Assign the catalog role to the principal role
    _r4 = requests.put(
        f"{POLARIS}/api/management/v1/principal-roles/{STUDENT_ROLE}/catalog-roles/{TRAINING_CATALOG}",
        headers=TRAINING_AUTH,
        json={"catalogRole": {"name": SANDBOX_READER}},
    )

    rbac_steps = [
        (f"Create principal role {STUDENT_ROLE}", _r1.status_code),
        (f"Create catalog role {SANDBOX_READER}", _r2.status_code),
        ("Grant TABLE_LIST on sandbox", _r3.status_code),
        (f"Assign {SANDBOX_READER} → {STUDENT_ROLE}", _r4.status_code),
    ]
    return (rbac_steps,)


@app.cell(hide_code=True)
def _(mo, pd, rbac_steps, status_note):
    mo.ui.table(
        pd.DataFrame([{"Step": s, "HTTP": c, "Outcome": status_note(c)} for s, c in rbac_steps]),
        selection=None,
        show_column_summaries=False,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    mo.md("""
    ---
    ## Step 10 — Compare both realms side by side

    The same three listings against each realm.
    """)
    return


@app.cell
def _(POLARIS, POLARIS_AUTH, TRAINING_AUTH, rbac_steps, requests):
    def realm_summary(auth):
        _base = f"{POLARIS}/api/management/v1"
        _catalogs = [c["name"] for c in requests.get(f"{_base}/catalogs", headers=auth).json().get("catalogs", [])]
        return {
            "Catalogs": _catalogs,
            "Principals": [p["name"] for p in requests.get(f"{_base}/principals", headers=auth).json().get("principals", [])],
            "Principal roles": [r["name"] for r in requests.get(f"{_base}/principal-roles", headers=auth).json().get("roles", [])],
            "Catalog roles": [
                f"{c}.{r['name']}"
                for c in _catalogs
                for r in requests.get(f"{_base}/catalogs/{c}/catalog-roles", headers=auth).json().get("roles", [])
            ],
        }

    comparison = {"POLARIS": realm_summary(POLARIS_AUTH), "TRAINING": realm_summary(TRAINING_AUTH)}
    return (comparison,)


@app.cell(hide_code=True)
def _(comparison, mo):
    def _panel(realm):
        _s = comparison[realm]
        return mo.vstack(
            [
                mo.md(f"### Realm `{realm}`"),
                mo.hstack(
                    [mo.stat(len(v), label=k, bordered=True) for k, v in _s.items()],
                    widths="equal",
                ),
                mo.md("\n\n".join(f"**{k}:** " + (", ".join(f"`{x}`" for x in v) or "_none_") for k, v in _s.items())),
            ]
        )

    _shared = set(comparison["POLARIS"]["Catalogs"]) & set(comparison["TRAINING"]["Catalogs"])
    mo.vstack(
        [
            mo.hstack([_panel("POLARIS"), _panel("TRAINING")], widths="equal", align="start"),
            mo.callout(
                mo.md(
                    "Each realm has its own completely independent set of catalogs, roles and principals. "
                    f"Catalogs visible in both realms: **{len(_shared)}**. Even the built-in `service_admin` role and the "
                    "`root` principal exist separately in each realm."
                ),
                kind="success" if not _shared else "warn",
            ),
        ]
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
            "Key takeaways": mo.md(
                """
                1. A realm is the top-level partition: catalogs, principals, roles and grants all live inside one
                2. The `Polaris-Realm` header selects the realm; tokens only verify in the realm that issued them
                3. Each realm has its own bootstrap admin (`REALM,client_id,client_secret`) — even its own `root`
                4. Names can repeat across realms without conflict, because nothing is shared
                5. Realms are configured at startup (`POLARIS_REALM_CONTEXT_REALMS`) and bootstrapped once
                """
            ),
            "Exercises": mo.md(
                """
                1. **Create a new principal** called `student_1` in the TRAINING realm. Get a token for `student_1`
                   and verify it can only see `training_catalog`.
                2. **Try cross-realm access** — use `student_1`'s token with `Polaris-Realm: POLARIS`.
                   Document the exact error response you receive.
                3. **Create a second catalog** called `exam_catalog` in the TRAINING realm. Verify it's invisible from the POLARIS realm.
                4. **Challenge:** write a function (or a bash script) that takes a realm name and prints a summary of all
                   catalogs, principal roles and catalog roles in that realm. Test it with both `POLARIS` and `TRAINING`.
                   (`realm_summary()` in Step 10 is a starting point.)
                5. **Discussion:** in a SaaS scenario, each customer gets a realm. What are the advantages of realm-level
                   isolation over separate catalogs within the same realm? When would you choose one over the other?
                """
            ),
            "Next lab": mo.md("**Lab 8 — Observability:** traces, metrics and logs for Trino and Polaris."),
        },
        multiple=True,
    )
    return


@app.cell(hide_code=True)
def _(mo):
    reset_button = mo.ui.run_button(label="Delete this lab's TRAINING objects", kind="danger")
    mo.vstack(
        [
            mo.md("""
            ### Optional — reset the TRAINING realm

            Re-running the notebook is safe as it is (creates return **409** and are skipped). To see Step 5 return an
            **empty** TRAINING realm again, delete the objects this lab created. Nothing in the POLARIS realm is touched.
            """),
            reset_button,
        ]
    )
    return (reset_button,)


@app.cell
def _(
    POLARIS,
    SANDBOX_READER,
    STUDENT_ROLE,
    TRAINING_CATALOG,
    comparison,
    mo,
    pd,
    realm_admin_token,
    requests,
    reset_button,
):
    mo.stop(not reset_button.value)

    _auth = {"Authorization": f"Bearer {realm_admin_token('TRAINING')}", "Polaris-Realm": "TRAINING"}
    _m = f"{POLARIS}/api/management/v1"
    # A catalog can only be dropped when it is empty: namespace and custom catalog roles first.
    _cleanup = [
        ("Namespace sandbox", f"{POLARIS}/api/catalog/v1/{TRAINING_CATALOG}/namespaces/sandbox"),
        (f"Catalog role {SANDBOX_READER}", f"{_m}/catalogs/{TRAINING_CATALOG}/catalog-roles/{SANDBOX_READER}"),
        (f"Principal role {STUDENT_ROLE}", f"{_m}/principal-roles/{STUDENT_ROLE}"),
        (f"Catalog {TRAINING_CATALOG}", f"{_m}/catalogs/{TRAINING_CATALOG}"),
    ]
    mo.ui.table(
        pd.DataFrame([{"Deleted": _label, "HTTP": requests.delete(_url, headers=_auth).status_code} for _label, _url in _cleanup]),
        selection=None,
        show_column_summaries=False,
    )
    return


if __name__ == "__main__":
    app.run()
