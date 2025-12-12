/* ========================================
   MOBILE MENU FUNCTIONALITY
   Archivo: static/js/mobile-menu.js
   ======================================== */

document.addEventListener('DOMContentLoaded', function() {
    // ========================================
    // VARIABLES Y ELEMENTOS
    // ========================================
    const mobileMenuToggle = document.getElementById('mobileMenuToggle');
    const sidebar = document.getElementById('sidebar');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    const navLinks = document.querySelectorAll('.nav-link');
    
    // ========================================
    // FUNCIÓN PARA TOGGLE DEL SIDEBAR
    // ========================================
    function toggleSidebar() {
        sidebar.classList.toggle('active');
        sidebarOverlay.classList.toggle('active');
        
        // Cambiar icono del botón
        const icon = mobileMenuToggle.querySelector('i');
        if (sidebar.classList.contains('active')) {
            icon.className = 'bi bi-x-lg';
            // Prevenir scroll del body cuando el menú está abierto
            document.body.style.overflow = 'hidden';
        } else {
            icon.className = 'bi bi-list';
            // Restaurar scroll del body
            document.body.style.overflow = '';
        }
    }
    
    // ========================================
    // CERRAR SIDEBAR
    // ========================================
    function closeSidebar() {
        if (sidebar.classList.contains('active')) {
            sidebar.classList.remove('active');
            sidebarOverlay.classList.remove('active');
            const icon = mobileMenuToggle.querySelector('i');
            icon.className = 'bi bi-list';
            document.body.style.overflow = '';
        }
    }
    
    // ========================================
    // EVENT LISTENERS
    // ========================================
    
    // Click en el botón hamburguesa
    if (mobileMenuToggle) {
        mobileMenuToggle.addEventListener('click', function(e) {
            e.stopPropagation();
            toggleSidebar();
        });
    }
    
    // Click en el overlay (fondo oscuro)
    if (sidebarOverlay) {
        sidebarOverlay.addEventListener('click', closeSidebar);
    }
    
    // Click en los enlaces del menú
    navLinks.forEach(function(link) {
        link.addEventListener('click', function() {
            // Solo cerrar en móvil
            if (window.innerWidth <= 768) {
                closeSidebar();
            }
        });
    });
    
    // Tecla ESC para cerrar
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape' && sidebar.classList.contains('active')) {
            closeSidebar();
        }
    });
    
    // ========================================
    // MANEJO DE RESIZE
    // ========================================
    let resizeTimer;
    window.addEventListener('resize', function() {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(function() {
            // Si cambiamos a desktop, cerrar el menú
            if (window.innerWidth > 768 && sidebar.classList.contains('active')) {
                closeSidebar();
            }
        }, 250);
    });
    
    // ========================================
    // PREVENIR SCROLL DEL BODY (iOS Safari)
    // ========================================
    const observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(mutation) {
            if (mutation.attributeName === 'class') {
                if (sidebar.classList.contains('active') && window.innerWidth <= 768) {
                    document.body.style.overflow = 'hidden';
                    document.body.style.position = 'fixed';
                    document.body.style.width = '100%';
                } else {
                    document.body.style.overflow = '';
                    document.body.style.position = '';
                    document.body.style.width = '';
                }
            }
        });
    });
    
    if (sidebar) {
        observer.observe(sidebar, { attributes: true });
    }
    
    // ========================================
    // SWIPE GESTURES (opcional pero mejora UX)
    // ========================================
    let touchStartX = 0;
    let touchEndX = 0;
    
    document.addEventListener('touchstart', function(e) {
        touchStartX = e.changedTouches[0].screenX;
    }, { passive: true });
    
    document.addEventListener('touchend', function(e) {
        touchEndX = e.changedTouches[0].screenX;
        handleSwipe();
    }, { passive: true });
    
    function handleSwipe() {
        const swipeThreshold = 50;
        const swipeDistance = touchEndX - touchStartX;
        
        // Swipe desde la izquierda para abrir
        if (touchStartX < 50 && swipeDistance > swipeThreshold && !sidebar.classList.contains('active')) {
            toggleSidebar();
        }
        
        // Swipe hacia la izquierda para cerrar
        if (swipeDistance < -swipeThreshold && sidebar.classList.contains('active')) {
            closeSidebar();
        }
    }
    
    // ========================================
    // LOG DE INICIALIZACIÓN
    // ========================================
    console.log('✅ Mobile menu initialized successfully');
});

/* ========================================
   UTILIDADES ADICIONALES
   ======================================== */

// Función para detectar dispositivo móvil
function isMobileDevice() {
    return window.innerWidth <= 768;
}

// Función para obtener altura real del viewport (útil para iOS)
function getRealViewportHeight() {
    return window.innerHeight || document.documentElement.clientHeight;
}

// Ajustar altura en iOS para evitar problemas con la barra de direcciones
window.addEventListener('resize', function() {
    if (isMobileDevice()) {
        const vh = getRealViewportHeight() * 0.01;
        document.documentElement.style.setProperty('--vh', `${vh}px`);
    }
});

// Ejecutar al cargar
if (isMobileDevice()) {
    const vh = getRealViewportHeight() * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
}

/* ========================================
   PREVENIR DOBLE TAP ZOOM EN iOS
   ======================================== */
let lastTouchEnd = 0;
document.addEventListener('touchend', function(event) {
    const now = Date.now();
    if (now - lastTouchEnd <= 300) {
        event.preventDefault();
    }
    lastTouchEnd = now;
}, false);