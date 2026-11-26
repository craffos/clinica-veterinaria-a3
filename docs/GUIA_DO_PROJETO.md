# Guia do Projeto SDM – Clínica Veterinária

Este guia explica o que é o projeto, o que tem em cada pasta e arquivo, como o Flask funciona, como o login funciona, e como front-end, back-end e banco de dados conversam entre si. Foi escrito para quem nunca usou Flask.

> Procurando **como o sistema foi construído, em etapas** (para a apresentação ou o relatório)? Veja [`ETAPAS_DE_DESENVOLVIMENTO.md`](ETAPAS_DE_DESENVOLVIMENTO.md).

---

## 1. O que é o projeto

Um sistema web para uma clínica veterinária. Ele permite:

- fazer login como veterinário ativo, com cadastro, senha e confirmação de e-mail;
- cadastrar tutores (com endereço, preenchido automaticamente pelo CEP) e seus animais;
- registrar consultas, vacinas e o vínculo de microchip na ficha de cada animal;
- comunicar ao governo (simulado) o cadastro dos animais e as vacinas antirrábicas, acompanhando o status de cada envio.

O sistema é feito de **três programas independentes**, mais os bancos de dados:

| Programa | Tecnologia | Porta | Função |
|---|---|---|---|
| **Frontend** | HTML, CSS, JavaScript | 8000 | A tela que o usuário vê |
| **API da clínica** | Python + Flask | 5000 | Login, regras de negócio e acesso ao banco da clínica |
| **API governamental simulada** | Python + Flask | 5001 | Finge ser o sistema do governo |
| **Banco da clínica** | MariaDB (XAMPP) | 3306 | Dados da clínica (`clinica_veterinaria`) |
| **Banco do governo** | MariaDB (XAMPP) | 3306 | Dados do governo (`governo_simulado`), separado |
| **ViaCEP** | API pública na internet | – | Consulta de endereço pelo CEP (só consumimos) |

---

## 2. Front e back são separados? Como tudo se comunica?

**Sim, são separados.** O frontend não tem acesso ao banco de dados. Ele só sabe "pedir coisas" para a API por HTTP, e a API responde com JSON.

```
 Navegador (frontend, porta 8000)
        │  HTTP / JSON  (fetch, com o token de login no cabeçalho)
        ▼
 API da clínica (Flask, porta 5000)  ──SQL──►  Banco clinica_veterinaria
        │
        ├──HTTPS / GET / JSON──►  ViaCEP (internet)
        │
        └──HTTP / JSON + X-API-Key──►  API governamental (Flask, porta 5001) ──SQL──► Banco governo_simulado
```

Regras importantes dessa arquitetura:

- **Só a API da clínica fala com o banco da clínica.** O frontend nunca faz SQL.
- **Só a API governamental fala com o banco do governo.** A clínica não acessa esse banco; ela manda uma requisição HTTP e recebe a resposta.
- **As interfaces entre aplicações usam HTTP com JSON; o acesso aos bancos usa SQL.** JSON é só um formato de texto para trocar dados, por exemplo `{"nome": "Cachorro"}`.
- Cada parte pode ser feita, testada e rodada separadamente. Isso ajuda o trabalho em grupo.

### Por que precisamos do CORS?
O navegador bloqueia, por segurança, uma página em `localhost:8000` que tenta chamar `localhost:5000` (portas diferentes contam como "sites" diferentes). O pacote `flask-cors`, ativado no `create_app`, diz ao navegador: "pode deixar, o frontend tem permissão". Sem isso, o `fetch` do frontend falha com erro de CORS.

---

## 3. Estrutura de pastas

```
.
├── README.md                  Instruções rápidas de instalação e execução
├── .gitignore                 O que o Git deve ignorar (venv, .env, etc.)
├── .gitattributes / LICENSE   Criados pelo GitHub
├── api-clinica/               API privada da clínica (Flask)
├── api-governo/               API governamental simulada (Flask)
├── database/                  Scripts SQL (a "fonte da verdade" do banco)
├── docs/                      DER e documentação
└── frontend/                  Interface web
```

