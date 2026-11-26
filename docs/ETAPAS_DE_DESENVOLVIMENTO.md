# Etapas de desenvolvimento

Este documento registra **como o sistema foi construído**, em ordem, com as decisões tomadas e por quê. Serve de referência para o relatório/apresentação e para quem quiser entender o raciocínio por trás do código (não só o que ele faz, mas por que foi feito assim).

> Para entender a estrutura do projeto e como o Flask funciona, veja [`GUIA_DO_PROJETO.md`](GUIA_DO_PROJETO.md). Este documento aqui é sobre o **processo**, não sobre "como usar".

---

> **Nota de revisão (25/11/2026):** as seções 1 a 10 registram a implementação inicial, conforme o histórico original. Não representam necessariamente o comportamento atual. As seções 11 a 17 descrevem as melhorias posteriores e os testes acompanhados. Para instalar o sistema, consulte o README atualizado.

## Ponto de partida

O projeto já tinha, antes desta etapa:

- o DER completo (10 entidades, revisado e com as cardinalidades corretas);
- o `schema.sql` e o `seed.sql` do banco da clínica, batendo com o DER;
- o esqueleto das duas APIs Flask (`create_app`, `config`, `db.py`) e um único CRUD de exemplo (espécie), para servir de modelo;
- a estrutura de pastas (`api-clinica/`, `api-governo/`, `database/`, `docs/`, `frontend/`) e o repositório Git já criado no GitHub.

A tarefa desta etapa foi **terminar o sistema inteiro**: todos os CRUDs, login, as integrações (ViaCEP e governo), e todo o frontend, sem reescrever o que já funcionava.

---

## 1. Planejamento antes de escrever código

Antes de mexer em qualquer arquivo, foi decidido:

- **Ordem de construção:** autenticação → cadastros (raça, endereço, tutor, animal) → atendimento clínico (consulta, vacina, microchip) → integrações (ViaCEP, governo) → frontend → testes → documentação. Essa ordem segue a dependência real: não dá para testar "consulta" sem ter "animal", nem "animal" sem "tutor".
- **Login com JWT**, não sessão de servidor. Motivo: a API é *stateless* (não guarda quem está logado em memória), o que é mais simples de testar e de rodar em duas portas diferentes (clínica e governo) sem compartilhar estado.
- **Senha do veterinário:** nunca gravada em texto puro. Foi usado `werkzeug.security` (já vem com o Flask, não precisa de biblioteca nova) em vez de implementar hash na mão.
- **Quem registra cada consulta/vacina/microchip é o veterinário logado** (tirado do token), não um campo escolhido no formulário. Isso elimina uma tela inteira (escolher o veterinário) e corresponde ao uso real: quem preenche o formulário é quem está atendendo.
- **Nada de DELETE de verdade** em dado com histórico clínico. Cada tabela já previa isso no DER (`ativo`, `status`, `data_desvinculacao`); a implementação só seguiu a regra.

---

## 2. Backend da clínica: autenticação

Arquivos: `app/auth.py`, `app/validacoes.py`, `app/routes/auth.py`.

1. `validacoes.py` ganhou funções pequenas e reaproveitáveis (`cpf_valido`, `cep_valido`, `campos_faltando`), para não repetir validação em cada rota.
2. `auth.py` ficou só com a lógica de token: `gerar_token()` (cria o JWT, válido por 8 horas) e o decorator `@login_required` (lê o cabeçalho `Authorization`, confere a assinatura, e expõe `g.veterinario` para a rota usar).
3. `routes/auth.py` usa os dois: `POST /auth/registrar` (valida CPF, cria o hash da senha, insere), `POST /auth/login` (confere a senha com `check_password_hash`, atualiza `ultimo_acesso`, devolve o token) e `GET /auth/me` (só para o frontend confirmar que o token ainda vale).

**Decisão consciente:** o campo `email_confirmado` do DER existe, mas o projeto não tem servidor de e-mail. Em vez de deixar essa funcionalidade pela metade, o cadastro já marca `email_confirmado = 1` automaticamente, com um comentário no código explicando que, num sistema real, isso dependeria de enviar um link/código por e-mail antes.

---

## 3. Backend da clínica: cadastros

