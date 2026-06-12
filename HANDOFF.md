# Agent Identity + Agent Engine + Agent Gateway — Handoff & Reproduction Runbook

You are picking up an exploration that builds a **reusable architectural stamp** for enterprise agentic
apps on Google Cloud. This file is self-contained: it explains what exists, why, the exact commands to
reproduce it in a fresh project, every hard-won gotcha, and how to finish the one piece that's blocked.

---

## 0. Guiding principle (read first — it shapes every decision)

**Cloud-native first. No reinvention.** The goal is to use the *advertised* platform capabilities
(Agent Identity, Agent Engine, Agent Gateway, Agent Registry bindings, gateway-brokered OBO, gateway
Model Armor) and **see them work**. Do **not** hand-roll a parallel implementation because the native
path was hard. Earlier in this project several things were hand-built and then **replaced by the native
equivalent** once understood. When a native capability doesn't work: **investigate it (docs/config/
support) and make it work, or document a genuine preview gap and pause** — never silently substitute a
workaround to "get to the finish line." This is exploration for a stamp many teams will reuse, not a
deadline sprint. Destructive/irreversible steps (deleting an engine, flipping a gateway to ENFORCE)
happen **only after** the new path is verified, keeping a fallback until then.

---

## 1. What this is (architecture)

An employee signs into a chat app and asks BigQuery questions; the agent answers **as that user**
(their own BigQuery access), governed end-to-end by the platform.

```
Employee (browser)
  → Auth0  (identity only — who you are; no data access)
  → Chainlit app  (Cloud Run; UI + drives the consent lifecycle)
  → Agent Engine runtime  (the agent; its own Agent Identity = SPIFFE/X.509, cert-bound mTLS tokens)
  → [Agent Gateway]  (egress governance: default-deny IAM, Model Armor, per-tool policy, audit)
  → BigQuery MCP server  (native Google MCP and/or self-hosted Toolbox MCP)
  → BigQuery  (queried AS the consenting user via on-behalf-of 3LO token from the managed vault)
```

Two trust domains, deliberately separate: **Auth0 = identity**, **Google 3LO connector + managed
credential vault = data**. The Auth0 `sub` is the `user_id` that keys the vault. The agent and the
vault hold the user's BigQuery token; **the app never does**.

The "stamp" demonstrates **Agent Identity + Agent Engine + Agent Gateway together**, with two
interchangeable BigQuery MCP backends switchable from the UI for a side-by-side comparison.

---

## 2. Current status

| Piece | State |
|---|---|
| BigQuery datasets + per-user access (the demo) | ✅ done |
| Model Armor template (for the original in-code guard) | ✅ done |
| Agent Identity OBO 3LO → BigQuery, **verified per-user** | ✅ working on engine `884190417417928704` |
| Auth0-gated Chainlit app on Cloud Run (consent lifecycle: connect/disconnect/re-prompt) | ✅ deployed |
| Agent Gateway egress gateway, Agent Registry, MCP server + binding | ✅ created (gateway-native pattern proven) |
| `agent_gw/` gateway-native agent code (registry toolsets, 2 backends, zero auth code) | ✅ built, validated locally |
| **Engine ↔ Agent Gateway attach** | ❌ **BLOCKED** — needs a separate project early-access activation (see §7) |

**Verified demo:** signed in as `behbooei@gmail.com` the agent reads `demo_finance.revenue` (allowed)
but not `demo_marketing.campaigns` (403); as `mr.behbooei@gmail.com` the mirror. Same agent, opposite
access — proving access follows the consenting human.

---

## 3. Repo map

| Path | What it is |
|---|---|
| `agent/` | The deployed agent (codelab base): Model Armor guard, BigQuery MCP tool, OBO tool. |
| `agent/tools/obo_bigquery_tools.py` | On-behalf-of-user BigQuery tool + `_FreshClientGcpAuthProvider` (pyOpenSSL fix). |
| `scripts/test_obo_agent.py` | CLI that drives the 3LO consent round-trip and verifies per-user access. |
| `obo_callback/` | Cloud Run service hosting the 3LO `continue_uri` (`credentials:finalize`). Superseded by the Chainlit `/oauth/callback` route but kept as reference. |
| `chainlit_app/` | **The app**: Auth0 login, calls Agent Engine, connector consent lifecycle, `/oauth/callback`. |
| `agent_gw/` | **The gateway-native stamp**: plain Agent Registry-resolved MCP toolsets, two switchable backends, no auth/guard code. Deploy this once the gateway attach is activated. |
| `deploy.py`, `set_env.sh` | Original OBO engine deploy + env (env is gitignored). |
| `setup/` | Codelab setup scripts (BigQuery, Model Armor template). |

