FROM nginx:1.28-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY web/dist/ /usr/share/nginx/html/
EXPOSE 80