Arquivos: `app/routes/racas.py`, `enderecos.py`, `tutores.py`, `animais.py`, `veterinarios.py`.

- `racas.py` e `enderecos.py` seguiram exatamente o padrão de `especies.py` (o modelo que já existia).
- `tutores.py` foi o primeiro módulo "não trivial": criar ou editar um tutor também grava o endereço dele, e são duas tabelas. Para evitar um endereço órfão se a segunda gravação falhar, essa rota usa `get_conn(autocommit=False)` e confirma as duas gravações juntas (`conn.commit()`) ou desfaz as duas (`conn.rollback()`). Essa necessidade motivou adicionar o parâmetro `autocommit` em `app/db.py` (que, por padrão, continua `True`, sem quebrar as rotas já prontas).
- `animais.py` implementa a regra mais importante do DER: a raça precisa pertencer à espécie escolhida. Isso é garantido **no banco** (chave estrangeira composta `fk_animal_raca_especie`, que já existia no schema); a API só traduz o erro do banco (`IntegrityError`) numa mensagem de API (`400`) em vez de deixar vazar um erro de SQL cru.
- `veterinarios.py` é só leitura: existe para telas futuras que precisem mostrar "quem é quem", sem expor senha/CPF.

---

## 4. Backend da clínica: atendimento clínico

Arquivos: `consultas.py`, `vacinas.py`, `microchips.py`.

- **Consulta:** CRUD normal, com um detalhe: "excluir" uma consulta marca `status = 'CANCELADA'` em vez de apagar (consulta é histórico clínico).
- **Vacina:** ao criar uma vacina com `antirrabica = true`, a rota chama o serviço de integração com o governo **depois** de gravar a vacina, assim ela fica salva na clínica mesmo que a comunicação com o governo falhe.
- **Microchip** foi o módulo com mais regras de negócio:
  - um animal só pode ter um vínculo ativo por vez;
  - um número de chip só pode estar ativo em um animal por vez;
  - nunca apagar: "desvincular" marca `ativo = 0` e `data_desvinculacao`.

  Essas regras já existiam no `schema.sql` como colunas geradas + `UNIQUE` (`animal_ativo`, `chip_ativo`). A API faz a mesma conferência **antes** de tentar gravar (para devolver uma mensagem de erro legível, tipo "este animal já tem um microchip ativo"), e ainda captura `IntegrityError` como segunda linha de defesa, para o caso de duas pessoas tentarem vincular o mesmo chip ao mesmo tempo (condição de corrida). Nesse caso o banco é a autoridade final, não a API.

---

## 5. Integração com serviços externos

### ViaCEP
`app/services/viacep_service.py` é só uma função (`buscar_cep`) que chama `https://viacep.com.br/ws/<cep>/json/` com a biblioteca `requests` e devolve `None` se der qualquer problema de rede. A rota `GET /cep/<cep>` trata os três casos possíveis: CEP mal formado (`400`), ViaCEP fora do ar (`502`) e CEP não encontrado (`404`).

### API governamental simulada
Esta foi a parte mais trabalhosa, por ter duas pontas (clínica e governo) que precisam concordar num contrato.

**Do lado da clínica** (`app/services/governo_service.py`):
1. Toda tentativa de comunicação cria uma linha em `integracao_governo`, com uma **chave de idempotência** nova (um UUID).
2. A função tenta enviar (`POST` para `/animais/` ou `/vacinas/` do governo).
3. O resultado atualiza a mesma linha: `CONFIRMADO` com o protocolo, ou `FALHA` com a mensagem de erro. Nunca lança uma exceção para quem chamou, já que criar um animal não pode quebrar só porque o governo está fora do ar.
4. `reenviar()` repete o envio **usando a mesma chave de idempotência** salva da primeira vez.

**Do lado do governo** (`app/routes/animais.py` e `vacinas.py`, no `api-governo`):
1. Cada endpoint primeiro confere se já existe uma `operacao_recebida` com aquela chave; se sim, devolve o mesmo protocolo de novo, sem duplicar nada. É isso que torna o reenvio seguro.
2. O cadastro de animal usa `INSERT ... ON DUPLICATE KEY UPDATE`, então o mesmo endpoint serve tanto para "cadastrar" quanto para "atualizar" (a clínica manda `tipo_operacao` diferente, mas o governo trata as duas como um "salvar").
3. Registrar uma vacina exige que o animal já esteja cadastrado (`422` se não estiver), refletindo a ordem real: o animal precisa existir antes da vacina dele.
4. Os dois endpoints aceitam `?simular_falha=1`, só para testar o reenvio sem precisar desligar o servidor de verdade.

