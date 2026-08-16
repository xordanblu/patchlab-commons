<p align="center">
  <img src="docs/assets/logo.svg" width="680" alt="PatchLab Commons">
</p>

<p align="center">
  <strong>Verificación con evidencia para cambios de software.</strong><br>
  Compara dos revisiones de Git. Ejecuta controles confiables. Detecta riesgos. Crea un Patch Passport portátil.
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="docs/ARCHITECTURE.md">Arquitectura</a> ·
  <a href="docs/PATCH_PASSPORT_SPEC.md">Especificación</a> ·
  <a href="docs/THREAT_MODEL.md">Modelo de amenazas</a> ·
  <a href="SECURITY.md">Seguridad</a>
</p>

> **Estado:** `0.1.0-alpha`. El flujo principal funciona y tiene pruebas. PatchLab registra evidencia. No demuestra por sí solo que un cambio sea correcto. Tampoco sustituye la revisión humana.

## Por qué existe

Una solicitud de cambios puede verse correcta y seguir siendo insegura.

La misma persona o el mismo agente puede escribir el cambio, agregar una prueba débil y declarar que todo funciona. Un diff normal tampoco responde con claridad estas preguntas:

- ¿El error existía antes del cambio?
- ¿La misma reproducción pasa después del cambio?
- ¿Se eliminaron, omitieron o debilitaron pruebas?
- ¿El cambio agregó permisos, red, secretos, binarios o dependencias?
- ¿Qué commits y qué política produjeron el resultado?

PatchLab registra las respuestas como evidencia revisable.

## Qué produce

```text
.patchlab/out/
├── report.json                     fuente principal para máquinas
├── report.md                       resumen para mantenedores
├── results.sarif                   hallazgos SARIF 2.1.0
├── passport.json                   manifiesto de integridad
├── patchlab-passport.tar.gz        paquete portátil
└── patchlab-passport.tar.gz.sha256 valor SHA-256 externo
```

Un **Patch Passport** une los commits, la política confiable, los comandos, los hallazgos, los tamaños y las huellas SHA-256.

## Capacidades principales

### Reproduce antes y después

Un comando puede estar obligado a fallar en la revisión base y pasar en la revisión nueva.

```toml
[[commands]]
name = "regression"
command = ["python", "-m", "unittest", "tests.test_regression"]
run_on = "both"
expected_exit = "base_nonzero_head_zero"
timeout_seconds = 120
required = true
```

### Ejecuta una verificación independiente

PatchLab puede ejecutar pruebas, compilaciones y scripts definidos por la política de la revisión base.

Los comandos son arreglos de argumentos. PatchLab no inicia un intérprete de comandos.

### Detecta riesgos

Las reglas actuales revisan:

- archivos y líneas fuera del alcance permitido;
- dependencias y archivos de bloqueo;
- cambios en GitHub Actions;
- permisos de escritura y `pull_request_target`;
- credenciales persistentes del checkout;
- acciones externas sin commit fijo;
- scripts remotos ejecutados de forma directa;
- archivos sensibles y posibles credenciales escritas en código;
- posible impresión de secretos;
- clientes de red y direcciones nuevas;
- pruebas eliminadas y aserciones removidas;
- omisiones, fallos esperados y ocultamiento de errores;
- archivos binarios o generados;
- intentos de debilitar `patchlab.toml` dentro del mismo cambio;
- diferencias entre los archivos reportados por Git y la evidencia que pudo analizar PatchLab.

Una **aserción** es una condición que una prueba exige como verdadera.

### Crea evidencia verificable

El paquete normaliza el orden, las fechas, el propietario, los permisos y la compresión. El verificador rechaza archivos inesperados, nombres duplicados, rutas inseguras, huellas inválidas y contenido demasiado grande.

PatchLab publica esquemas JSON estrictos para `report.json` y `passport.json`.

## Inicio local

PatchLab necesita Python 3.11 o posterior y Git.

```bash
git clone https://github.com/xordanblu/patchlab-commons.git
cd patchlab-commons
python -m pip install -e .
patchlab --version
patchlab doctor
```

Crea una configuración y un flujo de GitHub de solo lectura:

```bash
patchlab init
```

Compara dos commits:

```bash
patchlab verify \
  --base HEAD~1 \
  --head HEAD \
  --config patchlab.toml \
  --config-source base \
  --output .patchlab/out
```

Verifica un paquete recibido:

```bash
patchlab verify-passport .patchlab/out/patchlab-passport.tar.gz
```

## Dos demostraciones completas

Una corrección válida debe pasar:

```bash
python scripts/run_demo.py --output .patchlab/demo
```

Un flujo con privilegios debe fallar y producir evidencia válida:

```bash
python scripts/run_attack_demo.py --output .patchlab/blocked-demo
```

La demostración bloqueada detecta escritura, `pull_request_target`, credenciales persistentes, una acción sin commit fijo, ejecución remota y acceso nuevo a red.

Los resultados listos para revisar están en [`examples/sample-passport`](examples/sample-passport) y [`examples/blocked-passport`](examples/blocked-passport).

