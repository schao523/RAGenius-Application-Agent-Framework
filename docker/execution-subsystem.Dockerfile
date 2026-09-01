FROM node:22-bookworm-slim

WORKDIR /app

ENV PORT=3001
ENV ARTIFACT_STORAGE_ROOT=/runtime/execution/artifacts

COPY ragenius_execution_subsystem/package*.json ./
COPY ragenius_execution_subsystem/prisma ./prisma

RUN npm ci

COPY ragenius_execution_subsystem ./

RUN npx prisma generate \
    && npm run build

ENV NODE_ENV=production

EXPOSE 3001

CMD ["sh", "-c", "npx prisma migrate deploy && node dist/src/server.js"]