**Por que isso importa para a nota do projeto:** essa é a parte que demonstra "sistemas distribuídos" de verdade: dois serviços independentes, com bancos separados, que precisam continuar funcionando (ou pelo menos falhar de forma registrada e recuperável) mesmo quando um deles está indisponível.

---

## 6. Testes, sem ter o MariaDB disponível

Esta máquina onde o código foi escrito **não tem o XAMPP/MariaDB instalado**. Em vez de entregar o código sem testar, foi criado um banco falso em Python só para a validação:

- Um `pymysql.connect` falso devolve uma conexão/cursor que:
  - **confere se o número de `%s` no SQL bate com o número de parâmetros** (pega erro de "esqueci de passar um valor");
  - **olha o `FROM`/`INTO`/`UPDATE` do SQL** para saber qual tabela devolver como resultado fabricado (assim uma rota que faz `JOIN` com três tabelas recebe a linha certa, não a de qualquer tabela citada);
  - respeita a diferença entre "nenhum resultado" e "um resultado", para testar os casos de erro (ex.: tutor não encontrado → `404`).
- Em cima disso, o `app.test_client()` do próprio Flask disparou **todas as rotas das duas APIs**, incluindo os casos de erro de propósito (CPF inválido, sem token, microchip duplicado, vacina sem animal cadastrado no governo, etc.).
- Esse teste pegou pelo menos um bug de verdade: a rota de reenvio de integração (`POST /integracoes/<id>/reenviar`) fazia duas consultas SQL diferentes dentro do mesmo pedido, e a primeira versão do "banco falso" devolvia a linha errada para a segunda consulta, escondendo um `KeyError`. Corrigir o próprio teste (para ele reconhecer a tabela certa de cada consulta) revelou que o código da aplicação estava correto; o problema era só do simulador.
- Depois, as duas APIs foram **de fato colocadas no ar** (`python run.py`, com esse mesmo banco falso) e o frontend foi testado **clicando nas telas de verdade** num navegador: login, criar tutor (com busca de CEP real), listar/editar animal, abrir a ficha do animal e usar as três abas, cadastrar espécie/raça, e ver o painel de integrações (inclusive clicando em "Reenviar"). Não apareceu nenhum erro no console do navegador.

**O que isso garante, e o que não garante:** essa bateria de testes fornece evidências sobre os caminhos exercitados em Python (sem erros de digitação, de parâmetro, de importação, de formato de resposta) e que o frontend conversa certo com a API (JSON no formato esperado, CORS, token, etc.). **Não substitui** testar com o MariaDB de verdade: nomes de coluna errados no SQL, restrições `UNIQUE`/`FOREIGN KEY` reais e a performance das consultas só aparecem rodando contra o banco. Por isso, o primeiro passo de quem for usar o projeto deve ser rodar os scripts de `database/` no XAMPP e testar um fluxo completo (criar tutor → criar animal → registrar consulta/vacina/microchip) com o banco real.

---

## 7. Frontend

O frontend foi escrito por último de propósito: só depois de todas as rotas existirem e estarem testadas é que dava para saber exatamente quais campos cada tela precisava mandar e receber.

1. **Sistema visual primeiro** (`css/style.css`): cores, cartões, tabela, formulário, modal, abas e selos de status foram definidos uma vez só, antes de qualquer página, para todas saírem consistentes (a mesma barra lateral, os mesmos botões) sem repetir CSS.
2. **Infraestrutura compartilhada** (`js/api.js`, `js/auth.js`, `js/nav.js`): o `fetch` com o token, o guard de login, e a função que desenha a barra lateral. Assim, cada página HTML fica curta e focada só na sua própria tela.
3. **Páginas, na ordem das dependências:** login → painel inicial → tutores (CEP) → animais (espécie/raça) → ficha do animal (consultas/vacinas/microchip, as três abas) → cadastros de apoio → integrações.
4. A **ficha do animal** (`animal.html`) foi a página mais trabalhosa, porque reúne três fluxos (consulta, vacina, microchip) numa tela só, com abas, cada uma com seu formulário e sua lista de histórico. Isso espelha a estrutura do DER, com ANIMAL no centro das relações 1:N com CONSULTA, VACINA e VINCULO_MICROCHIP.

