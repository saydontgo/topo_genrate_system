(function () {
    let initialized = false;

    function closeAllSubmenus(exceptItem) {
        const submenuItems = document.querySelectorAll('.has-submenu');
        submenuItems.forEach((listItem) => {
            if (exceptItem && listItem === exceptItem) {
                return;
            }

            listItem.classList.remove('is-open');
            const trigger = listItem.querySelector(':scope > a');
            if (trigger) {
                trigger.setAttribute('aria-expanded', 'false');
            }
        });
    }

    function initSubmenus() {
        const submenuItems = document.querySelectorAll('.has-submenu > a');
        submenuItems.forEach((item) => {
            if (item.dataset.p4primeSubmenuBound === '1') {
                return;
            }

            item.dataset.p4primeSubmenuBound = '1';
            item.setAttribute('aria-expanded', 'false');
            item.addEventListener('click', (event) => {
                const listItem = item.parentElement;
                if (!listItem) {
                    return;
                }

                if (window.innerWidth > 1180) {
                    closeAllSubmenus();
                    return;
                }

                event.preventDefault();
                const willOpen = !listItem.classList.contains('is-open');
                closeAllSubmenus(willOpen ? listItem : null);
                listItem.classList.toggle('is-open', willOpen);
                item.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            });
        });

        document.addEventListener('click', (event) => {
            if (!(event.target instanceof Element)) {
                return;
            }

            if (event.target.closest('.has-submenu')) {
                return;
            }

            closeAllSubmenus();
        });
    }

    function initNavToggle() {
        const toggleButton = document.getElementById('nav-toggle');
        const nav = document.getElementById('primary-nav');
        const topBar = document.querySelector('.top-bar');
        if (!toggleButton || !nav || !topBar) {
            return;
        }

        function closeNav() {
            nav.classList.remove('is-open');
            topBar.classList.remove('is-nav-open');
            toggleButton.setAttribute('aria-expanded', 'false');
            closeAllSubmenus();
        }

        function syncDesktopState() {
            if (window.innerWidth > 1180) {
                nav.classList.remove('is-open');
                topBar.classList.remove('is-nav-open');
                toggleButton.setAttribute('aria-expanded', 'false');
                closeAllSubmenus();
            }
        }

        toggleButton.addEventListener('click', () => {
            const willOpen = !nav.classList.contains('is-open');
            nav.classList.toggle('is-open', willOpen);
            topBar.classList.toggle('is-nav-open', willOpen);
            toggleButton.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        });

        document.addEventListener('click', (event) => {
            if (window.innerWidth > 1180) {
                return;
            }

            if (!(event.target instanceof Element)) {
                return;
            }

            if (event.target.closest('.top-bar')) {
                return;
            }

            closeNav();
        });

        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                closeNav();
                closeAllSubmenus();
            }
        });

        window.addEventListener('resize', syncDesktopState);
    }

    function initParticleBackground() {
        if (window.__p4primeBackgroundInitialized) {
            return;
        }

        window.__p4primeBackgroundInitialized = true;

        const body = document.body;
        if (!body) {
            return;
        }

        const canvas = document.createElement('canvas');
        const context = canvas.getContext('2d');
        if (!context) {
            return;
        }

        const config = {
            zIndex: -1,
            opacity: 0.92,
        };

        let canvasWidth = 0;
        let canvasHeight = 0;
        let nodes = [];
        let routes = [];
        let pulses = [];
        let beacons = [];
        let lastTimestamp = performance.now();
        const reducedMotion = Boolean(window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches);
        const frameFunc = window.requestAnimationFrame
            || window.webkitRequestAnimationFrame
            || window.mozRequestAnimationFrame
            || function (fn) { window.setTimeout(fn, 1000 / 40); };

        canvas.id = 'p4prime-background-canvas';
        canvas.style.cssText = `position:fixed;top:0;left:0;z-index:${config.zIndex};opacity:${config.opacity};pointer-events:none`;
        body.appendChild(canvas);

        function setCanvasSize() {
            canvasWidth = canvas.width = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth;
            canvasHeight = canvas.height = window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight;
            buildScene();
        }

        function clamp(value, min, max) {
            return Math.max(min, Math.min(max, value));
        }

        function createNodes() {
            const columns = clamp(Math.round(canvasWidth / 260), 4, 7);
            const rows = clamp(Math.round(canvasHeight / 210), 3, 6);
            const columnGap = canvasWidth / (columns + 1);
            const rowGap = canvasHeight / (rows + 1);
            const points = [];

            for (let row = 1; row <= rows; row += 1) {
                for (let column = 1; column <= columns; column += 1) {
                    const driftX = (Math.random() - 0.5) * columnGap * 0.34;
                    const driftY = (Math.random() - 0.5) * rowGap * 0.34;
                    points.push({
                        x: column * columnGap + driftX,
                        y: row * rowGap + driftY,
                        radius: 2 + Math.random() * 1.8,
                        tone: (row + column) % 4 === 0 ? 'amber' : 'teal',
                    });
                }
            }

            return points;
        }

        function distance(a, b) {
            const dx = a.x - b.x;
            const dy = a.y - b.y;
            return Math.sqrt(dx * dx + dy * dy);
        }

        function buildRoutes(pointList) {
            const sceneRoutes = [];
            const seen = new Set();

            pointList.forEach((point, index) => {
                const candidates = pointList
                    .map((otherPoint, otherIndex) => ({ otherPoint, otherIndex }))
                    .filter(({ otherPoint, otherIndex }) => otherIndex !== index && otherPoint.x >= point.x - 24)
                    .sort((left, right) => distance(point, left.otherPoint) - distance(point, right.otherPoint))
                    .slice(0, 4);

                candidates.forEach(({ otherPoint, otherIndex }, candidateIndex) => {
                    const routeDistance = distance(point, otherPoint);
                    if (routeDistance > canvasWidth * 0.28) {
                        return;
                    }

                    const sameBand = Math.abs(otherPoint.y - point.y) < canvasHeight * 0.18;
                    if (!sameBand && candidateIndex > 1) {
                        return;
                    }

                    const key = index < otherIndex ? `${index}:${otherIndex}` : `${otherIndex}:${index}`;
                    if (seen.has(key)) {
                        return;
                    }

                    seen.add(key);
                    const midpointX = (point.x + otherPoint.x) / 2;
                    const midpointY = (point.y + otherPoint.y) / 2;
                    const curveOffset = (Math.random() - 0.5) * Math.min(48, routeDistance * 0.16);
                    sceneRoutes.push({
                        from: point,
                        to: otherPoint,
                        control: {
                            x: midpointX,
                            y: midpointY + curveOffset + (candidateIndex % 2 === 0 ? -18 : 18),
                        },
                        tone: sceneRoutes.length % 5 === 0 ? 'amber' : 'teal',
                        width: 1 + Math.random() * 0.6,
                    });
                });
            });

            return sceneRoutes;
        }

        function buildPulses(routeList) {
            return routeList
                .filter((_, index) => index % 2 === 0)
                .slice(0, 22)
                .map((route, index) => ({
                    route,
                    progress: Math.random(),
                    speed: reducedMotion ? 0 : 0.00012 + (index % 6) * 0.00003,
                    direction: index % 3 === 0 ? -1 : 1,
                    radius: index % 4 === 0 ? 3.4 : 2.6,
                }));
        }

        function buildBeacons(pointList) {
            return pointList.filter((_, index) => index % 6 === 0).slice(0, 6);
        }

        function buildScene() {
            nodes = createNodes();
            routes = buildRoutes(nodes);
            pulses = buildPulses(routes);
            beacons = buildBeacons(nodes);
        }

        function getQuadraticPoint(route, progress) {
            const t = clamp(progress, 0, 1);
            const inverse = 1 - t;
            return {
                x: inverse * inverse * route.from.x + 2 * inverse * t * route.control.x + t * t * route.to.x,
                y: inverse * inverse * route.from.y + 2 * inverse * t * route.control.y + t * t * route.to.y,
            };
        }

        function drawRoute(route, emphasis) {
            const strength = emphasis || 1;
            const gradient = context.createLinearGradient(route.from.x, route.from.y, route.to.x, route.to.y);
            if (route.tone === 'amber') {
                gradient.addColorStop(0, `rgba(216, 141, 67, ${0.035 * strength})`);
                gradient.addColorStop(1, `rgba(216, 141, 67, ${0.16 * strength})`);
            } else {
                gradient.addColorStop(0, `rgba(15, 138, 120, ${0.03 * strength})`);
                gradient.addColorStop(1, `rgba(15, 138, 120, ${0.14 * strength})`);
            }

            context.beginPath();
            context.moveTo(route.from.x, route.from.y);
            context.quadraticCurveTo(route.control.x, route.control.y, route.to.x, route.to.y);
            context.lineWidth = route.width + (strength - 1) * 0.3;
            context.strokeStyle = gradient;
            context.stroke();
        }

        function drawBeacon(point, timestamp) {
            const phase = reducedMotion ? 0.4 : 0.4 + (Math.sin(timestamp / 1600 + point.x * 0.008) + 1) * 0.12;
            context.beginPath();
            context.arc(point.x, point.y, 18 + phase * 10, 0, Math.PI * 2);
            context.strokeStyle = 'rgba(15, 138, 120, 0.08)';
            context.lineWidth = 1;
            context.stroke();

            context.beginPath();
            context.arc(point.x, point.y, 28 + phase * 12, 0, Math.PI * 2);
            context.strokeStyle = 'rgba(216, 141, 67, 0.05)';
            context.lineWidth = 1;
            context.stroke();
        }

        function drawNode(point) {
            context.beginPath();
            context.arc(point.x, point.y, point.radius, 0, Math.PI * 2);
            context.fillStyle = point.tone === 'amber' ? 'rgba(216, 141, 67, 0.34)' : 'rgba(15, 138, 120, 0.30)';
            context.shadowBlur = 12;
            context.shadowColor = point.tone === 'amber' ? 'rgba(216, 141, 67, 0.16)' : 'rgba(15, 138, 120, 0.14)';
            context.fill();
            context.shadowBlur = 0;
        }

        function drawPulse(pulse) {
            const head = getQuadraticPoint(pulse.route, pulse.progress);
            const tailProgress = pulse.progress - 0.08 * pulse.direction;
            const tail = getQuadraticPoint(pulse.route, clamp(tailProgress, 0, 1));
            const tone = pulse.route.tone === 'amber' ? '216, 141, 67' : '15, 138, 120';

            context.beginPath();
            context.moveTo(tail.x, tail.y);
            context.lineTo(head.x, head.y);
            context.strokeStyle = `rgba(${tone}, 0.42)`;
            context.lineWidth = 1.8;
            context.stroke();

            context.beginPath();
            context.arc(head.x, head.y, pulse.radius, 0, Math.PI * 2);
            context.fillStyle = `rgba(${tone}, 0.88)`;
            context.shadowBlur = 18;
            context.shadowColor = `rgba(${tone}, 0.24)`;
            context.fill();
            context.shadowBlur = 0;
        }

        function drawCanvas(timestamp) {
            const delta = timestamp - lastTimestamp;
            lastTimestamp = timestamp;
            context.clearRect(0, 0, canvasWidth, canvasHeight);

            routes.forEach((route, index) => {
                drawRoute(route, index % 7 === 0 ? 1.45 : 1);
            });

            beacons.forEach((point) => drawBeacon(point, timestamp));

            pulses.forEach((pulse) => {
                if (!reducedMotion) {
                    pulse.progress += delta * pulse.speed * pulse.direction;
                    if (pulse.progress > 1.05) {
                        pulse.progress = -0.02;
                    }
                    if (pulse.progress < -0.05) {
                        pulse.progress = 1.02;
                    }
                }

                drawPulse(pulse);
            });

            nodes.forEach(drawNode);

            frameFunc(drawCanvas);
        }

        setCanvasSize();
        window.addEventListener('resize', setCanvasSize);
        window.setTimeout(() => frameFunc(drawCanvas), 100);
    }

    function init() {
        if (initialized) {
            return;
        }

        initialized = true;
        initSubmenus();
        initNavToggle();
        initParticleBackground();
    }

    window.P4PrimeShell = { init };
}());