---

## 4. Cada pasta e cada arquivo

### 4.1 Raiz

| Arquivo | O que faz |
|---|---|
| `README.md` | Porta de entrada do projeto: arquitetura, como rodar, regras de Git. |
| `.gitignore` | Lista o que **não** vai para o GitHub: `venv/`, `__pycache__/`, `.env` (senhas) e arquivos do editor. |
| `.gitattributes` | Padroniza o fim de linha dos arquivos entre Windows e outros sistemas. |
| `LICENSE` | Licença do projeto, criada pelo GitHub. |

### 4.2 `api-clinica/` – o back-end principal

| Arquivo | O que faz |
|---|---|
| `run.py` | **Ponto de partida.** Cria o app e o liga na porta 5000. Você roda `python run.py`. |
| `requirements.txt` | Bibliotecas Python: Flask, flask-cors, PyMySQL, python-dotenv, requests, **PyJWT** (login). |
| `.env.example` | Modelo das configurações (banco, `SECRET_KEY` do login, endereço do governo e `GOVERNO_API_KEY`). Cada pessoa copia para `.env`. |
| `app/__init__.py` | `create_app()`: cria o Flask, liga o CORS, **registra todos os blueprints** e trata erros (404/405/500) em JSON. |
| `app/config.py` | Lê o `.env` e guarda tudo numa classe `Config`. |
| `app/db.py` | `get_conn()`, que abre a conexão com o MariaDB. Aceita `autocommit=False` para operações que gravam em duas tabelas de uma vez (ver `tutores.py`). |
| `app/auth.py` | Geração e validação do JWT, consulta do estado do veterinário e da lista de revogação: `gerar_token()` e `@login_required`. |
| `app/validacoes.py` | Funções pequenas: validar CPF, CEP, achar campos obrigatórios faltando. |
| `app/routes/` | **Um arquivo por assunto.** Veja a tabela abaixo. |
| `openapi.json` | Especificação OpenAPI/Swagger da API, gerada por `docs/gerar_openapi.py`. Servida em `GET /docs` (Swagger UI) e `GET /openapi.json`. |
| `app/services/viacep_service.py` | Fala com a API pública ViaCEP. |
| `app/services/governo_service.py` | Persiste a integração e o payload na transação clínica, envia após o commit e permite reenvio com a mesma chave e conteúdo. |
| `tests/` | Reservado para testes automatizados futuros (hoje vazio). |

Rotas (`app/routes/`): os módulos clínicos protegidos exigem `@login_required`. Cadastro, confirmação e login são públicos; `/auth/me` e `/auth/logout` são protegidos. A documentação atual também apresenta espécies, raças, endereços e CEP sem exigência de JWT; revisar essa exposição antes de produção:

| Arquivo | Prefixo | O que cobre |
|---|---|---|
| `auth.py` | `/auth` | Cadastro, confirmação de e-mail, login, consulta de sessão e logout com revogação JWT |
| `especies.py` | `/especies` | CRUD de espécie (o modelo original) |
| `racas.py` | `/racas` | CRUD de raça (sempre ligada a uma espécie) |
| `enderecos.py` | `/enderecos` | CRUD de endereço |
| `tutores.py` | `/tutores` | CRUD de tutor, já gravando o endereço junto (transação) |
| `animais.py` | `/animais` | CRUD de animal + tentativa de sincronização após persistência local |
| `veterinarios.py` | `/veterinarios` | Lista de veterinários (somente leitura) |
| `consultas.py` | `/consultas` | CRUD de consulta (o veterinário vem do token) |
| `vacinas.py` | `/vacinas` | Cadastro, consulta e atualização de vacina; antirrábica aciona o governo, sem exclusão física |
| `microchips.py` | `/microchips` | Vincular/desvincular microchip, com histórico |
| `cep.py` | `/cep` | Consulta de CEP via ViaCEP |
| `integracoes.py` | `/integracoes` | Listagem, consulta individual e reenvio de integrações elegíveis |
| `docs.py` | `/docs`, `/openapi.json` | Documentação interativa (Swagger UI) |

