# Paquete del operador: «Ask First Pay» al PayPal AI Hackathon

Interno, en español. Sale de `main` antes de publicar el repositorio (paso 2 de la limpieza).

**Cierre oficial:** jueves 12-nov a las 12:00 hora del Pacífico, 15:00 en Bogotá.
**Plan:** enviar el **11-nov**, con un día de margen. Son cuatro actos y en total toman cerca de
una hora. Solo tú puedes hacerlos: usan tus cuentas (PayPal, YouTube, GitHub, Devpost) y tres
de ellos no se deshacen: el vídeo público, el repositorio público y el envío.

| # | Acto | Cuándo | Tiempo | Desbloquea |
|---|---|---|---|---|
| 5 | Aprobar dos depósitos en el sandbox de PayPal y correr un comando | hoy 10-nov o mañana temprano | 10 min | la evidencia de que PayPal funciona de verdad (`docs/SANDBOX_RUN.md`) |
| 6 | Subir el vídeo a YouTube como **Público** (opcional: grabar tu voz antes) | 11-nov en la mañana | 15 min (+30 con voz) | el enlace del vídeo que pide Devpost |
| 7 | Hacer público el repositorio | 11-nov, después de que yo deje la limpieza hecha | 2 min | el enlace «Try it out» y el requisito de repo público |
| 8 | Llenar el formulario de Devpost y pulsar **Submit** | 11-nov | 20 min | la entrega |

## Acto 5 — Aprobar los depósitos en el sandbox (10 minutos)

Las dos órdenes ya existen en el sandbox de PayPal: `4P84215448488980A` (cobro) y
`1AR010595L356942N` (liberación). Las creó la coordinadora el 10-nov con
`scripts/sandbox_run.py`. PayPal pide iniciar sesión con una cuenta de **comprador** del sandbox,
y esa contraseña es tuya.

1. En https://developer.paypal.com entra a «Testing Tools → Sandbox Accounts». Abre la cuenta de
   tipo **Personal** y, en «View/Edit account», copia su correo y su contraseña.
2. Abre los dos enlaces, inicia sesión con esa cuenta y pulsa «Continuar» en cada uno:
   - https://www.sandbox.paypal.com/checkoutnow?token=4P84215448488980A
   - https://www.sandbox.paypal.com/checkoutnow?token=1AR010595L356942N

   Después PayPal te manda a `localhost:8000`. Si esa página no carga, no pasa nada: la
   aprobación ya quedó registrada.
3. En la terminal de Claude Code, pega esta línea con el `!` delante:

   ```
   ! cd ~/Desarrollos/hackathon-paypal-ask-first-pay && set -a && . ./.env && set +a && .venv/bin/python scripts/sandbox_run.py --continue 4P84215448488980A --void-order 1AR010595L356942N
   ```

   Hace el cobro, el reintento con el mismo identificador y la liberación del depósito, y
   escribe `docs/SANDBOX_RUN.md` con los identificadores de PayPal, sin credenciales.

**Si los enlaces ya vencieron**, corre la misma línea sin `--continue …`: crea dos órdenes nuevas
y te da sus enlaces.

**Si no lo haces**, la entrega sigue siendo válida. El texto de Devpost dice que el camino del
sandbox está «listo para correr» y no afirma una corrida real.

## Acto 6 — El vídeo en YouTube (15 minutos)

**Estado:** VÍDEO_PENDIENTE

## Acto 7 — Hacer público el repositorio (2 minutos)

**Estado:** LIMPIEZA_PENDIENTE

## Acto 8 — El formulario de Devpost (20 minutos)

1. Abre https://paypalaihackathon.devpost.com/ con tu cuenta e inicia «Enter a Submission».
2. Llena cada campo copiando de `docs/SUBMISSION_CHECKLIST.md` → «Form fields». Lo principal:
   - **Project name:** Ask First Pay
   - **Tagline:** "Can it touch my money?" An AI front desk for clinics that can hold a PayPal deposit on its own. Only the owner's tap moves it.
   - **About the project:** pega `docs/DEVPOST.md` desde «Inspiration» hasta «What's next».
   - **Built with:** python, fastapi, jinja, httpx, paypal-orders-v2, paypal-payments-v2, anthropic-claude, ed25519, webcrypto, ag-grid
   - **Try it out:** https://github.com/cleveria-ai/ask-first-pay
   - **Video demo link:** el enlace público de YouTube del acto 6.
   - **Image gallery:** las imágenes de `docs/screenshots/`, en el orden de la lista.
   - **Sponsor prize AG Grid:** pega la sección *Built with AG Grid* de `docs/DEVPOST.md`.
   - **País, tipo de participante, equipo, impuestos:** solo tú. Softronica entra como
     organización y tú como representante. Colombia no está entre los países excluidos
     (línea 115 de las reglas).
3. Acepta los términos y pulsa **Submit**. Devpost permite editar el envío hasta el cierre.

## Glosario

- **Sandbox:** el entorno de pruebas de PayPal, con dinero ficticio.
- **Orden y depósito retenido:** el cliente aprueba un pago que queda retenido, no cobrado; el
  dueño decide después si se cobra o se libera.
- **Limpieza previa:** sacar de la rama principal las notas internas (encargos, revisiones de
  jueces, notas en español) antes de que el repositorio sea público.
