from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .json_provider import JSONProvider
from .routes import animais, docs, vacinas


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json = JSONProvider(app)  # datas sem fuso (veja app/json_provider.py)
    CORS(app)

    app.register_blueprint(animais.bp)
    app.register_blueprint(vacinas.bp)
    app.register_blueprint(docs.bp)  # GET /docs (Swagger UI) e GET /openapi.json

    @app.get("/")
    def inicio():
        return jsonify({"mensagem": "API Governamental Simulada no ar"})

    @app.errorhandler(404)
    def nao_encontrado(_e):
        return jsonify({"erro": "rota não encontrada"}), 404

    @app.errorhandler(500)
    def erro_interno(_e):
        return jsonify({"erro": "erro interno no servidor"}), 500

    return app
