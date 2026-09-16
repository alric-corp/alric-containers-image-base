#!/bin/bash
#
# Baixa os certificados corporativos (CloudSec + Itaú) e o bundle público da
# Mozilla, verifica cada um contra um manifesto SHA-256 aprovado, valida
# formato e janela de validade de cada certificado, e só então monta
# ca_bundle_interna.crt / ca_bundle_externa.crt.
#
# O SHA-256 detecta qualquer mudança de bytes em relação ao conteúdo já
# revisado (rotação legítima, corrupção, ou fonte comprometida) — não
# substitui, sozinho, a confiança de que uma CA é idônea (isso vem da
# revisão humana no momento em que o manifesto é atualizado, --pin) nem
# garante que o conteúdo aprovado continua válido com o tempo (por isso a
# checagem de validade roda em toda execução, não só no --pin).
#
# A validação de cada certificado (validate_pem_bundle, abaixo) cobre
# FORMATO e JANELA DE VALIDADE apenas: parsing X.509 bem-formado,
# notBefore <= agora <= notAfter. Ela NÃO verifica atributos de CA
# (basicConstraints/keyUsage), nem a legitimidade da autoridade emissora —
# isso continua dependendo da revisão humana no --pin.
#
# Uso:
#   certificados.sh <caminho-saida> [--lockfile <arquivo>]
#       Baixa, verifica contra o lockfile, valida formato/validade dos
#       certificados e escreve os bundles + JSON em <caminho-saida>. Falha
#       (sem gerar nenhum bundle) se algo não bater ou algum certificado
#       estiver malformado, ainda não válido ou expirado.
#
#   certificados.sh --pin [--lockfile <arquivo>]
#       Baixa os certificados atuais, valida formato/validade, e
#       (re)escreve o lockfile com os hashes correntes. Não gera bundles.
#       Serve pra propor uma atualização — revisar o diff do lockfile
#       (quais arquivos mudaram, hash antigo vs novo) num PR, com
#       confirmação do time responsável (Containers Products), antes do
#       merge.
#
#       IMPORTANTE: --pin sempre aceita o que está em S3 agora como novo
#       baseline. Antes de rodar --pin de novo (inclusive ao retomar testes
#       depois de um tempo), rode o modo normal primeiro contra o lockfile
#       já existente — isso é o que de fato detecta uma alteração não
#       revisada. Rodar --pin cegamente "lava" qualquer mudança que tenha
#       acontecido enquanto ninguém olhava, sem nunca sinalizar o desvio.
#
# Dependências: aws, curl, jq, openssl, e as variantes GNU de `date` (com
# suporte a `date -d`) e `sha256sum` — não as variantes BSD (macOS nativo).
# O preflight abaixo falha cedo com mensagem clara se alguma faltar, em vez
# de um erro confuso no meio da validação de certificado.
#
# Buckets configuráveis via variável de ambiente, pra testar sem editar o
# script (ex.: contra um bucket pessoal de teste):
#   CERTIFICADOS_BUCKET_CLOUDSEC   (default: cloud-ca-certs-bundle-prod-sa-east-1)
#   CERTIFICADOS_BUCKET_CACERTCORP (default: 04955781234-mock-cacertcorp)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOCKFILE="$SCRIPT_DIR/certificados.sha256"
CAMINHO=""
PIN=false

BUCKET_CLOUDSEC="${CERTIFICADOS_BUCKET_CLOUDSEC:-cloud-ca-certs-bundle-prod-sa-east-1}"
BUCKET_CACERTCORP="${CERTIFICADOS_BUCKET_CACERTCORP:-04955781234-mock-cacertcorp}"

# Único ponto de verdade pra quais arquivos são esperados — usado pro
# download, pro --pin, e pra checagem de completude do lockfile.
EXPECTED_FILES="ca_bundle.crt cacorp.cer cloud-s0653.cer corp-r0650.cer corp-s0143.cer mozilla.crt"

check_dependencies() {
  local missing=""
  for cmd in aws curl jq openssl sha256sum date grep; do
    command -v "$cmd" >/dev/null 2>&1 || missing="$missing $cmd"
  done
  if [ -n "$missing" ]; then
    echo "ERRO: comando(s) não encontrado(s) no PATH:$missing" >&2
    exit 4
  fi
  if ! date -d "1970-01-01T00:00:00Z" +%s >/dev/null 2>&1; then
    echo "ERRO: 'date' disponível não suporta 'date -d' (GNU date)." >&2
    echo "No macOS, o 'date' nativo é BSD e não serve — instale coreutils" >&2
    echo "(brew install coreutils) e garanta que 'date' resolva pro GNU date" >&2
    echo "(ex.: PATH=\"\$(brew --prefix coreutils)/libexec/gnubin:\$PATH\")." >&2
    exit 4
  fi
  if ! printf 'a' | sha256sum >/dev/null 2>&1; then
    echo "ERRO: 'sha256sum' disponível não é compatível com o formato GNU" >&2
    echo "(precisa suportar 'sha256sum -c' no formato '<hash>  <arquivo>')." >&2
    exit 4
  fi
}
check_dependencies

