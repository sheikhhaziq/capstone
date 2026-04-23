(function() {
    const THEME_KEY = 'mindbridge_theme';
    const THEME_DARK = 'dark';
    const THEME_LIGHT = 'light';

    function getPreferredTheme() {
        const storedTheme = localStorage.getItem(THEME_KEY);
        if (storedTheme) return storedTheme;
        return window.matchMedia('(prefers-color-scheme: dark)').matches ? THEME_DARK : THEME_LIGHT;
    }

    function setTheme(theme) {
        document.documentElement.setAttribute('data-theme', theme);
        localStorage.setItem(THEME_KEY, theme);
        updateToggleIcon(theme);
    }

    function updateToggleIcon(theme) {
        const icon = document.getElementById('theme-toggle-icon');
        if (icon) {
            icon.textContent = theme === THEME_DARK ? '🌙' : '☀️';
        }
    }

    function toggleTheme() {
        const currentTheme = document.documentElement.getAttribute('data-theme') || THEME_LIGHT;
        setTheme(currentTheme === THEME_DARK ? THEME_LIGHT : THEME_DARK);
    }

    // Initialize theme immediately to avoid flash
    const initialTheme = getPreferredTheme();
    document.documentElement.setAttribute('data-theme', initialTheme);

    window.addEventListener('DOMContentLoaded', () => {
        setTheme(initialTheme);
        
        const toggleBtn = document.getElementById('theme-toggle');
        if (toggleBtn) {
            toggleBtn.addEventListener('click', toggleTheme);
        }

        // Sidebar and Mobile Menu Logic
        const sidebar = document.querySelector('.sidebar');
        const mobileToggle = document.getElementById('mobile-menu-toggle');
        
        if (mobileToggle && sidebar) {
            mobileToggle.addEventListener('click', () => {
                sidebar.classList.toggle('active');
            });
        }

        // Animated Background Blobs
        const blobContainer = document.createElement('div');
        blobContainer.className = 'blob-container';
        blobContainer.innerHTML = `
            <div class="blob blob-1"></div>
            <div class="blob blob-2"></div>
        `;
        document.body.prepend(blobContainer);
    });

    window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', e => {
        if (!localStorage.getItem(THEME_KEY)) {
            setTheme(e.matches ? THEME_DARK : THEME_LIGHT);
        }
    });

    window.addEventListener('storage', (e) => {
        if (e.key === THEME_KEY) setTheme(e.newValue);
    });
})();