---

## 8. Documentação

Por fim, a documentação foi revisada/reescrita para refletir o sistema **pronto**, não mais o esqueleto inicial:

- `GUIA_DO_PROJETO.md`: atualizado com todas as rotas, o funcionamento do login/JWT, a transação do tutor, e o status real do projeto.
- `ETAPAS_DE_DESENVOLVIMENTO.md` (este arquivo): o histórico do processo, para quem for apresentar o trabalho explicar as decisões tomadas.
- `README.md`: atualizado com o login de demonstração e qualquer novo passo de instalação.
- `database/clinica/seed.sql`: ganhou um veterinário de demonstração, para o grupo não precisar se cadastrar manualmente só para testar.

---

## 9. Teste contra o banco de verdade (depois que o XAMPP foi instalado)

Tudo até aqui tinha sido validado só com o banco simulado. Assim que o MariaDB ficou disponível (via XAMPP), foi feito um teste de ponta a ponta de verdade: login → criar tutor (com busca de CEP real) → criar animal → a clínica avisar a API governamental sozinha → registrar consulta → registrar vacina antirrábica → a vacina ser confirmada no governo, com protocolo → vincular microchip. Esse teste encontrou dois problemas reais, que só apareceriam rodando contra um banco de verdade:

1. **O `governo/schema.sql` tinha sido importado no banco errado** (`clinica_veterinaria` em vez de `governo_simulado`), um detalhe de como o phpMyAdmin mantém o banco selecionado entre importações, não um erro do script em si. Corrigido criando as tabelas certas no banco certo.
2. **Bug de fuso horário:** o Flask devolvia `datetime`/`date` no formato RFC 1123 (`"Tue, 24 Nov 2026 14:30:00 GMT"`), que **afirma** ser UTC. O navegador acreditava nisso e convertia para o fuso local, deslocando a hora exibida (e, em campos só de data, até o dia). Corrigido dos dois lados: a API agora devolve a data "crua" (`"2026-11-24 14:30:00"`, sem fuso) através de um `JSONProvider` próprio (`app/json_provider.py`), e o frontend (`js/nav.js`) lê esses números na mão, sem usar `new Date(texto)` (que é exatamente o que causa esse tipo de ambiguidade).

Isso mostra por que "testei com um banco simulado" não é a mesma coisa que "testei de verdade": erros de configuração (schema no banco errado) e erros de fuso horário só aparecem com infraestrutura real na mesa.

## 10. Documentação da API (Swagger/OpenAPI)

Depois do sistema completo e testado, foi gerada a documentação interativa dos endpoints, pendente desde a Semana 5 do cronograma:

- `docs/gerar_openapi.py` monta a especificação OpenAPI 3.0 das duas APIs (24 caminhos na clínica, 4 no governo) como um dicionário Python e grava em `openapi.json` dentro de cada pasta (`api-clinica/`, `api-governo/`). É um script, não um JSON escrito à mão, para ficar fácil de estender quando uma rota nova for criada.
- Cada API ganhou um módulo `app/routes/docs.py` com duas rotas nativas do Flask: `GET /openapi.json` (devolve o arquivo) e `GET /docs` (uma página HTML simples que carrega o Swagger UI via CDN, apontando para `/openapi.json`).
- A documentação foi testada de verdade: um login foi executado **direto pela tela do Swagger** (botão "Try it out"), contra a API rodando com o banco real, e devolveu o mesmo token que o frontend recebe.

## Decisões iniciais (registro histórico)

