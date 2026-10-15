#!/usr/bin/env bash
# Consumo auditado ponta a ponta, na esteira do time consumidor. Ordem fixa e
# fail-closed; nenhuma etapa publica imagem, move tag ou altera registry:
#   1. verify             resolve cada referência uma vez, executa os verificadores
#                         da Factory e grava record + lock (sem lock em qualquer falha);
#   2. check-dockerfile   FROM somente pelas bases do lock, estágio final = runtime;
#   3. build              testes da aplicação no estágio -dev e imagem final runtime,
#                         sempre pelos digests do lock (nunca pela tag);
#   4. smoke              executa a imagem final com hardening e consulta /health e /info;
#   5. record-consumption evidência JSON do que foi efetivamente consumido.
#
# Uso:
#   consume.sh --policy FILE --out DIR [--runtime REF] [--build REF]
#              [--release-record FILE] [--factory-checkout DIR] [--verifier-script FILE]
#              [--context DIR] [--image-tag NAME] [--platform linux/amd64|linux/arm64]
#              [--require-level full-policy]
set -euo pipefail

usage() {
  cat >&2 <<'EOF'
Uso: consume.sh --policy FILE --out DIR [--runtime REF] [--build REF]
                [--release-record FILE] [--factory-checkout DIR] [--verifier-script FILE]
                [--context DIR] [--image-tag NAME] [--platform linux/amd64|linux/arm64]
                [--require-level full-policy]
EOF
  exit 2
}

HERE=$(cd "$(dirname "$0")" && pwd)
GATE="$HERE/audited_consumer.py"
POLICY=""
OUT=""
CONTEXT="$HERE"
IMAGE_TAG="audited-consumer:local"
PLATFORM=""
REQUIRE_LEVEL=""
VERIFY_ARGS=()

while [[ $# -gt 0 ]]; do
  [[ $# -ge 2 ]] || usage
  case "$1" in
    --policy) POLICY="$2" ;;
    --out) OUT="$2" ;;
    --context) CONTEXT="$2" ;;
    --image-tag) IMAGE_TAG="$2" ;;
    --platform) PLATFORM="$2" ;;
    --require-level) REQUIRE_LEVEL="$2" ;;
    --runtime|--build|--release-record|--factory-checkout|--verifier-script) VERIFY_ARGS+=("$1" "$2") ;;
    *) echo "argumento desconhecido: $1" >&2; usage ;;
  esac
  shift 2
done
[[ -n "$POLICY" && -n "$OUT" ]] || usage
[[ -z "$PLATFORM" || "$PLATFORM" == linux/amd64 || "$PLATFORM" == linux/arm64 ]] || {
  echo "--platform deve ser linux/amd64 ou linux/arm64" >&2; exit 2; }

echo "== 1/5 verify"
python3 -B "$GATE" verify --policy "$POLICY" --out "$OUT/verification" ${VERIFY_ARGS[@]+"${VERIFY_ARGS[@]}"}
LOCK="$OUT/verification/verified-bases.lock.json"

echo "== 2/5 check-dockerfile"
python3 -B "$GATE" check-dockerfile --lock "$LOCK" --dockerfile "$CONTEXT/Dockerfile" > "$OUT/dockerfile-check.json" || {
  cat "$OUT/dockerfile-check.json" >&2; exit 1; }

# Falha do gate interrompe aqui (atribuição sob set -e); nenhum arg vem de tag.
ARGS_TEXT=$(python3 -B "$GATE" build-args --lock "$LOCK" ${REQUIRE_LEVEL:+--require-level "$REQUIRE_LEVEL"})
BUILD_ARGS=()
while IFS= read -r line; do
  [[ -n "$line" ]] && BUILD_ARGS+=("$line")
done <<< "$ARGS_TEXT"
PLATFORM_ARGS=()
[[ -n "$PLATFORM" ]] && PLATFORM_ARGS=(--platform "$PLATFORM")
EFFECTIVE_PLATFORM=${PLATFORM:-host}

echo "== 3/5 build (testes da aplicação no estágio -dev + imagem final)"
BUILD=FAIL
SMOKE=NOT_RUN
rm -f "$OUT/image-id.txt"
if docker buildx build --load ${PLATFORM_ARGS[@]+"${PLATFORM_ARGS[@]}"} ${BUILD_ARGS[@]+"${BUILD_ARGS[@]}"} \
    --iidfile "$OUT/image-id.txt" -t "$IMAGE_TAG" "$CONTEXT"; then
  BUILD=PASS
fi
IMAGE_ID=$(cat "$OUT/image-id.txt" 2>/dev/null || true)

if [[ "$BUILD" == PASS ]]; then
  echo "== 4/5 smoke"
  CONTAINER=$(docker run -d --rm --read-only --cap-drop ALL --security-opt no-new-privileges \
    --tmpfs /tmp --tmpfs /app/work ${PLATFORM_ARGS[@]+"${PLATFORM_ARGS[@]}"} -p 127.0.0.1::8080 "$IMAGE_TAG")
  trap 'docker stop "$CONTAINER" >/dev/null 2>&1 || true' EXIT
  ADDRESS=$(docker port "$CONTAINER" 8080/tcp | head -n 1)
  SMOKE=FAIL
  for _ in $(seq 1 30); do
    if curl -fsS "http://$ADDRESS/health" > "$OUT/health.json" 2>/dev/null; then
      if curl -fsS "http://$ADDRESS/info" > "$OUT/info.json" && python3 -B - "$OUT/info.json" <<'EOF'
import json, sys
info = json.load(open(sys.argv[1]))
security = info.get('security', {})
ok = info.get('status') == 'ok' and security.get('uid') == 10000 and security.get('gid') == 10000
sys.exit(0 if ok else 1)
EOF
      then
        SMOKE=PASS
      fi
      break
    fi
    sleep 1
  done
fi

echo "== 5/5 record-consumption"
if [[ -z "$IMAGE_ID" ]]; then
  echo "BLOCKED BUILD_FAILED: build/testes da aplicação falharam com as bases verificadas" >&2
  exit 1
fi
python3 -B "$GATE" record-consumption --lock "$LOCK" --out "$OUT/consumption-record.json" \
  --image-id "$IMAGE_ID" --platform "$EFFECTIVE_PLATFORM" --build "$BUILD" --smoke "$SMOKE"
echo "consumo auditado: PASS ($IMAGE_TAG, $EFFECTIVE_PLATFORM)"
