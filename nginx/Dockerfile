FROM nginx:1.27-alpine

RUN apk add --no-cache apache2-utils

COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/docker-entrypoint.sh /docker-entrypoint.d/10-generate-htpasswd.sh

RUN chmod +x /docker-entrypoint.d/10-generate-htpasswd.sh
