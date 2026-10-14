import React from "react";
import { Swiper, SwiperSlide } from "swiper/react";
import { Navigation, Pagination, Autoplay } from "swiper/modules";
import "swiper/css";
import "swiper/css/navigation";
import "swiper/css/pagination";
import styles from "./styles.module.css";

// Features principais - estático
const FeatureList = [
  {
    title: "conheca!",
    img: "img/lupa.png",
    description: "Leia nossa documentação e saiba quais são as novidades.",
    linkLabel: "Documentação",
    linkHref: "/docs/documentation",
  },
  {
    title: "pergunte!",
    img: "img/pergunte.png",
    description: "Confira nosso FAQ, glossário e como entrar em contato.",
    linkLabel: "Ajuda",
    linkHref: "/docs/support/faq",
  },
  {
    title: "contribua!",
    img: "img/lapis.png",
    description: "Saiba como começar a contribuir e evoluir nosso produto.",
    linkLabel: "Contribuições",
    linkHref: "/docs/contributing",
  },
  {
    title: "se atualize",
    img: "img/new.png",
    description: "Fique por dentro das novidades e atualizações.",
    linkLabel: "Release notes",
    linkHref: "/docs/release-notes",
  },
  {
    title: "cases de uso",
    img: "img/cases.png",
    description: "Veja exemplos de pipelines configurados para diferentes cenários.",
    linkLabel: "Exemplos",
    linkHref: "/docs/documentation/cases",
  },
  {
    title: "boas práticas",
    img: "img/check.png",
    description: "Aprenda recomendações de uso e otimizações para seus pipelines.",
    linkLabel: "Guia de boas práticas",
    linkHref: "/docs/documentation/best-practices",
  },
];

// Runners - carrossel
const RunnerGuides = [
  {
    title: "Escolha do Runner",
    description:
      "Saiba como escolher o runner ideal para o seu job de acordo com CPU, memória e tempo de execução.",
  },
  {
    title: "Execução por Região",
    description:
      "Aprenda a configurar seus jobs para rodar em runners localizados em regiões específicas da AWS.",
  },
  {
    title: "Consumo de Hardware",
    description:
      "Entenda como monitorar e otimizar o consumo de hardware do seu runner para evitar gargalos.",
  },
];

export default function HomepageFeatures() {
  return (
    <div>
      {/* Features estáticas */}
      <section className={styles.features}>
        {FeatureList.map((feature, idx) => (
          <div key={idx} className={styles.feature}>
            <img src={feature.img} alt={feature.title} />
            <h3>{feature.title}</h3>
            <p>{feature.description}</p>
            <a href={feature.linkHref} className={styles.link}>
              {feature.linkLabel}
            </a>
          </div>
        ))}
      </section>

      {/* Runners - carrossel */}
      <section className={styles.runners}>
        <h2>Guia para clientes de runners</h2>
        <Swiper
          modules={[Navigation, Pagination, Autoplay]}
          spaceBetween={30}
          slidesPerView={1}
          navigation
          pagination={{ clickable: true }}
          autoplay={{ delay: 4000 }}
          loop
        >
          {RunnerGuides.map((guide, idx) => (
            <SwiperSlide key={idx}>
              <div className={styles.runnerCard}>
                <h3>{guide.title}</h3>
                <p>{guide.description}</p>
              </div>
            </SwiperSlide>
          ))}
        </Swiper>
      </section>
    </div>
  );
}