### 4.3 `api-governo/` – o "governo" simulado

| Arquivo | O que faz |
|---|---|
| `app/auth.py` | Decorator `@api_key_required`: valida `X-API-Key` nas rotas de negócio. |
| `app/config.py` | Carrega as configurações do banco e a chave governamental. |
| `app/routes/animais.py` | `POST /animais/`: cadastro/atualização idempotente e versionada; GET por ID da clínica e por microchip; POST aceita `?simular_falha=1`. |
| `app/routes/vacinas.py` | `POST /vacinas/`: registra vacina antirrábica mesmo sem cadastro governamental prévio do animal. |
| `app/routes/docs.py` | Documentação interativa (Swagger UI), igual à da clínica. |
| `app/utils.py` | Gera o número de protocolo (ex.: `AN-20261123153000-X7K9A1B2C3D4`). |

Roda na porta **5001**, com banco próprio (`governo_simulado`). As bases são logicamente separadas, embora usem a mesma instância MariaDB no ambiente local. A raiz e a documentação são públicas; as rotas de negócio exigem API Key.

### 4.4 `database/` – scripts SQL

| Arquivo | O que faz |
|---|---|
| `clinica/schema.sql` | Cria o banco `clinica_veterinaria` e as 11 tabelas da clínica, incluindo `token_revogado`, com chaves, unicidades e regras. |
| `clinica/seed.sql` | Espécies (Cachorro, Gato, Ave, Coelho), uma raça "SRD" por espécie, e um **veterinário de demonstração** (`dev@clinica.com` / `clinica123`). |
| `governo/schema.sql` | Cria o banco `governo_simulado` (animais registrados, vacinas registradas e controle de idempotência). |

> O banco do XAMPP é **local** de cada pessoa e não vai para o GitHub. Por isso os `.sql` ficam no repositório: cada pessoa roda os scripts e fica com o mesmo banco. Se alguém mudar uma tabela, deve atualizar o `schema.sql` e avisar o grupo.

A clínica mantém as dez entidades de domínio originais (endereço, tutor, espécie, raça, animal, veterinário, consulta, vacina, vínculo de microchip e integração governamental), mais `token_revogado`. O veterinário possui hash e expiração do token de confirmação e data de confirmação. A integração armazena `payload_original` em JSON, chave única, status, protocolo, tentativas e datas.

O governo possui três tabelas: `animal_registrado` (ID da clínica e microchip únicos, versão de origem), `operacao_recebida` (chave de idempotência, hash e protocolo) e `vacina_antirrabica_registrada` (ID da vacina da clínica único, ID do animal da clínica e vínculo governamental opcional). Uma vacina recebida antes do animal pode ser associada quando o cadastro chegar.

### 4.5 `docs/`

| Item | O que é |
|---|---|
| `der/A3_DER_Clinica_Veterinaria.drawio` | DER editável no draw.io (revisar para refletir o schema atualizado). |
| `der/A3_DER_Clinica_Veterinaria.pdf` / `.png` | O mesmo DER em PDF e imagem, para o documento acadêmico. |
| `der/versoes-anteriores/` | Versão antiga do DER, guardada por segurança. |
| `GUIA_DO_PROJETO.md` | Este guia. |
| `ETAPAS_DE_DESENVOLVIMENTO.md` | Como o sistema foi construído, passo a passo. |
| `postman/` | Coleções de requisições para testes das APIs e da integração. |
| `evidencias/` | Evidências de execução dos testes. |
| `gerar_openapi.py` | Gera o `openapi.json` de cada API (Swagger). Rode de novo ao criar uma rota. |

### 4.6 `frontend/`

