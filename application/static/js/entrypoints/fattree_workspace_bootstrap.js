(function () {
    function bootstrap() {
        if (window.P4PrimeFatTreeWorkspace && typeof window.P4PrimeFatTreeWorkspace.init === 'function') {
            window.P4PrimeFatTreeWorkspace.init();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
    } else {
        bootstrap();
    }
}());