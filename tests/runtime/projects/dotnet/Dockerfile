# Multi-stage real do M07, versionado: `dotnet publish` na variante -dev
# (SDK) e execução na variante de runtime (ASP.NET runtime, sem SDK). As
# duas imagens chegam por build-arg porque o executor as carrega do artifact
# OCI candidato, não de um registry.
ARG BUILD_IMAGE
ARG RUNTIME_IMAGE
# Major do runtime, vindo do nome do framework no catalogo: um SDK 8 nao
# compila net10.0. O default preserva o comportamento do dotnet10.
ARG RUNTIME_MAJOR=10

FROM ${BUILD_IMAGE} AS build
# Redeclarado: um ARG antes do primeiro FROM so vale para as linhas FROM.
ARG RUNTIME_MAJOR
# HOME/caches explícitos: o SDK precisa de um home gravável e a imagem -dev
# não presume um. Telemetria e first-run desligados para não tentar rede.
ENV HOME=/tmp \
    DOTNET_CLI_HOME=/tmp \
    NUGET_PACKAGES=/tmp/nuget \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 \
    DOTNET_NOLOGO=1 \
    DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
WORKDIR /app
COPY --chown=10000:10000 App.csproj NuGet.config Program.cs ./
# Shell-form de propósito: é o `RUN` normal de um Dockerfile e só funciona
# porque a variante -dev tem shell (M07).
RUN dotnet publish App.csproj -c Release -o /app/out --no-self-contained \
    -p:RuntimeMajor=${RUNTIME_MAJOR}

FROM ${RUNTIME_IMAGE}
COPY --from=build --chown=10000:10000 /app/out /app/out
ENTRYPOINT ["dotnet", "/app/out/runtime-contract.dll"]
