"""Coding missions + a safe-ish runner for the player's code.

CURRICULUM is the mission order. Entries are either a Mission (a lesson) or a
function rng -> Mission (a REVIEW: same idea again with new names/numbers, and
wrong answers cost ammo). Every mission has check(code) -> (ok, feedback).
On failure the game shows feedback + hints[0], then hints[1], then the answer.
"""
import builtins
import random
import sys
import traceback
from dataclasses import dataclass
from typing import Callable

SAFE_BUILTINS = {n: getattr(builtins, n) for n in (
    'range', 'len', 'int', 'float', 'str', 'bool', 'list', 'dict', 'tuple', 'set',
    'abs', 'min', 'max', 'sum', 'round', 'enumerate', 'sorted', 'reversed', 'zip',
    'isinstance', 'Exception', 'ValueError', 'TypeError')}

MAX_STEPS = 50_000
REVIEW_PENALTY = 6      # reserve ammo lost per wrong review answer
REVIEW_REWARD = 15      # reserve ammo for solving a review


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
            tip = 'Indentation problem. Code inside if / for / while / def must be pushed right by 4 spaces (press Tab).'
        elif "expected ':'" in msg:
            tip = 'Lines that start with if, else, for, while or def must end with a colon  :'
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
    if isinstance(e, TypeError) and 'can only concatenate str' in str(e):
        return f'{line}You tried to join text and a number with +. Keep them the same type.'
    if isinstance(e, IndexError):
        return f'{line}That list position does not exist. Remember: the first item is [0].'
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
    check: Callable[[str], tuple]
    hints: list
    answer: str
    reward: str          # key the game applies (see game.apply_reward)
    reward_text: str
    wave: int = 0        # enemies spawned after solving
    boss: bool = False
    review: bool = False
    starter: str = ''


# ---------- check builders ----------

def var_problem(ns, name, value):
    if name not in ns:
        return f'No variable named  {name}  was created. Names must match exactly.'
    v = ns[name]
    if isinstance(value, (int, float)) and isinstance(v, str):
        return f'{name} is the TEXT {v!r}. Numbers do not use quotes.'
    if v != value:
        return f'{name} is {v!r}, it should be {value!r}.'
    return None


def check_print(word):
    def check(code):
        ns, out, err = run_code(code)
        if err:
            return False, err
        said = out.strip()
        if not said:
            return False, 'Nothing was printed. Did you use print( )?'
        if said != word:
            if said.lower() == word.lower():
                return False, f'Close! Capital letters matter. Print exactly:  {word}'
            return False, f'You printed  {said}  but it should be exactly:  {word}'
        return True, out
    return check


def check_var(name, value, env=None, uses=None, must=None):
    """uses: a variable name the code must use. must: (keyword, message)."""
    def check(code):
        ns, out, err = run_code(code, env)
        if err:
            return False, err
        p = var_problem(ns, name, value)
        if p:
            return False, p
        if uses and uses not in code:
            return False, f'Right value, but use the  {uses}  variable. That is the point of variables!'
        if must and must[0] not in code:
            return False, must[1]
        return True, out
    return check


def check_if_call(var, op, limit, func):
    below = op == '<'
    word = 'below' if below else 'above'

    def check(code):
        for v in (limit - 20, limit - 1, limit, limit + 1, limit + 25):
            calls = []
            ns, out, err = run_code(code, {var: v, func: lambda: calls.append(1)})
            if err:
                return False, err
            should = v < limit if below else v > limit
            if should and not calls:
                return False, f'{func}() did not run when {var} was {v}.'
            if not should and calls:
                return False, f'{func}() ran when {var} was {v}. It should only run when {var} is {word} {limit}.'
        return True, ''
    return check


def check_if_else(var, limit, yes, no):
    def check(code):
        for v in (limit - 30, limit, limit + 1, limit + 40):
            calls = []
            env = {var: v, yes: lambda: calls.append(yes), no: lambda: calls.append(no)}
            ns, out, err = run_code(code, env)
            if err:
                return False, err
            want = yes if v > limit else no
            if calls != [want]:
                got = ' and '.join(f'{c}()' for c in calls) or 'nothing'
                return False, f'When {var} was {v}, your code called {got}. It should call only {want}().'
        if 'else' not in code:
            return False, 'Works, but use else: for the "otherwise" part.'
        return True, ''
    return check


