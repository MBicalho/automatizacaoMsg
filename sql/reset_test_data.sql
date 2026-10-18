/*
    Reset completo dos dados de teste do projeto automatizacaoMsg.

    Escopo confirmado para limpeza:
      - automatizacao.HISTORICO_TENTATIVAS_ENVIO_WPP
      - automatizacao.ETAPAS_SOLICITACAO_WPP
      - automatizacao.SOLICITACOES_ENVIO_WPP
      - automatizacao.CONTROLE_ENVIO_WPP
      - automatizacao.MENSAGEM_WPP
      - automatizacao.CONTATOS_WPP
      - automatizacao.TIPO_ENVIO_WPP

    O script preserva tabelas, schemas, colunas, chaves, indices e restricoes.
    Reinsere os 3 tipos basicos de envio apos o reset.
*/
USE [AUTOMATIZACAO];
GO

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
SET NOCOUNT ON;
SET XACT_ABORT ON;
GO

IF DB_NAME() <> N'AUTOMATIZACAO'
    THROW 51000, 'Banco de dados inesperado. A limpeza foi cancelada.', 1;

DECLARE @tabelas_esperadas TABLE (nome SYSNAME PRIMARY KEY);
INSERT INTO @tabelas_esperadas (nome)
VALUES
    (N'HISTORICO_TENTATIVAS_ENVIO_WPP'),
    (N'ETAPAS_SOLICITACAO_WPP'),
    (N'SOLICITACOES_ENVIO_WPP'),
    (N'CONTROLE_ENVIO_WPP'),
    (N'MENSAGEM_WPP'),
    (N'CONTATOS_WPP'),
    (N'TIPO_ENVIO_WPP');

-- Auditoria de objetos existentes: tabelas adicionais nao entram no reset.
SELECT t.name AS tabela_encontrada
FROM sys.tables AS t
INNER JOIN sys.schemas AS s ON s.schema_id = t.schema_id
WHERE s.name = N'automatizacao'
ORDER BY t.name;

-- Nao apaga dados se alguma tabela externa depender das tabelas deste projeto.
IF EXISTS (
    SELECT 1
    FROM sys.foreign_keys AS fk
    INNER JOIN sys.tables AS filha ON filha.object_id = fk.parent_object_id
    INNER JOIN sys.schemas AS schema_filha ON schema_filha.schema_id = filha.schema_id
    INNER JOIN sys.tables AS pai ON pai.object_id = fk.referenced_object_id
    INNER JOIN sys.schemas AS schema_pai ON schema_pai.schema_id = pai.schema_id
    INNER JOIN @tabelas_esperadas AS e ON e.nome = pai.name
    LEFT JOIN @tabelas_esperadas AS origem_no_escopo ON origem_no_escopo.nome = filha.name
    WHERE schema_pai.name = N'automatizacao'
      AND (schema_filha.name <> N'automatizacao' OR origem_no_escopo.nome IS NULL)
)
    THROW 51002, 'Existe chave estrangeira de uma tabela fora do escopo. A limpeza foi cancelada.', 1;

DECLARE @contagens TABLE (
    tabela SYSNAME NOT NULL PRIMARY KEY,
    registros_antes BIGINT NOT NULL,
    registros_removidos BIGINT NULL,
    registros_depois BIGINT NULL
);

INSERT INTO @contagens (tabela, registros_antes)
SELECT N'HISTORICO_TENTATIVAS_ENVIO_WPP', COUNT_BIG(*) FROM automatizacao.HISTORICO_TENTATIVAS_ENVIO_WPP
UNION ALL
SELECT N'ETAPAS_SOLICITACAO_WPP', COUNT_BIG(*) FROM automatizacao.ETAPAS_SOLICITACAO_WPP
UNION ALL
SELECT N'SOLICITACOES_ENVIO_WPP', COUNT_BIG(*) FROM automatizacao.SOLICITACOES_ENVIO_WPP
UNION ALL
SELECT N'CONTROLE_ENVIO_WPP', COUNT_BIG(*) FROM automatizacao.CONTROLE_ENVIO_WPP
UNION ALL
SELECT N'MENSAGEM_WPP', COUNT_BIG(*) FROM automatizacao.MENSAGEM_WPP
UNION ALL
SELECT N'CONTATOS_WPP', COUNT_BIG(*) FROM automatizacao.CONTATOS_WPP
UNION ALL
SELECT N'TIPO_ENVIO_WPP', COUNT_BIG(*) FROM automatizacao.TIPO_ENVIO_WPP;

