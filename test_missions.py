"""Run: python test_missions.py"""
import random

from missions import CURRICULUM, Mission, build_mission, run_code, feedback_for

for i in range(len(CURRICULUM)):
    for seed in range(25):  # reviews are random: try many variants
        m = build_mission(i, random.Random(seed))
        ok, msg = m.check(m.answer)
        assert ok, (m.title, m.answer, msg)
        assert not m.check(m.starter)[0], m.title
        assert m.review == (not isinstance(CURRICULUM[i], Mission)), m.title

M = [build_mission(i, random.Random(0)) for i in range(len(CURRICULUM))]
by_title = {m.title: m for m in M}

# common beginner mistakes get specific feedback
assert 'quotes' in by_title['Load the Gun'].check('ammo = "12"')[1]
assert 'Python doesn' in by_title['Boot Up'].check('print(online)')[1]
assert 'Capital' in by_title['Boot Up'].check('print("Online")')[1]
assert 'colon' in by_title['Med Protocol'].check('if health < 50\n    heal()')[1]
assert 'loop' in by_title['Burst Fire'].check('fire()\nfire()\nfire()')[1]
assert 'space' in by_title['Call Sign'].check('greeting = "Hello" + player')[1]
assert not by_title['Call Sign'].check('greeting = "Hello Ace"')[0]       # hard-coding caught
assert not by_title['Smart Targeting'].check('strong = 2')[0]
assert 'else' in by_title['Fight or Flight'].check('if health > 50:\n    attack()\nif health <= 50:\n    retreat()')[1]
assert 'retreat' in by_title['Fight or Flight'].check('if health > 50:\n    attack()')[1]
assert 'inputs' in by_title['Sentry'].check('def double():\n    return 2')[1]
assert 'return' in by_title['Jump Jets'].check('def jump_power():\n    x = 6')[1]
assert not by_title['Inventory'].check('first = weapons[0]\ncount = 3')[0]
assert 'too long' in by_title['Sentry'].check('def double(n):\n    while True:\n        pass')[1]
assert 'too long' in run_code('while True:\n    pass')[2]
assert 'too long' in run_code('x = 0\nwhile True: x += 1')[2]

# hint escalation: hint1, then hint1+2, then answer
m = by_title['Load the Gun']
assert 'HINT' in feedback_for(m, 1, 'x') and m.hints[1] not in feedback_for(m, 1, 'x')
assert m.hints[1] in feedback_for(m, 2, 'x')
assert m.answer in feedback_for(m, 3, 'x')
print(f'all {len(CURRICULUM)} missions pass')
