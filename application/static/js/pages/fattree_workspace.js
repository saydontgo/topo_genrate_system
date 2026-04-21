(function () {
    let runtime = null;
    let workspacePrimed = false;

    async function primeWorkspace() {
        if (workspacePrimed) {
            return;
        }

        workspacePrimed = true;

        try {
            const response = await fetch('/initiate_topo', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: window.location.href }),
            });
            const data = await response.json();
            if (!response.ok) {
                throw new Error(data.error || '初始化 FatTree6 工作区失败');
            }
            console.log('FatTree6 workspace primed:', data.status);
        } catch (error) {
            console.error('FatTree6 workspace prime failed:', error);
        }
    }

    function init() {
        if (runtime || !window.P4PrimeWorkspaceRuntime) {
            if (runtime) {
                runtime.init();
            }
            return;
        }

        runtime = window.P4PrimeWorkspaceRuntime.create({
            topologySelection: 'fat6',
            initialStatusMessage: '请先装载 P4，再点击“生成 FatTree6 拓扑”。',
            buildAcceptedMessage: (data) => `后端已接受 ${data.topology} 构建请求，正在同步 FatTree6 视图...`,
            p4LoadedMessage: 'P4 程序已装载，可以继续生成 FatTree6 拓扑。',
            flowInjectedMessage: '流表已注入，可以开始发送 FatTree6 验证流量。',
            primarySendLabel: '发送',
            expectedPathLabel: '预期路径',
            uploadReadyMessage: () => '当前页面是 FatTree6 基线工作区，不会自动切换到上传拓扑。',
        });
        primeWorkspace();
        runtime.init();
    }

    window.P4PrimeFatTreeWorkspace = { init };
}());