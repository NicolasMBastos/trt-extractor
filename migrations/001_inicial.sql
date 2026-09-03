-- 001_inicial.sql — esquema base do trt-extractor
--
-- Princípios que o esquema precisa garantir, não só documentar:
--
--   1. A unidade de trabalho é (numero_cnj, grau, tipo_documento). Idempotência
--      vem de UNIQUE nessa tripla — reprocessar não duplica.
--   2. A unidade de armazenamento é o sha256. Dedup entre 1º e 2º grau é
--      consequência, não código: uma cópia física, N referências lógicas.
--   3. A máquina de estados é validada por trigger, não por convenção. Um estado
--      terminal não volta atrás e uma transição ilegal falha na escrita.
--   4. SIGILOSO e INEXISTENTE são terminais LEGÍTIMOS. As views de métrica os
--      excluem do denominador de erro.
--
-- Rodar: psql -d trt_extractor -f migrations/001_inicial.sql

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------------------------------------------------------------------------
-- Vocabulário. Espelha core/contracts.py — mudar aqui exige mudar lá.
-- ---------------------------------------------------------------------------

CREATE TYPE grau AS ENUM ('1', '2', 'S');

CREATE TYPE tipo_documento AS ENUM (
    'peticao_inicial',
    'acordao',
    'sentenca',
    'acordo',
    'laudo_pericia',
    'outro'
);

CREATE TYPE estado_job AS ENUM (
    'PENDENTE',
    'SUBMETIDO',
    'GERANDO',
    'BAIXADO',
    'CLASSIFICADO',
    'ARQUIVADO',
    'FALHA_TRANSIENTE',
    'SIGILOSO',
    'INEXISTENTE',
    'FALHA_PERMANENTE'
);

CREATE TYPE via_aquisicao AS ENUM (
    'pdpj_api',
    'mni_soap',
    'autos_filtrado',
    'doc_individual',
    'browser',
    'legado'
);

CREATE TYPE metodo_classificacao AS ENUM (
    'tipo_pje',
    'posicao_fluxo',
    'keywords',
    'llm',
    'humano'
);

-- ---------------------------------------------------------------------------
-- Credenciais. Nasce da constatação de que a credencial — e não o tribunal — é
-- hoje o gargalo e o ponto de falha silenciosa (arquitetura §2, D4).
-- NUNCA guardar chave privada, senha ou PIN aqui. Só a referência ao repositório
-- do SO e a validade, para alertar antes de expirar.
-- ---------------------------------------------------------------------------

CREATE TABLE credencial (
    id                       text PRIMARY KEY,
    rotulo                   text NOT NULL,
    cpf_hash                 text NOT NULL,   -- sha256 do CPF; nunca o CPF cru
    certificado_thumbprint   text,
    certificado_expira_em    timestamptz,
    ativa                    boolean NOT NULL DEFAULT true,
    criada_em                timestamptz NOT NULL DEFAULT now()
);

COMMENT ON COLUMN credencial.cpf_hash IS
    'sha256 do CPF. Permite reconciliar sem armazenar o dado pessoal.';
COMMENT ON COLUMN credencial.certificado_expira_em IS
    'Expiração silenciosa de certificado é modo de falha real: alertar com folga.';

-- ---------------------------------------------------------------------------
-- Processo. Um processo existe por (numero_cnj, grau) — o mesmo CNJ tramita em
-- graus diferentes com conjuntos de documentos diferentes.
-- ---------------------------------------------------------------------------

CREATE TABLE processo (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    numero_cnj    char(25) NOT NULL,          -- NNNNNNN-DD.AAAA.J.TR.OOOO
    grau          grau     NOT NULL,
    tribunal      text     NOT NULL,          -- 'TRT2'; casa com capabilities.yaml
    -- Metadado existe só para saber QUAL arquivo buscar e ONDE guardar.
    -- Este não é um projeto de metadados.
    classe_codigo integer,
    tem_alvo      boolean,                    -- triagem: movimentos indicam peça-alvo?
    triado_em     timestamptz,
    criado_em     timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT processo_cnj_grau_uk UNIQUE (numero_cnj, grau),
    CONSTRAINT processo_cnj_formato_ck
        CHECK (numero_cnj ~ '^[0-9]{7}-[0-9]{2}\.[0-9]{4}\.[0-9]\.[0-9]{2}\.[0-9]{4}$')
);

