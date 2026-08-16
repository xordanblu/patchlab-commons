<p align="center">
  <img src="docs/assets/logo.svg" width="680" alt="PatchLab Commons">
</p>

<p align="center">
  <strong>Verificación con evidencia para cambios de software.</strong><br>
  Compara dos revisiones de Git. Revisa capacidades nuevas. Ejecuta controles limitados. Crea un Patch Passport portátil.
</p>

<p align="center">
  <a href="README.md">English</a> ·
  <a href="docs/ARCHITECTURE.md">Arquitectura</a> ·
  <a href="docs/GITHUB_ACTION.md">GitHub Action</a> ·
  <a href="docs/PATCH_PASSPORT_SPEC.md">Especificación</a> ·
  <a href="docs/THREAT_MODEL.md">Modelo de amenazas</a> ·
  <a href="SECURITY.md">Seguridad</a>
</p>

> **Estado:** `0.2.0` Alpha. El flujo principal funciona y tiene pruebas. PatchLab registra evidencia. No demuestra que un cambio sea correcto, completo o libre de vulnerabilidades. La revisión humana sigue siendo obligatoria.

## Por qué existe PatchLab

Una solicitud de cambios puede verse correcta y seguir siendo insegura.

La misma persona o el mismo agente puede escribir el cambio, agregar una prueba débil y declarar que todo funciona. Un diff de líneas tampoco responde preguntas importantes:

- ¿El defecto existía antes del cambio?
- ¿La misma reproducción pasa después del cambio?
- ¿Se eliminaron, omitieron o debilitaron pruebas?
- ¿El cambio agregó permisos de escritura, red, secretos, binarios o dependencias?
- ¿Qué commits, política y límite de ejecución produjeron el resultado?

PatchLab registra esas respuestas como evidencia que un mantenedor puede revisar.

## Qué produce PatchLab

```text
.patchlab/out/
├── report.json                     fuente legible por programas
├── report.md                       resumen para el mantenedor
├── results.sarif                   hallazgos SARIF 2.1.0
├── passport.json                   identidad y manifiesto de artefactos
├── patchlab-passport.tar.gz        paquete portátil de evidencia
└── patchlab-passport.tar.gz.sha256 valor externo de integridad
```

Un **Patch Passport** une los commits, la política confiable, el límite de ejecución, los comandos, los hallazgos, los tamaños y las huellas SHA-256 en un archivo limitado.

## Capacidades principales

### Reproducir antes y después

Un comando puede exigir que el defecto falle en la revisión base y pase en la revisión candidata.

```toml
[[commands]]
name = "regression"
command = ["python", "-m", "unittest", "tests.test_regression"]
run_on = "both"
expected_exit = "base_nonzero_head_zero"
timeout_seconds = 120
required = true
```

### Mantener la política independiente

En una solicitud de cambios, PatchLab carga `patchlab.toml` desde la **revisión base**. El candidato no puede reemplazar en silencio la política que lo evalúa.

PatchLab crea las copias desde los objetos de árbol y archivo de Git. No usa filtros de checkout, hooks, worktrees ni `git archive`. Una regla `export-ignore` controlada por el candidato no puede quitar archivos de la copia ejecutada.

### Detectar riesgos de revisión

Las reglas deterministas revisan:

- archivos y líneas fuera del alcance permitido;
- manifiestos y archivos de bloqueo de dependencias;
- cambios de GitHub Actions;
- permisos de escritura y `pull_request_target`;
- credenciales persistentes del checkout;
- acciones externas sin commit fijo;
- scripts descargados y ejecutados directamente;
- archivos sensibles y posibles credenciales escritas en el código;
- posible impresión de secretos;
- clientes y direcciones nuevas de red;
- pruebas eliminadas, aserciones removidas, omisiones y silenciamiento de fallos;
- archivos binarios o generados;
- intentos de debilitar `patchlab.toml`;
- diferencias entre los metadatos de Git y el diff interpretado.

### Elegir un límite de ejecución

PatchLab tiene estos modos:

| Modo | Ejecuta código del proyecto | Uso |
|---|---:|---|
| `static` | No | Predeterminado. Revisa cambios sin ejecutar código candidato. |
| `container` | Sí | Linux con Docker o Podman y una imagen fija. |
| `auto` | Cuando existe un proveedor aislado | Falla de forma segura si necesita comandos y no hay aislamiento. |
| `native` | Sí | Solo código local confiable. Requiere aceptación explícita. |

El modo contenedor usa un usuario sin privilegios, raíz de solo lectura, código de solo lectura, capacidades Linux eliminadas, `no-new-privileges`, red bloqueada por defecto y límites de CPU, memoria, procesos, tiempo, salida y espacio temporal.

Este modo reduce el acceso directo al host. No equivale a una máquina virtual. El contenedor comparte el kernel del host.

El modo nativo es un límite débil. No impide que el código lea archivos del usuario, use la red o ataque el host. No lo uses con solicitudes de cambios desconocidas.

## Instalación

PatchLab requiere Python 3.11 a 3.14 y Git.

Desde el código fuente:

```bash
python -I -m pip install --no-deps .
patchlab --version
patchlab doctor
```

Para desarrollar:

```bash
python -I -m pip install -r requirements-dev.txt -e .
make verify
```

