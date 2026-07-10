from flask import jsonify


def success(data=None, message="success"):

    return jsonify(

        {

            "code": 0,

            "message": message,

            "data": data

        }

    )


def fail(message="error", code=1):

    return jsonify(

        {

            "code": code,

            "message": message,

            "data": None

        }

    )