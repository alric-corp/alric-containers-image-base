import React from "react";
import OriginalLayout from "@theme-original/Layout";
import styles from "./styles.module.css";

export default function Layout({ children, noNavbar, ...props }) {
  // Páginas que desenham o próprio topo (noNavbar) precisam do <main> daqui.
  // As páginas de documentação já têm o seu: envolvê-las criaria landmarks
  // <main> aninhados.
  return (
    <div className={noNavbar ? styles.withoutNavbar : undefined}>
      <OriginalLayout {...props}>{noNavbar ? <main>{children}</main> : children}</OriginalLayout>
    </div>
  );
}
