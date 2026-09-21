ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${BUILD_IMAGE} AS build
ENV HOME=/tmp DOTNET_CLI_HOME=/tmp NUGET_PACKAGES=/tmp/nuget \
    DOTNET_CLI_TELEMETRY_OPTOUT=1 DOTNET_NOLOGO=1 DOTNET_SKIP_FIRST_TIME_EXPERIENCE=1
WORKDIR /app
COPY --chown=10000:10000 App.csproj NuGet.config Program.cs ./
RUN dotnet restore App.csproj --configfile NuGet.config && \
    dotnet publish App.csproj -c Release -o /app/out --no-restore --no-self-contained

FROM ${RUNTIME_IMAGE}
COPY --from=build --chown=10000:10000 /app/out /app/out
EXPOSE 8080
ENTRYPOINT ["dotnet", "/app/out/consumer-app.dll"]
