USE AUTOMATIZACAO;
GO

-- Migracao 002: Adiciona ID_CONTROLE_SHEETS na tabela CONTATOS_WPP
-- Permite rastrear e atualizar o contato diretamente quando telefone ou nome
-- forem alterados na linha correspondente da planilha (aba Controle).

IF COL_LENGTH('automatizacao.CONTATOS_WPP', 'ID_CONTROLE_SHEETS') IS NULL
BEGIN
    ALTER TABLE automatizacao.CONTATOS_WPP
    ADD ID_CONTROLE_SHEETS NVARCHAR(100) NULL;
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = 'IX_CONTATOS_WPP_ID_CONTROLE_SHEETS'
      AND object_id = OBJECT_ID('automatizacao.CONTATOS_WPP')
)
BEGIN
    CREATE INDEX IX_CONTATOS_WPP_ID_CONTROLE_SHEETS
    ON automatizacao.CONTATOS_WPP (ID_CONTROLE_SHEETS)
    WHERE ID_CONTROLE_SHEETS IS NOT NULL;
END
GO
