from flask import Flask
from flask_cors import CORS
from api.dify import dify


def create_app():

    app = Flask(__name__)

    CORS(app)

    app.register_blueprint(dify)

    return app


app = create_app()


if __name__ == "__main__":

    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True

    )


@app.errorhandler(Exception)

def handle_error(e):

    return {

        "code":500,

        "message":str(e),

        "data":None

    },500

@app.errorhandler(404)

def not_found(e):

    return {

        "code":404,

        "message":"API不存在",

        "data":None

    },404