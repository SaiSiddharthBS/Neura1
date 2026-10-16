FROM node:24-slim AS build
RUN corepack enable
WORKDIR /app
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile
COPY . .
ARG NEURA1_API_URL=http://api:8000
ENV NEURA1_API_URL=$NEURA1_API_URL
RUN pnpm build

FROM node:24-slim
RUN corepack enable
WORKDIR /app
COPY --from=build /app ./
ENV NODE_ENV=production PORT=3000
EXPOSE 3000
CMD ["pnpm", "start"]
