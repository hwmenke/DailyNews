"""
app.py - Flask application entry point.

Route groups are organised into Blueprints under blueprints/:
  symbols        /api/symbols …
  data           /api/fetch, /api/refresh, /api/ohlcv, /api/data-manager …
  indicators     /api/indicators, /api/stats, /api/knn, /api/backtest,
                 /api/adaptive-trend, /api/trend-scan
  scanner        /api/scanner …
  newsletter     /api/newsletter …
"""

import logging
import os

from flask import Flask, send_from_directory
from flask_cors import CORS

import database as db
from blueprints.symbols       import bp as symbols_bp
from blueprints.data          import bp as data_bp
from blueprints.indicators_bp import bp as indicators_bp
from blueprints.scanner_bp    import bp as scanner_bp
from blueprints.newsletter_bp import bp as newsletter_bp

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder=".", static_url_path="")
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:8050").split(",")]
CORS(app, origins=_cors_origins)

db.init_db()

app.register_blueprint(symbols_bp)
app.register_blueprint(data_bp)
app.register_blueprint(indicators_bp)
app.register_blueprint(scanner_bp)
app.register_blueprint(newsletter_bp)


@app.route("/")
def index():
    return send_from_directory(".", "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8050))
    host = os.environ.get("HOST", "127.0.0.1")
    logger.info("Financial Dashboard running at http://%s:%s", host, port)
    app.run(
        debug=os.environ.get("DEBUG", "false").lower() == "true",
        threaded=True,
        host=host,
        port=port,
    )
