from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .json_provider import JSONProvider
from .routes import animais, auth, cep, consultas, docs, enderecos, especies, integracoes, microchips, racas, tutores, vacinas, veterinarios


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.json = JSONProvider(app)  # datas sem fuso (veja app/json_provider.py)
    CORS(app)  # permite o frontend (outra porta) chamar a API

    # Cada módulo de rotas é um "blueprint". Para adicionar um novo,
    # crie o arquivo em routes/ e registre aqui.
    app.register_blueprint(auth.bp)
    app.register_blueprint(especies.bp)
    app.register_blueprint(racas.bp)
    app.register_blueprint(enderecos.bp)
    app.register_blueprint(tutores.bp)
    app.register_blueprint(animais.bp)
    app.register_blueprint(veterinarios.bp)
    app.register_blueprint(consultas.bp)
    app.register_blueprint(vacinas.bp)
    app.register_blueprint(microchips.bp)
    app.register_blueprint(cep.bp)
    app.register_blueprint(integracoes.bp)
    app.register_blueprint(docs.bp)  # GET /docs (Swagger UI) e GET /openapi.json

    @app.get("/")
    def inicio():
        return jsonify({"mensagem": "API da Clínica no ar"})

    # Erros "crus" do Flask (404 de rota inexistente, 500 de bug) também
    # devem voltar como JSON, já que quem consome esta API é sempre código,
    # nunca uma pessoa olhando a página.
    @app.errorhandler(404)
    def nao_encontrado(_e):
        return jsonify({"erro": "rota não encontrada"}), 404

    @app.errorhandler(405)
    def metodo_nao_permitido(_e):
        return jsonify({"erro": "método HTTP não permitido para esta rota"}), 405

    @app.errorhandler(500)
    def erro_interno(_e):
        return jsonify({"erro": "erro interno no servidor"}), 500

    return app