def check_calls(func, n):
    def check(code):
        calls = []
        ns, out, err = run_code(code, {func: lambda: calls.append(1)})
        if err:
            return False, err
        if len(calls) != n:
            return False, f'{func}() was called {len(calls)} times, it should be {n}.'
        if 'for' not in code:
            return False, 'Works, but use a for loop. Imagine typing it 100 times!'
        return True, ''
    return check


def call_player_func(f, name, args):
    """Call the player's function inside run_code so infinite loops are still stopped."""
    ns, out, err = run_code(f'_result = {name}(*_args)', {name: f, '_args': args})
    return ns.get('_result'), err


def check_func(name, cases):
    """cases: list of (args_tuple, expected_return)."""
    def check(code):
        ns, out, err = run_code(code)
        if err:
            return False, err
        f = ns.get(name)
        if f is None:
            return False, f'No function named  {name}  was defined. Start with  def {name}'
        if not callable(f):
            return False, f'{name} must be a function (use def), not a variable.'
        for args, want in cases:
            got, err = call_player_func(f, name, args)
            if err:
                if 'positional argument' in err:
                    shape = f'def {name}(n):' if args else f'def {name}():'
                    return False, f'{name} has the wrong number of inputs. It should start with  {shape}'
                return False, err
            shown = f'{name}({", ".join(map(repr, args))})'
            if got is None:
                return False, f'{shown} gives nothing back. Add a  return  line inside the function.'
            if got != want:
                return False, f'{shown} returned {got!r}, it should return {want!r}.'
        return True, ''
    return check


def check_list(name, items):
    def check(code):
        ns, out, err = run_code(code)
        if err:
            return False, err
        w = ns.get(name)
        if w is None:
            return False, f'No variable named  {name}  was created.'
        if not isinstance(w, list):
            return False, f'{name} must be a list, made with square brackets [ ].'
        if w != items:
            return False, f'{name} is {w!r}. It should be {items!r} (same order).'
        return True, ''
    return check


def check_greeting(code):
    for player in ('Ace', 'Nova'):
        ns, out, err = run_code(code, {'player': player})
        if err:
            return False, err
        g = ns.get('greeting')
        if g is None:
            return False, 'No variable named  greeting  was created.'
        if g == 'Hello' + player:
            return False, 'Missing space! Text joins exactly as written. Put a space inside the quotes: "Hello "'
        if g != 'Hello ' + player:
            return False, (f'When player was "{player}", greeting was {g!r}. It should be "Hello {player}". '
                           'Use the player variable, not the name itself.')
    return True, ''


def check_index(code):
    for items in (['pistol', 'shotgun', 'rifle'], ['laser', 'bow']):
        ns, out, err = run_code(code, {'weapons': list(items)})
        if err:
            return False, err
        for name, want in (('first', items[0]), ('count', len(items))):
            p = var_problem(ns, name, want)
            if p:
                return False, f'For weapons = {items}: {p}'
    if 'len' not in code:
        return False, 'Use len(weapons) to count. Your code must work for any list.'
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


# ---------- review generators (same idea, new numbers, wrong answers cost ammo) ----------

REVIEW_NOTE = f'REVIEW: you know this one! Each wrong answer costs {REVIEW_PENALTY} ammo.'


def review(title, lesson, task, check, hints, answer, wave):
    return Mission(title=f'Review: {title}', lesson=lesson, task=task, check=check, hints=hints, answer=answer,
                   reward='ammo', reward_text=f'+{REVIEW_REWARD} reserve ammo.', wave=wave, review=True)


def review_print(rng, wave=2):
    word = rng.choice(['reload', 'ready', 'target locked', 'go go go', 'all clear', 'shields up'])
    return review('print', 'print("text") shows text. Text needs quotes.',
                  f'Print exactly:  {word}', check_print(word),
                  ['print( ) with the text inside quotes.', f'print("...") with  {word}  inside'],
                  f'print("{word}")', wave)


