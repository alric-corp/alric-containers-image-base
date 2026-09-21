ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${BUILD_IMAGE} AS build
ENV HOME=/tmp npm_config_cache=/tmp/npm-cache npm_config_audit=false npm_config_fund=false
WORKDIR /app
COPY --chown=10000:10000 package.json package-lock.json build.cjs server.cjs ./
RUN npm ci --offline --ignore-scripts --no-audit --no-fund && npm run build --offline

FROM ${RUNTIME_IMAGE}
COPY --from=build --chown=10000:10000 /app/dist/server.cjs /app/server.cjs
EXPOSE 8080
ENTRYPOINT ["/usr/bin/node", "/app/server.cjs"]