| Arquivo | O que faz |
|---|---|
| `login.html` | Tela de entrada: login, cadastro e confirmação de e-mail por token. |
| `index.html` | Painel inicial: saudação, contadores (tutores e animais ativos, integrações confirmadas e não confirmadas) e explicação do fluxo. |
| `tutores.html` | Lista, busca, cria e edita tutores. O formulário tem o botão **Buscar CEP**, que preenche o endereço. |
| `animais.html` | Lista, busca, cria e edita animais. O formulário tem os selects encadeados **espécie → raça**. |
| `animal.html` | **Ficha do animal**, a tela mais importante: três abas (Consultas, Vacinas, Microchip), cada uma com formulário de registro e histórico. |
| `cadastros.html` | Administração de Espécies e Raças. |
| `integracoes.html` | Painel da integração com o governo: status de cada envio, com filtro de status e botão **Reenviar** conforme `pode_reenviar`. |
| `js/api.js` | Função `api.get/post/put/delete`: monta o `fetch`, inclui o token de login no cabeçalho e trata erros. |
| `js/auth.js` | `getToken`, `salvarSessao`, `logout`, `exigirLogin` (usadas por toda página protegida). |
| `js/nav.js` | Desenha a barra lateral (igual em todas as páginas) e funções auxiliares (`escaparHtml`, `formatarData`, `mostrarAviso`). |
| `css/style.css` | Sistema visual único: cores, cartões, tabelas, formulários, modais, selos de status, abas, responsivo. |

---

## 5. Como o Flask funciona

Flask é uma biblioteca Python para criar **servidores web**. Ele fica "escutando" numa porta, esperando pedidos (requisições), e para cada pedido executa uma função sua e devolve uma resposta.

### 5.1 Os 5 conceitos básicos

1. **Rota (endpoint):** um endereço + um método HTTP que está ligado a uma função. Exemplo: `GET /especies/`.
2. **Método HTTP:** o "verbo" do pedido (`GET`, `POST`, `PUT`, `DELETE`).
3. **Requisição (`request`):** o que o cliente mandou (corpo JSON, parâmetros na URL, cabeçalhos como o token de login).
4. **Resposta:** o que a API devolve (JSON + código de status).
5. **Blueprint:** um "grupo de rotas" em um arquivo próprio, para não ter tudo num arquivo gigante.

### 5.2 Anatomia de uma rota (do nosso `especies.py`)

```python
bp = Blueprint("especies", __name__, url_prefix="/especies")   # grupo de rotas; todas começam com /especies

@bp.get("/")                       # GET /especies/
def listar():
    with get_conn() as conn, conn.cursor() as cur:             # abre conexão com o banco
        cur.execute("SELECT ... FROM especie")                 # executa o SQL
        return jsonify(cur.fetchall())                         # devolve o resultado como JSON
```

- `@bp.get("/")` diz: "quando chegar um GET em `/especies/`, execute a função abaixo".
- `jsonify(...)` transforma dicionários e listas Python em JSON.
- `<int:id_especie>` na rota (ex.: `/especies/<int:id_especie>`) captura um número da URL e o entrega como parâmetro da função.

### 5.3 A "fábrica" do app (`create_app`)

Em vez de criar o Flask solto, usamos a função `create_app()` (em `app/__init__.py`). Ela:

1. cria o app e carrega as configurações (`Config`);
2. liga o CORS;
3. **registra cada Blueprint** (`app.register_blueprint(especies.bp)`, e assim por diante para os módulos de rotas);
4. define a rota de teste `GET /` e os tratadores de erro (404/405/500 em JSON).

Quando o `run.py` roda, ele chama `create_app()` e sobe o servidor. **Registrar o Blueprint é obrigatório:** se você criar um arquivo de rotas e esquecer de registrá-lo no `__init__.py`, as rotas não existem.

### 5.4 Configuração e `.env`

Senhas e endereços do banco **não ficam escritos no código**. Ficam no `.env` (fora do Git). O `config.py` lê esse arquivo e o `db.py` usa as configurações para conectar. Assim, cada integrante pode ter uma senha diferente no seu XAMPP sem alterar o código.