while [ $# -gt 0 ]; do
  case "$1" in
    --lockfile)
      LOCKFILE="$2"
      shift 2
      ;;
    --pin)
      PIN=true
      shift
      ;;
    -h|--help)
      sed -n '2,26p' "$0" | sed 's/^# \{0,1\}//'
      exit 0
      ;;
    *)
      CAMINHO="$1"
      shift
      ;;
  esac
done

if [ "$PIN" = false ] && [ -z "$CAMINHO" ]; then
  echo "uso: certificados.sh <caminho-saida> [--lockfile <arquivo>]" >&2
  echo "     certificados.sh --pin [--lockfile <arquivo>]" >&2
  exit 2
fi

# Resolve pra caminho absoluto ANTES de qualquer `cd`. Sem isso, um
# --lockfile relativo é lido corretamente na checagem de completude (roda
# no diretório de invocação) mas procurado no lugar errado quando
# `sha256sum -c` roda dentro de `(cd "$STAGING" && ...)` — mesmo nome,
# dois diretórios diferentes, dois resultados diferentes.
LOCKFILE_DIR="$(cd "$(dirname "$LOCKFILE")" && pwd)"
LOCKFILE="$LOCKFILE_DIR/$(basename "$LOCKFILE")"

CURL="curl --fail --show-error --silent --location --max-time 30 --retry 3 --retry-delay 2"

STAGING="$(mktemp -d)"
trap 'rm -rf "$STAGING"' EXIT

aws s3 cp "s3://$BUCKET_CLOUDSEC/ca_bundle.crt" "$STAGING/ca_bundle.crt" --quiet
aws s3 cp "s3://$BUCKET_CACERTCORP/cacorp.cer" "$STAGING/cacorp.cer" --quiet
aws s3 cp "s3://$BUCKET_CACERTCORP/cloud-s0653.cer" "$STAGING/cloud-s0653.cer" --quiet
aws s3 cp "s3://$BUCKET_CACERTCORP/corp-r0650.cer" "$STAGING/corp-r0650.cer" --quiet
aws s3 cp "s3://$BUCKET_CLOUDSEC/Corp-S0143.cer" "$STAGING/corp-s0143.cer" --quiet
$CURL https://curl.se/ca/cacert.pem -o "$STAGING/mozilla.crt"

for f in $EXPECTED_FILES; do
  test -s "$STAGING/$f"
done

