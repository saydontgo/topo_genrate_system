// 更新时间
function updateTime() {
    const now = new Date();
    const timeString = now.toLocaleTimeString();
    const dateString = now.toLocaleDateString();
    const timeElement = document.getElementById('time');
    timeElement.textContent = `${dateString} ${timeString}`;
}

// 初始调用更新时间
updateTime();

// 每秒更新一次时间
setInterval(updateTime, 1000);

// 子菜单的展开与收起
const submenuItems = document.querySelectorAll('.has-submenu > a');
submenuItems.forEach(item => {
    item.addEventListener('click', (e) => {
        const submenu = item.nextElementSibling;
        submenu.style.display = submenu.style.display === 'block' ? 'none' : 'block';
        e.preventDefault(); // 阻止默认行为，防止页面跳转
    });
});


!function () {
    //封装方法，压缩之后减少文件大小
    function get_attribute(node, attr, default_value) {
        return node.getAttribute(attr) || default_value;
    }

    //封装方法，压缩之后减少文件大小
    function get_by_tagname(name) {
        return document.getElementsByTagName(name);
    }

    //获取配置参数
    function get_config_option() {
        var scripts = get_by_tagname("script"),
            script_len = scripts.length,
            script = scripts[script_len - 1]; //当前加载的script
        return {
            l: script_len, //长度，用于生成id用
            z: get_attribute(script, "zIndex", -1), //z-index
            o: get_attribute(script, "opacity", 0.8), //opacity
            c: get_attribute(script, "color", "255,255,255"), //color
            n: get_attribute(script, "count", 350) //count
        };
    }

    //设置canvas的高宽
    function set_canvas_size() {
        canvas_width = the_canvas.width = window.innerWidth || document.documentElement.clientWidth || document.body.clientWidth,
            canvas_height = the_canvas.height = window.innerHeight || document.documentElement.clientHeight || document.body.clientHeight;
    }

    //绘制过程
    function draw_canvas() {
        context.clearRect(0, 0, canvas_width, canvas_height);
        //随机的线条和当前位置联合数组
        var e, i, d, x_dist, y_dist, dist; //临时节点
        //遍历处理每一个点
        random_points.forEach(function (r, idx) {
            r.x += r.xa,
                r.y += r.ya, //移动
                r.xa *= r.x > canvas_width || r.x < 0 ? -1 : 1,
                r.ya *= r.y > canvas_height || r.y < 0 ? -1 : 1, //碰到边界，反向反弹
                context.fillRect(r.x - 0.5, r.y - 0.5, 1, 1); //绘制一个宽高为1的点
            //从下一个点开始
            for (i = idx + 1; i < all_array.length; i++) {
                e = all_array[i];
                // 当前点存在
                if (null !== e.x && null !== e.y) {
                    x_dist = r.x - e.x; //x轴距离 l
                    y_dist = r.y - e.y; //y轴距离 n
                    dist = x_dist * x_dist + y_dist * y_dist; //总距离, m

                    dist < e.max && (e === current_point && dist >= e.max / 2 && (r.x -= 0.03 * x_dist, r.y -= 0.03 * y_dist), //靠近的时候加速
                        d = (e.max - dist) / e.max,
                        context.beginPath(),
                        context.lineWidth = d / 2,
                        context.strokeStyle = "#000000",
                        context.moveTo(r.x, r.y),
                        context.lineTo(e.x, e.y),
                        context.stroke());
                }
            }
        }), frame_func(draw_canvas);
    }

    //创建画布，并添加到body中
    var the_canvas = document.createElement("canvas"), //画布
        config = get_config_option(), //配置
        canvas_id = "c_n" + config.l, //canvas id
        context = the_canvas.getContext("2d"), canvas_width, canvas_height,
        frame_func = window.requestAnimationFrame || window.webkitRequestAnimationFrame || window.mozRequestAnimationFrame || window.oRequestAnimationFrame || window.msRequestAnimationFrame || function (func) {
            window.setTimeout(func, 1000 / 40);
        }, random = Math.random,
        current_point = {
            x: null, //当前鼠标x
            y: null, //当前鼠标y
            max: 20000 // 圈半径的平方
        },
        all_array;
    the_canvas.id = canvas_id;
    the_canvas.style.cssText = "position:fixed;top:0;left:0;z-index:" + config.z + ";opacity:" + config.o;
    get_by_tagname("body")[0].appendChild(the_canvas);

    //初始化画布大小
    set_canvas_size();
    window.onresize = set_canvas_size;
    //当时鼠标位置存储，离开的时候，释放当前位置信息
    window.onmousemove = function (e) {
        e = e || window.event;
        current_point.x = e.clientX;
        current_point.y = e.clientY;
    }, window.onmouseout = function () {
        current_point.x = null;
        current_point.y = null;
    };
    //随机生成config.n条线位置信息
    for (var random_points = [], i = 0; config.n > i; i++) {
        var x = random() * canvas_width, //随机位置
            y = random() * canvas_height,
            xa = 2 * random() - 1, //随机运动方向
            ya = 2 * random() - 1;
        // 随机点
        random_points.push({
            x: x,
            y: y,
            xa: xa,
            ya: ya,
            max: 6000 //沾附距离
        });
    }
    all_array = random_points.concat([current_point]);
    //0.1秒后绘制
    setTimeout(function () {
        draw_canvas();
    }, 100);
}();
// ========== AI 助手交互功能 (V2 - 文件上传 & Markdown) ==========
document.addEventListener('DOMContentLoaded', function() {
    // --- 获取DOM元素 ---
    const aiSidebar = document.getElementById('ai-assistant-sidebar');
    if (!aiSidebar) {
        return; // 如果页面没有助手，直接退出
    }

    const chatWindow = document.getElementById('chat-window');
    const userInput = document.getElementById('user-input');
    const sendBtn = document.getElementById('send-btn');
    const uploadInitialScreen = document.getElementById('upload-initial-screen');
    const uploadBtn = document.getElementById('upload-btn');
    const fileInput = document.getElementById('topology-file-input');
    const uploadError = document.getElementById('upload-error');
    const chatInputArea = document.getElementById('chat-input-area');
    const suggestedQuestionsContainer = document.getElementById('suggested-questions');
    
    // 格式详情提示
    const showFormatDetailsLink = document.getElementById('show-format-details');
    const formatDetails = document.getElementById('format-details');

    // --- 状态变量 ---
    let currentSessionId = null;
    let isWaitingForResponse = false;
    // 1. 获取控制滑动的相关元素
    const aiSwitch = document.getElementById('ai-assistant-switch');
    const closeBtn = document.getElementById('close-ai-sidebar');

    // 2. 确保这些控制元素存在，再绑定事件
    if (aiSwitch && closeBtn && aiSidebar) {
        
        // 点击页面右上角的开关按钮
        aiSwitch.addEventListener('click', (event) => {
            // 阻止事件冒泡到document，以防立即触发下面的外部点击关闭逻辑
            event.stopPropagation(); 
            // 为侧边栏添加 .open 类，CSS会根据这个类来执行滑入动画
            aiSidebar.classList.add('open');
        });

        // 点击侧边栏内部的关闭按钮 (X)
        closeBtn.addEventListener('click', () => {
            // 移除 .open 类，CSS会执行滑出动画
            aiSidebar.classList.remove('open');
        });

        // 点击侧边栏外部的任何地方 (实现点击空白处关闭)
        document.addEventListener('click', (event) => {
            // 检查侧边栏是否是打开状态，并且确认点击的不是开关按钮本身
            if (aiSidebar.classList.contains('open') && !aiSwitch.contains(event.target)) {
                 // 确认点击的目标不是侧边栏或其内部的任何元素
                if (!aiSidebar.contains(event.target)) {
                    aiSidebar.classList.remove('open');
                }
            }
        });
    }

    // --- 工具函数 ---
    const toggleLoadingState = (isLoading) => {
        isWaitingForResponse = isLoading;
        userInput.disabled = isLoading;
        sendBtn.disabled = isLoading;
        if (isLoading) {
            sendBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i>';
        } else {
            sendBtn.innerHTML = '<i class="fas fa-paper-plane"></i>';
        }
    };
    
    const displayError = (message) => {
        uploadError.textContent = message;
        uploadError.style.display = 'block';
    };

    // --- 核心功能 ---

    // 1. 文件上传逻辑
    uploadBtn.addEventListener('click', () => fileInput.click());

    fileInput.addEventListener('change', async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        uploadError.style.display = 'none';
        uploadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 上传并验证中...';
        uploadBtn.disabled = true;

        const formData = new FormData();
        formData.append('file', file);

        try {
            const response = await fetch('/upload_topology', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();

            if (!response.ok) {
                // 显示后端返回的详细错误信息
                let errorMsg = data.error || `服务器错误: ${response.status}`;
                if (data.template) {
                    errorMsg += `\n期望的格式类似: ${data.template}`;
                }
                throw new Error(errorMsg);
            }
            
            // 上传成功！
            currentSessionId = data.session_id;
            uploadInitialScreen.style.display = 'none'; // 隐藏上传界面
            chatInputArea.style.display = 'block';     // 显示输入框

            // 显示AI的首次分析
            appendBotMessage(data.initial_response);
            toggleLoadingState(false);

        } catch (error) {
            displayError(error.message);
        } finally {
            uploadBtn.innerHTML = '<i class="fas fa-upload"></i> 点击上传文件';
            uploadBtn.disabled = false;
            fileInput.value = ''; // 清空文件选择，以便下次上传
        }
    });

    // 2. 发送消息逻辑
    const sendMessage = async () => {
        const messageText = userInput.value.trim();
        if (messageText === '' || isWaitingForResponse) return;

        toggleLoadingState(true);
        appendUserMessage(messageText);
        userInput.value = '';
        suggestedQuestionsContainer.innerHTML = ''; // 清空旧的推荐问题

        try {
            const response = await fetch('/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ message: messageText })
            });
            const data = await response.json();
            if (!response.ok) throw new Error(data.error || '请求失败');

            appendBotMessage(data);

        } catch (error) {
            const errorData = { analysis: `抱歉，请求出错：${error.message}`, files: [], questions: [] };
            appendBotMessage(errorData);
        } finally {
            toggleLoadingState(false);
        }
    };

    // 3. 渲染消息到UI
    const appendUserMessage = (text) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message user';
        messageDiv.textContent = text;
        chatWindow.appendChild(messageDiv);
        chatWindow.scrollTop = chatWindow.scrollHeight;
    };
    
    const appendBotMessage = (data) => {
        const messageDiv = document.createElement('div');
        messageDiv.className = 'chat-message bot';
        let htmlContent = '';
        
        // 渲染Markdown分析
        if (data.analysis) {
            htmlContent += `<div class="message-content">${marked.parse(data.analysis)}</div>`;
        }

        // 创建可下载的文件链接
        if (data.files && data.files.length > 0) {
            htmlContent += '<div class="download-section">';
            data.files.forEach(file => {
                if (file.content) {
                    const blob = new Blob([file.content], { type: 'text/plain' });
                    const url = URL.createObjectURL(blob);
                    htmlContent += `<a href="${url}" download="${file.filename}" class="download-button"><i class="fas fa-download"></i> 下载 ${file.filename}</a> `;
                }
            });
            htmlContent += '</div>';
        }
        
        messageDiv.innerHTML = htmlContent;
        chatWindow.appendChild(messageDiv);
        // 渲染"猜你想问"
        suggestedQuestionsContainer.innerHTML = '';
        if (data.questions && data.questions.length > 0) {
            data.questions.forEach(q => {
                if (!q) return;
                const btn = document.createElement('button');
                btn.className = 'suggested-question-btn';
                btn.textContent = q;
                
                // 【核心修正】为按钮的点击事件添加 event.stopPropagation()
                btn.onclick = (event) => {
                    // 阻止这个点击事件继续冒泡到 document
                    event.stopPropagation(); 
                    
                    // 执行原有的功能
                    userInput.value = q;
                    sendMessage();
                };
                
                suggestedQuestionsContainer.appendChild(btn);
            });
        }
        
        chatWindow.scrollTop = chatWindow.scrollHeight;
    };
    
    // --- 绑定事件 ---
    sendBtn.addEventListener('click', sendMessage);
    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });

    showFormatDetailsLink.addEventListener('click', (e) => {
        e.preventDefault();
        formatDetails.style.display = formatDetails.style.display === 'none' ? 'block' : 'none';
    });
});