### 5.5 A conexão com o banco (`db.py`)

```python
with get_conn() as conn, conn.cursor() as cur:
    cur.execute("SELECT ... WHERE id = %s", (valor,))
```

- `get_conn()` abre a conexão; o `with` fecha automaticamente no final.
- O **cursor** (`cur`) é quem executa SQL e traz resultados.
- Usamos `DictCursor`: cada linha vem como dicionário (`{"id_especie": 1, "nome": "Cachorro"}`), que o `jsonify` converte direto em JSON.
- `autocommit=True` por padrão: cada `INSERT`/`UPDATE` já é gravado na hora.
- **Sempre use `%s` e passe os valores numa tupla.** Nunca monte o SQL concatenando texto: isso abriria brecha para **SQL injection** (um ataque em que o usuário digita SQL malicioso no campo).

**Transação (duas tabelas de uma vez só):** criar um tutor grava `endereco` e `tutor`. Se a segunda gravação falhasse depois da primeira já ter acontecido, sobraria um endereço "órfão". Por isso `tutores.py` usa `get_conn(autocommit=False)` e só confirma (`conn.commit()`) depois das duas gravações; se algo der errado, `conn.rollback()` desfaz tudo.

---

## 6. Login e token (JWT)

### 6.1 Cadastro e confirmação

`POST /auth/registrar` valida os dados, grava a senha com hash Werkzeug e cria um veterinário ainda não confirmado. O token aleatório de confirmação é apresentado no terminal da API, simulando o envio por e-mail. No banco ficam o hash SHA-256 do token e sua expiração de 30 minutos. `POST /auth/confirmar` recebe e-mail e token, valida o prazo e o estado do cadastro, confirma o e-mail e invalida o token para impedir reutilização.

### 6.2 Login e autorização

1. `POST /auth/login` verifica e-mail e senha, cadastro ativo e confirmação de e-mail. A senha nunca é armazenada em texto puro.
2. A API emite JWT assinado, com identificação do veterinário, expiração (8 horas conforme documentação) e identificador único `jti`.
3. O frontend armazena o token no `localStorage` e envia `Authorization: Bearer <token>` nas chamadas autenticadas.
4. `@login_required` valida assinatura, expiração e campos obrigatórios, consulta a revogação e verifica se o veterinário continua ativo e confirmado. Token ausente, inválido, expirado ou revogado resulta em 401; conta inativa ou não confirmada resulta em 403.
5. `g.veterinario` fornece a identidade autenticada para consultas, vacinas e microchips. O frontend não escolhe o responsável por esses registros.

### 6.3 Logout

`POST /auth/logout` registra o `jti` em `token_revogado`. O token deixa de ser aceito mesmo antes da expiração. O frontend remove a sessão local e retorna ao login; se a chamada falhar, a limpeza local não garante revogação no servidor.

### 6.4 Segurança entre serviços

A clínica envia `X-API-Key` ao governo. Ambas as APIs leem a mesma `GOVERNO_API_KEY` de seus respectivos `.env`. A API governamental usa comparação de tempo constante; chave ausente ou inválida resulta em 401, configuração ausente no servidor em 503. A chave não deve ser enviada ao frontend, registrada em evidências ou versionada no Git.

O HTTP local, CORS de desenvolvimento, e-mail simulado e armazenamento de JWT no navegador são escolhas acadêmicas. Para produção, revisar HTTPS, restrições CORS, proteção contra XSS, gerenciamento de segredos, permissões e envio real de e-mail.

---

## 7. Como funciona um endpoint, passo a passo

Exemplo: registro de vacina antirrábica na ficha do animal.

