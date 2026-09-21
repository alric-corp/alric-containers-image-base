ARG BUILD_IMAGE
ARG RUNTIME_IMAGE

FROM ${BUILD_IMAGE} AS build
ENV HOME=/tmp
WORKDIR /app
COPY --chown=10000:10000 Main.java ./
RUN javac --add-modules jdk.httpserver -d /app/classes Main.java

FROM ${RUNTIME_IMAGE}
COPY --from=build --chown=10000:10000 /app/classes /app/classes
EXPOSE 8080
ENTRYPOINT ["java", "--add-modules", "jdk.httpserver", "-cp", "/app/classes", "Main"]