| Decisão | Por quê |
|---|---|
| JWT em vez de sessão de servidor | Inicialmente sem sessão em memória; posteriormente passou a consultar o banco para verificar revogação e situação do veterinário |
| Veterinário logado define quem atende | Reflete o uso real; evita campo redundante no formulário |
| Inativação lógica (`ativo`/`status`) em vez de `DELETE` | Preserva histórico clínico, que é dado sensível e não pode sumir |
| Transação na criação do tutor | Evita endereço "órfão" se a segunda gravação falhar |
| Chave de idempotência no envio ao governo | Permite reenviar com segurança sem duplicar registros |
| Falha no governo não derruba o cadastro local | Os dois sistemas são independentes; um fora do ar não pode travar o outro |
| Banco falso para testar sem MariaDB | Permitiu achar bugs de Python antes de depender de infraestrutura externa, mas não substitui testar com o banco de verdade |
| Datas sem fuso horário na API | O sistema é de uma clínica só, sem suporte a fusos diferentes; afirmar "isto é UTC" (como o Flask faz por padrão) só criava confusão e deslocava a hora exibida |


---

## 11. Revisão da autenticação e segurança (25/11/2026)

A confirmação automática de e-mail da etapa inicial foi substituída por um fluxo explícito de confirmação. O envio de e-mail é simulado no terminal da API, sem depender de SMTP.

- `POST /auth/registrar`: valida os dados, grava a senha com hash e cria o veterinário com `email_confirmado = 0`. Gera um token aleatório de confirmação, guarda somente seu hash SHA-256 e define validade de 30 minutos.
- `POST /auth/confirmar`: valida e-mail, token, prazo e situação do cadastro. Confirma o e-mail e invalida o token utilizado.
- `POST /auth/login`: exige senha correta, cadastro ativo e e-mail confirmado; atualiza o último acesso.
- `@login_required`: valida o JWT, sua expiração e identificador único (`jti`), consulta a situação atual do veterinário e verifica se o token foi revogado.
- `POST /auth/logout`: registra o `jti` na tabela `token_revogado`. O frontend também remove os dados da sessão local.

**Decisão:** manter JWT sem sessão em memória, mas consultar o banco a cada acesso protegido para permitir revogação imediata e bloqueio de usuários inativos. Não se trata mais de autenticação completamente sem estado persistente.

A API governamental passou a exigir `X-API-Key` nos endpoints de negócio. A chave é configurada em `GOVERNO_API_KEY` nos dois arquivos `.env`, com comparação segura no servidor. A chave não deve ser enviada ao frontend nem versionada. Foi realizada uma rotação de chave e verificado que a nova era aceita e a anterior rejeitada.

## 12. Evolução da modelagem relacional

Os bancos continuam logicamente independentes, hospedados na mesma instância MariaDB no ambiente acadêmico.

| Banco / tabela | Alteração | Motivo |
|---|---|---|
| Clínica / `veterinario` | `token_confirmacao_hash`, `token_confirmacao_expira`, `data_confirmacao` | Confirmar e-mail com prazo e uso único |
| Clínica / `token_revogado` | Nova tabela, PK `jti`, FK para veterinário e datas de revogação e expiração | Invalidar JWT no servidor |
| Clínica / `integracao_governo` | `payload_original JSON NOT NULL` | Preservar o conteúdo exato para reenvio |
| Governo / `animal_registrado` | `versao_origem` e unicidade do microchip | Ordenar atualizações e impedir duplicidade de RFID |
| Governo / `operacao_recebida` | `payload_hash` | Identificar reutilização conflitante da chave |
| Governo / `vacina_antirrabica_registrada` | `id_registro` passa a aceitar NULL; `id_animal_clinica` obrigatório e indexado | Receber vacina mesmo antes do cadastro governamental do animal |

A clínica passou de 10 para 11 tabelas; o governo mantém 3. Foram feitos backups antes das alterações e os scripts de schema foram atualizados. A restauração dos backups e uma instalação limpa completa dos scripts finais ainda precisam ser verificadas. O DER deve refletir essas mudanças; sua atualização gráfica é uma etapa separada.

## 13. Integração confiável entre os serviços

### 13.1 Persistência antes da comunicação

O fluxo foi revisado para evitar que uma operação clínica seja gravada sem o correspondente registro de integração:

1. Validar os dados e iniciar uma transação no banco da clínica.
2. Gravar o animal, vínculo de microchip ou vacina, conforme a operação.
3. Quando houver integração obrigatória, gravar `integracao_governo` com status `PENDENTE`, UUID de idempotência e `payload_original`, na mesma transação.
4. Confirmar a transação local (`commit`).
5. Tentar o POST ao governo com a API Key e timeout de 5 segundos.
6. Atualizar o estado da integração conforme a resposta, sem desfazer o registro clínico já confirmado.

