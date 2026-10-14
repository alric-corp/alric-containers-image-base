import React from "react";
import OriginalLayout from "@theme-original/Layout";
import styles from "./styles.module.css";

export default function Layout({ children, noNavbar, ...props }) {
  return (
    <div className={noNavbar ? styles.withoutNavbar : undefined}>
      <OriginalLayout {...props}>
        <main>{children}</main>
      </OriginalLayout>
    </div>
  );
}
