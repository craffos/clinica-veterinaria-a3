-- ============================================================
-- Banco da API governamental SIMULADA: governo_simulado
-- Projeto A3 - Sistemas Distribuídos e Mobile
-- Persistência independente do banco da clínica.
-- Script de instalação; não migra tabelas existentes.
-- ============================================================

CREATE DATABASE IF NOT EXISTS governo_simulado
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE governo_simulado;

CREATE TABLE IF NOT EXISTS animal_registrado (
  id_registro         INT AUTO_INCREMENT PRIMARY KEY,
  id_animal_clinica   INT          NOT NULL,
  nome                VARCHAR(80)  NOT NULL,
  especie             VARCHAR(60)  NOT NULL,
  raca                VARCHAR(80)  NULL,
  numero_microchip    VARCHAR(15)  NULL,
  -- Impede que reenvios antigos sobrescrevam versões recentes.
  versao_origem       BIGINT UNSIGNED NOT NULL DEFAULT 0,
  protocolo           VARCHAR(60)  NOT NULL,
  data_registro       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  data_atualizacao    DATETIME     NULL,
  CONSTRAINT uk_gov_animal_clinica UNIQUE (id_animal_clinica),
  CONSTRAINT uk_gov_animal_protocolo UNIQUE (protocolo),
  CONSTRAINT uk_gov_animal_microchip UNIQUE (numero_microchip)
) ENGINE=InnoDB;

-- Aceita notificações antes do cadastro governamental do animal.
-- O vínculo local pode ser preenchido posteriormente.
CREATE TABLE IF NOT EXISTS vacina_antirrabica_registrada (
  id_registro_vacina  INT AUTO_INCREMENT PRIMARY KEY,
  id_registro         INT          NULL,
  id_animal_clinica   INT          NOT NULL,
  id_vacina_clinica   INT          NOT NULL,
  data_aplicacao      DATE         NOT NULL,
  lote                VARCHAR(50)  NULL,
  protocolo           VARCHAR(60)  NOT NULL,
  data_registro       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  numero_microchip VARCHAR(15) NULL,
  nome_animal VARCHAR(80) NULL,
  nome_vacina VARCHAR(100) NULL,
  fabricante VARCHAR(100) NULL,
  id_veterinario_clinica INT NULL,
  nome_veterinario VARCHAR(150) NULL,
  crmv VARCHAR(20) NULL,
  uf_crmv CHAR(2) NULL,
  INDEX idx_gov_vacina_animal_clinica (id_animal_clinica),
  CONSTRAINT uk_gov_vacina_clinica UNIQUE (id_vacina_clinica),
  CONSTRAINT uk_gov_vacina_protocolo UNIQUE (protocolo),
  CONSTRAINT fk_gov_vacina_animal FOREIGN KEY (id_registro)
    REFERENCES animal_registrado (id_registro)
) ENGINE=InnoDB;

-- Idempotência: preserva o protocolo e o hash SHA-256 do payload.
-- Hash nulo permitido para compatibilidade com operações antigas.
CREATE TABLE IF NOT EXISTS operacao_recebida (
  chave_idempotencia  VARCHAR(100) PRIMARY KEY,
  payload_hash        CHAR(64)     NULL,
  protocolo           VARCHAR(60)  NOT NULL,
  data_recebimento    DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- Fim do script: 3 tabelas.