Essa abordagem se aproxima do padrão *transactional outbox*. O envio inicial é síncrono, após o commit; não há worker ou fila externa nem retentativa automática em segundo plano. A indisponibilidade pode aumentar a latência da resposta, mas não deve causar perda do registro local.

### 13.2 Estados e reenvio

| Estado | Significado |
|---|---|
| `PENDENTE` | Aguardando envio ou nova tentativa após falha transitória |
| `ENVIADO` | Tentativa em processamento, ainda sem confirmação definitiva |
| `CONFIRMADO` | Protocolo recebido e confirmação persistida |
| `FALHA` | Erro registrado, por exemplo rejeição do pedido pelo governo |

O serviço incrementa `tentativas`, registra `ultima_tentativa` e controla a aquisição da tentativa por atualização condicional no banco. Uma tentativa `ENVIADO` antiga pode ser recuperada após a janela de dois minutos. A interface utiliza `pode_reenviar` para determinar a disponibilidade da ação. O reenvio reutiliza o payload e a chave originais; uma integração confirmada não pode ser reenviada pela rota da clínica.

### 13.3 Idempotência, concorrência e versionamento

O governo registra a chave de idempotência, o hash do conteúdo e o protocolo. A repetição do mesmo conteúdo com a mesma chave deve retornar o protocolo original; a reutilização da chave com conteúdo diferente deve ser rejeitada. Restrições de unicidade e transações complementam as verificações da aplicação.

O identificador da integração local é usado como `versao_origem` nos envios de animal. O objetivo é impedir que uma atualização antiga, reenviada posteriormente, sobrescreva uma versão mais recente. Essa estratégia pressupõe uma origem clínica única, como neste projeto acadêmico; múltiplas clínicas exigiriam identificação de origem e regras adicionais. A validação isolada de todos os conflitos de versão e cenários concorrentes não está demonstrada neste documento.

### 13.4 Vacinação antirrábica independente

Toda vacina antirrábica aplicada deve ser registrada no governo, mesmo quando o animal ainda não possui cadastro governamental. A vacina mantém o identificador de origem do animal e pode ter `id_registro` nulo até a associação posterior. Vacinas não antirrábicas permanecem apenas no banco clínico. Campos essenciais de uma vacina já integrada não podem ser alterados livremente, evitando divergência entre os serviços; não foi implementado um fluxo específico de retificação governamental.

## 14. Evolução do frontend

- `login.html`: formulário de confirmação de e-mail, além do cadastro e login.
- `js/auth.js`: logout com chamada à API e limpeza da sessão local.
- `index.html`: indicadores de tutores, animais e integrações confirmadas ou não confirmadas.
- `integracoes.html`: indicadores por estado, filtro, protocolo, tentativas, datas e ação de reenvio quando elegível.

A interface continua utilizando HTML, CSS e JavaScript, com Fetch API e JWT. A API privada concentra as regras de negócio; o navegador não acessa diretamente o banco nem recebe a chave governamental.

## 15. Validações acompanhadas no ambiente real

Os testes abaixo foram executados durante a revisão de 25/11/2026 com as APIs locais e MariaDB. São evidências de cenários específicos, não uma certificação de cobertura integral.

| Cenário | Resultado observado |
|---|---|
| Cadastro sem confirmação | Cadastro criado; login bloqueado |
| Confirmação inválida, válida e repetida | Token inválido rejeitado; válido aceito; reutilização rejeitada |
| Login e senha incorreta | Login válido aceito; senha incorreta rejeitada |
| Veterinário inativo | Login e acesso com JWT anteriormente emitido bloqueados |
| JWT ausente ou adulterado | Acesso protegido rejeitado |
| Logout | JWT revogado e reutilização rejeitada; novo login permitido |
| Rotação da API Key | Nova chave aceita; antiga rejeitada |
| Vacina não antirrábica (INT-07) | Registro local sem integração governamental |
| Governo desligado (INT-08) | HTTP 201 na clínica, vacina persistida e integração pendente |
| Reenvio após recuperação (INT-09) | Integração confirmada com protocolo e duas tentativas |
| Reenvio de integração confirmada (INT-10) | HTTP 409; registro governamental não duplicado no cenário |
| Cadastro e confirmação pelo frontend | Fluxo concluído, login e acesso ao painel |
| Indisponibilidade e recuperação pelo frontend | Vacina persistida, integração pendente e posterior confirmação |
| Swagger governamental | Consulta autenticada de animal retornou HTTP 200 |