```text
1. animal.html → api.post("/vacinas/", dados)
2. js/api.js → HTTP POST com JSON e JWT
3. API clínica → valida autenticação, animal e dados da vacina
4. Transação local → INSERT vacina + INSERT integracao_governo (PENDENTE)
5. COMMIT → vacina e payload ficam persistidos juntos
6. governo_service → inicia tentativa (ENVIADO), envia POST com X-API-Key
7. Governo → valida, grava de forma idempotente e devolve protocolo
8. Clínica → atualiza status, protocolo, datas ou mensagem de erro
9. API clínica → HTTP 201, id_vacina, antirrabica e id_integracao
10. Frontend → atualiza histórico; painel permite acompanhar a integração
```

O envio é tentado de forma síncrona após o commit, não por um worker em segundo plano. Uma indisponibilidade remota pode aumentar a latência da resposta, mas não desfaz a vacina já persistida. O timeout HTTP configurado no serviço é de 5 segundos. Vacinas não antirrábicas não criam integração; `id_integracao` pode ser nulo. A flag `antirrabica` indica o tipo de vacina, não a confirmação governamental.

### Códigos de status HTTP que usamos

| Código | Significado | Quando |
|---|---|---|
| `200` | OK | Consulta ou atualização deu certo |
| `201` | Criado | Um registro novo foi criado (POST) |
| `400` | Pedido inválido | Faltou um campo obrigatório ou o dado é inválido |
| `401` | Não autenticado | Faltou o token, ou ele é inválido/expirou, ou a senha está errada |
| `404` | Não encontrado | O id pedido não existe |
| `409` | Conflito | Ex.: CPF duplicado, ou o animal já tem um microchip ativo |
| `403` | Proibido | Veterinário inativo ou não confirmado |
| `502` | Falha de serviço externo | Erro na consulta ViaCEP |
| `503` | Serviço indisponível | Falha simulada ou indisponibilidade do serviço |
| `500` | Erro no servidor | Bug ou banco fora do ar |

O `js/api.js` olha o status: se não for sucesso, lança um erro com a mensagem que veio no campo `erro` do JSON (e, se for `401` fora do login, limpa a sessão e redireciona).

---

## 8. O que é CRUD

**CRUD** são as 4 operações básicas sobre qualquer dado: **C**reate (criar), **R**ead (ler), **U**pdate (atualizar), **D**elete (apagar). Cada uma corresponde a um método HTTP e a um comando SQL:

| Operação | Método HTTP | Endpoint (espécie) | SQL |
|---|---|---|---|
| **Create** | `POST` | `POST /especies/` | `INSERT INTO especie ...` |
| **Read** (lista) | `GET` | `GET /especies/` | `SELECT ... FROM especie` |
| **Read** (um) | `GET` | `GET /especies/3` | `SELECT ... WHERE id_especie = 3` |
| **Update** | `PUT` | `PUT /especies/3` | `UPDATE especie SET ... WHERE id_especie = 3` |
| **Delete** | `DELETE` | `DELETE /especies/3` | no nosso caso, `UPDATE ... SET ativo = 0` |

### Inativação lógica (por que o DELETE não apaga)
No nosso projeto, "excluir" significa **marcar `ativo = 0`**, e não apagar a linha, para espécie, raça, tutor e animal. Motivo: um tutor ou um animal pode já ter histórico (consultas, vacinas). Apagar quebraria esses registros. Consulta não tem campo `ativo`: "cancelar" marca `status = 'CANCELADA'`. Vínculo de microchip nunca é apagado: "desvincular" marca `ativo = 0` e preenche `data_desvinculacao`.

### Validações
Antes de gravar, a rota confere o que chegou (campos obrigatórios, CPF válido, sexo entre `M`/`F`, etc.). Se faltar algo, responde `400` com uma mensagem clara. **Nunca confie nos dados que vêm do frontend:** a validação precisa estar na API.

---

## 9. Como criar um novo módulo (receita)

Exemplo: um CRUD novo qualquer.

