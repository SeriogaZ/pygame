"""Coding missions + a safe-ish runner for the player's code.

Each mission has a check(code) -> (ok, feedback). On failure the game shows
feedback plus hints[0], then hints[1], then the full answer.
"""
import builtins
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable

SAFE_BUILTINS = {n: getattr(builtins, n) for n in (
    'range', 'len', 'int', 'float', 'str', 'bool', 'list', 'dict', 'tuple', 'set',
    'abs', 'min', 'max', 'sum', 'round', 'enumerate', 'sorted', 'reversed', 'zip',
    'isinstance', 'Exception', 'ValueError', 'TypeError')}

MAX_STEPS = 50_000


class TooLong(Exception):
    pass


def friendly(e):
    """Turn a Python exception into a beginner-readable message."""
    if isinstance(e, TooLong):
        return 'Your code ran too long and was stopped. Is there a loop that never ends?'
    if isinstance(e, SyntaxError):
        msg = (e.msg or '').lower()
        where = f'Line {e.lineno}: ' if e.lineno else ''
        if isinstance(e, IndentationError) or 'indent' in msg:
            tip = 'Indentation problem. Code inside if / for / def must be pushed right by 4 spaces (press Tab).'
        elif "expected ':'" in msg:
            tip = 'Lines that start with if, for, while or def must end with a colon  :'
        elif 'unterminated string' in msg or 'eol while' in msg:
            tip = 'You opened a quote " but never closed it.'
        elif 'never closed' in msg or 'unmatched' in msg or 'was not closed' in msg:
            tip = 'A bracket ( [ is not matched with its closing ) ].'
        elif "maybe you meant '=='" in msg:
            tip = 'Use == to compare, = to store a value.'
        else:
            tip = f'Python could not read this ({e.msg}). Check spelling, quotes, brackets and colons.'
        return where + tip
    line = ''
    for frame in traceback.extract_tb(e.__traceback__):
        if frame.filename == '<player>':
            line = f'Line {frame.lineno}: '
    if isinstance(e, NameError):
        name = str(e).split("'")[1] if "'" in str(e) else '?'
        return (f"{line}Python doesn't know the name: {name}\nTypo? Names are case-sensitive. "
                f'If you meant text, put it in quotes: "{name}"')
    if isinstance(e, ZeroDivisionError):
        return f'{line}You divided by zero.'
    return f'{line}{type(e).__name__}: {e}'


def run_code(code, env=None):
    """Run player code. Returns (namespace, printed_output, error_message_or_None)."""
    out = []

    def _print(*args, sep=' ', end='\n'):
        out.append(sep.join(map(str, args)) + end)

    ns = {'__builtins__': {**SAFE_BUILTINS, 'print': _print}}
    ns.update(env or {})
    steps = 0

    def tracer(frame, event, arg):
        nonlocal steps
        if frame.f_code.co_filename != '<player>':
            return None
        steps += 1
        if steps > MAX_STEPS:
            raise TooLong()
        return tracer

    try:
        compiled = compile(code, '<player>', 'exec')
    except SyntaxError as e:
        return ns, '', friendly(e)
    old = sys.gettrace()
    sys.settrace(tracer)
    try:
        exec(compiled, ns)
        err = None
    except Exception as e:
        err = friendly(e)
    finally:
        sys.settrace(old)
    return ns, ''.join(out), err


@dataclass
class Mission:
    title: str
    lesson: str
    task: str
    starter: str
    check: Callable[[str], tuple]
    hints: list
    answer: str
    reward: str          # key the game applies (see game.apply_reward)
    reward_text: str
    wave: int = 0        # enemies spawned after solving
    boss: bool = False


# ---------- checks ----------

def check_print(code):
    ns, out, err = run_code(code)
    if err:
        return False, err
    if not out.strip():
        return False, 'Nothing was printed.'
    if out.strip().lower() != 'online':
        return False, f'You printed  {out.strip()}  but the suit wants exactly:  online'
    return True, out


