FROM nginx:1.27-alpine

# Install utilities for managing basic authentication.
RUN apk add --no-cache apache2-utils

# Remove default site content.
RUN rm -rf /usr/share/nginx/html/*

# Copy custom nginx configuration and auth placeholder.
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/auth.conf /etc/nginx/conf.d/auth.conf

# Copy startup script that wires basic auth at runtime.
COPY nginx/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# Copy static site assets into the nginx web root.
COPY . /usr/share/nginx/html/
RUN rm -rf /usr/share/nginx/html/nginx

# Start nginx via the custom entrypoint (handles auth + Cloud Run integration).
CMD ["/docker-entrypoint.sh"]
