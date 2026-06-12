#!/usr/bin/env bash
# Deploy the Auth0-gated Chainlit UI to Cloud Run. It calls the deployed agent on Agent
# Engine and orchestrates Agent Identity OBO consent. Idempotent. Modeled on
# mcp-toolbox/scripts/06_deploy_agent.sh.
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-project-4382e8df-acc3-437e-9e7}"
REGION="${REGION:-us-central1}"
SERVICE="${SERVICE:-obo-chainlit}"
SA_EMAIL="chainlit-app-sa@${PROJECT_ID}.iam.gserviceaccount.com"
AGENT_ENGINE_ID="${AGENT_ENGINE_ID:-884190417417928704}"
OBO_CONNECTOR="projects/${PROJECT_ID}/locations/${REGION}/connectors/bigquery-3lo"

# Reuse the mcp-toolbox Auth0 app + secrets (same GCP project).
AUTH0_CLIENT_ID="${AUTH0_CLIENT_ID:-fJta0a1DB3itvmmo3bddufnZDnfzSlGK}"
AUTH0_DOMAIN="${AUTH0_DOMAIN:-dev-6d1lsgbv5w63zkmo.us.auth0.com}"
SECRET_AUTH0="auth0-client-secret"
SECRET_CHAINLIT="chainlit-auth-secret"

cd "$(dirname "$0")"

gcloud run deploy "$SERVICE" --quiet \
  --source . --region "$REGION" --project "$PROJECT_ID" \
  --service-account "$SA_EMAIL" \
  --allow-unauthenticated --min-instances=1 --max-instances=1 \
  --set-env-vars="^##^GOOGLE_CLOUD_PROJECT=${PROJECT_ID}##GOOGLE_CLOUD_LOCATION=${REGION}##AGENT_ENGINE_ID=${AGENT_ENGINE_ID}##OBO_CONNECTOR=${OBO_CONNECTOR}##OBO_SCOPE=https://www.googleapis.com/auth/bigquery##OAUTH_AUTH0_CLIENT_ID=${AUTH0_CLIENT_ID}##OAUTH_AUTH0_DOMAIN=${AUTH0_DOMAIN}" \
  --set-secrets="OAUTH_AUTH0_CLIENT_SECRET=${SECRET_AUTH0}:latest,CHAINLIT_AUTH_SECRET=${SECRET_CHAINLIT}:latest"

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" --format='value(status.url)')"

# Point the app at its own public URL (continue_uri base + Chainlit redirect) and pin sessions.
gcloud run services update "$SERVICE" --region "$REGION" --project "$PROJECT_ID" --quiet \
  --update-env-vars="APP_BASE_URL=${URL},CHAINLIT_URL=${URL}" --session-affinity >/dev/null

echo "Deployed: ${URL}"
echo "Register these on the Auth0 application:"
echo "   Allowed Callback URL:  ${URL}/auth/oauth/auth0/callback"
echo "Data-consent callback (continue_uri, no Auth0 change needed): ${URL}/oauth/callback"