# Valida formato e janela de validade de cada certificado de cada arquivo
# (um arquivo pode ter mais de um, como o bundle da Mozilla). Um checksum
# aprovado não protege contra isso — o conteúdo pode ser byte-a-byte
# idêntico ao que foi revisado e ainda assim ter vencido com o tempo, ou
# ter sido aprovado já malformado/expirado na primeira vez.
#
# O parser rastreia estado explícito de BEGIN/END: um bloco que abre sem
# fechar (arquivo truncado no meio de um certificado) ou um BEGIN antes do
# bloco anterior terminar (fragmento truncado seguido de outro certificado)
# são erros — não dá pra simplesmente ignorar o trecho inválido e seguir
# validando só o que sobrou.
validate_pem_bundle() {
  local bundle_file="$1" label="$2" metadata_file="${3:-}"
  local count=0 in_block=0 tmp_cert startdate start_epoch now_epoch
  tmp_cert="$(mktemp)"
  # `|| [ -n "$line" ]` é necessário: sem isso, a última linha de um arquivo
  # sem newline final nunca entra no corpo do loop (read retorna != 0 no
  # EOF mesmo tendo lido conteúdo) — um certificado válido cujo END não
  # tenha newline final seria rejeitado, e um fragmento BEGIN sem newline
  # final ficaria invisível ao parser (passando batido).
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in
      "-----BEGIN CERTIFICATE-----")
        if [ "$in_block" -eq 1 ]; then
          echo "ERRO: $label tem um BEGIN antes do bloco anterior terminar (delimitador PEM incompleto)." >&2
          rm -f "$tmp_cert"
          return 1
        fi
        in_block=1
        : > "$tmp_cert"
        printf '%s\n' "$line" >> "$tmp_cert"
        ;;
      "-----END CERTIFICATE-----")
        if [ "$in_block" -ne 1 ]; then
          echo "ERRO: $label tem um END CERTIFICATE sem um BEGIN correspondente." >&2
          rm -f "$tmp_cert"
          return 1
        fi
        printf '%s\n' "$line" >> "$tmp_cert"
        count=$((count + 1))
        if ! openssl x509 -in "$tmp_cert" -noout -checkend 0 >/dev/null 2>&1; then
          echo "ERRO: certificado #$count em $label é malformado ou já expirou." >&2
          rm -f "$tmp_cert"
          return 1
        fi
        startdate="$(openssl x509 -in "$tmp_cert" -noout -startdate | cut -d= -f2)"
        start_epoch="$(date -d "$startdate" +%s)"
        now_epoch="$(date +%s)"
        if [ "$start_epoch" -gt "$now_epoch" ]; then
          echo "ERRO: certificado #$count em $label ainda não é válido (notBefore no futuro: $startdate)." >&2
          rm -f "$tmp_cert"
          return 1
        fi
        if [ -n "$metadata_file" ]; then
          local subject issuer enddate fingerprint
          subject="$(openssl x509 -in "$tmp_cert" -noout -subject | sed 's/^subject=//')"
          issuer="$(openssl x509 -in "$tmp_cert" -noout -issuer | sed 's/^issuer=//')"
          enddate="$(openssl x509 -in "$tmp_cert" -noout -enddate | cut -d= -f2)"
          fingerprint="$(openssl x509 -in "$tmp_cert" -noout -fingerprint -sha256 | cut -d= -f2)"
          printf '%s|%s|%s|notBefore=%s|notAfter=%s|fingerprint_sha256=%s\n' \
            "$label" "$subject" "$issuer" "$startdate" "$enddate" "$fingerprint" >> "$metadata_file"
        fi
        in_block=0
        ;;
      *)
        if [ "$in_block" -eq 1 ]; then
          printf '%s\n' "$line" >> "$tmp_cert"
        fi
        # fora de um bloco: comentários/cabeçalhos entre certificados (como
        # os do bundle da Mozilla) não fazem parte de nenhum certificado —
        # ignorados de propósito, não há o que validar neles.
        ;;
    esac
  done < "$bundle_file"

  if [ "$in_block" -eq 1 ]; then
    echo "ERRO: $label termina com um bloco de certificado incompleto (sem END CERTIFICATE)." >&2
    rm -f "$tmp_cert"
    return 1
  fi

  rm -f "$tmp_cert"
  if [ "$count" -eq 0 ]; then
    echo "ERRO: nenhum certificado X.509 válido encontrado em $label." >&2
    return 1
  fi
}

# Gera um arquivo de metadados legível por humano (subject/issuer/
# validade/fingerprint por certificado) SEMPRE, nos dois modos — não só no
# --pin. Isso é o que torna um diff de PR revisável de verdade (hash
# sozinho não diz nada sobre o que mudou), e recomputá-lo em toda execução
# de verificação (não só ao aprovar) é o que permite detectar se o arquivo
# de metadados foi adulterado ou ficou desatualizado em relação ao que
# está de fato aprovado.
METADATA_FILE="${LOCKFILE%.sha256}.metadata.txt"
METADATA_STAGING="$STAGING/metadata.new"
: > "$METADATA_STAGING"
for f in $EXPECTED_FILES; do
  validate_pem_bundle "$STAGING/$f" "$f" "$METADATA_STAGING"
done

if [ "$PIN" = true ]; then
  # Lockfile vai pra um arquivo de staging primeiro, e só é copiado por
  # cima do real DEPOIS que os metadados já tiverem sido gravados com
  # sucesso. Com set -e, se a gravação dos metadados falhar, o script sai
  # aqui e o lockfile real nunca é tocado. Não é uma transação atômica
  # dos dois arquivos: se a segunda cópia falhar, os metadados podem ser
  # novos com um lockfile antigo. A verificação normal rejeita essa
  # divergência; restaure o par do Git ou repita o --pin após revisão.
  (cd "$STAGING" && sha256sum $EXPECTED_FILES) > "$STAGING/lockfile.new"
  cp "$METADATA_STAGING" "$METADATA_FILE"
  cp "$STAGING/lockfile.new" "$LOCKFILE"
  echo "Lockfile atualizado em $LOCKFILE." >&2
  echo "Metadados legíveis atualizados em $METADATA_FILE." >&2
  echo "Revise quais arquivos/certificados mudaram (git diff em ambos)," >&2
  echo "confirme a rotação com o time responsável (Containers Products)," >&2
  echo "e abra um PR — não aplique isso direto em produção." >&2
  exit 0
fi