`*.env`, `set_env.sh` are gitignored — recreate them from `.env.example` files and the values below.

---

## 4. Reference environment (OUR values — replace for your project)

The receiving project is different; treat these as the example to mirror. Set as env vars up front:

```bash
export PROJECT_ID=project-4382e8df-acc3-437e-9e7     # -> your project
export REGION=us-central1
export ORG_ID=807464006833                            # -> your org (agent-identity principals)
# Two test users with asymmetric dataset access (use accounts you control):
#   behbooei@gmail.com     -> READER on demo_finance.revenue
#   mr.behbooei@gmail.com  -> READER on demo_marketing.campaigns
```

Existing named resources in our project (you will recreate equivalents):
- Connectors (3LO auth providers): `bigquery-3lo` (allowed scope `.../auth/bigquery`), `min3lo`.
- OAuth client (Web app), used by the connector: `498952340824-9cae8li92in7lcjno2ftjpcqa309hk0k`.
- Egress gateway: `agw-egress` (`AGENT_TO_ANYWHERE`, protocols MCP).
- Registry MCP server: `toolbox-mcp` → `https://toolbox-xj5hg43iaa-uc.a.run.app/mcp` (self-hosted
  MCP Toolbox, `useClientOAuth: true`). Native Google MCP = `https://bigquery.googleapis.com/mcp`.
- Agent Engine (OBO, no gateway): `884190417417928704`.
- Chainlit service: `https://obo-chainlit-xj5hg43iaa-uc.a.run.app` (Auth0 callback
  `…/auth/oauth/auth0/callback`, data-consent callback `…/oauth/callback`).
- Auth0: tenant `dev-6d1lsgbv5w63zkmo.us.auth0.com`, client `fJta0a1DB3itvmmo3bddufnZDnfzSlGK`
  (reused from a sibling `mcp-toolbox` project). Secrets in Secret Manager: `auth0-client-secret`,
  `chainlit-auth-secret`.
- Service accounts: `obo-callback-sa@…`, `chainlit-app-sa@…`. Custom role:
  `projects/$PROJECT_ID/roles/obo_connector_app` (retrieveCredentials + revokeAuthorizations + authorizations.get/list).

---

## 5. Prerequisites

1. `gcloud` authed; `gcloud config set project $PROJECT_ID`. Python venv with the repo `requirements`.
2. Enable APIs: `aiplatform, bigquery, modelarmor, storage, cloudresourcemanager, iam,
   iamcredentials, iamconnectors, iamconnectorcredentials, run, cloudbuild, secretmanager,
   agentregistry, networksecurity, networkservices, dns, compute, logging, monitoring, cloudtrace`.
3. **Two distinct early-access allowlists** (this is the crux for the gateway work):
   - **Agent Gateway** preview — lets you create gateways/registry/bindings.
   - **Agent Engine ↔ Agent Gateway integration** — lets you *attach* an engine to a gateway. **This is
     the one we lack.** Without it the attach returns `400 FAILED_PRECONDITION: Agent Engine integration
     with Agent Gateway requires additional early-access activation for this Google Cloud project.`
   Request both via the Agent Gateway preview form / your Google account team.
4. An Auth0 tenant + a Regular Web App (client id/secret). Add the Chainlit callback URL after deploy.

---

## 6. Reproduction runbook

### Phase A — BigQuery demo data + per-user access
- Create datasets `demo_finance` (table `revenue`) and `demo_marketing` (table `campaigns`); seed a few
  rows. Grant dataset-level **READER** ACLs: `behbooei@gmail.com` on `demo_finance`,
  `mr.behbooei@gmail.com` on `demo_marketing`. (Dataset ACLs, not project IAM — `tabledata.list` then
  needs no `jobUser`.) The codelab `customer_service`/`admin` datasets (`setup/setup_bigquery.py`) are
  optional for the OBO demo.

### Phase B — Agent Identity OBO engine (the working baseline)
1. **OAuth client** (Console → APIs & Services → Credentials → OAuth client ID → Web application).
   Consent screen External/Testing; add the two test users; scope `.../auth/bigquery`. Note that
   **Testing-mode refresh tokens expire ~7 days** (re-consent needed; the app re-prompts gracefully).
