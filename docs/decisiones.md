# Decisiones técnicas que afectan el texto de la tesis

Registro de decisiones del código que precisan, corrigen o amplían lo escrito en la tesis.
Cada una debe trasladarse al documento (columna «Dónde»).

| # | Decisión | Motivo | Dónde actualizar la tesis |
|---|---|---|---|
| D1 | Población: 10 512 órdenes ≤ 8 UIT (10 467 sin anuladas), no 10 624 | 112 órdenes derivan de procedimientos de selección | 1.1, 1.7.1, 3.1.1, 3.4, 4.5.4 (prompt ya enviado a Word) |
| D2 | El filtro por monto se aplica desde ago-2024, no solo en 2025; se excluyen además las órdenes marcadas «Deviene de Procesos de Selección» | El campo «tipo de contratación» está vacío desde ago-2024 | 3.4, 3.5.2, 3.5.4, Anexo 1 |
| D3 | Entre ago-2024 y mar-2025 el estado de la orden se marca como no confiable (`estado_confiable = FALSE`) | Ninguna orden figura como devengada; en ago-dic 2024 tampoco hay anuladas ni expediente SIAF | 3.1.2, R-05, 4.5.4 |
| D4 | La expresión regular del código de finalidad acepta tres formatos: `-0000888`, `- 0006508` y el código a mitad del texto | Formatos observados en 2023-2025; con el formato único se perdía todo 2025 | 3.5.2 |
| D5 | No se «corrige la codificación»: la Ñ y las tildes llegan como «¿» desde el portal y no se pueden recuperar. Los nombres de finalidad se tomarán de la Consulta Amigable | Defecto de origen, no de lectura | 3.1.2, 3.5.4, 4.5.4 |
| D6 | **[Confirmada]** Se seudonimizan los RUC que empiezan con **10, 15 y 17** (la tesis solo menciona 10) | 15 y 17 también corresponden a personas naturales (9 órdenes) | 3.5.2, 3.7, Anexo 1 Ficha 1, RNF-07 |
| D7 | Seudónimo = `PN-` + 12 caracteres de HMAC-SHA256 con clave secreta en `.env` | Estable entre cargas (RNF-12) e irreversible sin la clave | 3.7, 4.4.4 |
| D8 | Tres esquemas: `datos` (visible para el asistente), `eval` y `auditoria` (invisibles para `asistente_ro`) | Evita que C1/C2 lean las respuestas de referencia del banco | 4.3.3 |
| D9 | **[Confirmada]** Regla de anuladas: el **conteo** las incluye y el **monto** las excluye | Interpretación de «se excluirán del cálculo del gasto, pero se conservarán para los conteos» (3.4) | 3.4, diccionario semántico de C2 |
| D10 | Consultas por meta o por estado cuyo periodo toca ago-2024 a mar-2025: la herramienta se abstiene. Las consultas sin esos filtros sí se responden, con advertencia sobre las anuladas no identificables | La abstención por «meses sin código» solo aplica a consultas que cruzan órdenes con metas | RF-15, 4.1 (controles) |
| D11 | Cuatro archivos de 2023 (ene, feb, set, dic) fueron guardados de nuevo en Excel; el manifiesto lo registra | Reproducibilidad: no son el original del portal | Volver a descargarlos o declararlo en 3.5.2 |
| D12 | LLM de desarrollo: `openai/gpt-oss-120b` en Groq, temperatura 0, semilla fija, `reasoning_effort=low`. Costo por consulta calculado a **precio de lista** (US$ 0,15 / 0,60 por millón) aunque se use el nivel gratuito | La tesis cita gpt-6.1-terra, que no está disponible | 1.7.1, 3.1.2, Tabla 15, Tabla 21 |