if [ ! -s "$LOCKFILE" ]; then
  echo "ERRO: lockfile $LOCKFILE ausente ou vazio." >&2
  echo "Rode 'certificados.sh --pin' para gerá-lo (com revisão antes do PR)." >&2
  exit 3
fi

# sha256sum -c só confere as entradas presentes no lockfile — um manifesto
# incompleto (faltando um arquivo, por exemplo) passaria silenciosamente
# sem detectar que aquele certificado nunca foi de fato revisado. Por isso
# exigimos que o lockfile liste exatamente os arquivos esperados, nem mais
# nem menos, antes de sequer rodar a verificação de hash.
LOCKFILE_ENTRIES="$(awk '{print $2}' "$LOCKFILE" | sort | tr '\n' ' ')"
EXPECTED_SORTED="$(printf '%s\n' $EXPECTED_FILES | sort | tr '\n' ' ')"
if [ "$LOCKFILE_ENTRIES" != "$EXPECTED_SORTED" ]; then
  echo "ERRO: lockfile não lista exatamente os arquivos esperados." >&2
  echo "  esperado:  $EXPECTED_SORTED" >&2
  echo "  encontrado: $LOCKFILE_ENTRIES" >&2
  exit 3
fi

# sha256sum -c trata uma linha malformada como AVISO, não erro — ela
# simplesmente não é conferida, e o comando ainda sai com 0 se todas as
# OUTRAS linhas baterem. Isso permite que uma entrada com hash inválido
# (ex.: "INVALID  cacorp.cer") passe sem que aquele certificado específico
# seja verificado contra nada. Exigimos o formato exato de cada linha
# antes de confiar no sha256sum pra fazer a comparação.
while IFS= read -r lockline || [ -n "$lockline" ]; do
  [ -n "$lockline" ] || continue
  if ! printf '%s\n' "$lockline" | grep -qE '^[0-9a-f]{64}  [^[:space:]]+$'; then
    echo "ERRO: linha malformada no lockfile (esperado 64 hex minúsculos + dois espaços + nome do arquivo): $lockline" >&2
    exit 3
  fi
done < "$LOCKFILE"

if ! (cd "$STAGING" && sha256sum -c "$LOCKFILE") >&2; then
  echo "ERRO: um ou mais certificados não batem com o manifesto aprovado ($LOCKFILE)." >&2
  echo "Pode ser uma rotação legítima (revisar e rodar --pin) ou uma fonte" >&2
  echo "comprometida (S3 ou distribuição Mozilla). Nenhum bundle foi gerado." >&2
  exit 1
fi

# O SHA-256 do lockfile só garante integridade dos certificados — nada
# aqui verificava o arquivo de metadados até agora. Um metadata.txt
# adulterado (ex.: subject/issuer trocados por texto sem relação nenhuma
# com os certificados reais) passava batido, porque nada comparava seu
# conteúdo com nada. Recomputamos os metadados a partir dos MESMOS bytes
# já verificados por hash (METADATA_STAGING) e exigimos que batam
# byte-a-byte com o que está commitado — se um reviewer aprovou um PR
# olhando pro metadata.txt, esse é o mesmo texto que devia estar aqui.
if [ ! -s "$METADATA_FILE" ]; then
  echo "ERRO: metadados $METADATA_FILE ausentes ou vazios." >&2
  echo "Rode 'certificados.sh --pin' para gerá-los junto com o lockfile." >&2
  exit 3
fi
if ! diff -q "$METADATA_STAGING" "$METADATA_FILE" >/dev/null 2>&1; then
  echo "ERRO: metadados ($METADATA_FILE) divergem do que seria gerado a partir" >&2
  echo "dos certificados já verificados pelo hash acima. Foram editados" >&2
  echo "manualmente, corrompidos, ou ficaram desatualizados em relação ao" >&2
  echo "lockfile aprovado. Nenhum bundle foi gerado." >&2
  exit 1
fi

mkdir -p "$CAMINHO"
# Os arquivos aprovados podem não ter newline final. Separe-os para que
# END e BEGIN de certificados consecutivos não virem uma única linha.
for f in ca_bundle.crt cacorp.cer cloud-s0653.cer corp-r0650.cer corp-s0143.cer; do
  cat "$STAGING/$f"
  printf '\n'
done > "$CAMINHO/ca_bundle_interna.crt"
cat "$CAMINHO/ca_bundle_interna.crt" "$STAGING/mozilla.crt" > "$CAMINHO/ca_bundle_externa.crt"

jq -n \
    --rawfile ca_bundle_interna "$CAMINHO/ca_bundle_interna.crt" \
    --rawfile ca_bundle_externa "$CAMINHO/ca_bundle_externa.crt" \
    '{"ca_bundle_interna":$ca_bundle_interna, "ca_bundle_externa":$ca_bundle_externa}'
