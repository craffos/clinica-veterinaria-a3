-- ============================================================
-- Banco da clínica: clinica_veterinaria (MariaDB / XAMPP)
-- Baseado no DER "A3 DER - Clínica Veterinária".
--
-- Projeto A3 - Sistemas Distribuídos e Mobile
--
-- Criação da estrutura do banco de dados.
-- Inclui autenticação, confirmação de cadastro e revogação JWT.
-- Inclui Transactional Outbox com payload original persistido.
--
-- Utiliza IF NOT EXISTS para preservar tabelas existentes.
-- Este script não altera a estrutura de tabelas já criadas.
-- Bancos de versões anteriores exigem migração específica.
-- ============================================================

CREATE DATABASE IF NOT EXISTS clinica_veterinaria
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

USE clinica_veterinaria;

-- ============================================================
-- CADASTRO
-- ============================================================

CREATE TABLE IF NOT EXISTS endereco (
  id_endereco  INT AUTO_INCREMENT PRIMARY KEY,
  cep          CHAR(8)      NOT NULL,
  logradouro   VARCHAR(150) NOT NULL,
  numero       VARCHAR(15)  NOT NULL,
  complemento  VARCHAR(100)  NULL,
  bairro       VARCHAR(100)  NOT NULL,
  cidade       VARCHAR(100)  NOT NULL,
  uf           CHAR(2)      NOT NULL,
  codigo_ibge  CHAR(7)      NULL
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS tutor (
  id_tutor       INT AUTO_INCREMENT PRIMARY KEY,
  nome_completo  VARCHAR(150) NOT NULL,
  cpf            CHAR(11)     NOT NULL,
  dt_nasc        DATE         NULL,
  email          VARCHAR(120) NULL,
  telefone       VARCHAR(20)  NULL,
  id_endereco    INT          NOT NULL,
  data_cadastro  DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ativo          TINYINT(1)   NOT NULL DEFAULT 1,

  CONSTRAINT uk_tutor_cpf UNIQUE (cpf),

  CONSTRAINT fk_tutor_endereco
    FOREIGN KEY (id_endereco)
    REFERENCES endereco (id_endereco)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS especie (
  id_especie  INT AUTO_INCREMENT PRIMARY KEY,
  nome        VARCHAR(60)  NOT NULL,
  descricao   VARCHAR(255) NULL,
  ativo       TINYINT(1)   NOT NULL DEFAULT 1,

  CONSTRAINT uk_especie_nome UNIQUE (nome)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS raca (
  id_raca     INT AUTO_INCREMENT PRIMARY KEY,
  nome        VARCHAR(80)  NOT NULL,
  id_especie  INT          NOT NULL,
  descricao   VARCHAR(255) NULL,
  ativo       TINYINT(1)   NOT NULL DEFAULT 1,

  CONSTRAINT uk_raca_especie_nome
    UNIQUE (id_especie, nome),

  -- Necessário para a chave estrangeira composta de animal.
  CONSTRAINT uk_raca_id_especie
    UNIQUE (id_raca, id_especie),

  CONSTRAINT fk_raca_especie
    FOREIGN KEY (id_especie)
    REFERENCES especie (id_especie)
) ENGINE=InnoDB;


CREATE TABLE IF NOT EXISTS animal (
  id_animal   INT AUTO_INCREMENT PRIMARY KEY,
  nome        VARCHAR(80)  NOT NULL,
  id_especie  INT          NOT NULL,
  id_raca     INT          NOT NULL,
  sexo           ENUM('M','F') NOT NULL,
  cor            VARCHAR(80)  NULL,
  peso_atual     DECIMAL(6,2) NULL,
  dt_nasc        DATE         NULL,
  idade_estimada SMALLINT UNSIGNED NULL,
  porte       ENUM('PEQUENO','MEDIO','GRANDE') NULL,
  id_tutor    INT          NOT NULL,
  observacao  TEXT         NULL,
  ativo       TINYINT(1)   NOT NULL DEFAULT 1,

  CONSTRAINT fk_animal_tutor
    FOREIGN KEY (id_tutor)
    REFERENCES tutor (id_tutor),

  CONSTRAINT fk_animal_especie
    FOREIGN KEY (id_especie)
    REFERENCES especie (id_especie),

  -- Garante que a raça pertence à espécie escolhida.
  -- Utilizar a raça SRD quando não houver raça definida.
  CONSTRAINT fk_animal_raca_especie
    FOREIGN KEY (id_raca, id_especie)
    REFERENCES raca (id_raca, id_especie)
) ENGINE=InnoDB;


-- ============================================================
-- VETERINÁRIO E AUTENTICAÇÃO
-- ============================================================

CREATE TABLE IF NOT EXISTS veterinario (
  id_veterinario          INT AUTO_INCREMENT PRIMARY KEY,
  nome_completo           VARCHAR(150) NOT NULL,
  cpf                     CHAR(11)     NOT NULL,
  crmv                    VARCHAR(20)  NOT NULL,
  uf_crmv                 CHAR(2)      NOT NULL,
  email                   VARCHAR(120) NOT NULL,
  telefone                VARCHAR(20)  NULL,
  senha_hash              VARCHAR(255) NOT NULL,
  email_confirmado        TINYINT(1)   NOT NULL DEFAULT 0,
  ativo                   TINYINT(1)   NOT NULL DEFAULT 1,
  ultimo_acesso           DATETIME     NULL,
  data_cadastro           DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,

  -- Confirmação segura do cadastro.
  token_confirmacao_hash    CHAR(64) NULL,
  token_confirmacao_expira  DATETIME NULL,
  data_confirmacao          DATETIME NULL,

  CONSTRAINT uk_vet_cpf
    UNIQUE (cpf),

  CONSTRAINT uk_vet_email
    UNIQUE (email),

  CONSTRAINT uk_vet_crmv
    UNIQUE (crmv, uf_crmv)
) ENGINE=InnoDB;


-- ============================================================
-- REVOGAÇÃO DE TOKENS JWT
-- ============================================================
-- Armazena o identificador único (JTI) dos tokens revogados.
-- Permite invalidar sessões antes da expiração natural do JWT.
-- Não armazena o token JWT completo.
-- ============================================================

CREATE TABLE IF NOT EXISTS token_revogado (
  jti               CHAR(36) NOT NULL,
  id_veterinario    INT      NOT NULL,
  data_revogacao    DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data_expiracao    DATETIME NOT NULL,

  PRIMARY KEY (jti),

  INDEX idx_token_veterinario (id_veterinario),
  INDEX idx_token_expiracao (data_expiracao),

  CONSTRAINT fk_token_revogado_veterinario
    FOREIGN KEY (id_veterinario)
    REFERENCES veterinario (id_veterinario)
    ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;


-- ============================================================
-- ATENDIMENTO CLÍNICO
-- ============================================================

CREATE TABLE IF NOT EXISTS consulta (
  id_consulta     INT AUTO_INCREMENT PRIMARY KEY,
  id_animal       INT          NOT NULL,
  id_veterinario  INT          NOT NULL,
  data_hora       DATETIME     NOT NULL,
  motivo          VARCHAR(255) NOT NULL,
  historico       TEXT         NULL,
  sintomas        TEXT         NULL,
  diagnostico     TEXT         NULL,
  tratamento      TEXT         NULL,
  prescricao      TEXT         NULL,
  peso_consulta   DECIMAL(6,2) NULL,
  temperatura     DECIMAL(4,2) NULL,
  observacao      TEXT         NULL,

  status ENUM(
    'AGENDADA',
    'EM_ATENDIMENTO',
    'CONCLUIDA',
    'CANCELADA',
    'NAO_COMPARECEU'
  ) NOT NULL DEFAULT 'AGENDADA',

  CONSTRAINT fk_consulta_animal
    FOREIGN KEY (id_animal)
    REFERENCES animal (id_animal),

  CONSTRAINT fk_consulta_vet
    FOREIGN KEY (id_veterinario)
    REFERENCES veterinario (id_veterinario)
) ENGINE=InnoDB;


-- Uma linha representa uma vacinação agendada, aplicada ou cancelada.

CREATE TABLE IF NOT EXISTS vacina (
  id_vacina          INT AUTO_INCREMENT PRIMARY KEY,
  id_animal          INT          NOT NULL,
  id_veterinario     INT          NOT NULL,
  nome_vacina        VARCHAR(100) NOT NULL,
  tipo_vacina VARCHAR(80) NULL,

  -- Vacinas antirrábicas devem ser enviadas à API governamental.
  antirrabica        TINYINT(1)   NOT NULL DEFAULT 0,

  fabricante         VARCHAR(100) NULL,
  lote               VARCHAR(50)  NULL,
  validade_lote DATE NULL,
  data_aplicacao     DATE         NOT NULL,
  dose               VARCHAR(30)  NULL,
  via_administracao  VARCHAR(30)  NULL,
  proxima_dose       DATE         NULL,
  observacao         TEXT         NULL,
  status ENUM('AGENDADA','APLICADA','CANCELADA') NOT NULL DEFAULT 'APLICADA',

  CONSTRAINT fk_vacina_animal
    FOREIGN KEY (id_animal)
    REFERENCES animal (id_animal),

  CONSTRAINT fk_vacina_vet
    FOREIGN KEY (id_veterinario)
    REFERENCES veterinario (id_veterinario)
) ENGINE=InnoDB;


-- ============================================================
-- IDENTIFICAÇÃO E HISTÓRICO DE MICROCHIPS
-- ============================================================
-- Preserva o histórico dos vínculos.
-- A desvinculação é realizada alterando ativo para 0.
-- ============================================================

CREATE TABLE IF NOT EXISTS vinculo_microchip (
  id_vinculo          INT AUTO_INCREMENT PRIMARY KEY,
  id_animal           INT          NOT NULL,
  id_veterinario      INT          NOT NULL,
  numero_microchip    VARCHAR(15)  NOT NULL,
  data_vinculacao     DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data_desvinculacao  DATETIME     NULL,
  ativo               TINYINT(1)   NOT NULL DEFAULT 1,
  observacao          TEXT         NULL,

  -- Colunas geradas para controlar vínculos ativos.
  animal_ativo INT
    AS (IF(ativo = 1, id_animal, NULL)) STORED,

  chip_ativo VARCHAR(15)
    AS (IF(ativo = 1, numero_microchip, NULL)) STORED,

  CONSTRAINT uk_microchip_numero
    UNIQUE (numero_microchip),

  CONSTRAINT uk_um_vinculo_ativo_por_animal
    UNIQUE (animal_ativo),

  CONSTRAINT uk_um_vinculo_ativo_por_chip
    UNIQUE (chip_ativo),

  CONSTRAINT fk_vinculo_animal
    FOREIGN KEY (id_animal)
    REFERENCES animal (id_animal),

  CONSTRAINT fk_vinculo_vet
    FOREIGN KEY (id_veterinario)
    REFERENCES veterinario (id_veterinario)
) ENGINE=InnoDB;


-- ============================================================
-- INTEGRAÇÃO GOVERNAMENTAL
-- ============================================================
-- Acompanha as operações enviadas à API governamental simulada.
-- A API governamental possui banco de dados independente.
-- ============================================================

CREATE TABLE IF NOT EXISTS integracao_governo (
  id_integracao       INT AUTO_INCREMENT PRIMARY KEY,
  id_animal           INT          NOT NULL,
  id_vacina           INT          NULL,

  tipo_operacao ENUM(
    'CADASTRO_ANIMAL',
    'ATUALIZACAO_ANIMAL',
    'VACINA_ANTIRRABICA'
  ) NOT NULL,

  status ENUM(
    'PENDENTE',
    'ENVIADO',
    'CONFIRMADO',
    'FALHA'
  ) NOT NULL DEFAULT 'PENDENTE',

  chave_idempotencia  VARCHAR(100) NOT NULL,
  payload_original    JSON         NOT NULL,
  protocolo           VARCHAR(60)  NULL,
  tentativas          INT          NOT NULL DEFAULT 0,
  data_criacao        DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  ultima_tentativa    DATETIME     NULL,
  data_confirmacao    DATETIME     NULL,
  mensagem_erro       VARCHAR(500) NULL,

  CONSTRAINT uk_integracao_idempotencia
    UNIQUE (chave_idempotencia),

  CONSTRAINT fk_integracao_animal
    FOREIGN KEY (id_animal)
    REFERENCES animal (id_animal),

  CONSTRAINT fk_integracao_vacina
    FOREIGN KEY (id_vacina)
    REFERENCES vacina (id_vacina)
) ENGINE=InnoDB;


-- ============================================================
-- FIM DO SCRIPT
-- Total: 11 tabelas
-- ============================================================
