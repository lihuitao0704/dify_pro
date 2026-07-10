import sys
from pathlib import Path

# 将项目根目录加入 sys.path，使 study_abroad_agent 包可被导入
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from flask import Flask
from flask_cors import CORS
from api.dify import dify


def create_app():

    app = Flask(__name__)

    CORS(app)

    app.register_blueprint(dify)

    # ── 错误处理（必须在注册蓝图之后、app.run 之前）──
    @app.errorhandler(Exception)
    def handle_error(e):
        return {
            "code": 500,
            "message": str(e),
            "data": None
        }, 500

    @app.errorhandler(404)
    def not_found(e):
        return {
            "code": 404,
            "message": "API不存在",
            "data": None
        }, 404

    return app


app = create_app()


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
