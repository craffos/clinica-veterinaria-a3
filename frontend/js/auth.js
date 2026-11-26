
// Gerenciamento da autenticação e da sessão do veterinário.

function getToken() {
    return localStorage.getItem("token");
}


function getVeterinarioLogado() {
    const bruto = localStorage.getItem("veterinario");

    return bruto ? JSON.parse(bruto) : null;
}


function salvarSessao(token, veterinario) {
    localStorage.setItem("token", token);

    localStorage.setItem(
        "veterinario",
        JSON.stringify(veterinario)
    );
}


async function logout() {

    const token = getToken();

    try {

        // Solicita a revogação do JWT no servidor.
        if (token) {
            await api.post("/auth/logout");
        }

    } catch (erro) {

        // Informa caso não seja possível confirmar a revogação.
        console.error("Erro ao revogar a sessão:", erro.message);

        alert(
            "A sessão local será encerrada, mas não foi possível " +
            "confirmar a revogação do token no servidor."
        );

    } finally {

        // Remove os dados da sessão do navegador.
        localStorage.removeItem("token");
        localStorage.removeItem("veterinario");

        // Redireciona para a tela de login.
        location.href = "login.html";
    }
}


function exigirLogin() {

    if (!getToken()) {

        location.href = "login.html";

        throw new Error("redirecionando para o login");
    }
}
