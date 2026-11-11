"""Run: python test_missions.py"""
from missions import MISSIONS, run_code, feedback_for

for m in MISSIONS:
    ok, msg = m.check(m.answer)
    assert ok, (m.title, msg)
    assert not m.check(m.starter)[0], m.title

# common beginner mistakes get specific feedback
assert 'quotes' in MISSIONS[1].check('ammo = "12"')[1]
assert 'Python doesn' in MISSIONS[0].check('print(online)')[1]
assert 'colon' in MISSIONS[3].check('if health < 50\n    heal()')[1]
assert 'loop' in MISSIONS[4].check('fire()\nfire()\nfire()')[1]
assert not MISSIONS[7].check('strong = 2')[0]          # hard-coding is caught
assert 'too long' in run_code('while True:\n    pass')[2]
assert 'too long' in run_code('x = 0\nwhile True: x += 1')[2]

# hint escalation: hint1, then hint1+2, then answer
m = MISSIONS[1]
assert 'HINT' in feedback_for(m, 1, 'x') and m.hints[1] not in feedback_for(m, 1, 'x')
assert m.hints[1] in feedback_for(m, 2, 'x')
assert m.answer in feedback_for(m, 3, 'x')
print('all mission checks pass')
