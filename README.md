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
2. `Preferences → System → General → External scripting using → Local` (для запуску з терміналу).
3. **64-бітний Python, сумісний з вашим Resolve.** Скрипт сам знаходить модуль `DaVinciResolveScript`
   у стандартних місцях Windows / macOS / Linux або за змінною `RESOLVE_SCRIPT_API`.
4. Без сторонніх залежностей — лише стандартна бібліотека Python.

**Усередині Resolve:** скопіюйте файл з `menu_scripts/` у
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
відповідають офіційному README Blackmagic (Resolve 20.1).

## Статус і чесні нотатки

- Логіка покрита тестами; виклики API звірені з офіційною документацією Resolve 20.1.
- Запуск на реальному Resolve 20.1 перевірявся: модуль `fusionscript` від Resolve **не ініціалізувався
  на Python 3.13 і 3.14**. Тепер у такому разі скрипт показує зрозуміле повідомлення замість трейсбеку.
  Для роботи з Resolve використовуйте старішу версію Python (напр. 3.10–3.12); повний прогін на живому
  Resolve — наступний крок.
- Drop-frame підтримується для 29.97 / 59.94; інші частоти рахуються як non-drop.

---
Автор: Ілля Мірошников · [github.com/moonblo0d](https://github.com/moonblo0d)