2. **3LO connector** (the OBO broker):
   ```bash
   gcloud alpha agent-identity connectors create bigquery-3lo --location=$REGION \
     --three-legged-oauth-authorization-url="https://accounts.google.com/o/oauth2/v2/auth" \
     --three-legged-oauth-token-url="https://oauth2.googleapis.com/token" \
     --three-legged-oauth-client-id=CLIENT_ID --three-legged-oauth-client-secret=CLIENT_SECRET \
     --allowed-scopes="https://www.googleapis.com/auth/bigquery"
   gcloud alpha agent-identity connectors describe bigquery-3lo --location=$REGION  # -> redirectUrl
   ```
   Add that `redirectUrl` to the OAuth client's Authorized redirect URIs.
3. **Engine shell with Agent Identity** (Python: `vertexai.Client(..., http_options=dict(api_version="v1beta1"))`
   then `client.agent_engines.create(config={"identity_type": types.IdentityType.AGENT_IDENTITY, "display_name": ...})`).
   See `deploy.py` for the full flow incl. baseline IAM.
4. **Baseline IAM** to the engine's Agent Identity principal
   (`principal://agents.global.org-$ORG_ID.system.id.goog/resources/aiplatform/projects/$PROJECT_NUMBER/locations/$REGION/reasoningEngines/$ENGINE_ID`):
   `serviceusage.serviceUsageConsumer, aiplatform.expressUser, browser, iamconnectors.user,
   mcp.toolUser, bigquery.jobUser`, plus **conditional** `bigquery.dataViewer` if you also want the
   agent-as-itself path (`resource.name.startsWith('projects/$PROJECT_ID/datasets/customer_service')`).
5. **Deploy code**: `adk deploy agent_engine --project $PROJECT_ID --region $REGION
   --agent_engine_id $ENGINE_ID --env_file agent/.env agent`.
6. **Verify**: `python scripts/test_obo_agent.py initiate behbooei` → open the printed consent URL,
   consent as `behbooei@gmail.com` → `python scripts/test_obo_agent.py resume behbooei`.

### Phase C — Auth0-gated Chainlit app (Cloud Run)
- `chainlit_app/` calls Agent Engine `stream_query` and orchestrates consent via the connector
  (`connector_client.py` → `credentials:{retrieve,finalize}`; `/oauth/callback` route is the
  `continue_uri`). Dedicated SA `chainlit-app-sa` with `roles/aiplatform.user` + the custom
  `obo_connector_app` role + Secret Manager access to the two secrets.
- Deploy: `bash chainlit_app/deploy.sh` (source build, `--allow-unauthenticated`, Auth0 env + secrets,
  `--min-instances=1 --max-instances=1`, then sets `APP_BASE_URL`/`CHAINLIT_URL` + `--session-affinity`).
- Register `<cloud-run-url>/auth/oauth/auth0/callback` in the Auth0 app's Allowed Callback URLs.

### Phase D — Agent Gateway (the cloud-native target, "beyond")
Requires the **Agent Engine ↔ Agent Gateway integration** activation (§7). Steps:
1. **Gateways** (egress + ingress) via `gcloud alpha network-services agent-gateways import` from YAML
   (`protocols: [MCP]`, `googleManaged.governedAccessPath: AGENT_TO_ANYWHERE` / `CLIENT_TO_AGENT`,
   `registries: [//agentregistry.googleapis.com/projects/$PROJECT_ID/locations/$REGION]`).
