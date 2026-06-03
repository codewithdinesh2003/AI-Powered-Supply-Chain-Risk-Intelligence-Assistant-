# ── Development stage (default) ───────────────────────────────────────────────
FROM node:20-alpine AS dev

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]


# ── Production build stage ─────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json* ./
RUN npm ci
COPY . .
RUN npm run build


# ── Production runtime (nginx) ────────────────────────────────────────────────
FROM nginx:1.27-alpine AS prod

COPY --from=builder /app/dist /usr/share/nginx/html

# nginx config: SPA fallback + reverse proxy for /api
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
