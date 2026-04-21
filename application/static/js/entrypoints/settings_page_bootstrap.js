(function () {
    function bootstrap() {
        if (window.P4PrimeSettingsPage && typeof window.P4PrimeSettingsPage.init === 'function') {
            window.P4PrimeSettingsPage.init();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
    } else {
        bootstrap();
    }
}());