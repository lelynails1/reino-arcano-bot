# Reino Arcano RPG — Bot 24/7 para ArcaneChat / Delta Chat

Bot de juego RPG persistente inspirado en el compendio de **Reino Arcano**, con soporte completo para:
- Verificación automática de cifrado E2EE (SecureJoin) con mensaje de bienvenida automático y `/start`.
- Barra rápida de comandos tras cada respuesta (`/yo · /menu · /guerra · /ayuda`).
- Imágenes evolutivas de Castillos al subir de nivel (5 rangos) e icono del reino.
- Mini-App interactiva `arcano.xdc` (< 40 KB) sincronizada en tiempo real con SQLite.
- Despliegue 24/7 en **Deplexo** (`deplexo.yaml` + `Dockerfile` + almacenamiento persistente en `/data`).

## Variables de Entorno (Deplexo)
- `BOT_NAME`: Nombre público del bot (ej. `Reino Arcano RPG`).
- `BOT_STATUS`: Estado del perfil.
- `BOT_DATA_DIR`: Directorio persistente (en Deplexo: `/data`).
- `BOT_ADDR` / `BOT_PASSWORD`: Opcional (si usas `seed_account/`, ya viene preconfigurado con tu cuenta `arcanechat.me`).
