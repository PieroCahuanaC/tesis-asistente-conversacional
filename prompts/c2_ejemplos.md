Ejemplos resueltos (preguntas de práctica, distintas de las que te harán):

Ejemplo 1. Pregunta: ¿Cuánto saldo le quedaba a la meta 0304103 a fines de julio de 2023?
```sql
SELECT round(sum(pim) - coalesce(sum(certificado) FILTER (WHERE mes BETWEEN 1 AND 7), 0), 2) FROM datos.ejecucion_presupuestal WHERE finalidad = '0304103' AND anio = 2023
```

Ejemplo 2. Pregunta: ¿Cuánto saldo presupuestal tenía la meta de patrullaje municipal por sector - serenazgo al cierre de setiembre de 2024?
```sql
-- Paso 1, buscar el código de la meta por su nombre: «patrullaje municipal por sector - serenazgo» → finalidad 0106645
-- SELECT DISTINCT finalidad FROM datos.ejecucion_presupuestal WHERE anio = 2024 AND translate(lower(nombre_meta), 'áéíóúü', 'aeiouu') LIKE '%patrullaje municipal por sector - serenazgo%'
-- Paso 2, consulta principal con el código encontrado:
SELECT round(sum(pim) - coalesce(sum(certificado) FILTER (WHERE mes BETWEEN 1 AND 9), 0), 2) FROM datos.ejecucion_presupuestal WHERE finalidad = '0106645' AND anio = 2024
```

Ejemplo 3. Pregunta: ¿Cuánto se devengó en la meta 0383575 entre agosto y noviembre de 2024?
```sql
SELECT coalesce(sum(devengado), 0) FROM datos.ejecucion_presupuestal WHERE finalidad = '0383575' AND anio = 2024 AND mes BETWEEN 8 AND 11
```

Ejemplo 4. Pregunta: ¿Cuánto se comprometió en mantenimiento de infraestructura construida en el cuarto trimestre de 2024?
```sql
-- Paso 1, buscar el código de la meta por su nombre: «mantenimiento de infraestructura construida» → finalidad 0001018
-- SELECT DISTINCT finalidad FROM datos.ejecucion_presupuestal WHERE anio = 2024 AND translate(lower(nombre_meta), 'áéíóúü', 'aeiouu') LIKE '%mantenimiento de infraestructura construida%'
-- Paso 2, consulta principal con el código encontrado:
SELECT coalesce(sum(comprometido_anual), 0) FROM datos.ejecucion_presupuestal WHERE finalidad = '0001018' AND anio = 2024 AND mes BETWEEN 10 AND 12
```

Ejemplo 5. Pregunta: ¿Cuántas órdenes de compra menores o iguales a 8 UIT se emitieron en junio de 2024 y por qué monto total?
```sql
SELECT count(*), coalesce(sum(monto_soles) FILTER (WHERE estado <> 'anulada'), 0) FROM datos.orden WHERE incluida AND anio = 2024 AND mes BETWEEN 6 AND 6 AND tipo_orden = 'O/C'
```

Ejemplo 6. Pregunta: ¿Cuáles fueron las tres metas con mayor PIM en 2024?
```sql
SELECT finalidad, sum(pim) AS v FROM datos.ejecucion_presupuestal WHERE anio = 2024  GROUP BY finalidad ORDER BY v DESC, finalidad LIMIT 3
```

Ejemplo 7. Pregunta: ¿En cuánto cambió el PIM total de la municipalidad de 2024 a 2025?
```sql
SELECT v2 - v1, round(100 * (v2 - v1) / v1, 2) FROM (SELECT sum(pim) FILTER (WHERE anio = 2024) AS v1, sum(pim) FILTER (WHERE anio = 2025) AS v2 FROM datos.ejecucion_presupuestal) t
```

Ejemplo 8. Pregunta: ¿Qué metas superan el 95 % de ejecución (devengado) de su PIM al cierre de enero de 2025?
```sql
WITH f AS (SELECT finalidad, sum(pim) AS pim, sum(devengado) FILTER (WHERE mes BETWEEN 1 AND 1) AS dev FROM datos.ejecucion_presupuestal WHERE anio = 2025 GROUP BY finalidad) SELECT finalidad FROM f WHERE pim > 0 AND round(100 * coalesce(dev, 0) / pim, 2) > 95 ORDER BY finalidad
```

Ejemplo 9. Pregunta: ¿Cuántas metas tenían una ejecución menor al 30 % de su PIM al cierre de setiembre de 2025?
```sql
WITH f AS (SELECT finalidad, sum(pim) AS pim, sum(devengado) FILTER (WHERE mes BETWEEN 1 AND 9) AS dev FROM datos.ejecucion_presupuestal WHERE anio = 2025 GROUP BY finalidad) SELECT count(*) FROM f WHERE pim > 0 AND round(100 * coalesce(dev, 0) / pim, 2) < 30
```

Ejemplo 10. Pregunta: Si el área usuaria de la meta de patrullaje municipal por sector - serenazgo pide S/ 20 000 en octubre de 2024, ¿le alcanza el saldo? ¿Cuánto sobraría o faltaría?
```sql
-- Paso 1, buscar el código de la meta por su nombre: «patrullaje municipal por sector - serenazgo» → finalidad 0106645
-- SELECT DISTINCT finalidad FROM datos.ejecucion_presupuestal WHERE anio = 2024 AND translate(lower(nombre_meta), 'áéíóúü', 'aeiouu') LIKE '%patrullaje municipal por sector - serenazgo%'
-- Paso 2, consulta principal con el código encontrado:
SELECT s, s - 20000.0, CASE WHEN s - 20000.0 >= 0 THEN 'alcanza' ELSE 'no alcanza' END FROM (SELECT round(sum(pim) - coalesce(sum(certificado) FILTER (WHERE mes BETWEEN 1 AND 10), 0), 2) AS s FROM datos.ejecucion_presupuestal WHERE finalidad = '0106645' AND anio = 2024) t
```

Ejemplo 11. Pregunta: ¿Cuál era el saldo de la meta 0000888 al cierre de marzo de 2022?
No se consulta la base: se responde «[ABSTENCIÓN]» porque 2022 está fuera del periodo de los datos (enero 2023 a diciembre 2025).

Ejemplo 12. Pregunta: ¿Cuánto se gastó en órdenes menores o iguales a 8 UIT de la meta 0215720 en setiembre de 2024?
No se consulta la base: se responde «[ABSTENCIÓN]» porque entre agosto de 2024 y marzo de 2025 las órdenes no traen código de finalidad, así que no se puede saber a qué meta pertenecen.
