-- Dados iniciais. Pode rodar mais de uma vez (INSERT IGNORE não duplica).
USE clinica_veterinaria;

INSERT IGNORE INTO especie (nome, descricao) VALUES
  ('Cachorro', 'Cães domésticos'),
  ('Gato',     'Gatos domésticos'),
  ('Ave',      'Aves de companhia'),
  ('Coelho',   'Coelhos e similares');

-- Uma raça "SRD" (Sem Raça Definida) para cada espécie cadastrada
INSERT IGNORE INTO raca (nome, id_especie, descricao)
SELECT 'SRD', id_especie, 'Sem Raça Definida' FROM especie;

-- Veterinário de demonstração, só para o grupo conseguir logar sem
-- precisar se cadastrar primeiro. Login: dev@clinica.com / senha: clinica123
-- (troquem a senha ou apaguem este usuário antes de qualquer uso "sério").
INSERT IGNORE INTO veterinario
  (nome_completo, cpf, crmv, uf_crmv, email, telefone, senha_hash, email_confirmado)
VALUES (
  'Veterinário Demonstração', '11144477735', '00000', 'SP', 'dev@clinica.com', '11999999999',
  'scrypt:32768:8:1$dkwzih4zpJEnrFFE$09f55933ef71b6b992d56a1c52718dd143d8f63a538b60c27a907f04a6b0a8c14014bef9d40c2ff09ef4c6ef31762dec891d2f2c077b96cadc71514de13d0b66',
  1
);
