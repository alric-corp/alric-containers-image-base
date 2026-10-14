import React, { ReactNode } from 'react';
import styles from './Card.module.css';

interface CardProps {
  children: ReactNode;
}

export function Card({ children }: CardProps) {
  return <div className={styles.card}>{children}</div>;
}

export function CardHeader({ children }: { children: ReactNode }) {
  return <div className={styles.cardHeader}>{children}</div>;
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h3 className={styles.cardTitle}>{children}</h3>;
}

export function CardBody({ children }: { children: ReactNode }) {
  return <div className={styles.cardBody}>{children}</div>;
}
