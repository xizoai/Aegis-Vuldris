# syntax=docker/dockerfile:1
#
# Aegis Vuldris frontend image: build the React app, then serve the static output
# with nginx.
#
# The container serves only static assets. It has no application secrets and no
# database access; all API calls go to the backend over the internal network,
# and the browser attaches the bearer token.

# The build context is this directory, so paths are relative to it.
# ---------------------------------------------------------------- build stage
FROM node:22-alpine AS builder

WORKDIR /build

# Dependency manifests first so the install layer caches independently of source.
COPY package.json package-lock.json* ./

# `npm ci` when a lockfile is present (reproducible, fails on drift), otherwise
# fall back to `npm install` for a first checkout.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY . ./

# VITE_API_BASE_URL is baked in at build time. It must be a path, not an
# absolute origin, so the same image works behind any hostname and the browser
# stays same-origin with the reverse proxy.
ENV VITE_API_BASE_URL=/api/v1
RUN npm run build

# -------------------------------------------------------------- runtime stage
FROM nginx:1.31-alpine AS runtime

# Replace the stock config entirely: the SPA needs history fallback and an
# explicit /api proxy, neither of which the default config provides.
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/conf.d/aegis.conf

COPY --from=builder /build/dist /usr/share/nginx/html

# nginx:alpine ships an unprivileged `nginx` user but runs as root to bind :80.
# Running unprivileged on :8080 avoids needing CAP_NET_BIND_SERVICE and lets the
# container drop all capabilities.
RUN touch /var/run/nginx.pid \
    && chown -R nginx:nginx /var/run/nginx.pid /var/cache/nginx /usr/share/nginx/html \
    && sed -i 's|^pid .*|pid /tmp/nginx.pid;|' /etc/nginx/nginx.conf \
    && sed -i 's|listen  *80;|listen 8080;|' /etc/nginx/conf.d/aegis.conf

USER nginx

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://127.0.0.1:8080/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