CREATE INDEX processo_tribunal_ix ON processo (tribunal);
-- Triagem: achar o que ainda não foi avaliado, ou o que tem alvo e falta baixar.
CREATE INDEX processo_sem_triagem_ix ON processo (tribunal) WHERE triado_em IS NULL;

-- ---------------------------------------------------------------------------
-- Blob. Content-addressed. É o entregável do projeto.
-- ---------------------------------------------------------------------------

CREATE TABLE blob (
    sha256          char(64) PRIMARY KEY,
    tamanho_bytes   bigint NOT NULL CHECK (tamanho_bytes > 0),
    content_type    text,
    storage_uri     text NOT NULL,            -- file://... na fase <5, s3://... depois
    tem_texto       boolean,                  -- null = ainda não verificado
    ocr_estado      text NOT NULL DEFAULT 'nao_requerido'
        CHECK (ocr_estado IN ('nao_requerido','pendente','processando','concluido','falhou')),
    ocr_sha256      char(64) REFERENCES blob (sha256),  -- versão com camada de texto
    criado_em       timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE blob IS
    'Uma cópia física por conteúdo. O dedup 1º/2º grau cai fora de graça daqui.';
COMMENT ON COLUMN blob.ocr_estado IS
    'OCR nunca inline no caminho de download — fila separada, assíncrona.';

-- ---------------------------------------------------------------------------
-- Job — a máquina de estados da seção 3.3 do briefing.
-- "Completar os que faltaram petição inicial" é um SELECT aqui, não uma fila
-- especial.
-- ---------------------------------------------------------------------------

CREATE TABLE job (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    processo_id        uuid NOT NULL REFERENCES processo (id) ON DELETE CASCADE,
    numero_cnj         char(25) NOT NULL,
    grau               grau NOT NULL,
    tipo_documento     tipo_documento NOT NULL,

    estado             estado_job NOT NULL DEFAULT 'PENDENTE',
    via                via_aquisicao,
    credencial_id      text REFERENCES credencial (id),

    id_pedido          text,                  -- handle do tribunal (Área de Download)
    submetido_em       timestamptz,
    tentativas         integer NOT NULL DEFAULT 0 CHECK (tentativas >= 0),
    proxima_tentativa  timestamptz,           -- backoff exponencial com jitter
    deadline           timestamptz,
    ultimo_erro        text,

    criado_em          timestamptz NOT NULL DEFAULT now(),
    atualizado_em      timestamptz NOT NULL DEFAULT now(),

    -- Idempotência. É esta linha que garante que reprocessar não duplica.
    CONSTRAINT job_chave_uk UNIQUE (numero_cnj, grau, tipo_documento)
);

-- Fila: quem está pronto para ser pego agora. Casa com SELECT ... FOR UPDATE
-- SKIP LOCKED, que é a fila do projeto — sem Kafka, o gargalo é o tribunal.
CREATE INDEX job_fila_ix
    ON job (proxima_tentativa NULLS FIRST, criado_em)
    WHERE estado IN ('PENDENTE', 'FALHA_TRANSIENTE');

-- Poll: quem está esperando o tribunal gerar.
CREATE INDEX job_aguardando_ix ON job (submetido_em)
    WHERE estado IN ('SUBMETIDO', 'GERANDO');

CREATE INDEX job_estado_ix     ON job (estado);
CREATE INDEX job_processo_ix   ON job (processo_id);

-- ---------------------------------------------------------------------------
-- Transições legais. A máquina de estados é do banco, não da convenção.
-- ---------------------------------------------------------------------------

CREATE TABLE transicao_permitida (
    de   estado_job NOT NULL,
    para estado_job NOT NULL,
    PRIMARY KEY (de, para)
);

INSERT INTO transicao_permitida (de, para) VALUES
    -- caminho feliz
    ('PENDENTE',        'SUBMETIDO'),
    ('SUBMETIDO',       'GERANDO'),
    ('SUBMETIDO',       'BAIXADO'),      -- via síncrona (MNI, API direta)
    ('GERANDO',         'BAIXADO'),
    ('BAIXADO',         'CLASSIFICADO'),
    ('CLASSIFICADO',    'ARQUIVADO'),
    -- retry transiente: qualquer etapa não-terminal pode tropeçar e voltar
    ('PENDENTE',        'FALHA_TRANSIENTE'),
    ('SUBMETIDO',       'FALHA_TRANSIENTE'),
    ('GERANDO',         'FALHA_TRANSIENTE'),
    ('BAIXADO',         'FALHA_TRANSIENTE'),
    ('CLASSIFICADO',    'FALHA_TRANSIENTE'),
    ('FALHA_TRANSIENTE','PENDENTE'),
    ('FALHA_TRANSIENTE','SUBMETIDO'),
    ('FALHA_TRANSIENTE','FALHA_PERMANENTE'),  -- estourou o teto de tentativas
    -- terminais legítimos: descobertos ao listar ou ao submeter
    ('PENDENTE',        'SIGILOSO'),
    ('SUBMETIDO',       'SIGILOSO'),
    ('GERANDO',         'SIGILOSO'),
    ('PENDENTE',        'INEXISTENTE'),
    ('SUBMETIDO',       'INEXISTENTE'),
    ('GERANDO',         'INEXISTENTE'),
    -- dead-letter
    ('PENDENTE',        'FALHA_PERMANENTE'),
    ('SUBMETIDO',       'FALHA_PERMANENTE'),
    ('GERANDO',         'FALHA_PERMANENTE'),
    ('BAIXADO',         'FALHA_PERMANENTE'),
    ('CLASSIFICADO',    'FALHA_PERMANENTE'),
    -- revisão humana pode ressuscitar um dead-letter, e só ela
    ('FALHA_PERMANENTE','PENDENTE');

COMMENT ON TABLE transicao_permitida IS
    'ARQUIVADO, SIGILOSO e INEXISTENTE não têm saída: são terminais de verdade. '
    'FALHA_PERMANENTE só sai por reenfileiramento manual (revisão humana).';

CREATE OR REPLACE FUNCTION valida_transicao_job() RETURNS trigger AS $$
BEGIN
    IF NEW.estado = OLD.estado THEN
        NEW.atualizado_em := now();
        RETURN NEW;
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM transicao_permitida
        WHERE de = OLD.estado AND para = NEW.estado
    ) THEN
        RAISE EXCEPTION
            'transicao ilegal de % para % no job % (%/%/%)',
            OLD.estado, NEW.estado, NEW.id,
            NEW.numero_cnj, NEW.grau, NEW.tipo_documento
            USING ERRCODE = 'check_violation';
    END IF;

    NEW.atualizado_em := now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER job_valida_transicao
    BEFORE UPDATE ON job
    FOR EACH ROW EXECUTE FUNCTION valida_transicao_job();

