-- Ficha 2 con la estructura real de los datos abiertos del MEF (diagnóstico S1).
-- Reemplaza la tabla preliminar (vacía) de la versión inicial del esquema.
DROP TABLE IF EXISTS datos.ejecucion_presupuestal CASCADE;

CREATE TABLE datos.ejecucion_presupuestal (
    id                        bigserial PRIMARY KEY,
    anio                      smallint NOT NULL,
    mes                       smallint NOT NULL CHECK (mes BETWEEN 0 AND 12),
    sec_func                  integer NOT NULL,
    finalidad                 char(7) NOT NULL,
    nombre_meta               text,
    tipo_act_proy             text CHECK (tipo_act_proy IN ('actividad', 'proyecto')),
    producto_proyecto         text,
    producto_proyecto_nombre  text,
    actividad_nombre          text,
    funcion_nombre            text,
    categoria_gasto           text,
    fuente_financiamiento     text,
    rubro                     text,
    generica_nombre           text,
    clasificador              text NOT NULL,
    clasificador_nombre       text,
    pia                       numeric(16,2) NOT NULL DEFAULT 0,
    pim                       numeric(16,2) NOT NULL DEFAULT 0,
    certificado               numeric(16,2) NOT NULL DEFAULT 0,
    comprometido_anual        numeric(16,2) NOT NULL DEFAULT 0,
    comprometido_mensual      numeric(16,2) NOT NULL DEFAULT 0,
    devengado                 numeric(16,2) NOT NULL DEFAULT 0,
    girado                    numeric(16,2) NOT NULL DEFAULT 0,
    id_carga                  integer NOT NULL REFERENCES datos.carga
);
CREATE INDEX ejecucion_finalidad_idx ON datos.ejecucion_presupuestal (anio, finalidad, mes);

COMMENT ON TABLE datos.ejecucion_presupuestal IS
  'Ejecución presupuestal de la Municipalidad Distrital de Uchumayo (Consulta Amigable del MEF), por meta, mes, fuente y clasificador';
COMMENT ON COLUMN datos.ejecucion_presupuestal.mes IS
  '0 = marco anual (PIA y PIM vigentes a la fecha de corte); 1-12 = flujos del mes (certificado, comprometido, devengado, girado)';
COMMENT ON COLUMN datos.ejecucion_presupuestal.finalidad IS 'Código de finalidad de 7 dígitos; es el que figura en las órdenes del PTE';
COMMENT ON COLUMN datos.ejecucion_presupuestal.sec_func IS 'Número de meta (secuencia funcional) del año; una finalidad puede tener varias metas';
COMMENT ON COLUMN datos.ejecucion_presupuestal.certificado IS 'Certificación del mes (puede ser negativa por rebajas)';
