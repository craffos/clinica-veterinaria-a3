// Funções que falam com a API da clínica. Toda página inclui este arquivo.
const API_URL = "http://localhost:5000";

async function requisicao(metodo, caminho, corpo) {
  const opcoes = { method: metodo, headers: { "Content-Type": "application/json" } };

  const token = localStorage.getItem("token");
  if (token) opcoes.headers["Authorization"] = `Bearer ${token}`;

  if (corpo !== undefined) opcoes.body = JSON.stringify(corpo);

  let resposta;
  try {
    resposta = await fetch(API_URL + caminho, opcoes);
  } catch (erroDeRede) {
    throw new Error("Não foi possível falar com a API da clínica. Ela está rodando na porta 5000?");
  }

  // Sessão expirada ou token inválido: manda de volta para o login.
  if (resposta.status === 401 && caminho !== "/auth/login") {
    localStorage.removeItem("token");
    localStorage.removeItem("veterinario");
    if (!location.pathname.endsWith("login.html")) {
      location.href = "login.html";
    }
  }

  const dados = await resposta.json().catch(() => ({}));
  if (!resposta.ok) {
    throw new Error(dados.erro || `Erro ${resposta.status} na requisição`);
  }
  return dados;
}

const api = {
  get: (caminho) => requisicao("GET", caminho),
  post: (caminho, corpo) => requisicao("POST", caminho, corpo),
  put: (caminho, corpo) => requisicao("PUT", caminho, corpo),
  delete: (caminho) => requisicao("DELETE", caminho),
};