El paquete de ejecución no declara dependencias externas de Python.

## Inicio local

Crea una configuración y un workflow de GitHub de solo lectura:

```bash
patchlab init
```

La revisión estática no ejecuta código:

```bash
patchlab verify \
  --base HEAD~1 \
  --head HEAD \
  --config patchlab.toml \
  --config-source base \
  --execution-mode static \
  --output .patchlab/out
```

Ejecuta los comandos dentro de un contenedor aislado en Linux:

```bash
patchlab verify \
  --base HEAD~1 \
  --head HEAD \
  --config patchlab.toml \
  --config-source base \
  --execution-mode container \
  --container-runtime docker \
  --container-image 'python@sha256:<huella-de-64-caracteres>' \
  --no-network \
  --output .patchlab/out
```

La imagen debe usar una huella del registro o un ID local inmutable.

Verifica un paquete recibido:

```bash
patchlab verify-passport .patchlab/out/patchlab-passport.tar.gz
```

## Configuración

```toml
[project]
name = "example-project"

[execution]
mode = "static"
container_runtime = "auto"
container_image = ""
network = false
memory_mb = 1024
cpus = 1.0
pids_limit = 128
tmpfs_mb = 64
allow_unsafe_native = false

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
```

Las decisiones son `allow`, `review` o `deny`. PatchLab rechaza claves desconocidas. Un error de escritura no puede elegir un valor más débil en silencio.

Consulta [`docs/RULES.md`](docs/RULES.md) y [`examples/patchlab.toml`](examples/patchlab.toml).

## GitHub Action

Usa una acción publicada o un checkout confiable separado. No uses `uses: ./` desde el repositorio candidato para revisar una solicitud no confiable.

```yaml
- uses: xordanblu/patchlab-commons@d152f4a4dc806359006e668e306ceb1d0c2bcfb5
  id: patchlab
  with:
    base: ${{ github.event.pull_request.base.sha }}
    head: ${{ github.event.pull_request.head.sha }}
    repository: .
    config: patchlab.toml
    config-source: base
    execution-mode: static
    output: .patchlab/out
    fail-on-review: "true"
```

El ejemplo fija la implementación endurecida a un SHA completo. Revisa ese commit antes de usarlo.

El workflow debe usar `pull_request`, permisos de solo lectura, historial completo y credenciales no persistentes. No debe entregar secretos al código candidato.

```yaml
permissions:
  contents: read

- uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
  with:
    fetch-depth: 0
    persist-credentials: false
```

Consulta [`examples/github-action.yml`](examples/github-action.yml) y [`docs/GITHUB_ACTION.md`](docs/GITHUB_ACTION.md).

## Demostraciones

Una corrección válida debe pasar:

```bash
python -I scripts/run_demo.py --output .patchlab/demo
patchlab verify-passport .patchlab/demo/patchlab-passport.tar.gz
```

Un workflow con privilegios debe fallar y producir evidencia válida:

```bash
python -I scripts/run_attack_demo.py --output .patchlab/blocked-demo
patchlab verify-passport .patchlab/blocked-demo/patchlab-passport.tar.gz
```

Los resultados listos para revisar están en [`examples/sample-passport`](examples/sample-passport) y [`examples/blocked-passport`](examples/blocked-passport).

## Límite de seguridad

PatchLab protege el coordinador contra formas comunes de sustitución de módulos Python y variables hostiles de Git. La acción inicia Python en modo aislado y sin `site`. Solo importa el código incluido con la acción. No ejecuta `pip` durante el arranque.

Git usa un entorno mínimo y no interactivo. Las copias tienen límites de archivos, tamaño, rutas, modos y enlaces simbólicos.

El coordinador confiable escribe y verifica la evidencia final fuera del contenedor no confiable.

Lee [`docs/THREAT_MODEL.md`](docs/THREAT_MODEL.md), [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) y [`SECURITY.md`](SECURITY.md) antes de usar PatchLab en una revisión sensible.

## Desarrollo y validación

```bash
make compile
make test
make coverage
make demos
make checks
```

El CI está configurado para Python 3.11, 3.12, 3.13 y 3.14 en Linux, macOS y Windows. Otros trabajos revisan cobertura, paquetes, resistencia del arranque de la acción, aislamiento real en Linux, demostraciones y CodeQL.

Un control remoto solo es autoritativo cuando se ejecuta en GitHub. [`docs/VALIDATION.md`](docs/VALIDATION.md) separa la evidencia local de la evidencia remota.

## Principios

1. **Evidencia antes que confianza.** Una afirmación no es una prueba.
2. **Política independiente.** El cambio no define su propia aprobación.
3. **Fallo seguro.** La falta de aislamiento no se convierte en ejecución nativa.
4. **Permisos mínimos.** La revisión normal usa acceso de solo lectura.
5. **Decisiones deterministas.** La lógica principal no necesita un modelo de IA.
6. **Autoridad humana.** El mantenedor conserva la decisión final.
7. **Registros portátiles.** La evidencia funciona fuera de una sola plataforma.
8. **Acceso bilingüe.** La documentación principal existe en inglés y español.
9. **Sin adopción falsa.** El impacto requiere uso comprobado.

## Licencia

Apache License 2.0. Consulta [`LICENSE`](LICENSE).
