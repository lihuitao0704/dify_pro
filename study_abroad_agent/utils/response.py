from flask import jsonify


def success(data=None, message="success"):
    return jsonify(
        {
            "code": 0,
            "message": message,
            "data": data
        }
    ), 200


def fail(message="error", code=1, http_code=400):
    return jsonify(
        {
            "code": code,
            "message": message,
            "data": None
        }
    ), http_code
