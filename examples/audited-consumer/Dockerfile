# check=skip=InvalidDefaultArgInFrom
# Exemplo de consumo auditado. As duas bases chegam SOMENTE pelos build args
# gerados do lock verificado (<registry>/image-base-<framework>@sha256:<índice>).
# Os ARGs não têm default: sem o lock, o build falha em vez de resolver uma tag
# (por isso a checagem InvalidDefaultArgInFrom do BuildKit é desligada acima).
ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${BUILD_IMAGE} AS build
ENV HOME=/tmp GOCACHE=/tmp/gocache GOMODCACHE=/tmp/gomodcache GOPATH=/tmp/gopath \
    GOPROXY=off GOTOOLCHAIN=local CGO_ENABLED=0
WORKDIR /app
COPY --chown=10000:10000 app/go.mod app/main.go app/main_test.go ./
# Testes da aplicação com o toolchain verificado da -dev: falha de vet/teste
# falha o build e nenhuma imagem final é produzida.
RUN go vet ./... && go test ./... && go build -trimpath -buildvcs=false -o /app/consumer-app .

# Estágio final sempre na variante runtime, nunca na -dev.
FROM ${RUNTIME_IMAGE}
COPY --from=build --chown=10000:10000 /app/consumer-app /app/consumer-app
EXPOSE 8080
ENTRYPOINT ["/app/consumer-app"]
