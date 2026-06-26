#!/usr/bin/env bash
# 部署 Claude Managed Agent
set -euo pipefail

AGENT_NAME="${1:-risk-agent}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
AGENT_DIR="${PROJECT_ROOT}/5_deploy/agents/${AGENT_NAME}"

if [[ ! -d "$AGENT_DIR" ]]; then
  echo "Error: Agent '${AGENT_NAME}' not found at ${AGENT_DIR}"
  exit 1
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "Error: ANTHROPIC_API_KEY not set"
  exit 1
fi

echo "Deploying agent: ${AGENT_NAME}"
echo "Agent dir: ${AGENT_DIR}"

# 1. 驗證 agent.yaml
echo "→ Validating agent.yaml..."
python "${PROJECT_ROOT}/scripts/validate.py" "${AGENT_DIR}/agent.yaml"

# 2. 同步 skills（確保 agent bundle 使用最新 skills）
echo "→ Syncing skills..."
python "${PROJECT_ROOT}/scripts/sync_skills.py" "${AGENT_NAME}"

# 3. 部署 subagents（depth-1 先部署）
echo "→ Deploying subagents..."
for subagent_yaml in "${AGENT_DIR}/subagents/"*.yaml; do
  subagent_name=$(basename "${subagent_yaml}" .yaml)
  echo "  Deploying subagent: ${subagent_name}"
  python "${PROJECT_ROOT}/scripts/deploy_managed_agent.py" \
    --yaml "${subagent_yaml}" \
    --name "${AGENT_NAME}-${subagent_name}"
done

# 4. 部署主 orchestrator
echo "→ Deploying orchestrator: ${AGENT_NAME}"
python "${PROJECT_ROOT}/scripts/deploy_managed_agent.py" \
  --yaml "${AGENT_DIR}/agent.yaml" \
  --name "${AGENT_NAME}"

echo "✅ Agent '${AGENT_NAME}' deployed successfully"
