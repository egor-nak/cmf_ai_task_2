# Как отправить этот репозиторий на GitHub — пошагово

Всё уже закоммичено локально (ветка `main`), а `.env` с вашим API-ключом защищён `.gitignore` и на GitHub не попадёт. Осталось создать репозиторий на GitHub и запушить.

---

## Шаг 0. Проверка (1 минута)

Откройте Терминал (Cmd+Пробел → «Terminal») и выполните:

```bash
cd ~/Claude/Projects/AI_angents_task_cmf
git status
git log --oneline | head -5
```

Ожидаемо: `On branch main`, рабочее дерево чистое (или только неотслеживаемый docx-отчёт), в логе — осмысленные коммиты. Если `git` не установлен, macOS сама предложит поставить Command Line Tools — согласитесь и повторите.

---

## Способ А — через сайт GitHub + Терминал (без установки чего-либо)

### А1. Создайте пустой репозиторий

1. Зайдите на https://github.com и войдите (или зарегистрируйтесь — бесплатно).
2. Справа вверху: **+** → **New repository**.
3. **Repository name:** например `mentor-student-agents`.
4. **Public** (чтобы преподаватель открыл по ссылке) или **Private** (тогда добавьте преподавателя в Settings → Collaborators).
5. ВАЖНО: **ничего не отмечайте** — ни «Add a README», ни «.gitignore», ни лицензию. Репозиторий должен остаться пустым, иначе push отклонится.
6. Нажмите **Create repository**.

### А2. Создайте Personal Access Token (это ваш «пароль» для push)

GitHub не принимает пароль от аккаунта в терминале — нужен токен:

1. GitHub → аватар справа вверху → **Settings**.
2. Внизу слева: **Developer settings** → **Personal access tokens** → **Tokens (classic)**.
3. **Generate new token (classic)**.
4. Note: `homework push`; Expiration: 30 days; отметьте галочку **repo** (весь блок).
5. **Generate token** → скопируйте токен (`ghp_...`) сразу — второй раз его не покажут.

### А3. Свяжите и запушьте

В Терминале (подставьте СВОЙ ник GitHub и имя репозитория):

```bash
cd ~/Claude/Projects/AI_angents_task_cmf
git remote add origin https://github.com/ВАШ_НИК/mentor-student-agents.git
git push -u origin main
```

Когда спросит:
- **Username:** ваш ник GitHub
- **Password:** вставьте ТОКЕН (не пароль!). Ввод не отображается — это нормально, вставьте и Enter.

### А4. Проверьте

Откройте `https://github.com/ВАШ_НИК/mentor-student-agents` — вы должны увидеть: `README.md`, `SUBMISSION.md`, папки `prompts/`, `course/`, `src/`, `transcripts/` и историю коммитов (вкладка Commits).

---

## Способ Б — через GitHub CLI (быстрее, если не боитесь установить одну утилиту)

```bash
brew install gh          # если нет brew: https://brew.sh (одна команда установки)
gh auth login            # выберите GitHub.com → HTTPS → Login with a web browser → следуйте подсказкам
cd ~/Claude/Projects/AI_angents_task_cmf
gh repo create mentor-student-agents --public --source=. --push
```

Одна последняя команда сама создаст репозиторий и запушит всё. Готовую ссылку она напечатает в конце.

---

## Как потом дослать живой прогон (после завершения урока 10)

Сгенерированные прогоны `transcripts/run-*` в `.gitignore`, поэтому добавлять их надо явно:

```bash
cd ~/Claude/Projects/AI_angents_task_cmf
git add -f transcripts/run-ВАШ_ШТАМП.md transcripts/run-ВАШ_ШТАМП-memory.json
git commit -m "add live free-model run"
git push
```

То же самое для любых будущих правок: `git add <файлы>` → `git commit -m "..."` → `git push`.

---

## Что включено / исключено

- **Уйдёт на GitHub:** SUBMISSION.md (документ сдачи), промпты, курс, код, референсный транскрипт, README, эта инструкция.
- **НЕ уйдёт (и не должно):** `.env` с вашим API-ключом, `__pycache__`, сырые прогоны `run-*` (пока не добавите явно).
- Проверить, что ключ в безопасности: `git check-ignore .env` должен напечатать `.env`.

---

## Если что-то пошло не так

| Ошибка | Причина и решение |
|---|---|
| `remote origin already exists` | Уже привязывали. `git remote set-url origin https://github.com/ВАШ_НИК/ИМЯ.git` |
| `Authentication failed` | Ввели пароль аккаунта вместо токена, либо у токена нет галочки `repo`. Создайте токен заново (шаг А2). |
| `Updates were rejected... fetch first` | Репозиторий на GitHub не пустой (создали с README). Либо пересоздайте пустым, либо: `git pull origin main --allow-unrelated-histories`, разрешите конфликт, `git push`. |
| `Support for password authentication was removed` | То же: используйте токен, не пароль. |
| push висит и молчит | Введённый токен не вставился. Ctrl+C и повторите `git push`, вставив токен через Cmd+V. |

---

## Что сдавать

Ссылку на репозиторий (`https://github.com/ВАШ_НИК/mentor-student-agents`). Если школа требует один файл — это `SUBMISSION.md`.
