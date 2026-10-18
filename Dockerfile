# ─────────────────────────────────────────────────────────────
# AETHER — multi-stage production image
# Stage 1: build the static site with Vite (Node 22)
# Stage 2: serve it with a hardened, caching Nginx (Alpine)
# Final image ≈ 25 MB.  Usage:  docker build -t aether . && docker run -p 8080:80 aether
# ─────────────────────────────────────────────────────────────
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.27-alpine AS runtime
COPY deploy/nginx-docker.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
HEALTHCHECK --interval=30s --timeout=4s --retries=3 \
  CMD wget -qO- http://127.0.0.1/healthz >/dev/null 2>&1 || exit 1
CMD ["nginx", "-g", "daemon off;"]
