# Syntax Siege

First-person sandbox shooter where you upgrade yourself by writing Python.

Every mission teaches one idea (print, variables, math, if, loops, functions, lists, loops + if).
Wrong code? You get a specific clue, then a bigger hint, and on the 3rd miss the answer.
Solve it and you get an upgrade (gun, damage, auto-heal, burst fire, jump jets, shotgun, radar)
and a wave of enemies to fight. After the last mission the terminal becomes a free sandbox
where your code spawns enemies, builds boxes and changes physics.

## Run (works offline after install)

    pip install -r requirements.txt
    python game.py

## Controls

| Key | Action |
|---|---|
| WASD / mouse / Space | move, look, jump |
| Left click / R | shoot / reload |
| T | open terminal (game pauses) |
| F5 or RUN | run your code |
| Esc | close terminal |

Progress saves to `save.json`; delete it to start over.

## Add a mission

Append a `Mission(...)` to `MISSIONS` in `missions.py` with a `check(code)` function,
two hints and the answer, then run `python test_missions.py`.
