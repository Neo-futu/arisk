#!/usr/bin/env bash
# 進入 arisk 的 bl-dev 聯調 shell（dev 雲庫零入口端口轉發 + RDS IAM）。
# 參照 ideclare/scripts/bl-dev.sh；arisk 用自有庫，app 名為 arisk。
set -euo pipefail

PROFILE="DevDataDebugPermissionSet-078682762287"
REGION=""
LOGIN=0

usage() {
  cat >&2 <<EOF
usage: scripts/bl-dev.sh [--profile <aws-profile>] [--region <region>] [--login]

  --profile   AWS profile (default: $PROFILE)
  --region    AWS region (default: bl-dev 默认 ap-east-1)
  --login     先執行 'aws sso login'
EOF
  exit "${1:-0}"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --profile) PROFILE="${2:?--profile requires a value}"; shift 2 ;;
    --region)  REGION="${2:?--region requires a value}";  shift 2 ;;
    --login)   LOGIN=1; shift ;;
    --help|-h) usage 0 ;;
    *) echo "unknown option: $1" >&2; usage 2 ;;
  esac
done

if [ "$LOGIN" -eq 1 ]; then
  echo "==> aws sso login --profile $PROFILE"
  aws sso login --profile "$PROFILE"
fi

CMD=(bl-dev --profile "$PROFILE")
[ -n "$REGION" ] && CMD+=(--region "$REGION")
CMD+=(shell arisk)

echo "==> ${CMD[*]}"
exec "${CMD[@]}"
