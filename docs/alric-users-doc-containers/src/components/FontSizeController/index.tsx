import React, { useState, useEffect } from 'react';
import styles from './styles.module.css';

export default function FontSizeController() {
  const [fontSize, setFontSize] = useState(16);
  const [isFocusMode, setIsFocusMode] = useState(false);

  useEffect(() => {
    // Recuperar tamanho salvo no localStorage
    const savedFontSize = localStorage.getItem('docusaurus-font-size');
    if (savedFontSize) {
      const size = parseInt(savedFontSize, 10);
      setFontSize(size);
      applyFontSize(size);
    }

    // Verificar se o modo foco está ativo
    const checkFocusMode = () => {
      setIsFocusMode(document.body.classList.contains('focus-mode'));
    };

    // Verificar estado inicial
    checkFocusMode();

    // Observer para mudanças na classe focus-mode
    const observer = new MutationObserver(checkFocusMode);
    observer.observe(document.body, {
      attributes: true,
      attributeFilter: ['class']
    });

    return () => {
      observer.disconnect();
    };
  }, []);

  const applyFontSize = (size: number) => {
    document.documentElement.style.setProperty('--content-font-size', `${size}px`);
    localStorage.setItem('docusaurus-font-size', size.toString());
  };

  const handleFontSizeChange = (newSize: number) => {
    setFontSize(newSize);
    applyFontSize(newSize);
  };

  const increaseFontSize = () => {
    const newSize = Math.min(fontSize + 2, 24);
    handleFontSizeChange(newSize);
  };

  const decreaseFontSize = () => {
    const newSize = Math.max(fontSize - 2, 12);
    handleFontSizeChange(newSize);
  };

  const resetFontSize = () => {
    handleFontSizeChange(16);
  };

  // Só renderizar se o modo foco estiver ativo
  if (!isFocusMode) {
    return null;
  }

  return (
    <div className={styles.fontSizeController}>
      <div className={styles.controllerHeader}>
        <span className={styles.controllerTitle}>Tamanho do Texto</span>
        <button 
          className={styles.resetButton}
          onClick={resetFontSize}
          title="Resetar tamanho"
        >
          ↻
        </button>
      </div>
      
      <div className={styles.sliderContainer}>
        <button 
          className={styles.fontButton}
          onClick={decreaseFontSize}
          disabled={fontSize <= 12}
          title="Diminuir fonte"
        >
          A⁻
        </button>
        
        <div className={styles.sliderWrapper}>
          <input
            type="range"
            min="12"
            max="24"
            step="2"
            value={fontSize}
            onChange={(e) => handleFontSizeChange(parseInt(e.target.value))}
            className={styles.slider}
            aria-label="Controle de tamanho da fonte"
          />
          <div className={styles.sliderLabels}>
            <span className={styles.minLabel}>12</span>
            <span className={styles.currentSize}>{fontSize}px</span>
            <span className={styles.maxLabel}>24</span>
          </div>
        </div>
        
        <button 
          className={styles.fontButton}
          onClick={increaseFontSize}
          disabled={fontSize >= 24}
          title="Aumentar fonte"
        >
          A⁺
        </button>
      </div>
    </div>
  );
}