### Evidência de recuperação pelo Postman

A vacina local de ID 3 foi registrada durante a indisponibilidade governamental. A integração de ID 5 permaneceu `PENDENTE`, com uma tentativa e sem protocolo. Após reiniciar a API governamental, o reenvio confirmou a mesma integração, com duas tentativas. Uma nova solicitação de reenvio retornou 409. A consulta aos bancos confirmou um único registro governamental para a vacina nesse cenário.

### Evidência de recuperação pelo frontend

Com a API governamental desligada, foi cadastrada a vacina local de ID 4 (lote fictício `RAIVA-FRONTEND-001`). A integração de ID 7 ficou pendente, com uma tentativa. Após reiniciar o governo, o botão Reenviar confirmou a operação com duas tentativas. A conferência SQL identificou a vacina nos dois bancos, com protocolo correspondente e erro limpo. O painel passou de seis integrações confirmadas e uma pendente para sete confirmadas.

### Limites da validação

Os testes foram manuais e roteirizados, com Postman, Swagger, navegador e consultas SQL. A compilação sintática de arquivos Python não substitui testes funcionais. O relatório final deve relacionar cada requisito obrigatório à evidência correspondente, inclusive CPF duplicado, CEP válido/inválido, histórico clínico e duplicidade de microchip. Não se deve considerar todos os casos aprovados apenas pela existência de uma rota ou coleção. Não foram demonstrados testes de carga, concorrência exaustiva, instalação limpa ou restauração de backup.

## 16. Documentação e preparação da entrega

A especificação Swagger/OpenAPI 3.0 foi atualizada para a versão 1.2.0. A documentação exibida contém 27 caminhos e 46 operações HTTP na clínica e 5 caminhos e 5 operações no governo, totalizando 32 caminhos e 51 operações documentadas. Esses números representam a especificação, não a quantidade de testes aprovados.

As coleções Postman estão organizadas em `docs/postman/`: API da clínica, API governamental e testes de integração. Antes da entrega, revisar os arquivos exportados para remover credenciais reais, tokens e dados pessoais; utilizar variáveis de ambiente e dados fictícios. As evidências devem ser organizadas em `docs/evidencias/`.

O README e o Guia do Projeto foram revisados. A atualização gráfica do DER, o relatório de testes, a documentação acadêmica e a apresentação final permanecem como etapas de fechamento. O cronograma original termina em 26/11/2026.

## 17. Decisões técnicas atuais para a banca

| Decisão | Justificativa |
|---|---|
| Duas APIs e dois bancos lógicos | Separar responsabilidades e demonstrar comunicação distribuída |
| JWT com verificação no banco | Bloquear usuários inativos e sessões revogadas |
| Confirmação simulada de e-mail | Atender ao fluxo acadêmico sem infraestrutura SMTP |
| API Key entre serviços | Restringir endpoints governamentais de negócio |
| Transação local e payload persistido | Preservar dados e permitir recuperação de falhas |
| Idempotência e hash | Evitar duplicação e detectar conteúdo conflitante |
| Versionamento de origem | Evitar sobrescrita por mensagens antigas |
| Reenvio manual controlado | Recuperar operações sem infraestrutura adicional de filas |
| Vacina independente do cadastro governamental | Garantir a comunicação obrigatória da vacinação antirrábica |
| Inativação lógica | Preservar histórico clínico |

**Limitações acadêmicas:** execução local em HTTP, servidor Flask de desenvolvimento, e-mail simulado, JWT armazenado no navegador e ausência de monitoramento ou retentativa automática em segundo plano. Uma implantação real exigiria HTTPS, configuração de produção, gestão segura de segredos, revisão de CORS, proteção de dados pessoais e testes adicionais.
