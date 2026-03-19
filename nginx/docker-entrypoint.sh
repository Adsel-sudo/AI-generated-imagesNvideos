#!/bin/sh
set -eu

HTPASSWD_FILE="/etc/nginx/.htpasswd"

if [ -z "${BASIC_AUTH_USER:-}" ]; then
  echo "ERROR: BASIC_AUTH_USER is not set." >&2
  exit 1
fi

if [ -z "${BASIC_AUTH_PASSWORD:-}" ]; then
  echo "ERROR: BASIC_AUTH_PASSWORD is not set." >&2
  exit 1
fi

htpasswd -bc "$HTPASSWD_FILE" "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD"

echo "Generated Basic Auth credentials at $HTPASSWD_FILE for user '$BASIC_AUTH_USER'."