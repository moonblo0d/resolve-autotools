# resolve-autotools — автоматизація рутини в DaVinci Resolve

Python-інструменти на офіційному **DaVinci Resolve Scripting API**, які забирають повторювані операції
постпродакшну, щоб монтажер чи художник займався творчістю, а не клацанням:

| Команда | Що робить |
|---|---|
| `import` | Імпортує папку в окремий bin. **Послідовності кадрів** (`shot_0001.png … shot_0120.png`) стають одним кліпом, пропущені кадри знаходяться й повідомляються. За бажанням одразу збирає таймлайн у природному порядку (`shot_2` перед `shot_10`). |
| `markers` | Ставить маркери з CSV із правками (таймкод, колір, назва, нотатка, тривалість). Усі помилки CSV видно одразу з номерами рядків. |
| `shotlist` | Експортує монтаж у CSV: трек, кліп, record in/out, тривалість, вихідний файл. Відкривається в Excel / Google Sheets. |
| `render` | Ставить у Render Queue кілька таймлайнів з одним пресетом і безпечними іменами файлів (`{project}_{timeline}_{date}`), за потреби рендерить і показує прогрес. |
| `info` | Проєкт, таймлайни (fps, тривалість, стартовий таймкод) і доступні пресети рендеру. |

## Приклади

```bash
# зйомковий день -> bin "Day 01" + таймлайн "Assembly"
python -m resolve_autotools import "D:\footage\Day 01" --timeline Assembly

# правки від клієнта -> маркери на поточному таймлайні
python -m resolve_autotools markers examples/review_notes.csv

# монтажний лист
python -m resolve_autotools shotlist shots.csv --timeline "Edit v3"

# усі таймлайни проєкту одним пресетом, з прогресом
python -m resolve_autotools render --preset "YouTube - 1080p" --out D:\renders --wait
```

Формат CSV з правками ([приклад](examples/review_notes.csv)), роздільник `,` або `;`:

```csv
timecode,color,name,note,duration
00:00:02:00,Red,Jump cut,Remove the jump cut before the title,12
01:00:12:00,Blue,Absolute TC,Absolute timecodes work too,24
```

Таймкоди можна давати і **відносні** (від початку таймлайну, як експортують більшість сервісів рев'ю),
і **абсолютні** (`01:00:12:00` на таймлайні, що стартує з `01:00:00:00`).

## Що всередині

```
resolve_autotools/
  timecode.py   SMPTE-таймкод <-> кадри, зокрема drop-frame 29.97 / 59.94
  media.py      пошук послідовностей кадрів: padding, 0999 -> 1000, пропуски, природне сортування
  markers.py    розбір CSV з правками, перевірка кольорів і тривалостей
  ops.py        операції над Resolve API: bin, ImportMedia, таймлайн, маркери, shot list, render queue
  connect.py    підключення до Resolve зсередини і ззовні, зрозумілі помилки
  cli.py        командний рядок
menu_scripts/   скрипт для меню Workspace > Scripts усередині Resolve
tests/          43 тести + фейковий Resolve API за офіційною документацією
```

Чиста логіка (таймкоди, послідовності, CSV) відокремлена від виклику API, тому її легко тестувати
й перевикористовувати в інших пайплайнах.

## Налаштування

1. **DaVinci Resolve** має бути запущений, з відкритим проєктом.
2. **З терміналу (CLI) — лише DaVinci Resolve Studio.** У безкоштовній версії зовнішній доступ до API
   закритий: `fusionscript` не ініціалізується за будь-якої версії Python, і скрипт про це прямо повідомляє.
   У Studio: `Preferences → System → General → External scripting using → Local`.
3. **Безкоштовна версія — запуск усередині Resolve** (`Workspace → Console → Py3` або меню `Workspace → Scripts`).
   Для цього Resolve має «бачити» Python: ставте його класичним інсталятором з python.org
   (Python, встановлений новим менеджером `py install`, Resolve 20.1 не знаходить — «Python 3 was not found»).
4. Скрипт сам знаходить модуль `DaVinciResolveScript` у стандартних місцях Windows / macOS / Linux
   або за змінною `RESOLVE_SCRIPT_API`. Без сторонніх залежностей — лише стандартна бібліотека.

**Безкоштовна версія — будь-яка команда з консолі Resolve** (`Workspace → Console → Py3`):

```python
import sys; sys.path.insert(0, r"C:\tools\resolve-autotools")
from resolve_autotools import cli
cli.main(["import", r"D:\footage\Day 01", "--timeline", "Assembly"], resolve=resolve)
cli.main(["shotlist", r"D:\shots.csv"], resolve=resolve)
```

**Меню Resolve:** скопіюйте файл з `menu_scripts/` у
`%APPDATA%\Blackmagic Design\DaVinci Resolve\Support\Fusion\Scripts\Utility` (Windows),
задайте змінну `RESOLVE_AUTOTOOLS_PATH` = шлях до цієї папки — і скрипт з'явиться в
`Workspace → Scripts`. Він експортує shot list поточного таймлайну на робочий стіл.

## Тести

```bash
python -m unittest discover -s tests -t .
```

43 тести: таймкоди (non-drop і drop-frame з еталонними значеннями, напр. `01:00:00;00` = 107892 кадри),
пошук послідовностей на реальних файлах у тимчасовій папці, розбір CSV з помилками, а також
імпорт, маркери, shot list, черга рендеру й CLI на **фейковому Resolve API**, методи й типи якого
відповідають офіційному README Blackmagic (Resolve 20.1) і звірені з живим запуском (див. нижче).

## Статус і чесні нотатки

- **Перевірено на живому DaVinci Resolve 20.1** (безкоштовна версія, консоль Py3, Python 3.12.10)
  на згенерованих PNG-секвенціях у тимчасовому проєкті:
  - `import` → 4 кліпи: `shotA_[0001-0048].png`, `shotB_…`, а секвенція з пропуском кадрів 13–14 розбита на 2 кліпи
    з попередженням, `notes.txt` пропущено; таймлайн `Assembly` зібрано в правильному порядку;
  - `markers` → маркер з кольором, назвою, нотаткою й тривалістю 12 кадрів; маркери за межами таймлайну
    (4 с 22 к) відхилені з поясненням;
  - `shotlist` → 4 рядки з точними record in/out (`01:00:04:12 → 01:00:04:22`);
  - `render` → пресет `H.264 Master`, файл `autotools-live-test_Assembly.mov` відрендерено.
- Фейковий API для тестів після цього підігнано під реальну поведінку Resolve (назви секвенцій).
- Що виявив живий запуск: зовнішній API доступний лише в Studio (у безкоштовній `fusionscript` → `SystemError`,
  тепер це зрозуміле повідомлення, покрите тестом), а консоль Resolve не бачить Python від `py install`.
- Drop-frame підтримується для 29.97 / 59.94; інші частоти рахуються як non-drop.

---
Автор: Ілля Мірошников · [github.com/moonblo0d](https://github.com/moonblo0d)