def check_ammo(code):
    ns, out, err = run_code(code)
    if err:
        return False, err
    if 'ammo' not in ns:
        return False, 'No variable named  ammo  was created.'
    if ns['ammo'] == '12':
        return False, 'ammo is the TEXT "12". Numbers do not use quotes.'
    if ns['ammo'] != 12:
        return False, f'ammo is {ns["ammo"]!r}, it should be 12.'
    return True, ''


def check_damage(code):
    ns, out, err = run_code(code, {'base_damage': 10})
    if err:
        return False, err
    if 'damage' not in ns:
        return False, 'No variable named  damage  was created.'
    if ns['damage'] != 30:
        return False, f'damage is {ns["damage"]!r}, it should be base_damage times 3 (30).'
    if 'base_damage' not in code:
        return False, 'Right number, but use the base_damage variable. That is the point of variables!'
    return True, ''


def check_if(code):
    for hp, should in ((30, True), (49, True), (50, False), (80, False)):
        calls = []
        ns, out, err = run_code(code, {'health': hp, 'heal': lambda: calls.append(1)})
        if err:
            return False, err
        if should and not calls:
            return False, f'heal() did not run when health was {hp}.'
        if not should and calls:
            return False, f'heal() ran when health was {hp}. It should only run BELOW 50.'
    return True, ''


def check_loop(code):
    calls = []
    ns, out, err = run_code(code, {'fire': lambda: calls.append(1)})
    if err:
        return False, err
    if len(calls) != 3:
        return False, f'fire() was called {len(calls)} times, it should be 3.'
    if 'for' not in code:
        return False, 'Works, but use a for loop. Imagine typing fire() 100 times!'
    return True, ''


def check_func(code):
    ns, out, err = run_code(code)
    if err:
        return False, err
    f = ns.get('jump_power')
    if f is None:
        return False, 'No function named  jump_power  was defined.'
    if not callable(f):
        return False, 'jump_power must be a function (use def), not a variable.'
    _, _, err = run_code('result = jump_power()', {'jump_power': f})
    if err:
        return False, err
    r = f()
    if r is None:
        return False, 'Your function gives nothing back. Add a  return  line inside it.'
    if r != 6:
        return False, f'jump_power() returns {r!r}, it should return 6.'
    return True, ''


def check_list(code):
    ns, out, err = run_code(code)
    if err:
        return False, err
    w = ns.get('weapons')
    if w is None:
        return False, 'No variable named  weapons  was created.'
    if not isinstance(w, list):
        return False, 'weapons must be a list, made with square brackets [ ].'
    if sorted(w) != ['pistol', 'shotgun']:
        return False, f'weapons is {w!r}. It should hold exactly "pistol" and "shotgun".'
    return True, ''


def check_count(code):
    for hps, expect in (([40, 120, 75, 10], 2), ([60, 70, 80], 3), ([], 0)):
        ns, out, err = run_code(code, {'enemies': list(hps)})
        if err:
            return False, err
        if 'strong' not in ns:
            return False, 'No variable named  strong  was created.'
        if ns['strong'] != expect:
            return False, (f'For enemies = {hps}, strong was {ns["strong"]!r} but should be {expect}. '
                           'Your code must work for ANY list, so count with a loop.')
    return True, ''