def review_var(rng, wave=3):
    name = rng.choice(['shields', 'fuel', 'armor_level', 'speed', 'lives'])
    value = rng.randint(3, 99)
    return review('variables', 'name = value   stores a value. Numbers have no quotes.',
                  f'Create a variable called  {name}  and set it to {value}.', check_var(name, value),
                  ['Name first, then =, then the number.', f'{name} = ...'], f'{name} = {value}', wave)


def review_math(rng, wave=3):
    var, k = rng.choice(['level', 'rank', 'combo']), rng.randint(2, 9)
    val = rng.randint(2, 9)
    target, op, word, res = rng.choice([('bonus', '*', 'times', val * k), ('total', '+', 'plus', val + k)])
    return review('math', 'Math: + - * /   You can use variables in math.',
                  f'{var} already exists (it is {val}).\nCreate  {target}  equal to {var} {word} {k}.',
                  check_var(target, res, env={var: val}, uses=var),
                  [f'Use the  {op}  symbol.', f'{target} = {var} {op} ...'], f'{target} = {var} {op} {k}', wave)


def review_if(rng, wave=4):
    var, func = rng.choice([('ammo', 'reload'), ('fuel', 'refuel'), ('shield', 'recharge')])
    op, word = rng.choice([('<', 'below'), ('>', 'above')])
    limit = rng.choice([5, 10, 20, 30, 75])
    return review('if', 'if condition:\n    code      (colon + indent)',
                  f'If {var} is {word} {limit}, call  {func}()', check_if_call(var, op, limit, func),
                  [f'{word} means  {op}', f'if {var} {op} {limit}:\n    ...'], f'if {var} {op} {limit}:\n    {func}()', wave)


def review_loop(rng, wave=4):
    func, n = rng.choice(['build', 'scan', 'jump', 'charge']), rng.randint(2, 7)
    return review('for loop', 'for i in range(n):\n    code      repeats n times',
                  f'Call  {func}()  exactly {n} times using a for loop.', check_calls(func, n),
                  [f'range({n}) loops {n} times.', f'for i in range({n}):\n    ...'], f'for i in range({n}):\n    {func}()', wave)


def review_func(rng, wave=5):
    name, op, k = rng.choice([('triple', '*', 3), ('add_five', '+', 5), ('double', '*', 2), ('add_ten', '+', 10)])
    cases = [((n,), eval(f'{n} {op} {k}')) for n in (1, 4, 7)]
    return review('functions', 'def name(x):\n    return something',
                  f'Define a function  {name}  that takes one number\nand returns it {"times" if op == "*" else "plus"} {k}.',
                  check_func(name, cases),
                  [f'def {name}(n):   then an indented return line.', f'return n {op} {k}'],
                  f'def {name}(n):\n    return n {op} {k}', wave)


def review_list(rng, wave=5):
    name, items = rng.choice([('squad', ['Ace', 'Nova', 'Rex']), ('colors', ['red', 'blue']),
                              ('ammo_types', ['bullet', 'shell']), ('maps', ['desert', 'city', 'moon'])])
    shown = ', '.join(f'"{i}"' for i in items)
    return review('lists', 'A list:  name = ["a", "b"]', f'Make a list called  {name}  holding {shown}\n(in that order).',
                  check_list(name, items), ['Square brackets [ ], text in quotes, commas between.',
                                            f'{name} = [{", ".join(chr(34) * 2 for _ in items)}]  fill in the text'],
                  f'{name} = [{shown}]', wave)


def final_review(rng):
    m = rng.choice([review_math, review_if, review_loop, review_func, review_list])(rng, wave=14)
    m.title = 'Final Review: ' + m.title.split(': ')[1]
    m.boss = True
    return m


# ---------- the curriculum ----------

