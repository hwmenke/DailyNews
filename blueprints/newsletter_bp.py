from flask import Blueprint, jsonify, request
import newsletter_engine

bp = Blueprint("newsletter", __name__, url_prefix="/api")


@bp.route("/newsletter/data", methods=["GET"])
def get_newsletter_data():
    try:
        n_charts = min(int(request.args.get("n", 20)), 50)
    except (TypeError, ValueError):
        n_charts = 20
    try:
        data = newsletter_engine.compute_newsletter_data(n_charts=n_charts)
        return jsonify(data)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
