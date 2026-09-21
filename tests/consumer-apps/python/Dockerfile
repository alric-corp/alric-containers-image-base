ARG RUNTIME_IMAGE

FROM ${RUNTIME_IMAGE}
COPY --chown=10000:10000 app.py /app/app.py
EXPOSE 8080
ENTRYPOINT ["/usr/bin/python3", "-B", "/app/app.py"]
