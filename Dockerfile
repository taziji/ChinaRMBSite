FROM nginx:1.27-alpine

# Remove default site content.
RUN rm -rf /usr/share/nginx/html/*

# Copy custom nginx configuration (listens on Cloud Run's default port 8080).
COPY nginx/default.conf /etc/nginx/conf.d/default.conf

# Copy static site assets into the nginx web root.
COPY . /usr/share/nginx/html/
RUN rm -rf /usr/share/nginx/html/nginx

# Use a simple start script to honour the $PORT environment variable if Google changes it.
CMD ["/bin/sh", "-c", "sed -i \"s/\\$PORT/${PORT:-8080}/g\" /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