## Configuración

En una solicitud de cambios, PatchLab carga `patchlab.toml` desde la **revisión base**. El candidato no puede reemplazar en silencio la política que lo evalúa.

Para la primera instalación, integra `patchlab.toml` en la rama principal antes de activar el flujo de pull requests. Las siguientes ejecuciones podrán usar la política confiable de la revisión base.

```toml
[project]
name = "example-project"

[scope]
allow = ["src/**", "tests/**", "pyproject.toml", ".github/workflows/**"]
deny = ["**/*.pem", "**/*.key", ".env", ".env.*"]
max_files = 60
max_added_lines = 2500
max_deleted_lines = 2500

[policy]
dependency_changes = "review"
workflow_changes = "review"
dangerous_permissions = "deny"
secret_exposure = "deny"
network_additions = "review"
test_weakening = "deny"
binary_files = "review"
generated_files = "review"
fail_on_review = false
require_clean_worktree = false
require_human_review = true

[[commands]]
name = "tests"
command = ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
run_on = "head"
expected_exit = "zero"
timeout_seconds = 300
required = true
```

Las decisiones son `allow`, `review` o `deny`.

PatchLab rechaza claves desconocidas. Un error de escritura no puede activar un valor más débil en silencio.

Consulta [`docs/RULES.md`](docs/RULES.md) y [`examples/patchlab.toml`](examples/patchlab.toml).

## Acción de GitHub

```yaml
- uses: xordanblu/patchlab-commons@v0.1.0
  id: patchlab
  with:
    base: ${{ github.event.pull_request.base.sha }}
    head: ${{ github.event.pull_request.head.sha }}
    repository: .
    config: patchlab.toml
    config-source: base
    output: .patchlab/out
    fail-on-review: "true"
```

El checkout necesita todo el historial. No debe guardar credenciales:

```yaml
- uses: actions/checkout@11d5960a326750d5838078e36cf38b85af677262 # v4
  with:
    fetch-depth: 0
    persist-credentials: false
```

La acción agrega `report.md` al resumen del trabajo. También expone las rutas, el resultado, el código de salida y la huella del paquete.

Consulta [`examples/github-action.yml`](examples/github-action.yml) y [`docs/GITHUB_ACTION.md`](docs/GITHUB_ACTION.md).

## Límite de seguridad

PatchLab reduce las variables de entorno heredadas. Cada comando usa un directorio personal y temporal desechable. PatchLab elimina configuraciones normales del usuario, cierra la entrada estándar, limita la salida, oculta formas comunes de credenciales, aplica tiempos máximos y termina el grupo de procesos cuando el sistema lo permite.

PatchLab también desactiva hooks de Git, monitores de archivos, programas externos de diff, filtros de texto, configuración global, solicitudes interactivas y paginadores durante la inspección.

Los comandos configurados todavía ejecutan código del proyecto. Los árboles de Git separan revisiones. **No forman un aislamiento completo del sistema operativo.**

Usa trabajadores desechables. Usa un contenedor o una máquina virtual cuando el código no sea confiable. No expongas secretos a una revisión de pull request.

Las rutas de salida no pueden escapar del repositorio ni seguir enlaces simbólicos. La verificación del paquete es de solo lectura y tiene límites de tamaño.

Lee [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md).

## Principios

1. La evidencia va antes que la confianza.
2. El cambio no define su propia aprobación.
3. La verificación normal usa permisos de solo lectura.
4. Las decisiones principales no necesitan un modelo de IA.
5. El mantenedor conserva la decisión final.
6. La evidencia funciona fuera de una sola plataforma.
7. La documentación principal existe en español e inglés.
8. El impacto se demuestra con uso real. No con métricas compradas.

## Desarrollo

```bash
python -m pip install -e ".[dev]"
make compile
make coverage
make demo
make attack-demo
make build
```

El paquete normal no usa dependencias externas de Python.

CI prueba Python 3.11, 3.12 y 3.13 en Linux, macOS y Windows. También construye el paquete, mide cobertura, ejecuta las dos demostraciones y usa CodeQL.

## Documentos

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
- [`docs/PATCH_PASSPORT_SPEC.md`](docs/PATCH_PASSPORT_SPEC.md)
- [`docs/report.schema.json`](docs/report.schema.json)
- [`docs/passport.schema.json`](docs/passport.schema.json)
- [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md)
- [`docs/RULES.md`](docs/RULES.md)
- [`docs/ROADMAP.md`](docs/ROADMAP.md)
- [`docs/IMPACT.md`](docs/IMPACT.md)
- [`docs/VALIDATION.md`](docs/VALIDATION.md)
- [`GOVERNANCE.md`](GOVERNANCE.md)
- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`SUPPORT.md`](SUPPORT.md)
- [`docs/RELEASING.md`](docs/RELEASING.md)

## Licencia

Apache License 2.0. Consulta [`LICENSE`](LICENSE) y [`NOTICE`](NOTICE).
