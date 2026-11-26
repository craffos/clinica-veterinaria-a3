"""Documentação interativa da API (Swagger UI), lendo o arquivo
openapi.json que fica na raiz de api-clinica/ (gerado por
docs/gerar_openapi.py, na raiz do projeto)."""
import os

from flask import Blueprint, jsonify, send_from_directory

bp = Blueprint("docs", __name__)

RAIZ_API = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@bp.get("/openapi.json")
def especificacao():
    return send_from_directory(RAIZ_API, "openapi.json")


@bp.get("/docs")
def documentacao():
    # Swagger UI carregado via CDN (precisa de internet); só a página HTML é local.
    return """
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Documentação · API da Clínica</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui.css">
</head>
<body>
  <div id="swagger-ui"></div>
  <script src="https://cdn.jsdelivr.net/npm/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
  <script>
    window.ui = SwaggerUIBundle({
      url: "/openapi.json",
      dom_id: "#swagger-ui",
      presets: [SwaggerUIBundle.presets.apis],
    });
  </script>
</body>
</html>
"""
