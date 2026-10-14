import React from "react";
import clsx from "clsx";
import useIsBrowser from "@docusaurus/useIsBrowser";
import IconLightMode from "@theme/Icon/LightMode";
import IconDarkMode from "@theme/Icon/DarkMode";
import styles from "./styles.module.css";

function ColorModeToggle({ className, buttonClassName, value, onChange }) {
  const isBrowser = useIsBrowser();

  // garante um valor padrão se value for null/undefined
  const currentMode = (value ?? "light").toString();
  const modoAtual = currentMode === "dark" ? "escuro" : "claro";

  const title = `Trocar entre tema claro e escuro (atualmente ${modoAtual})`;

  return (
    <div className={clsx(styles.toggle, className)}>
      <button
        className={clsx(
          "clean-btn",
          styles.toggleButton,
          !isBrowser && styles.toggleButtonDisabled,
          buttonClassName
        )}
        type="button"
        onClick={() => onChange(currentMode === "dark" ? "light" : "dark")}
        disabled={!isBrowser}
        title={title}
        aria-live="polite"
      >
        <IconLightMode
          className={clsx(styles.toggleIcon, styles.lightToggleIcon)}
        />
        <IconDarkMode
          className={clsx(styles.toggleIcon, styles.darkToggleIcon)}
        />
      </button>
    </div>
  );
}

export default React.memo(ColorModeToggle);