CURRICULUM = [
    Mission(
        title='Boot Up',
        lesson='print() shows a message.\nText always goes inside quotes:\n\n    print("hello")',
        task='Your suit is offline. Print the word  online',
        starter='# type your code below, then press F5 (or RUN)\n',
        check=check_print('online'),
        hints=['Use print( ) and put the text inside quotes.',
               'It looks like  print("...")  with the word online inside.'],
        answer='print("online")',
        reward='hud', reward_text='Suit online. HUD activated.'),
    Mission(
        title='Load the Gun',
        lesson='A variable is a name that stores a value:\n\n    lives = 3\n\nNumbers do NOT use quotes.',
        task='Create a variable called  ammo  and set it to 12.',
        check=check_var('ammo', 12),
        hints=['Write the name, then =, then the number.', 'ammo = ...   (a number, no quotes)'],
        answer='ammo = 12',
        reward='gun', reward_text='Pistol unlocked. Left click to shoot, R to reload.', wave=3),
    review_print,
    Mission(
        title='Overcharge',
        lesson='Python does math with  +  -  *  /\nYou can use variables in math:\n\n    total = price * 2',
        task='base_damage already exists (it is 10).\nCreate  damage  equal to base_damage times 3.',
        check=check_var('damage', 30, env={'base_damage': 10}, uses='base_damage'),
        hints=['Multiply with the star symbol  *', 'damage = base_damage * ...'],
        answer='damage = base_damage * 3',
        reward='damage', reward_text='Damage tripled!', wave=4),
    review_var,
    review_math,
    Mission(
        title='Call Sign',
        lesson='Text is called a string. Join strings with +\n\n    full = "Super " + "Nova"\n\ngives "Super Nova". Spaces count!',
        task='player holds your name (text).\nCreate  greeting  that is "Hello " joined with player.',
        check=check_greeting,
        hints=['Join with +  and keep the space inside the quotes: "Hello "',
               'greeting = "Hello " + ...   (the variable, no quotes)'],
        answer='greeting = "Hello " + player',
        reward='armor', reward_text='Armor plating: you take 30% less damage.', wave=4),
    Mission(
        title='Med Protocol',
        lesson='if runs code only when a condition is True.\nEnd the line with a colon, and indent the\ncode under it (Tab = 4 spaces):\n\n    if score > 10:\n        win()',
        task='health is a number. If health is below 50,\ncall  heal()',
        check=check_if_call('health', '<', 50, 'heal'),
        hints=['"below" means the  <  sign:  health < 50',
               'Two lines: the if line ends with  :  and the\nnext line  heal()  is indented.'],
        answer='if health < 50:\n    heal()',
        reward='regen', reward_text='Auto-heal: you regenerate while below 50 health.', wave=5),
    review_if,
    Mission(
        title='Fight or Flight',
        lesson='else runs when the if condition is False:\n\n    if coins > 5:\n        buy()\n    else:\n        save()\n\nelse lines up with if, and ends with a colon.',
        task='If health is above 50 call  attack()\notherwise call  retreat()',
        check=check_if_else('health', 50, 'attack', 'retreat'),
        hints=['"above" is  >  . else: goes on its own line, not indented.',
               'if health > 50:\n    attack()\nelse:\n    ...'],
        answer='if health > 50:\n    attack()\nelse:\n    retreat()',
        reward='sprint', reward_text='Sprint boots: hold Shift to run.', wave=5),
    Mission(
        title='Burst Fire',
        lesson='A for loop repeats indented code:\n\n    for i in range(4):\n        jump()\n\nruns jump() 4 times.',
        task='Call  fire()  exactly 3 times using a for loop.',
        check=check_calls('fire', 3),
        hints=['range(3) gives you 3 rounds of the loop.', 'for i in range(3):\n    ...   (indented fire())'],
        answer='for i in range(3):\n    fire()',
        reward='burst', reward_text='Burst fire: every click fires 3 shots.', wave=6),
    review_loop,
    Mission(
        title='Counting Up',
        lesson='The loop variable changes every round:\n\n    for i in range(1, 4):\n        print(i)\n\nprints 1, 2, 3 (it stops BEFORE 4).',
        task='Create  total = 0  then use a for loop to add\nthe numbers 1 to 5 to it. (total ends as 15)',
        check=check_var('total', 15, must=('for', 'Right number, but use a for loop to add them up.')),
        hints=['range(1, 6) gives 1, 2, 3, 4, 5.', 'Inside the loop:  total = total + i'],
        answer='total = 0\nfor i in range(1, 6):\n    total = total + i',
        reward='grenade', reward_text='Grenades: press G to throw one.', wave=6),
    Mission(
        title='Jump Jets',
        lesson='def creates a function: a named block of code.\nreturn sends a value back:\n\n    def lucky():\n        return 7',
        task='Define a function called  jump_power  that\nreturns 6.',
        check=check_func('jump_power', [((), 6)]),
        hints=['Start with  def jump_power():  (note the colon).', 'Inside the function (indented) write  return 6'],
        answer='def jump_power():\n    return 6',
        reward='jump', reward_text='Jump jets online: you jump 3x higher.', wave=6, boss=True),
    Mission(
        title='Sentry',
        lesson='Functions can take inputs (parameters):\n\n    def add_one(n):\n        return n + 1\n\nadd_one(4) gives 5.',
        task='Define  double  that takes a number and\nreturns it times 2.',
        check=check_func('double', [((3,), 6), ((10,), 20), ((0,), 0)]),
        hints=['def double(n):  (n is the input)', 'Inside:  return n * 2'],
        answer='def double(n):\n    return n * 2',
        reward='turret', reward_text='Sentry turret: press Q to place it.', wave=7),
    review_func,
    Mission(
        title='Arsenal',
        lesson='A list holds many values in square brackets,\nseparated by commas:\n\n    colors = ["red", "blue"]',
        task='Make a list called  weapons  that holds\n"pistol" and "shotgun" (in that order).',
        check=check_list('weapons', ['pistol', 'shotgun']),
        hints=['Lists use  [ ]  and each text needs quotes.', 'weapons = ["...", "..."]'],
        answer='weapons = ["pistol", "shotgun"]',
        reward='shotgun', reward_text='Shotgun shells: every shot fires 6 pellets.', wave=8),
    Mission(
        title='Inventory',
        lesson='Get an item by its position (starts at 0!):\n\n    colors[0]    first item\n    len(colors)  how many items',
        task='weapons is a list. Create  first  = its first\nitem, and  count  = how many items it has.',
        check=check_index,
        hints=['The first item is  weapons[0]', 'count = len(weapons)'],
        answer='first = weapons[0]\ncount = len(weapons)',
        reward='mag', reward_text='Extended magazine: 50 rounds.', wave=8),
    review_list,
    Mission(
        title='Smart Targeting',
        lesson='Combine loops and if. Count with a variable:\n\n    big = 0\n    for n in numbers:\n        if n > 5:\n            big = big + 1',
        task='enemies is a list of enemy health numbers.\nStore in  strong  how many have health above 50.',
        check=check_count,
        hints=['Start with  strong = 0  then loop:  for hp in enemies:',
               'Inside the loop:  if hp > 50:  then add 1 to strong.'],
        answer='strong = 0\nfor hp in enemies:\n    if hp > 50:\n        strong = strong + 1',
        reward='radar', reward_text='Radar online: enemies are marked through walls.', wave=10, boss=True),
    Mission(
        title='Full Auto',
        lesson='while repeats as long as a condition is True:\n\n    n = 0\n    while n < 3:\n        n = n + 1\n\nCareful: if it never becomes False, it runs forever!',
        task='Create  charge = 0  then use a while loop that\nadds 5 to charge while charge is below 100.',
        check=check_var('charge', 100, must=('while', 'Right number, but use a while loop.')),
        hints=['while charge < 100:', 'Inside the loop:  charge = charge + 5'],
        answer='charge = 0\nwhile charge < 100:\n    charge = charge + 5',
        reward='auto', reward_text='Full auto: hold the mouse button to keep firing.', wave=12),
    final_review,
]


def build_mission(i, rng=random):
    entry = CURRICULUM[i]
    return entry if isinstance(entry, Mission) else entry(rng)


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
