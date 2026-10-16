# Containers Products

Portal de documentação em Docusaurus. A página inicial apresenta Image Base, EKS
e ECS; a documentação de Image Base começa na rota `/image-base`.

## Desenvolvimento local

Na pasta `docs/alric-users-doc-containers`:

```bash
npm ci
npm start -- --host 127.0.0.1 --port 4185 --no-open
```

Acesse <http://127.0.0.1:4185/image-base>.

## Documentação de Image Base

As páginas ficam em [`image-base/`](image-base/), uma instância própria de docs
(`id: image-base`) servida em `/image-base`. A navegação lateral, que também define
a ordem anterior/próxima, está em [`sidebars-image-base.js`](sidebars-image-base.js).

| Pasta | Conteúdo |
| --- | --- |
| `image-base/index.mdx` | Visão geral (`/image-base`) |
| `image-base/catalogo/` | Catálogo de imagens e runtime × `-dev` |
| `image-base/como-utilizar/` | Dockerfile, ambiente local, Amazon EKS e Amazon ECS |
| `image-base/troubleshooting/` | Diagnóstico por sintoma, EKS e ECS |
| `image-base/seguranca/` | Validações, atualizações, certificados e responsabilidades |
| `image-base/referencia/` | Arquiteturas, glossário e perguntas frequentes |

Para criar uma página, adicione o arquivo com `title`, `sidebar_label` e
`description` no front matter e inclua o id do documento em
`sidebars-image-base.js`. Use links relativos para os arquivos (`../catalogo/index.md`),
que o build valida, e ids explícitos nos títulos citados por outras páginas
(`## Título {#id}`).

O antigo guia de página única tinha âncoras como `/image-base#catalogo`. O componente
[`ImageBaseLegacyAnchors`](src/components/ImageBaseLegacyAnchors/index.js), usado na
visão geral, redireciona cada uma delas para a nova página. Ao mover uma seção
citada nesse mapa, atualize o destino correspondente.

Catálogo, disponibilidade e contratos de consumo vêm das fontes do repositório
(`frameworks/`, `policies/governance/catalog-support.json`, `policies/pipeline/` e
`docs/`). Atualize a documentação quando essas fontes mudarem.

A busca (`docusaurus-lunr-search`) é gerada no build: em `npm start` o campo fica
em "Carregando...". Use `npm run build` e `npm run serve` para testá-la.

## Build e preview

```bash
npm run build
npm run serve -- --host 127.0.0.1 --port 4185 --no-open
```

O build gera a pasta `build/`, ignorada pelo Git. O envio do código ao repositório
não publica o portal em um serviço de hospedagem.
