#!/bin/bash
# =============================================================================
# Secure Customer Service Agent - Environment Setup
# =============================================================================
# This script sets up everything needed for the codelab:
# - Enables required Google Cloud APIs
# - Creates BigQuery datasets and tables
# - Seeds sample data
# - Creates environment configuration file
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get project ID
PROJECT_ID=$(gcloud config get-value project 2>/dev/null)
if [ -z "$PROJECT_ID" ]; then
    echo -e "${RED}❌ Error: No Google Cloud project set.${NC}"
    echo "   Run: gcloud config set project YOUR_PROJECT_ID"
    exit 1
fi

echo -e "${BLUE}=================================================================${NC}"
echo -e "${BLUE}   Secure Customer Service Agent - Environment Setup${NC}"
echo -e "${BLUE}=================================================================${NC}"
echo ""
echo -e "   Project: ${GREEN}$PROJECT_ID${NC}"
echo ""

# Get the directory where this script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_DIR="$(dirname "$SCRIPT_DIR")"

# -----------------------------------------------------------------------------
# Step 1: Check and Enable Billing
# -----------------------------------------------------------------------------
echo -e "${YELLOW}💳 Step 1: Checking billing configuration...${NC}"

if ! python3 "${SCRIPT_DIR}/billing_enablement.py"; then
    echo ""
    echo -e "${RED}Billing setup incomplete. Please configure billing and try again.${NC}"
    exit 1
fi

echo ""

# -----------------------------------------------------------------------------
# Step 2: Enable Required APIs
# -----------------------------------------------------------------------------
echo -e "${YELLOW}📦 Step 2: Enabling required Google Cloud APIs...${NC}"

REQUIRED_APIS=(
    "aiplatform.googleapis.com"
    "bigquery.googleapis.com" 
    "modelarmor.googleapis.com"
    "storage.googleapis.com"
    "cloudresourcemanager.googleapis.com"
    "telemetry.googleapis.com"
)

for API in "${REQUIRED_APIS[@]}"; do
    if gcloud services list --enabled --filter="name:${API}" --format="value(name)" 2>/dev/null | grep -q "${API}"; then
        echo -e "   ${GREEN}✓${NC} ${API} (already enabled)"
    else
        echo -e "   ${YELLOW}→${NC} Enabling ${API}..."
        gcloud services enable "${API}" --quiet
        echo -e "   ${GREEN}✓${NC} ${API}"
    fi
done

echo ""

# -----------------------------------------------------------------------------
# Step 3: Enable MCP for BigQuery
# -----------------------------------------------------------------------------
echo -e "${YELLOW}🔌 Step 3: Enabling MCP for BigQuery...${NC}"

# Check if MCP is already enabled
if gcloud beta services mcp list --enabled --format="value(name.basename())" 2>/dev/null | grep -q "bigquery.googleapis.com"; then
    echo -e "   ${GREEN}✓${NC} BigQuery MCP already enabled"
else
    echo -e "   ${YELLOW}→${NC} Enabling BigQuery MCP..."
    gcloud beta services mcp enable bigquery.googleapis.com --quiet 2>/dev/null || {
        echo -e "   ${YELLOW}⚠${NC} MCP enable command not available, skipping..."
    }
fi

echo ""

# -----------------------------------------------------------------------------
# Step 4: Set Location
# -----------------------------------------------------------------------------
LOCATION="us-central1"
echo -e "${YELLOW}📍 Step 4: Setting location to ${LOCATION}...${NC}"
echo ""

# -----------------------------------------------------------------------------
# Step 5: Create BigQuery Datasets
# -----------------------------------------------------------------------------
echo -e "${YELLOW}🗄️ Step 5: Creating BigQuery datasets...${NC}"

# Customer service dataset (agent CAN access)
if bq show --dataset "${PROJECT_ID}:customer_service" >/dev/null 2>&1; then
    echo -e "   ${GREEN}✓${NC} Dataset 'customer_service' already exists"
