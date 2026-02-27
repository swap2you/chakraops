# R24.8: Frontend Docker packaging. Build from repo root: docker build -f frontend/Dockerfile .
# Build-time VITE_API_BASE_URL: URL the browser will use for API (e.g. http://localhost:8000 when using compose).

# Build stage
FROM node:20-alpine AS builder
WORKDIR /app

ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./
# Rollup fallback for Alpine (no native win32 binary needed in Linux build)
ENV ROLLUP_SKIP_NODEJS_NATIVE=1
RUN npm run build

# Serve stage: nginx
FROM nginx:alpine
# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html
# Default nginx config serves static files; SPA fallback to index.html
RUN echo 'server { listen 80; root /usr/share/nginx/html; index index.html; location / { try_files $uri $uri/ /index.html; } }' > /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
