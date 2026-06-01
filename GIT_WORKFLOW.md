# Cómo trabajamos con Git — Equipo Inteligencia Artificial SAGE
---

## La idea general

Git nos permite trabajar todos en el mismo código sin pisarnos. La regla central es una sola:

> **Nadie toca `main` directamente. Cada tarea vive en su propia branch.**

`main` es la versión que funciona. Tu trabajo va en una branch separada hasta que sea revisado y aprobado.

---

## Antes de arrancar (solo la primera vez)

### 1. Clonar los repos

```bash
# El backend de EVA
git clone https://github.com/SAGE-AHK/sage-agent.git
cd sage-agent

# NO CLONAR AMBOS REPOS DENTRO DEL MISMO DIRECTORIO

# El frontend de EVA
git clone https://github.com/SAGE-AHK/sage-agent-front.git
cd sage-agent-front
```

### 2. Instalar dependencias

**Backend:**
```bash
pip3 install -r requirements.txt --break-system-packages
```

**Frontend:**
```bash
npm install
```

### 3. Configurar tu identidad en Git (si nunca lo hiciste)

```bash
git config --global user.name "Tu Nombre"
git config --global user.email "tu@email.com"
```

---

## El flujo de trabajo — paso a paso

### Paso 1 — Antes de arrancar cualquier tarea, actualizate

```bash
git checkout main
git pull origin main
```

Esto asegura que partís de la versión más reciente. Hacelo siempre, aunque hayas trabajado ayer.

---

### Paso 2 — Crear una branch para tu tarea

```bash
git checkout -b feature/nombre-de-tu-tarea
```

**Ejemplos de nombres:**
```bash
git checkout -b feature/stt-web-speech-api
git checkout -b feature/tts-respuesta-voz
git checkout -b feature/endpoint-status
git checkout -b fix/token-limit-egresados
```

**Regla de nombres:**
- `feature/` → para algo nuevo
- `fix/` → para arreglar algo que está roto
- El nombre describe qué hace, no quién lo hace

---

### Paso 3 — Trabajar y commitear seguido

Cada vez que algo funciona, hacé un commit. No esperes a terminar todo.

```bash
# Ver qué archivos cambiaste
git status

# Agregar los archivos al commit
git add .

# Guardar el commit con un mensaje descriptivo
git commit -m "feat: agrega botón de micrófono al chat"
```

**Ejemplos de mensajes de commit:**
```bash
git commit -m "feat: agrega STT con Web Speech API"
git commit -m "feat: integra TTS para respuesta de EVA"
git commit -m "fix: corrige token limit en preguntas de lista"
git commit -m "docs: actualiza README con instrucciones de voz"
```

**Por qué commitear seguido:**
- Si algo se rompe, podés volver a la versión anterior
- Podemos ver el progreso paso a paso
- Es más fácil revisar muchos commits chicos que uno gigante al final

---

### Paso 4 — Subir tu branch a GitHub

```bash
git push origin feature/nombre-de-tu-tarea
```

La primera vez que pusheas una branch nueva, Git puede pedirte que confirmes. Escribí `yes` y listo.

---

### Paso 5 — Abrir un Pull Request

1. Entrás a GitHub y abrís el repo
2. Vas a ver un botón amarillo que dice **"Compare & pull request"** — hacé clic
3. Completás el formulario:
   - **Título:** qué hace tu PR en una línea
   - **Descripción:** qué hiciste, cómo lo probaste, si hay algo para tener en cuenta
4. En **Reviewers** (columna derecha), asignás a **Martín**, a **Joaco Allue** o a quien corresponda
5. Hacés clic en **"Create pull request"**

---

### Paso 6 — Esperar el review

Se va a revisar tu código y puede:
- **Aprobar y mergear** → tu código entra a `main`
- **Pedir cambios** → vas a recibir comentarios, hacés los cambios, commiteás y pusheás de nuevo en la misma branch
- **Hacer preguntas** → las responde en los comentarios del PR

> **Regla importante:** nunca mergees tu propia PR. Siempre espera a que sea revisada y mergeada por otra persona.

---

## Situaciones comunes

### "Me equivoqué en el mensaje del último commit"

```bash
git commit --amend -m "el mensaje correcto"
```

Solo si todavía no hiciste push.

### "Quiero ver qué commits hice"

```bash
git log --oneline
```

### "Quiero ver en qué branch estoy"

```bash
git branch
```

La branch actual tiene un `*` adelante.

### "Me salió un conflicto"

Un conflicto pasa cuando dos personas cambiaron la misma línea del mismo archivo. Git no sabe con cuál quedarse.

**Antes de intentar resolverlo solo, avisá en el grupo.** Es más fácil ayudar antes que después. No es algo malo — le pasa a todos.

### "Hice cambios en main por error"

No entres en pánico. Avisá antes de hacer cualquier otra cosa.

---

## Resumen rápido

```
1. git checkout main
2. git pull origin main
3. git checkout -b feature/mi-tarea
4. [trabajar, hacer cambios]
5. git add .
6. git commit -m "feat: descripción"
7. git push origin feature/mi-tarea
8. Abrir Pull Request en GitHub → asignar a Martín
```

---

## Reglas del equipo

- Nunca pushear directo a `main`
- Una branch por tarea — no mezclar cambios de cosas distintas
- El PR tiene que tener descripción, no solo el código
- Si algo se rompe o no sabés cómo seguir, avisá en el grupo antes de pushear
- Si no sabés algo, preguntá — todos estamos aprendiendo

---
