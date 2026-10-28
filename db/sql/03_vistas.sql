-- Vistas de consulta (se recrean en cada migración). v_finalidad_mes es MATERIALIZADA: se calcula una
-- vez y se refresca al cargar datos (scripts/cargar_mef.py); así cada consulta tarda milisegundos.

-- Situación presupuestal de cada finalidad al cierre de cada mes.
-- Saldo al mes m = PIM vigente a la fecha de corte - certificación acumulada de enero a m.
-- El PIM se publica solo como monto anual (MES_EJE = 0): no hay PIM histórico mes a mes.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'datos' AND c.relname = 'v_finalidad_mes' AND c.relkind = 'v') THEN
        EXECUTE 'DROP VIEW datos.v_finalidad_mes';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
               WHERE n.nspname = 'datos' AND c.relname = 'v_finalidad_mes' AND c.relkind = 'm') THEN
        EXECUTE 'DROP MATERIALIZED VIEW datos.v_finalidad_mes';
    END IF;
END $$;

CREATE MATERIALIZED VIEW datos.v_finalidad_mes AS
WITH marco AS (
    SELECT anio, finalidad, sum(pia) AS pia, sum(pim) AS pim
    FROM datos.ejecucion_presupuestal
    GROUP BY anio, finalidad
),
nombre AS (
    SELECT DISTINCT ON (anio, finalidad) anio, finalidad, nombre_meta
    FROM datos.ejecucion_presupuestal
    WHERE nombre_meta IS NOT NULL
    ORDER BY anio, finalidad, pim DESC, mes
),
flujo AS (
    SELECT anio, finalidad, mes,
           sum(certificado) AS certificado, sum(comprometido_anual) AS comprometido_anual,
           sum(devengado) AS devengado, sum(girado) AS girado
    FROM datos.ejecucion_presupuestal
    WHERE mes BETWEEN 1 AND 12
    GROUP BY anio, finalidad, mes
),
grilla AS (
    SELECT m.anio, m.finalidad, g.mes
    FROM marco m CROSS JOIN generate_series(1, 12) AS g(mes)
)
SELECT g.anio,
       g.mes,
       g.finalidad,
       n.nombre_meta,
       m.pia,
       m.pim,
       coalesce(f.certificado, 0)                                   AS certificado_mes,
       sum(coalesce(f.certificado, 0)) OVER w                       AS certificado_acum,
       sum(coalesce(f.comprometido_anual, 0)) OVER w                AS comprometido_acum,
       coalesce(f.devengado, 0)                                     AS devengado_mes,
       sum(coalesce(f.devengado, 0)) OVER w                         AS devengado_acum,
       sum(coalesce(f.girado, 0)) OVER w                            AS girado_acum,
       m.pim - sum(coalesce(f.certificado, 0)) OVER w               AS saldo,
       round(100 * sum(coalesce(f.devengado, 0)) OVER w / nullif(m.pim, 0), 2) AS avance_devengado_pct
FROM grilla g
JOIN marco m USING (anio, finalidad)
LEFT JOIN nombre n USING (anio, finalidad)
LEFT JOIN flujo f USING (anio, finalidad, mes)
WINDOW w AS (PARTITION BY g.anio, g.finalidad ORDER BY g.mes);

CREATE UNIQUE INDEX v_finalidad_mes_idx ON datos.v_finalidad_mes (anio, mes, finalidad);

COMMENT ON MATERIALIZED VIEW datos.v_finalidad_mes IS
  'Por finalidad y mes: PIM anual, certificación/compromiso/devengado acumulados al cierre del mes, saldo (PIM - certificación acumulada) y avance de ejecución';
