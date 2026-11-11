# Syntax Siege

First-person sandbox shooter for total beginners: you upgrade yourself by writing Python.

- **22 missions**: print, variables, math, strings, if, if/else, for loops, loop counters,
  functions, parameters, lists, indexing/len, loop + if, while.
- **Clues, not punishment**: wrong code gives a specific clue, then a bigger hint, and on the 3rd miss the answer.
- **Reviews**: every few lessons a REVIEW mission repeats an idea with new names and numbers.
  Each wrong review answer costs 6 ammo; solving one on the first try gives bonus ammo.
- **Upgrades** from lessons: pistol, damage, armor, auto-heal, sprint, burst fire, grenades,
  jump jets, sentry turret, shotgun, big magazine, radar, full auto.
- **Waves** of enemies (grunts, fast runners, bosses) after each mission. Enemies drop ammo.
- **Save slots**: 3 slots on the title screen. Progress auto-saves after each mission;
  Esc opens the pause menu (save, save & quit to title, save & exit).
- **Sandbox**: during waves and after the last mission the terminal runs free code that
  spawns enemies, builds boxes and changes speed/jump/gravity.

## Run (works offline after install)

    pip install -r requirements.txt
    python game.py

## Controls

| Key | Action |
|---|---|
| WASD / mouse / Space | move, look, jump |
| Left click / R | shoot / reload |
| Shift / G / Q | sprint / grenade / place turret (once unlocked) |
| T | open terminal (game pauses) |
| F5 or RUN | run your code |
| Esc | close terminal / pause menu |

Saves live in `saves.json`.

## Add a mission

Add a `Mission(...)` (lesson) or a `review_*` generator to `CURRICULUM` in `missions.py`,
then run `python test_missions.py`. Lesson rewards are applied in `apply_reward` in `game.py`.