-- ---------------------------------------------------------------------------
-- Documento — a referência lógica. N documentos podem apontar para 1 blob.
-- ---------------------------------------------------------------------------

CREATE TABLE documento (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id             uuid NOT NULL REFERENCES job (id) ON DELETE CASCADE,
    processo_id        uuid NOT NULL REFERENCES processo (id) ON DELETE CASCADE,
    sha256             char(64) REFERENCES blob (sha256),

    id_origem          text,                  -- id do documento no tribunal
    titulo             text,
    tipo_pje           text,                  -- rótulo cru, preenchido de forma
                                              -- inconsistente entre tribunais
    sequencia          integer,               -- posição na juntada: sinal forte
    polo_juntada       text,
    juntado_em         timestamptz,
    veio_de_consolidado boolean NOT NULL DEFAULT false,
    pagina_inicio      integer,               -- quando veio de split
    pagina_fim         integer,

    criado_em          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX documento_job_ix     ON documento (job_id);
CREATE INDEX documento_sha256_ix  ON documento (sha256);
CREATE UNIQUE INDEX documento_origem_uk
    ON documento (processo_id, id_origem) WHERE id_origem IS NOT NULL;

-- ---------------------------------------------------------------------------
-- Classificação. Sempre grava método e confiança.
-- ---------------------------------------------------------------------------

CREATE TABLE classificacao (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    documento_id   uuid NOT NULL REFERENCES documento (id) ON DELETE CASCADE,
    tipo           tipo_documento NOT NULL,
    metodo         metodo_classificacao NOT NULL,
    confianca      real NOT NULL CHECK (confianca >= 0 AND confianca <= 1),
    detalhe        jsonb NOT NULL DEFAULT '{}'::jsonb,
    revisao_humana boolean NOT NULL DEFAULT false,
    criada_em      timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX classificacao_documento_ix ON classificacao (documento_id);
-- Fila de revisão amostral: baixa confiança e ainda não revisado.
CREATE INDEX classificacao_revisar_ix ON classificacao (confianca)
    WHERE revisao_humana = false;

COMMENT ON COLUMN classificacao.detalhe IS
    'Para metodo=llm, guarda o veredito para não reprocessar o mesmo ambíguo.';

-- ---------------------------------------------------------------------------
-- Auditoria. Serve para debug, para demonstrar legitimidade e para LGPD.
-- ---------------------------------------------------------------------------

CREATE TABLE auditoria (
    id             bigserial PRIMARY KEY,
    ocorrido_em    timestamptz NOT NULL DEFAULT now(),
    credencial_id  text REFERENCES credencial (id),
    tribunal       text,
    numero_cnj     char(25),
    grau           grau,
    tipo_documento tipo_documento,
    via            via_aquisicao,
    acao           text NOT NULL,             -- authenticate|list|submit|poll|fetch
    resultado      text NOT NULL,             -- ok|transiente|permanente|sigiloso|...
    http_status    integer,
    duracao_ms     integer,
    detalhe        jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX auditoria_tempo_ix      ON auditoria (ocorrido_em DESC);
CREATE INDEX auditoria_credencial_ix ON auditoria (credencial_id, ocorrido_em DESC);
CREATE INDEX auditoria_processo_ix   ON auditoria (numero_cnj);

COMMENT ON TABLE auditoria IS
    'Qual credencial, qual processo, qual peça, quando, com que resultado.';

-- ---------------------------------------------------------------------------
-- Views de métrica. Existem para que SIGILOSO e INEXISTENTE não contaminem a
-- taxa de erro — eles são resultado legítimo, não falha.
-- ---------------------------------------------------------------------------

CREATE VIEW v_job_por_estado AS
SELECT p.tribunal, j.grau, j.tipo_documento, j.estado, j.via, count(*) AS total
FROM job j JOIN processo p ON p.id = j.processo_id
GROUP BY 1, 2, 3, 4, 5;

CREATE VIEW v_taxa_erro AS
SELECT
    p.tribunal,
    count(*) FILTER (WHERE j.estado = 'ARQUIVADO')          AS concluidos,
    count(*) FILTER (WHERE j.estado = 'FALHA_PERMANENTE')   AS falhas,
    count(*) FILTER (WHERE j.estado IN ('SIGILOSO','INEXISTENTE'))
                                                            AS terminais_legitimos,
    -- Denominador exclui os terminais legítimos, de propósito.
    round(
        count(*) FILTER (WHERE j.estado = 'FALHA_PERMANENTE')::numeric
        / NULLIF(count(*) FILTER (
            WHERE j.estado IN ('ARQUIVADO','FALHA_PERMANENTE')), 0),
        4
    ) AS taxa_erro
FROM job j JOIN processo p ON p.id = j.processo_id
GROUP BY 1;

COMMIT;