SELECT N'ANTES' AS fase, tabela, registros_antes AS registros
FROM @contagens
ORDER BY tabela;

BEGIN TRY
    BEGIN TRANSACTION;

    -- Ordem filha -> pai, respeitando as chaves estrangeiras conhecidas.
    DELETE FROM automatizacao.HISTORICO_TENTATIVAS_ENVIO_WPP;
    UPDATE @contagens SET registros_removidos = @@ROWCOUNT WHERE tabela = N'HISTORICO_TENTATIVAS_ENVIO_WPP';

    DELETE FROM automatizacao.ETAPAS_SOLICITACAO_WPP;
    UPDATE @contagens SET registros_removidos = @@ROWCOUNT WHERE tabela = N'ETAPAS_SOLICITACAO_WPP';

    DELETE FROM automatizacao.SOLICITACOES_ENVIO_WPP;
    UPDATE @contagens SET registros_removidos = @@ROWCOUNT WHERE tabela = N'SOLICITACOES_ENVIO_WPP';

    DELETE FROM automatizacao.CONTROLE_ENVIO_WPP;
    UPDATE @contagens SET registros_removidos = @@ROWCOUNT WHERE tabela = N'CONTROLE_ENVIO_WPP';

    DELETE FROM automatizacao.MENSAGEM_WPP;
    UPDATE @contagens SET registros_removidos = @@ROWCOUNT WHERE tabela = N'MENSAGEM_WPP';

    DELETE FROM automatizacao.CONTATOS_WPP;
    UPDATE @contagens SET registros_removidos = @@ROWCOUNT WHERE tabela = N'CONTATOS_WPP';

    DELETE FROM automatizacao.TIPO_ENVIO_WPP;
    UPDATE @contagens SET registros_removidos = @@ROWCOUNT WHERE tabela = N'TIPO_ENVIO_WPP';

    -- Reinicia identidades das tabelas
    DBCC CHECKIDENT ('automatizacao.HISTORICO_TENTATIVAS_ENVIO_WPP', RESEED, 0) WITH NO_INFOMSGS;
    DBCC CHECKIDENT ('automatizacao.ETAPAS_SOLICITACAO_WPP', RESEED, 0) WITH NO_INFOMSGS;
    DBCC CHECKIDENT ('automatizacao.SOLICITACOES_ENVIO_WPP', RESEED, 0) WITH NO_INFOMSGS;
    DBCC CHECKIDENT ('automatizacao.CONTROLE_ENVIO_WPP', RESEED, 0) WITH NO_INFOMSGS;
    DBCC CHECKIDENT ('automatizacao.CONTATOS_WPP', RESEED, 0) WITH NO_INFOMSGS;
    DBCC CHECKIDENT ('automatizacao.TIPO_ENVIO_WPP', RESEED, 0) WITH NO_INFOMSGS;
    -- MENSAGEM_WPP tem IDENTITY(0,1)
    DBCC CHECKIDENT ('automatizacao.MENSAGEM_WPP', RESEED, -1) WITH NO_INFOMSGS;

    -- Reinsere os tipos padrao de envio (IDs 1, 2, 3)
    INSERT INTO automatizacao.TIPO_ENVIO_WPP (DESCRICAO_TIPO_ENVIO)
    VALUES ('MENSAGEM'), ('DOCUMENTO'), ('IMAGEM');

    UPDATE @contagens
    SET registros_depois = CASE WHEN tabela = N'TIPO_ENVIO_WPP' THEN 3 ELSE 0 END;

    COMMIT TRANSACTION;

    SELECT N'DEPOIS' AS fase, tabela, registros_antes, registros_removidos, registros_depois
    FROM @contagens
    ORDER BY tabela;
END TRY
BEGIN CATCH
    IF XACT_STATE() <> 0
        ROLLBACK TRANSACTION;

    THROW;
END CATCH;
GO