2. **Register MCP servers** in the Agent Registry (both backends):
   ```bash
   gcloud alpha agent-registry services create toolbox-mcp --location=$REGION \
     --display-name="Toolbox BigQuery MCP" --mcp-server-spec-type=NO_SPEC \
     --interfaces=protocolBinding=JSONRPC,url=https://<toolbox-host>/mcp
   gcloud alpha agent-registry services create native-bq-mcp --location=$REGION \
     --display-name="Native Google BigQuery MCP" --mcp-server-spec-type=NO_SPEC \
     --interfaces=protocolBinding=JSONRPC,url=https://bigquery.googleapis.com/mcp
   ```
   (The self-hosted Toolbox MCP is the `mcp-toolbox` repo's `toolbox` server with `useClientOAuth: true`,
   deployed to Cloud Run; it forwards the caller's token to BigQuery.)
3. **Create the engine attached to the gateway(s)** — the gated step. Create an identity-only shell
   (Phase B-style), then attach via `adk deploy`'s config file:
   - `agent_gw/.agent_engine_config.json` holds `{"agent_gateway_config": {"agent_to_anywhere_config":
     {"agent_gateway": ".../agentGateways/agw-egress"}, "client_to_agent_config": {"agent_gateway":
     ".../agentGateways/agw-ingress"}}}`.
   - `adk deploy agent_engine --project $PROJECT_ID --region $REGION --agent_engine_id $NEW_ID
     --env_file agent_gw/.env --agent_engine_config_file <ABSOLUTE path to a NON-dot copy of that json>
     agent_gw`  (see gotcha §8 about the path).
4. **Bindings** (per agent — create AFTER the engine exists), one per MCP server:
   ```bash
   gcloud alpha agent-registry bindings create gw-toolbox-bind --location=$REGION \
     --source-identifier="urn:agent:…:reasoningEngines:$NEW_ID" \
     --target-identifier="urn:mcp:…:services:toolbox-mcp" \
     --auth-provider-binding="projects/$PROJECT_ID/locations/$REGION/connectors/bigquery-3lo" \
     --auth-provider-binding-continue-uri="<chainlit-url>/oauth/callback" \
     --auth-provider-binding-scopes="https://www.googleapis.com/auth/bigquery,openid,email"
   # repeat for native-bq-mcp
   ```
5. **Egress IAM**: grant the new agent identity `roles/iap.egressor` on each registered MCP service
   (default-deny otherwise). Add the read-only attribute condition where wanted:
   `api.getAttribute('iap.googleapis.com/mcp.tool.isReadOnly', false) == true`.
6. **Authorization policies** targeting the gateways (IAP `REQUEST_AUTHZ` extension; Model Armor
   `CONTENT_AUTHZ` extension). Start in **DRY_RUN** (audit-only), confirm egress in the gateway's Cloud
   Audit logs, then flip to **ENFORCE**.
7. **Point Chainlit at the new engine** (`AGENT_ENGINE_ID`) and add the Native/Toolbox selector buttons
   (set `mcp_backend` session state; `agent_gw` enforces one-active via `before_tool_callback`).
8. **Decommission** the old non-gateway engine `884…` only after the gateway path fully verifies.

---

## 7. The one blocker, precisely

`agent_gateway_config` exists **only** in the `v1beta1` reasoningEngines API (GA `v1` lacks the field).
Attaching an engine to a gateway returns, at the API level (SDK, `adk`, raw REST, and Console alike):

```
400 FAILED_PRECONDITION: Agent Engine integration with Agent Gateway requires additional
early-access activation for this Google Cloud project.
```

This is a **server-side, project-level** allowlist — no client/version/UI bypasses it (verified by
direct `v1beta1` PATCH). It is **separate** from the Agent Gateway preview (which lets you create
gateways/registry/bindings — all of which succeed). **If the receiving project already has this
activation, Phase D step 3 will simply succeed** and the rest of Phase D follows. If not, request it.

---

## 8. Critical gotchas & fixes (hard-won — keep these)

- **Agent Identity needs an mTLS-capable stack.** Agent Identity uses certificate-bound tokens accepted
  only over mTLS (workload SPIFFE cert at `GOOGLE_API_CERTIFICATE_CONFIG`). The codelab's pinned
  versions predate this. Required runtime deps: `google-adk[a2a,mcp,agent-identity]==2.2.0`,
  `google-genai==2.8.0`, `google-cloud-aiplatform==1.157.0`, `google-auth==2.53.0` (≥2.46 recognizes
  the workload cert config), **`aiohttp>=3.10`** (without it google-genai uses plain TLS → 401), and
  `pyopenssl`. Set `GOOGLE_API_USE_CLIENT_CERTIFICATE=true`. Symptom if wrong: every API call from the
  deployed agent fails `401 UNAUTHENTICATED`, surfaced as "Failed to create session". Works locally
  because local runs as your user creds, not the agent identity — the 401 only appears deployed.
- **pyOpenSSL frozen-context bug.** The stock ADK `GcpAuthProvider` caches one client; its mTLS adapter
  builds one pyOpenSSL `Context` that's frozen after first use, so the *second* `retrieveCredentials`
  dies with "Context has already been used to create a Connection, it cannot be mutated again". Fix:
  subclass to return a **fresh client per call** (`agent/tools/obo_bigquery_tools.py
  _FreshClientGcpAuthProvider`). NOTE: with the gateway-native path the binding/gateway brokers OBO and
  the agent carries no auth code — this fix is only for the hand-built OBO path.
- **Disable Cloud Trace at boot** for a freshly-provisioned Agent Identity engine (the Trace
  instrumentor's Resource Manager call races identity provisioning → boot 401). `enable_tracing=False`.
- **OAuth account selection.** The connector's auth URL uses `prompt=consent`, which forces the consent
  screen but **not** account re-selection — easy to consent as the wrong already-signed-in Google
  account. Present the URL with `prompt=select_account%20consent` (+ optional `login_hint`). Use a fresh
  `user_id` per attempt while testing — once a `user_id` consents the token is vaulted and re-initiate
  won't re-prompt.
- **finalize contract.** `POST iamconnectorcredentials.googleapis.com/v1alpha/{connector}/credentials:finalize`
  with `{userId, consentNonce, userIdValidationState}`. `userIdValidationState` arrives on the redirect;
  `consentNonce` is the `oauth2.nonce` from the consent request (NOT the OAuth `state`).
- **Chainlit custom route ordering.** Chainlit's SPA catch-all shadows added routes; insert your
  `/oauth/callback` at the FRONT: `fastapi_app.router.routes.insert(0, APIRoute(...))`.
- **`adk deploy --agent_engine_config_file` path.** The deploy stages a temp copy that **drops
  dotfiles** and resolves the path oddly. Pass an **absolute path to a NON-dot** JSON file (e.g. copy
  `agent_gw/.agent_engine_config.json` to `/abs/gw_engine_config.json` and point the flag at that).
- **Native Google MCP IS registerable** as an Agent Registry service (`--mcp-server-spec-type=NO_SPEC`,
  `url=https://bigquery.googleapis.com/mcp`) — so both backends can be gateway-governed.
- **Bindings are per-agent**: `source.identifier` = the engine's reasoningEngine URN, so bindings must
  be created **after** the engine exists.
- **Native OBO pattern** (use this, not the hand-built provider): `AgentRegistry(project, location)
  .get_mcp_toolset(server_name, continue_uri=…)` auto-resolves the server's binding into a
  `GcpAuthProviderScheme` → the agent has **zero auth code**. Consent still flows via the
  `adk_request_credential` EUC event + your app's `continue_uri` (so the Chainlit consent code stays —
  that part is the documented client responsibility, not reinvention). Register the provider once:
  `CredentialManager.register_auth_provider(GcpAuthProvider())`.
- **Toolbox MCP `useClientOAuth: true`** forwards the caller's token to BigQuery → preserves per-user
  access. The MCP Toolbox is in the sibling `mcp-toolbox` repo (`tools.yaml`: `list_datasets`,
  `list_tables`, `run_sql`).
- **Ingress (Client→Agent)** is a gateway "frontend" for the agent and is documented for MCP clients
  (Cursor/Claude Code/Gemini CLI) and Gemini Enterprise; **IAP isn't used for ingress**. Whether a
  custom web backend (Chainlit) can ride ingress is unconfirmed — the client endpoint only
  materializes once an engine is attached, so resolve it empirically at deploy.

---

## 9. Verify the finished gateway stamp (Phase D done)
1. Chainlit (new engine): sign in (Auth0) → connect as `behbooei` → toggle **Native** then **Toolbox**:
   "list datasets I can read" / "select * from demo_finance.revenue" → finance allowed, marketing 403
   on **both** backends; each answer labeled with the active backend; only one backend callable.
2. `mr.behbooei` → marketing allowed, finance 403 on both.
3. Gateway audit: egress to each MCP service appears in `agw-egress` Cloud Audit logs under the new
   agent identity; an unregistered egress is denied (default-deny).
4. (After ENFORCE) a destructive/non-read-only tool call is blocked by the attribute policy.
5. Decommission `884…` only after 1–4 pass.

---

## 10. Cleanup (if abandoning an attempt)
Delete only what you created, in dependency order: bindings → registry services → ingress gateway →
engine (REST `DELETE …/v1beta1/…/reasoningEngines/$ID?force=true`) → prune that identity's stale IAM
bindings. Never delete pre-existing shared resources or the working fallback engine.