1. Copie `app/routes/especies.py` (CRUD simples) ou `app/routes/consultas.py` (CRUD que usa `@login_required` e `g.veterinario`) para o novo arquivo.
2. Troque o nome do blueprint e o prefixo: `Blueprint("nome", __name__, url_prefix="/nome")`.
3. Troque a tabela e os campos nos SQLs.
4. Ajuste as validações.
5. Registre em `app/__init__.py`: importe o módulo e chame `app.register_blueprint(nome.bp)`.
6. Teste no Postman/Thunder Client, ou com o Swagger.
7. Faça a tela no frontend usando `api.get("/nome/")` etc.

---

## 10. Como as integrações funcionam

### ViaCEP (API pública)
O frontend **não** chama o ViaCEP direto. Ele chama a **nossa** rota `GET /cep/<cep>`, que usa `app/services/viacep_service.py` para consultar `https://viacep.com.br/ws/<cep>/json/`. Vantagem: o tratamento de erro fica num lugar só, e o frontend não depende de um serviço externo estar sempre no ar da mesma forma.

### API governamental simulada

**Persistência transacional.** Cadastro/atualização de animal, vínculo/desvínculo de microchip e registro de vacina antirrábica criam a operação de integração junto da alteração clínica, na mesma transação. O serviço guarda o JSON original (`payload_original`) e uma chave UUID única. Após o commit, tenta enviar o conteúdo persistido para `/animais/` ou `/vacinas/`, com `X-API-Key`. A vacina antirrábica é obrigatoriamente comunicada mesmo sem cadastro prévio do animal no governo.

**Idempotência.** O governo registra chave, hash SHA-256 do conteúdo normalizado e protocolo. Repetir a mesma chave e conteúdo devolve o protocolo anterior sem duplicar a operação; reutilizar a chave com conteúdo diferente resulta em 409. O ID da vacina da clínica também é único no governo. O reenvio reutiliza o payload original, não reconstrói os dados a partir do cadastro atual.

**Versionamento.** Operações de animal incluem `versao_origem`, derivada do ID da integração. Uma versão anterior não sobrescreve o estado mais recente. O microchip é único no cadastro governamental e pode ser consultado por `GET /animais/microchip/{numero_microchip}`; também há consulta por ID da clínica.

**Estados da integração:**

| Estado | Significado |
|---|---|
| PENDENTE | Aguardando envio ou nova tentativa após falha transitória, como timeout ou indisponibilidade. |
| ENVIADO | Tentativa iniciada; pode ser recuperada após dois minutos se não finalizada. |
| CONFIRMADO | Governo respondeu com protocolo válido. |
| FALHA | Erro registrado, por exemplo rejeição HTTP não transitória ou configuração inválida. |

`GET /integracoes/` lista operações com filtros de status e animal; `GET /integracoes/{id_integracao}` consulta uma operação. `POST /integracoes/{id_integracao}/reenviar` usa a mesma chave e payload. O campo `pode_reenviar` orienta o frontend: PENDENTE, FALHA ou ENVIADO com tentativa antiga. Operações confirmadas ou em tentativa recente não podem ser reenviadas (409). Um HTTP 200 no reenvio não garante confirmação: conferir o status retornado. Não há fila externa nem agendador automático de retentativas documentado.

A atualização de vacina já integrada não permite alterar a flag antirrábica, a data de aplicação ou o lote; não há fluxo de retificação governamental implementado. Vacinas não antirrábicas não precisam de comunicação.

Para testar falhas, usar `?simular_falha=1` em POST direto ao governo (com API Key) ou interromper temporariamente o servidor governamental durante um cadastro clínico. Após restabelecer o serviço, reenviar pelo painel e verificar protocolo e ausência de duplicação. Não executar testes destrutivos em dados reais.

---

## 11. Como rodar tudo (resumo)

