#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  scripts/protect-main-branch.sh [OWNER/REPO]

Configure the baseline main branch protection for an app repository:
  - require status check "test" to pass before merging;
  - require PR flow with stale reviews dismissed;
  - disable force-push and branch deletion.

Prerequisites:
  - GitHub CLI authenticated as a repo admin: gh auth status
  - target repository already has a main branch and .github/workflows/ci.yml
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "error: GitHub CLI (gh) is required" >&2
  exit 1
fi

repo="${1:-}"
if [[ -z "$repo" ]]; then
  repo="$(gh repo view --json nameWithOwner --jq '.nameWithOwner')"
fi

if [[ ! "$repo" =~ ^[^/]+/[^/]+$ ]]; then
  echo "error: repository must be in OWNER/REPO form, got: $repo" >&2
  exit 1
fi

gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  "repos/${repo}/branches/main/protection" \
  --input - >/dev/null <<'JSON'
{
  "required_status_checks": {
    "strict": true,
    "contexts": ["test"]
  },
  "enforce_admins": false,
  "required_pull_request_reviews": {
    "dismiss_stale_reviews": true,
    "require_code_owner_reviews": false,
    "required_approving_review_count": 0
  },
  "restrictions": null,
  "allow_force_pushes": false,
  "allow_deletions": false,
  "required_linear_history": false,
  "required_conversation_resolution": false
}
JSON

echo "Configured baseline main branch protection for ${repo}."
gh api \
  -H "Accept: application/vnd.github+json" \
  "repos/${repo}/branches/main/protection" \
  --jq '{
    required_status_checks: .required_status_checks.contexts,
    strict_status_checks: .required_status_checks.strict,
    dismiss_stale_reviews: .required_pull_request_reviews.dismiss_stale_reviews,
    required_approving_review_count: .required_pull_request_reviews.required_approving_review_count,
    allow_force_pushes: .allow_force_pushes.enabled,
    allow_deletions: .allow_deletions.enabled
  }'
