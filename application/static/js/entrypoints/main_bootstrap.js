(function () {
    function bootstrap() {
        if (window.P4PrimeShell && typeof window.P4PrimeShell.init === 'function') {
            window.P4PrimeShell.init();
        }

        if (window.P4PrimeAssistant && typeof window.P4PrimeAssistant.init === 'function') {
            window.P4PrimeAssistant.init();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
    } else {
        bootstrap();
    }
}());