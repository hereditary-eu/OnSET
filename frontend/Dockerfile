FROM node:26-bookworm AS build-stage
# dependencies are pinned by bun.lock (there is no package-lock.json)
RUN npm install -g bun@1.4.3
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
RUN bun run build

# production stage
FROM nginx:stable-alpine AS production-stage
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx/nginx.conf /etc/nginx/conf.d
COPY --from=build-stage /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
