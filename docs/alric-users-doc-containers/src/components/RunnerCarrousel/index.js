import React from "react";
import { Swiper, SwiperSlide } from "swiper/react";
import { Pagination, Navigation, Autoplay } from "swiper/modules";
import "swiper/css";
import "swiper/css/pagination";
import "swiper/css/navigation";
import styles from "./styles.module.css";
import RunningIcon from "@site/src/components/Icons/RunningIcon";

const runnerGuides = [
  {
    icon: <RunningIcon />,
    title: "Como escolher o runner ideal",
    description: "Avalie se seu job exige CPU, memória ou GPU.",
    tips: [
      "Analise requisitos de CPU/RAM",
      "Considere tempo de execução",
      "Avalie custo vs performance",
    ],
    color: "#4facfe",
  },
  {
    icon: "📊",
    title: "Monitorando consumo de hardware",
    description:
      "Utilize métricas do Datadog para avaliar CPU, RAM e storage dos runners.",
    tips: [
      "Configure alertas de uso",
      "Monitore métricas em tempo real",
      "Otimize baseado nos dados",
    ],
    color: "#f093fb",
  },
];

export default function RunnerCarousel() {
  return (
    <div className={styles.carouselContainer}>
      <Swiper
        modules={[Pagination, Navigation, Autoplay]}
        spaceBetween={30}
        slidesPerView={1}
        pagination={{
          clickable: true,
          dynamicBullets: true,
        }}
        navigation={{
          nextEl: `.${styles.swiperButtonNext}`,
          prevEl: `.${styles.swiperButtonPrev}`,
        }}
        autoplay={{
          delay: 5000,
          disableOnInteraction: false,
        }}
        loop={true}
        className={styles.runnerSwiper}
      >
        {runnerGuides.map((guide, index) => (
          <SwiperSlide key={index}>
            <div
              className={styles.slideCard}
              style={{ "--accent-color": guide.color }}
            >
              <div className={styles.slideHeader}>
                <div
                  className={styles.slideIcon}
                  style={{ backgroundColor: `${guide.color}20` }}
                >
                  {guide.icon}
                </div>
                <h3 className={styles.slideTitle}>{guide.title}</h3>
              </div>

              <p className={styles.slideDescription}>{guide.description}</p>

              <div className={styles.tipsList}>
                <h4 className={styles.tipsTitle}>💡 Dicas importantes:</h4>
                <ul className={styles.tips}>
                  {guide.tips.map((tip, tipIndex) => (
                    <li key={tipIndex} className={styles.tip}>
                      {tip}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </SwiperSlide>
        ))}
      </Swiper>

      {/* Custom Navigation Buttons */}
      <div className={`${styles.swiperButtonPrev} ${styles.customNavButton}`}>
        ←
      </div>
      <div className={`${styles.swiperButtonNext} ${styles.customNavButton}`}>
        →
      </div>
    </div>
  );
}
