# Plan: fine-tune propio de NLI para producción (base MIT + MultiNLI)

**Estado:** plan aprobado en dirección ("usemos siempre la mejor opción", 2026-10-07).
**Nada de esto corre solo:** el entrenamiento requiere decisión explícita de cómputo del dueño.

## Por qué

El candidato actual (`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`) declara licencia MIT en sus
pesos, pero se entrenó con MultiNLI + XNLI, y XNLI es **CC BY-NC 4.0** (no comercial). Si los
pesos entrenados son obra derivada de los datos es una pregunta legal **no resuelta**; para un
producto que se vende, la postura conservadora es tratarlo como no comercial.

Decisión: mDeBERTa-xnli queda **solo como benchmark interno**; para producción se entrena un
modelo propio con procedencia limpia.

## Qué se entrena

- **Base:** `microsoft/mdeberta-v3-base` — licencia **MIT** (tarjeta del modelo). Multilingüe
  (pre-entrenado en CC100 2.5T; ver "Incertidumbres").
- **Datos:** MultiNLI (`nyu-mll/multi_nli`, 392,702 pares, inglés). Licencias por sección
  (fuente: tarjeta del dataset en HuggingFace):
  - Mayoría del corpus (todos los géneros salvo ficción): licencia **OANC** — la tarjeta la
    resume como "permite usar, modificar y compartir libremente bajo términos permisivos".
  - Ficción / Seven Swords: **CC BY-SA 3.0** (atribución + share-alike).
  - Ficción / Living History y Password Incorrect: **CC BY 3.0** (atribución), con permiso
    explícito del autor.
  - Ficción / resto: dominio público en EE.UU. ("puede tener otra licencia en otros países").
  - Nada en MultiNLI es no-comercial. **Atribución obligatoria** para las piezas CC BY / CC BY-SA.
- **Transferencia al español:** el fine-tune es solo en inglés; el modelo base es multilingüe y
  transfiere zero-shot. Referencia publicada de esta receta exacta (fine-tune solo-inglés de
  mDeBERTaV3-base): **XNLI promedio 79.8% / español 84.4%** (paper DeBERTaV3, ICLR 2023,
  arXiv:2111.09543, Tabla 6). El candidato actual publica 84.5% en es
  (tarjeta de MoritzLaurer). Son cifras de terceros, **no medidas por nosotros**: el protocolo
  de abajo mide las nuestras.
- **Hiperparámetros** (los publicados por Laurer en la tarjeta del candidato): epochs 2,
  lr 2e-5, batch 16, warmup_ratio 0.1, weight_decay 0.06. Son los defaults de
  `scripts/mnli_finetune.py`.

## Cómo se ejecuta (cuando el dueño decida el cómputo)

1. Entrenar: `python scripts/mnli_finetune.py --sample 100000 --output ~/silhouette-nli-eval/finetuned`
   (requiere `pip install torch transformers datasets`).
2. Medir (números reales, XNLI-es + esXNLI nativo):
   `python scripts/mdeberta_local_eval.py --datasets xnli,esxnli --variants baseline_minilm_int8,mdeberta_finetuned_local`
   (la variante `mdeberta_finetuned_local` lee `<workdir>/finetuned`; si no existe, falla con
   instrucciones. El workdir por defecto es `~/silhouette-nli-eval`, igual que --output).
3. Criterio de adopción: paridad o mejora en español (esXNLI) frente al baseline actual y
   frente a los números del candidato con zona gris. Si no hay paridad, **se reportan los
   números reales tal cual** y el dueño decide.

## Opciones de cómputo (estimaciones, NO medidas)

- **a) Laptop del dueño, CPU, una noche:** submuestra 100k pares x 2 épocas. Estimación burda:
  varias horas a una noche. Sin GPU confirmada.
- **b) Codespace 2-core:** más lento que la laptop; solo viable con submuestra. Consume cuota
  gratuita (~120 core-horas/mes).
- **c) Colab/Kaggle GPU gratis:** ~1-2 h, pero requiere que el dueño lo ejecute con su cuenta.
- **d) GPU pagada:** requiere permiso explícito (dinero).

Recomendación: (a) si la laptop queda libre, o (c) si se quiere velocidad.

## Incertidumbres declaradas (no resueltas)

- **Pesos como obra derivada:** si un modelo fine-tuneado es obra derivada de sus datos de
  entrenamiento (afecta a XNLI-NC en el candidato actual y a las piezas CC BY-SA en la ruta
  propia) no está legalmente resuelto.
- **OANC:** solo se leyó el resumen de la tarjeta del dataset, no el texto completo de la
  licencia OANC. Leerlo antes de la primera distribución comercial.
- **CC100 (pre-entrenamiento del base):** crawl web; la misma clase de incertidumbre upstream
  que tiene todo modelo pre-entrenado en web, incluido el candidato actual. La concesión MIT
  es de Microsoft sobre su modelo.
- **Etiquetas HF:** las licencias en tarjetas de HuggingFace son autodeclaradas por quien sube
  el artefacto.
- **esXNLI:** sin licencia propia — solo evaluación interna; nunca se redistribuye ni entra en
  el producto.
- **MultiNLI ficción / dominio público:** "en EE.UU.; puede diferir en otros países" — relevante
  si el producto opera fuera de EE.UU.
