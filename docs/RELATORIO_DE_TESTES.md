# Relatório técnico de testes

**Projeto:** Sistema Web para Gestão de Clínica Veterinária com Integração de APIs  
**Unidade curricular:** Sistemas Distribuídos e Mobile — IBMR  
**Data de consolidação:** 25/11/2026

## 1. Objetivo e metodologia

Validar os fluxos funcionais, a autenticação, a persistência relacional e a comunicação entre a API privada da clínica e a API governamental simulada. Foram realizados testes manuais com Postman, frontend web, Swagger e consultas SQL no phpMyAdmin. Os resultados foram comparados com os comportamentos esperados. O ambiente utiliza Flask, MariaDB, API da clínica na porta 5000 e API governamental na porta 5001, com bancos independentes.

## 2. Matriz de rastreabilidade dos cenários obrigatórios

Os identificadores abaixo correspondem aos prefixos dos arquivos de evidência. A matriz consolida os resultados relatados durante o desenvolvimento; a presença de um arquivo no inventário não equivale à sua auditoria visual individual.

| Nº | Cenário | Resultado esperado | Evidência | Situação relatada |
|---|---|---|---|---|
| 1 | Login ativo e confirmado | Acesso autorizado | T06 | Aprovado |
| 2 | Veterinário inativo | Acesso negado | T08, T09 corrigido | Aprovado após correção |
| 3 | E-mail não confirmado | Login negado | T02, FRONT-02 | Aprovado |
| 4 | Senha incorreta | HTTP 401 | T07 | Aprovado |
| 5 | CPF de tutor duplicado | HTTP 409, sem novo tutor ou endereço de teste | T25A/B | Aprovado |
| 6 | CEP válido | HTTP 200 e endereço | T26 | Aprovado |
| 7 | CEP inválido | HTTP 400 ou 404 conforme cenário | T27A/B | Aprovado |
| 8 | Animal e vínculo de microchip | Persistência e vínculo | INT-03, INT-04 | Aprovado |
| 9 | Microchip duplicado | HTTP 409, vínculo original preservado | T28A/B | Aprovado |
| 10 | Consulta e histórico | Cadastro, recuperação e persistência | T29A/B/C | Aprovado |
| 11 | Vacinação e próxima dose | Persistência local dos dados | INT-06, INT-07 | Aprovado |
| 12 | Cadastro e atualização governamental | Sincronização confirmada | INT-03, INT-05 | Aprovado |
| 13 | Vacinação antirrábica | Integração obrigatória após persistência | INT-06, GOV-04 | Aprovado |
| 14 | Vacinação não antirrábica | Sem integração obrigatória | INT-07 | Aprovado |
| 15 | Governo indisponível | Registro local preservado e integração pendente | INT-08 | Aprovado |
| 16 | Reenvio e idempotência | Confirmação sem duplicação | INT-09, INT-10, GOV-05 | Aprovado |

A matriz utiliza 16 grupos de cenários para consolidar os requisitos acompanhados; reenvio e idempotência são tratados conjuntamente. A correspondência literal com a lista oficial deve ser conferida antes da entrega.

## 3. Autenticação e segurança

- T00–T08: disponibilidade, cadastro, duplicidade, confirmação de e-mail simulada, rejeição de token inválido ou reutilizado, login e bloqueio de usuário inativo.
- T09: falha inicial no acesso com JWT de veterinário posteriormente inativado. A autorização foi corrigida para verificar o estado atual do veterinário no banco; o reteste confirmou o bloqueio.
- T10–T14: acesso autorizado, ausência de JWT, adulteração e emissão de nova sessão.
- T15–T20: logout, persistência da revogação, rejeição de JWT revogado, logout sem autenticação e novo login.
- T21–T24: login e logout pelo frontend, persistência da revogação e atualização da documentação Swagger.

A confirmação utiliza token temporário com hash armazenado. O logout utiliza identificador JWT (jti) e registro de revogação. A API governamental exige X-API-Key nas operações protegidas. As credenciais não devem ser incluídas na entrega.

## 4. Testes complementares da API privada

| Teste | Resultado observado | Validação |
|---|---|---|
| T25A/B | 409 Conflict | CPF 12345678909 permaneceu associado a um único tutor; nenhum endereço de teste criado |
| T26 | 200 OK, 522 ms | CEP 20040002: Avenida Rio Branco, Centro, Rio de Janeiro/RJ |
| T27A | 400 Bad Request, 5 ms | CEP 12345 rejeitado por formato |
| T27B | 404 Not Found, 486 ms | CEP 99999999 não encontrado |
| T28A | 409 Conflict, 86 ms | Microchip duplicado rejeitado |
| T28B | Consulta SQL | Vínculo original ativo; zero vínculos para Bobsney; somente integração de cadastro ID 8, confirmada |
| T29A | 201 Created, 91 ms | Consulta ID 1 criada |
| T29B | 200 OK, 82 ms | Histórico recuperado para animal ID 2, veterinário ID 5 |
| T29C | Consulta SQL | Dados clínicos persistidos, status CONCLUIDA e relacionamentos confirmados |

