ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${BUILD_IMAGE} AS build
ENV HOME=/tmp GOCACHE=/tmp/gocache GOMODCACHE=/tmp/gomodcache \
    GOPATH=/tmp/gopath GOPROXY=off GOTOOLCHAIN=local CGO_ENABLED=0
WORKDIR /app
COPY --chown=10000:10000 go.mod main.go ./
RUN go build -trimpath -buildvcs=false -o /app/consumer-app .

FROM ${RUNTIME_IMAGE}
COPY --from=build --chown=10000:10000 /app/consumer-app /app/consumer-app
EXPOSE 8080
ENTRYPOINT ["/app/consumer-app"]
