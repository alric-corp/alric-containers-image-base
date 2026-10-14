import React, { useEffect } from 'react'; 

export default function Root({children}) {
  useEffect(() => {
    if (typeof window.gtag !== 'function') {
      window.gtag = () => {};
    }
  }, []);

  return (
    <div>
      {children}
    </div>
  );
}