Os tempos são observações pontuais, não métricas de desempenho sob carga.

## 5. API governamental e integração distribuída

### 5.1 API governamental

O inventário contém GOV-01 a GOV-13: disponibilidade, chave ausente e inválida, vacinação sem cadastro prévio, idempotência, conflito de idempotência, cadastro de animal, associação posterior de vacina, atualização, consulta por microchip, duplicidade, atualização desatualizada e indisponibilidade simulada. GOV-08 e GOV-12 possuem evidências complementares. A validação independente de versão desatualizada deve ser conferida: reutilizar a mesma chave de idempotência pode testar apenas repetição de operação, e não a proteção contra versão antiga.

### 5.2 Integração entre sistemas

| Teste | Fluxo | Resultado consolidado |
|---|---|---|
| INT-01 | Disponibilidade privada | API acessível |
| INT-02 | Login | JWT obtido |
| INT-03 | Cadastro de animal | Registro e confirmação governamental |
| INT-04 | Microchip | Vínculo local e atualização governamental |
| INT-05 | Atualização cadastral | Integração confirmada |
| INT-06 | Vacina antirrábica | Persistência local e governamental |
| INT-07 | Vacina não antirrábica | Persistência local, sem integração |
| INT-08 | Governo indisponível | HTTP 201; vacina ID 3 preservada; integração ID 5 PENDENTE, uma tentativa |
| INT-09 | Reenvio após recuperação | HTTP 200; integração ID 5 CONFIRMADO, duas tentativas, registro governamental persistido |
| INT-10 | Reenvio já confirmado | HTTP 409; protocolo preservado e ausência de duplicação no cenário testado |

O registro local e a operação de integração são persistidos antes do envio HTTP. O conteúdo original e a chave de idempotência são preservados para reenvio. A indisponibilidade não impede a gravação local. O reenvio demonstrado é manual; não se afirma existência de processamento automático em segundo plano.

## 6. Frontend e documentação de API

FRONT-01 a FRONT-06 registram cadastro de veterinário, bloqueio antes da confirmação, rejeição de token inválido, confirmação válida, login e persistência da autenticação. Também foi relatado teste de indisponibilidade e reenvio pelo frontend: vacina ID 4, integração ID 7, inicialmente PENDENTE e posteriormente CONFIRMADO com duas tentativas. As evidências específicas desse último fluxo não aparecem no inventário apresentado e devem ser anexadas se disponíveis.

A documentação Swagger foi atualizada e houve teste de consulta governamental autenticada. As coleções Postman complementam a documentação e permitem repetir requisições; a execução automatizada integral das coleções não foi comprovada.

## 7. Inventário de evidências

| Diretório relativo a docs/evidencias | Arquivos | Identificadores |
|---|---:|---|
| api-clinica | 40 | T00–T29 e complementos |
| api-governo | 15 | GOV-01–GOV-13 e complementos |
| frontend | 6 | FRONT-01–FRONT-06 |
| integracao | 30 | INT-01–INT-10 e complementos |
| **Total** | **91** | |

Contagem informada pelo PowerShell em 25/11/2026. Preservam-se os nomes existentes, inclusive `api-clinica/T24_Swagger_Autenticacao_Atualizado..png` e `integracao/INT-07B-persistencia-vacina-clinica.png.png`. Os arquivos T09 com sufixos FALHA e CORRIGIDO documentam a evolução da correção, não dois testes finais aprovados.

## 8. Limitações e conclusão

Os testes acompanhados demonstram os fluxos principais de autenticação, cadastro, atendimento clínico, consulta de CEP e integração governamental, incluindo recuperação após indisponibilidade. A cobertura documental preliminar é de 16 grupos de cenários, com 91 arquivos inventariados. Não representa garantia de ausência de defeitos.

Antes da entrega, conferir individualmente as evidências e remover ou ocultar JWTs, chaves, senhas, tokens de confirmação e dados pessoais. Não foi comprovada uma instalação limpa completa, nem foram executados testes sistemáticos de carga, concorrência ou segurança ofensiva. O fallback manual do ViaCEP e a rejeição independente de atualização desatualizada devem ser conferidos caso sejam apresentados como resultados validados. O DER atualizado permanece em revisão. Este relatório consolida os resultados informados e observados na conversa, sem executar novamente o sistema.
