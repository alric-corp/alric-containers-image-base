import React, { useState, useEffect } from 'react';
import styles from './styles.module.css';

export default function FocusMode() {
  const [isFocusMode, setIsFocusMode] = useState(false);

  useEffect(() => {
    if (isFocusMode) {
      document.body.classList.add('focus-mode');
    } else {
      document.body.classList.remove('focus-mode');
    }

    // Cleanup quando o componente for desmontado
    return () => {
      document.body.classList.remove('focus-mode');
    };
  }, [isFocusMode]);

  // Verificar se já tem o parâmetro focus=true na URL
  useEffect(() => {
    const urlParams = new URLSearchParams(window.location.search);
    const focusFromUrl = urlParams.get('focus') === 'true';
    
    if (focusFromUrl) {
      setIsFocusMode(true);
    }
  }, []);

  const toggleFocusMode = () => {
    const newFocusMode = !isFocusMode;
    setIsFocusMode(newFocusMode);
    
    // Opcional: atualizar a URL
    const url = new URL(window.location.href);
    if (newFocusMode) {
      url.searchParams.set('focus', 'true');
    } else {
      url.searchParams.delete('focus');
    }
    window.history.replaceState({}, '', url);
  };

  return (
    <div className={styles.focusToggleContainer}>
      <div className={styles.toggleWrapper}>
        <span className={styles.toggleLabel}>Modo Foco</span>
        <div 
          className={`${styles.toggle} ${isFocusMode ? styles.toggleActive : ''}`}
          onClick={toggleFocusMode}
          title={isFocusMode ? 'Sair do modo foco' : 'Entrar no modo foco'}
          aria-label={isFocusMode ? 'Sair do modo foco' : 'Entrar no modo foco'}
          role="switch"
          aria-checked={isFocusMode}
        >
          <div className={styles.toggleSlider}>
            <span className={styles.toggleIcon}>
              {isFocusMode ? '' : '👁️'}
            </span>
          </div>
        </div>
        <span className={styles.toggleStatus}>
          {isFocusMode ? 'Ativo' : 'Inativo'}
        </span>
      </div>
      <hr className={styles.separator} />
    </div>
  );
}