MISSIONS = [
    Mission(
        title='1. Boot Up',
        lesson='print() shows a message.\nText always goes inside quotes:\n\n    print("hello")',
        task='Your suit is offline. Print the word  online',
        starter='# type your code below, then press F5 (or RUN)\n',
        check=check_print,
        hints=['Use print( ) and put the text inside quotes.',
               'It looks like  print("...")  with the word online inside.'],
        answer='print("online")',
        reward='hud', reward_text='Suit online. HUD activated.'),
    Mission(
        title='2. Load the Gun',
        lesson='A variable is a name that stores a value:\n\n    lives = 3\n\nNumbers do NOT use quotes.',
        task='Create a variable called  ammo  and set it to 12.',
        starter='',
        check=check_ammo,
        hints=['Write the name, then =, then the number.',
               'ammo = ...   (a number, no quotes)'],
        answer='ammo = 12',
        reward='gun', reward_text='Pistol unlocked: 12 rounds. Left click to shoot, R to reload.',
        wave=3),
    Mission(
        title='3. Overcharge',
        lesson='Python does math with  +  -  *  /\nYou can use variables in math:\n\n    total = price * 2',
        task='base_damage already exists (it is 10).\nCreate  damage  equal to base_damage times 3.',
        starter='',
        check=check_damage,
        hints=['Multiply with the star symbol  *', 'damage = base_damage * ...'],
        answer='damage = base_damage * 3',
        reward='damage', reward_text='Damage tripled!',
        wave=5),
    Mission(
        title='4. Med Protocol',
        lesson='if runs code only when a condition is True.\nEnd the line with a colon, and indent the\ncode under it (Tab = 4 spaces):\n\n    if score > 10:\n        win()',
        task='health is a number. If health is below 50,\ncall  heal()',
        starter='',
        check=check_if,
        hints=['"below" means the  <  sign:  health < 50',
               'Two lines: the if line ends with  :  and the\nnext line  heal()  is indented.'],
        answer='if health < 50:\n    heal()',
        reward='regen', reward_text='Auto-heal installed: you regenerate while below 50 health.',
        wave=6),
    Mission(
        title='5. Burst Fire',
        lesson='A for loop repeats indented code:\n\n    for i in range(4):\n        jump()\n\nruns jump() 4 times.',
        task='Call  fire()  exactly 3 times using a for loop.',
        starter='',
        check=check_loop,
        hints=['range(3) gives you 3 rounds of the loop.',
               'for i in range(3):\n    ...   (indented fire())'],
        answer='for i in range(3):\n    fire()',
        reward='burst', reward_text='Burst fire: every click fires 3 shots.',
        wave=8),
    Mission(
        title='6. Jump Jets',
        lesson='def creates a function: a named block of code.\nreturn sends a value back:\n\n    def lucky():\n        return 7',
        task='Define a function called  jump_power  that\nreturns 6.',
        starter='',
        check=check_func,
        hints=['Start with  def jump_power():  (note the colon).',
               'Inside the function (indented) write  return 6'],
        answer='def jump_power():\n    return 6',
        reward='jump', reward_text='Jump jets online: you jump 3x higher.',
        wave=10, boss=True),
    Mission(
        title='7. Arsenal',
        lesson='A list holds many values in square brackets,\nseparated by commas:\n\n    colors = ["red", "blue"]',
        task='Make a list called  weapons  that holds the\ntext "pistol" and "shotgun".',
        starter='',
        check=check_list,
        hints=['Lists use  [ ]  and each text needs quotes.',
               'weapons = ["...", "..."]'],
        answer='weapons = ["pistol", "shotgun"]',
        reward='shotgun', reward_text='Shotgun shells loaded: every shot fires 6 pellets.',
        wave=12),
    Mission(
        title='8. Smart Targeting',
        lesson='Combine loops and if. Count with a variable:\n\n    big = 0\n    for n in numbers:\n        if n > 5:\n            big = big + 1',
        task='enemies is a list of enemy health numbers.\nStore in  strong  how many have health above 50.',
        starter='',
        check=check_count,
        hints=['Start with  strong = 0  then loop:  for hp in enemies:',
               'Inside the loop:  if hp > 50:  then add 1 to strong.'],
        answer='strong = 0\nfor hp in enemies:\n    if hp > 50:\n        strong = strong + 1',
        reward='radar', reward_text='Radar online: enemies are marked through walls.',
        wave=15, boss=True),
]


def feedback_for(mission, fails, msg):
    """What to show after the player's fails-th wrong attempt (1-based)."""
    lines = [msg]
    if fails >= 3:
        lines.append('\nANSWER (type it in yourself):\n' + mission.answer)
    else:
        lines += ['\nHINT: ' + h for h in mission.hints[:fails]]
    return '\n'.join(lines)


SANDBOX_HELP = '''FREE SANDBOX - your code controls the world.

spawn_enemy(3)        spawn enemies
spawn_box(x, z, size) build a box
heal(100)             heal yourself
set_speed(10)         walk speed
set_jump(8)           jump height
set_gravity(0.5)      gravity (1 = normal)
player_pos()          where you are (x, y, z)
enemy_count()         enemies alive

Example:
for i in range(5):
    spawn_box(i * 2, 10, 1)'''
