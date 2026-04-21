(function () {
    function bootstrap() {
        if (window.P4PrimeUploadedWorkspace && typeof window.P4PrimeUploadedWorkspace.init === 'function') {
            window.P4PrimeUploadedWorkspace.init();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bootstrap, { once: true });
    } else {
        bootstrap();
    }
}());