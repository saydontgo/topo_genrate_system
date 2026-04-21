(function () {
    let runtime = null;

    function init() {
        if (runtime || !window.P4PrimeWorkspaceRuntime) {
            if (runtime) {
                runtime.init();
            }
            return;
        }

        runtime = window.P4PrimeWorkspaceRuntime.create({
            topologySelection: 'current',
            initialStatusMessage: '如果你已经上传拓扑，请先装载 P4，再点击“生成当前上传拓扑”。',
            p4LoadedMessage: 'P4 程序已装载，可以继续生成当前上传拓扑。',
            flowInjectedMessage: '流表已注入，可以开始发送验证流量。',
            primarySendLabel: '单路径验证',
            secondarySendLabel: 'VBP 合法行为池验证',
            enableSecondarySend: true,
            expectedPathLabel: '预期主路径',
            autoRestorePendingTopology: true,
            uploadReadyMessage: (summary) => {
                if (!summary) {
                    return '已载入新的上传拓扑，现在可以装载 P4 并生成当前拓扑。';
                }

                return `已载入上传拓扑：${summary.switch_count} 台交换机、${summary.host_count} 台主机、${summary.link_count} 条链路。现在可以装载 P4 并生成当前拓扑。`;
            },
        });
        runtime.init();
    }

    window.P4PrimeUploadedWorkspace = { init };
}());