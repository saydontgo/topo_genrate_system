from flask import Flask
from p4utils.mininetlib.log import info
import atexit
import os
from LLM import r
from routes.pages import pages
from routes.settings_api import settings_api
from routes.topology_api import topology_api
from routes.upload_api import upload_api
SECRET_KEY = 'your-very-secret-and-complex-key-here'


def create_app():
    app = Flask(__name__)
    app.secret_key = SECRET_KEY
    app.register_blueprint(pages)
    app.register_blueprint(settings_api)
    app.register_blueprint(upload_api)
    app.register_blueprint(topology_api)
    return app


app = create_app()


# 清除redis内存  
@atexit.register
def cleanup_redis():
    info("quiting Flask, cleanning all the history")
    keys = r.keys("chat_history:*")
    if keys:
        r.delete(*keys)
# -------------ai大模型的调用逻辑--------------




# 启动服务
if __name__ == '__main__':
    debug_enabled = os.environ.get('P4PRIME_DEBUG', '').strip() == '1'
    app.run(host='0.0.0.0', port=5000, debug=debug_enabled, use_reloader=False)
