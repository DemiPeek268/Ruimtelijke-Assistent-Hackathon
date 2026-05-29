# Stage 1 — Build
FROM node:22-slim AS build

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

RUN npm run build

# Stage 2 — Serve
FROM nginx:stable-alpine

# Copy built assets
COPY --from=build /app/dist /usr/share/nginx/html

# Copy nginx config template
COPY nginx.conf /etc/nginx/templates/default.conf.template

EXPOSE 80

# API_URL is substituted into nginx config at container start via
# nginx docker image's built-in envsubst mechanism on /etc/nginx/templates/
ENV API_URL=http://backend:8000
