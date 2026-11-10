#!/bin/sh
# No arbitrary remote command substitution or implicit apply.
set -eu
[ "$#" -eq 1 ] || { echo 'usage: check|apply|test' >&2; exit 64; }
if [ "$1" = test ]; then
    cd /workspace/deploy/ansible
    exec molecule test -s default
fi
case "${DEPLOY_TARGET:-unset}:${DEPLOY_PROFILE:-unset}" in
  sl101-nura:nura|sl101-debian:debian) ;;
  *) echo 'missing or invalid Compose target/profile override' >&2; exit 64 ;;
esac
case "$1" in
  check) set -- --check --diff ;;
  apply)
    [ "${SL101_APPLY:-NO}" = YES ] || { echo 'apply requires SL101_APPLY=YES' >&2; exit 65; }
    set -- --diff ;;
  *) echo 'usage: check|apply' >&2; exit 64 ;;
esac
python3 /workspace/deploy/ansible/tools/render_public.py     --workspace /workspace --profile "$DEPLOY_PROFILE" --output /tmp/sl101-rendered
cd /workspace
exec ansible-playbook -i /inventory/hosts.yml deploy/ansible/playbooks/site.yml --limit "$DEPLOY_TARGET" "$@"