else
    echo -e "   ${YELLOW}→${NC} Creating dataset 'customer_service'..."
    bq mk --location=US --dataset \
        --description="Customer service data - accessible by the agent" \
        "${PROJECT_ID}:customer_service"
    echo -e "   ${GREEN}✓${NC} Dataset 'customer_service' created"
fi

# Admin dataset (agent CANNOT access - for demonstrating Agent Identity)
if bq show --dataset "${PROJECT_ID}:admin" >/dev/null 2>&1; then
    echo -e "   ${GREEN}✓${NC} Dataset 'admin' already exists"
else
    echo -e "   ${YELLOW}→${NC} Creating dataset 'admin'..."
    bq mk --location=US --dataset \
        --description="Administrative data - NOT accessible by the agent" \
        "${PROJECT_ID}:admin"
    echo -e "   ${GREEN}✓${NC} Dataset 'admin' created"
fi

echo ""

# -----------------------------------------------------------------------------
# Step 6: Create Tables and Load Data
# -----------------------------------------------------------------------------
echo -e "${YELLOW}📊 Step 6: Creating tables and loading sample data...${NC}"

# Run Python script to create tables and load data
python3 "${SCRIPT_DIR}/setup_bigquery.py"

echo ""

# -----------------------------------------------------------------------------
# Step 7: Create Environment File
# -----------------------------------------------------------------------------
echo -e "${YELLOW}⚙️ Step 7: Creating environment configuration...${NC}"

ENV_FILE="${REPO_DIR}/set_env.sh"

cat > "$ENV_FILE" << EOF
#!/bin/bash
# =============================================================================
# Secure Customer Service Agent - Environment Variables
# Generated: $(date)
# =============================================================================

export GOOGLE_CLOUD_PROJECT="${PROJECT_ID}"
export GOOGLE_CLOUD_LOCATION="${LOCATION}"
export PROJECT_ID="${PROJECT_ID}"
export LOCATION="${LOCATION}"

# Required for ADK to use Vertex AI backend
export GOOGLE_GENAI_USE_VERTEXAI="true"

# BigQuery datasets
export BQ_CUSTOMER_DATASET="customer_service"
export BQ_ADMIN_DATASET="admin"

# Model Armor template (will be set after running create_template.py)
export TEMPLATE_NAME=""

# Agent Engine (will be set after deployment)
export AGENT_ENGINE_ID=""

# Staging bucket for deployment
export STAGING_BUCKET="gs://secure-cs-agent-staging-${PROJECT_ID}"

echo "✅ Environment variables loaded for project: \${PROJECT_ID}"
EOF

chmod +x "$ENV_FILE"
echo -e "   ${GREEN}✓${NC} Created ${ENV_FILE}"

echo ""

# -----------------------------------------------------------------------------
# Step 8: Create Staging Bucket
# -----------------------------------------------------------------------------
echo -e "${YELLOW}🪣 Step 8: Creating staging bucket for deployment...${NC}"

BUCKET_NAME="secure-cs-agent-staging-${PROJECT_ID}"
if gsutil ls -b "gs://${BUCKET_NAME}" >/dev/null 2>&1; then
    echo -e "   ${GREEN}✓${NC} Staging bucket already exists"
else
    echo -e "   ${YELLOW}→${NC} Creating staging bucket..."
    gsutil mb -p "$PROJECT_ID" -l "$LOCATION" "gs://${BUCKET_NAME}"
    echo -e "   ${GREEN}✓${NC} Staging bucket created: gs://${BUCKET_NAME}"
fi

echo ""

# -----------------------------------------------------------------------------
# Complete!
# -----------------------------------------------------------------------------
echo -e "${GREEN}=================================================================${NC}"
echo -e "${GREEN}   ✅ Setup Complete!${NC}"
echo -e "${GREEN}=================================================================${NC}"
