# Containers Products

Portal de documentação em Docusaurus. A página inicial apresenta Image Base, EKS
e ECS; o guia completo de Image Base fica na rota `/image-base`.

## Desenvolvimento local

Na pasta `docs/alric-users-doc-containers`:

```bash
npm ci
npm start -- --host 127.0.0.1 --port 4185 --no-open
```

Acesse <http://127.0.0.1:4185/image-base>.

## Conteúdo do guia

Edite [`src/content/image-base.md`](src/content/image-base.md). O conteúdo é
compilado como MDX e exibido pelo layout de
[`src/pages/image-base.js`](src/pages/image-base.js), com índice gerado a partir
dos títulos e suporte a tabelas, blocos de código, seções expansíveis e Mermaid.

O guia foi incorporado do arquivo de trabalho
`factory-distroless-documentacao-completa-atual.md`, que reunia a transcrição
organizada das capturas de tela de `docs-factory-distroless/index.md`.

## Build e preview

```bash
npm run build
npm run serve -- --host 127.0.0.1 --port 4185 --no-open
```

O build gera a pasta `build/`, ignorada pelo Git. O envio do código ao repositório
não publica o portal em um serviço de hospedagem.
