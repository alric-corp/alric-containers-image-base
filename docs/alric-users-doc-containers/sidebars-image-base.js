// @ts-check

// This runs in Node.js - Don't use client-side code here (browser APIs, JSX...)

/**
 * Navegação da documentação de Image Base (instância de docs `image-base`,
 * servida em /image-base). A ordem dos itens também define a navegação
 * anterior/próxima no rodapé de cada página.
 *
 * @type {import('@docusaurus/plugin-content-docs').SidebarsConfig}
 */
const sidebars = {
  imageBase: [
    {
      type: "category",
      label: "Comece aqui",
      collapsed: false,
      items: ["index", "por-que-usar"],
    },
    {
      type: "category",
      label: "Catálogo de imagens",
      collapsed: false,
      items: ["catalogo/index", "catalogo/runtime-dev"],
    },
    {
      type: "category",
      label: "Como utilizar",
      collapsed: false,
      items: [
        "como-utilizar/dockerfile",
        "como-utilizar/ambiente-local",
        "como-utilizar/eks",
        "como-utilizar/ecs",
      ],
    },
    {
      type: "category",
      label: "Solução de problemas",
      items: ["troubleshooting/index", "troubleshooting/eks", "troubleshooting/ecs"],
    },
    {
      type: "category",
      label: "Segurança e boas práticas",
      items: [
        "seguranca/validacoes",
        "seguranca/atualizacoes",
        "seguranca/certificados",
      ],
    },
    {
      type: "category",
      label: "Referência",
      items: [
        "referencia/arquiteturas",
        "referencia/responsabilidades",
        "referencia/glossario",
        "referencia/faq",
      ],
    },
    "suporte",
  ],
};

export default sidebars;