1. Ligue o MySQL no XAMPP e rode os `.sql` de `database/` no phpMyAdmin (clinica/schema.sql → clinica/seed.sql → governo/schema.sql).
2. Em cada API, crie o `venv`, instale o `requirements.txt` e copie `.env.example` para `.env` se ainda não existir. Configure banco, segredo JWT da clínica e a mesma API Key aleatória nas duas APIs, sem publicar os valores. Consulte o [README](../README.md) para os comandos completos.
3. Inicie as APIs com `python run.py` em terminais separados e ambientes virtuais correspondentes (clínica 5000, governo 5001).
4. Em `frontend/`: `python -m http.server 8000` e abra `http://localhost:8000/login.html`.
5. Entre com o veterinário de demonstração (`dev@clinica.com` / `clinica123`) ou cadastre um novo e confirme o e-mail com o token exibido no terminal da clínica.

Para testar sem o frontend, use Postman ou Swagger. Na clínica, use `Authorization: Bearer <token>` nas rotas protegidas; no governo, `X-API-Key` nas rotas de negócio. Swagger: http://localhost:5000/docs e http://localhost:5001/docs. A versão 1.2.0 gerada por `python docs/gerar_openapi.py` possui 27 caminhos na clínica e 5 no governo. O frontend também foi executado pelo Live Server na porta 5500. Não compartilhe a seção Curl do Swagger com credenciais.

---

## 12. Status atual

**Implementado:** módulos clínicos, autenticação com confirmação e revogação, duas bases MariaDB, integração com ViaCEP, sincronização governamental autenticada, idempotência, versionamento, persistência local e reenvio, frontend e Swagger atualizado.

**Validações realizadas no ambiente local:** confirmação de cadastro e bloqueio de login não confirmado, senha incorreta, inativação e revogação de JWT; comunicação governamental com API Key; vacinação não antirrábica sem integração; indisponibilidade governamental com vacina local preservada; reenvio com confirmação e bloqueio de novo reenvio de operação confirmada. O fluxo de indisponibilidade e recuperação também foi exercitado pelo frontend, com conferência dos registros nos dois bancos. A documentação Swagger foi gerada e aberta nas duas APIs, e a consulta governamental autenticada retornou HTTP 200.

**Limitações e revisão final:** não foi demonstrada instalação limpa integral a partir dos scripts finais. A atualização do DER deve refletir as alterações do schema. Conferir evidências dos demais casos obrigatórios, coleções Postman, documentação acadêmica e apresentação. A verificação realizada é manual/roteirizada, não uma suíte automatizada completa; não se afirma cobertura integral dos endpoints nem prontidão para produção.

---

## 13. Glossário rápido

| Termo | Significado |
|---|---|
| **API** | Programa que recebe pedidos e devolve dados, sem tela. |
| **Endpoint** | Um endereço específico da API (ex.: `GET /especies/`). |
| **Rota** | A ligação entre um endereço + método e a função que o atende. |
| **REST** | Estilo de API onde cada coisa tem um endereço e os verbos HTTP indicam a ação. |
| **JSON** | Formato de texto para trocar dados entre programas. |
| **Blueprint** | Grupo de rotas do Flask num arquivo separado. |
| **CORS** | Permissão para um site em uma porta chamar uma API em outra. |
| **CRUD** | Criar, ler, atualizar e apagar. |
| **JWT** | "JSON Web Token": o formato do token de login, assinado digitalmente. |
| **Hash de senha** | Transformação de mão única da senha; o banco nunca guarda a senha em texto puro. |
| **Idempotência** | Repetir a mesma operação não gera duplicidade. |
| **Transação** | Um grupo de gravações que acontece tudo ou nada (commit/rollback). |
| **venv** | Ambiente virtual do Python: isola as bibliotecas de cada projeto. |
| **SQL injection** | Ataque que insere SQL malicioso num campo; mitigado por consultas parametrizadas com `%s` e valores separados. |

| **API Key** | Segredo compartilhado para autenticar chamadas entre serviços. |
| **jti** | Identificador único de um JWT, usado para revogação. |
| **Payload** | Conteúdo JSON de uma requisição. |
| **Versionamento de origem** | Número que permite identificar atualizações antigas de um registro. |
| **Outbox transacional** | Padrão de persistir a alteração de negócio e a mensagem de integração na mesma transação; neste projeto, com envio síncrono após commit e reenvio manual. |
