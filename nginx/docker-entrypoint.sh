#!/bin/sh
set -eu

# Create or disable basic authentication based on provided credentials.
if [ -n "${BASIC_AUTH_USER:-}" ] && [ -n "${BASIC_AUTH_PASSWORD:-}" ]; then
    htpasswd -bc /etc/nginx/.htpasswd "$BASIC_AUTH_USER" "$BASIC_AUTH_PASSWORD" >/dev/null 2>&1
    cat <<'EOF' > /etc/nginx/conf.d/auth.conf
auth_basic "Restricted";
auth_basic_user_file /etc/nginx/.htpasswd;
EOF
    echo "Basic authentication enabled for user '$BASIC_AUTH_USER'."
else
    echo "BASIC_AUTH_USER/BASIC_AUTH_PASSWORD not set; disabling basic authentication."
    echo "auth_basic off;" > /etc/nginx/conf.d/auth.conf
fi

exec nginx -g 'daemon off;'
