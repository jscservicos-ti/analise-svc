WITH urgencias AS (
    -- BLOCO 1: Busca os pacientes que deram entrada na urgência e já receberam alta
    SELECT 
        A.CD_ATENDIMENTO AS cd_atend_urg,
        A.CD_PACIENTE,
        P.NM_PACIENTE,
        A.HR_ATENDIMENTO AS hr_atend_urg,
        A.DT_ALTA
    FROM ATENDIME A
    INNER JOIN PACIENTE P ON A.CD_PACIENTE = P.CD_PACIENTE
    WHERE A.CD_MULTI_EMPRESA IN ($HMTJ - Empresas$)
      AND A.TP_ATENDIMENTO IN ('U', 'M')
      AND A.DT_ALTA IS NOT NULL
      -- Filtro de período aplicado na data de entrada da urgência
      AND A.DT_ATENDIMENTO BETWEEN $DataIni$ AND $DataFim$
      AND UPPER(P.NM_PACIENTE) NOT LIKE '%TESTE%'
),

totem AS (
    -- BLOCO 2: Busca o horário de retirada da senha no totem (Processo 1)
    SELECT 
        TA.CD_ATENDIMENTO,
        MAX(STP.DH_PROCESSO) AS dh_senha
    FROM TRIAGEM_ATENDIMENTO TA
    INNER JOIN SACR_TEMPO_PROCESSO STP ON STP.CD_TRIAGEM_ATENDIMENTO = TA.CD_TRIAGEM_ATENDIMENTO
    WHERE STP.CD_TIPO_TEMPO_PROCESSO = 1 
    GROUP BY TA.CD_ATENDIMENTO
),

internacoes AS (
    -- BLOCO 3: Busca todos os atendimentos de internação e o leito atualizado
    SELECT 
        I.CD_ATENDIMENTO AS cd_atend_int,
        I.CD_PACIENTE,
        I.HR_ATENDIMENTO AS hr_atend_int,
        L.DS_RESUMO AS leito
    FROM ATENDIME I
    LEFT JOIN LEITO L ON I.CD_LEITO = L.CD_LEITO
    WHERE I.CD_MULTI_EMPRESA IN ($HMTJ - Empresas$)
      AND I.TP_ATENDIMENTO = 'I'
),

pares_perfeitos AS (
    -- BLOCO 4: Conecta a urgência com a internação correspondente (até 48h após a entrada)
    SELECT 
        u.cd_atend_urg,
        i.cd_atend_int,
        ROW_NUMBER() OVER (PARTITION BY u.cd_atend_urg ORDER BY i.hr_atend_int ASC) AS rn_u2i,
        ROW_NUMBER() OVER (PARTITION BY i.cd_atend_int ORDER BY u.hr_atend_urg DESC) AS rn_i2u
    FROM urgencias u
    INNER JOIN internacoes i ON u.cd_paciente = i.cd_paciente
        -- Garante que a internação aconteceu DEPOIS da entrada na urgência
        AND i.hr_atend_int > u.hr_atend_urg
        -- Limita a busca para evitar cruzar com internações de meses depois
        AND i.hr_atend_int <= u.hr_atend_urg + 2 
)

-- BLOCO 5: Montagem final do relatório com as colunas formatadas
SELECT 
    U.cd_atend_urg AS ATENDIMENTO_URGENCIA,
    TO_CHAR(U.hr_atend_urg, 'DD/MM/YYYY HH24:MI') AS DATA_HORA_URGENCIA,
    NVL(TO_CHAR(T.dh_senha, 'DD/MM/YYYY HH24:MI'), 'Sem Registro') AS DATA_HORA_TOTEM,
    
    I.cd_atend_int AS ATENDIMENTO_INTERNACAO,
    TO_CHAR(I.hr_atend_int, 'DD/MM/YYYY HH24:MI') AS DATA_HORA_INTERNACAO,
    
    U.CD_PACIENTE AS CODIGO_PACIENTE,
    U.NM_PACIENTE AS NOME_PACIENTE,
    NVL(I.leito, 'Sem Leito') AS LEITO_INTERNACAO

FROM urgencias U
-- O INNER JOIN aqui funciona como um filtro final: 
-- Só vai exibir os pacientes que existem na urgência E que tiveram sucesso no "Par Perfeito" com a internação
INNER JOIN pares_perfeitos P ON U.cd_atend_urg = P.cd_atend_urg AND P.rn_u2i = 1 AND P.rn_i2u = 1
INNER JOIN internacoes I ON P.cd_atend_int = I.cd_atend_int
LEFT JOIN totem T ON U.cd_atend_urg = T.cd_atendimento

ORDER BY 
    U.hr_atend_urg DESC