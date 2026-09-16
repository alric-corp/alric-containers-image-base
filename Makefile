.DEFAULT_GOAL := help
PYTHON ?= python3
ACTIONLINT ?= actionlint
REUSABLE_WORKFLOWS_PATH ?= .reusable-workflows
# Generated agent workflows are validated by their compiler, not edited by hand.
WORKFLOWS := $(wildcard .github/workflows/*.yml)

UNAME_ARCH := $(shell uname -m)
ifeq ($(UNAME_ARCH),arm64)
  ARCH ?= aarch64
else ifeq ($(UNAME_ARCH),aarch64)
  ARCH ?= aarch64
else
  ARCH ?= x86_64
endif

MELANGE_KEY  := melange/.local-keys/melange.rsa
MELANGE_REPO := melange/packages

# apko/melange sempre rodam via `docker run` (nao como binario nativo extraido)
# para o Makefile funcionar em qualquer SO/arquitetura de dev (Mac, Linux, WSL).
DOCKER_MELANGE := docker run --rm -v "$(CURDIR)/melange":/work -w /work cgr.dev/chainguard/melange@sha256:43d6581e5f04b2f63b842782e581c4e06ff9ea23c81f0b3c8b9967034e38d90b


.PHONY: certificates oci help list keygen bundle build run clean test test-unit test-integration lint lint-local lint-shared lint-workflows check wolfi-trust

help:
	@echo "Build local das imagens deste repositorio (sem publicar em nenhum registry)."
	@echo ""
	@echo "  make list                            lista os frameworks disponiveis"
	@echo "  make build FRAMEWORK=go1-26           builda o OCI e carrega a arquitetura local, sem rebuild"
	@echo "  make run FRAMEWORK=go1-26 \\"
	@echo "       ENTRYPOINT=/usr/bin/go ARGS=version   builda e roda um comando na imagem"
	@echo "  make clean                            remove chave e pacotes locais"
	@echo "  make test-unit                        testes sem Docker, AWS ou rede"
	@echo "  make test-integration                 certificados, TLS e contrato do reusable"
	@echo "  make lint-local                       hardening, cobertura dos pins e lote padrao do catalogo"
	@echo "  make check                            testes e lints (inclui checkout do reusable)"
	@echo ""
	@echo "Variaveis: ARCH (padrao: $(ARCH), detectado do host)"

# Normal mode only: never repin trust inputs as a side effect of a build.
CERTIFICATES_OUTPUT ?= /tmp/image-base-certificates
certificates:
	@mkdir -p "$(CERTIFICATES_OUTPUT)"
	bash scripts/certificates/certificados.sh "$(CERTIFICATES_OUTPUT)" > "$(CERTIFICATES_OUTPUT).json"
	$(PYTHON) -B scripts/certificates/prepare_anchors.py stage --bundle "$(CERTIFICATES_OUTPUT)/ca_bundle_interna.crt"

list:
	@for f in frameworks/*.yaml; do basename "$$f" .yaml; done

test: test-unit test-integration

test-unit:
	$(PYTHON) -B -m unittest discover -s tests/unit -t . -p 'test_*.py' -v

test-integration:
	$(PYTHON) -B -m unittest discover -s tests/integration -t . -p 'test_*.py' -v

lint-local:
	$(PYTHON) -B -m scripts.pipeline.governance.lint_workflow_hardening
	$(PYTHON) -B -m scripts.pipeline.governance.pin_inventory lint
	$(PYTHON) -B -m scripts.pipeline.catalog.default_batch lint

lint-shared:
	$(PYTHON) -B -m scripts.pipeline.governance.workflow_dependencies lint
	$(PYTHON) -B -m scripts.pipeline.operations.operational_health lint

lint-workflows:
	$(ACTIONLINT) $(WORKFLOWS) \
		"$(REUSABLE_WORKFLOWS_PATH)/.github/workflows/validate-apko-images.yml" \
		"$(REUSABLE_WORKFLOWS_PATH)/.github/workflows/test-runtime-images.yml"

lint: lint-local lint-shared lint-workflows

check: test lint

# Chave de assinatura efemera do melange (nunca commitada, veja .gitignore).
$(MELANGE_KEY):
	@mkdir -p $(dir $(MELANGE_KEY))
	$(DOCKER_MELANGE) keygen .local-keys/melange.rsa

keygen: $(MELANGE_KEY)

# Âncoras revisadas; o perfil público não duplica o bundle fornecido pelo Wolfi.
wolfi-trust:
	$(PYTHON) -B -m scripts.pipeline.governance.pin_inventory trust

$(MELANGE_REPO): $(MELANGE_KEY) melange/image-base-ca-certificates.yaml $(wildcard melange/certificates/* melange/certificates/anchors/* melange/keys/*) | wolfi-trust
	$(PYTHON) -B scripts/certificates/prepare_anchors.py verify
	@mkdir -p $(MELANGE_REPO)/x86_64 $(MELANGE_REPO)/aarch64
	@set -eu; for BUILD_ARCH in x86_64 aarch64; do \
		docker run --privileged --rm -v "$(CURDIR)/melange":/work -w /work cgr.dev/chainguard/melange@sha256:43d6581e5f04b2f63b842782e581c4e06ff9ea23c81f0b3c8b9967034e38d90b \
			build image-base-ca-certificates.yaml --arch "$$BUILD_ARCH" --signing-key .local-keys/melange.rsa --build-date "$$(git show -s --format=%cI HEAD)"; \
	done
	@touch $(MELANGE_REPO)

bundle: wolfi-trust $(MELANGE_REPO)

oci: bundle
ifndef FRAMEWORK
	$(error defina FRAMEWORK, ex.: make build FRAMEWORK=go1-26. Rode "make list" para ver as opcoes)
endif
	APKO_IMAGE=cgr.dev/chainguard/apko@sha256:37e3aa165456e6c55fcded1e11af7ae9b010af914f0b25015c9a4247ec139c67 $(PYTHON) -B -m scripts.pipeline.artifacts.build_image $(FRAMEWORK) $(FRAMEWORK).oci \
		--engine docker --repository melange/packages --keyring melange/.local-keys/melange.rsa.pub $(if $(LOCKFILE),--lockfile "$(LOCKFILE)",)
	$(PYTHON) -B -m scripts.pipeline.artifacts.oci_artifact prepare $(FRAMEWORK).oci

build: oci
	$(PYTHON) -B -m scripts.pipeline.runtime.load_local $(FRAMEWORK).oci localhost/$(FRAMEWORK):local --arch $(ARCH)

run: build
ifndef ENTRYPOINT
	$(error defina ENTRYPOINT, ex.: make run FRAMEWORK=go1-26 ENTRYPOINT=/usr/bin/go ARGS=version)
endif
	docker run --rm --entrypoint $(ENTRYPOINT) localhost/$(FRAMEWORK):local $(ARGS)

clean:
	rm -rf melange/.local-keys melange/packages
	rm -f *.tar sbom-*.json *.spdx.json
