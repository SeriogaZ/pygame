"""Syntax Siege - a first-person sandbox shooter you upgrade by writing Python.

Run:  python game.py
Controls: WASD move, mouse look, Space jump, Left click shoot, R reload,
          T open terminal, F5 run code, Esc close terminal.
"""
import json
import os
import random
import textwrap
from types import SimpleNamespace

from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
from ursina.prefabs.text_field import TextField
from ursina.prefabs.ursfx import ursfx
from ursina.shaders import lit_with_shadows_shader

from missions import MISSIONS, SANDBOX_HELP, run_code, feedback_for

SAVE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'save.json')
ARENA = 55          # half-size of the walled arena
MAX_ENEMIES = 60
MAX_BOXES = 400

app = Ursina(title='Syntax Siege', borderless=False, development_mode=False)
window.color = color.black
random.seed(7)

S = SimpleNamespace(mission=0, phase='code', fails=0, editor_mission=-1,
                    hud=False, gun=False, ammo=0, mag=12, damage=10, burst=1, pellets=1,
                    regen=False, radar=False, reloading=False, paused=False,
                    banner_until=0.0)
enemies = []
boxes = []


def W(**kw):
    """World entity with lighting/shadows."""
    return Entity(shader=lit_with_shadows_shader, **kw)


def label(text='', **kw):
    # custom tag chars so code like  health < 50  is never parsed as a color tag
    t = Text('', start_tag='☾', end_tag='☽', **kw)
    t.text = text
    return t


def wrap(text, width=58):
    out = []
    for line in text.split('\n'):
        indent = ' ' * (len(line) - len(line.lstrip()))
        out.append(textwrap.fill(line, width, subsequent_indent=indent) if len(line) > width else line)
    return '\n'.join(out)


# ---------------- world ----------------
Sky()
sun = DirectionalLight(shadows=True)
sun.look_at(Vec3(1, -1.4, -.6))
AmbientLight(color=color.rgba(.55, .55, .6, 1))

ground = W(model='plane', scale=ARENA * 2 + 10, texture='white_cube', texture_scale=(60, 60),
           color=color.hsv(140, .25, .55), collider='box')
for x, z, sx, sz in ((0, ARENA, ARENA * 2, 1), (0, -ARENA, ARENA * 2, 1), (ARENA, 0, 1, ARENA * 2), (-ARENA, 0, 1, ARENA * 2)):
    W(model='cube', position=(x, 3, z), scale=(sx + 1, 6, sz + 1), texture='brick',
      texture_scale=(max(sx, sz) / 2, 3), color=color.hsv(20, .3, .7), collider='box')


def make_box(x, z, size=1.0, y=None, col=None):
    b = W(model='cube', position=(x, size / 2 if y is None else y, z), scale=size,
          texture='white_cube', color=col or color.hsv(30, .5, random.uniform(.45, .7)), collider='box')
    boxes.append(b)
    return b


for _ in range(28):
    x, z = random.uniform(-ARENA + 4, ARENA - 4), random.uniform(-ARENA + 4, ARENA - 4)
    if abs(x) < 8 and abs(z) < 8:
        continue
    s = random.choice((1.5, 2, 3))
    make_box(x, z, s)
    if random.random() < .3:
        make_box(x, z, s * .7, y=s + s * .35)
# a few platforms + ramps for the jump jets
for x, z in ((25, 25), (-25, -20), (-28, 26), (30, -28)):
    W(model='cube', position=(x, 2.5, z), scale=(8, 5, 8), texture='white_cube', texture_scale=(4, 4),
      color=color.hsv(210, .2, .6), collider='box')
sun.update_bounds()


# ---------------- player ----------------
player = FirstPersonController(position=(0, 1, 0), speed=7)
player.hp = 100.0
player.cursor.color = color.white

skin = color.hsv(25, .45, .85)
sleeve = color.hsv(210, .5, .35)
for side in (-1, 1):  # you are a person: forearms + hands in view
    arm = Entity(parent=camera, position=(.33 * side, -.42, .55), rotation=(-12, -8 * side, 0))
    Entity(parent=arm, model='cube', scale=(.13, .13, .45), color=sleeve, z=-.1)
    Entity(parent=arm, model='cube', scale=(.11, .1, .14), color=skin, z=.18)

gun = Entity(parent=camera, position=(.33, -.3, .78), enabled=False)
Entity(parent=gun, model='cube', scale=(.1, .15, .45), color=color.hsv(0, 0, .2))
Entity(parent=gun, model='cube', scale=(.08, .2, .1), position=(0, -.13, -.12), color=color.hsv(0, 0, .15))
muzzle = Entity(parent=gun, model='cube', scale=(.06, .06, .25), z=.32, color=color.black)
flash = Entity(parent=gun, model='quad', z=.48, scale=.1, color=color.orange, enabled=False)


# ---------------- HUD ----------------
hurt_overlay = Entity(parent=camera.ui, model='quad', scale=(3, 2), color=color.rgba(1, 0, 0, 0), z=5)
mission_text = label(position=window.top_left + Vec2(.02, -.02), scale=1.1)
health_text = label(position=window.bottom_left + Vec2(.03, .07), scale=1.8, color=color.lime, enabled=False)
ammo_text = label(position=window.bottom_right + Vec2(-.03, .07), origin=(.5, 0), scale=1.8, enabled=False)
banner = label(position=(0, .32), origin=(0, 0), scale=1.6, color=color.yellow)


def notify(msg, seconds=4):
    banner.text = msg
    S.banner_until = time.time() + seconds


# ---------------- enemies ----------------
class Enemy(Entity):
    # ponytail: enemies walk straight at you through crates; add pathfinding if it bothers players
    def __init__(self, position, boss=False):
        super().__init__(position=position, scale=1.9 if boss else 1)
        self.boss = boss
        self.hp = 450 if boss else 60
        self.speed = (1.8 if boss else random.uniform(2.4, 3.4)) + S.mission * .15
        self.attack_cd = 0
        self.collider = BoxCollider(self, center=Vec3(0, 1, 0), size=Vec3(.9, 2, .6))
        body = color.hsv(280, .7, .5) if boss else color.hsv(0, .75, .65)
        self.legs = [W(parent=self, model='cube', scale=(.25, .8, .25), position=(s * .15, .4, 0), color=color.hsv(0, 0, .2)) for s in (-1, 1)]
        self.torso = W(parent=self, model='cube', scale=(.6, .7, .35), y=1.15, color=body)
        for s in (-1, 1):
            W(parent=self, model='cube', scale=(.18, .65, .18), position=(s * .4, 1.15, 0), color=body)
        W(parent=self, model='cube', scale=(.35, .35, .35), y=1.7, color=color.hsv(25, .3, .5))
        Entity(parent=self, model='cube', scale=(.3, .08, .02), position=(0, 1.73, .18), color=color.cyan)
        self.marker = Entity(parent=self, model='sphere', y=2.4, scale=.25, color=color.red,
                             always_on_top=True, enabled=S.radar)
        enemies.append(self)

    def update(self):
        if S.paused:
            return
        to = player.position - self.position
        to.y = 0
        self.look_at(Vec3(player.x, self.y, player.z))
        if to.length() > 1.4 * self.scale_x:
            self.position += to.normalized() * self.speed * time.dt
            swing = math.sin(time.time() * 10) * 30
            self.legs[0].rotation_x, self.legs[1].rotation_x = swing, -swing
        else:
            self.attack_cd -= time.dt
            if self.attack_cd <= 0:
                self.attack_cd = 1
                hurt(25 if self.boss else 10)

    def hit(self, dmg):
        self.hp -= dmg
        self.torso.blink(color.white, duration=.08)
        self.position -= self.forward * .15
        if self.hp <= 0 and self in enemies:
            enemies.remove(self)
            self.collider = None
            ursfx([(0, 1), (.1, .7), (.2, .3), (.35, .1), (.5, 0)], volume=.4, wave='sine', pitch=8, pitch_change=-12, speed=2)
            self.animate_scale(0, .2)
            destroy(self, delay=.25)
            check_wave_clear()


def spawn_enemy(boss=False):
    if len(enemies) >= MAX_ENEMIES:
        return
    ang = random.uniform(0, 6.283)
    r = random.uniform(22, 40)
    x = clamp(player.x + math.cos(ang) * r, -ARENA + 3, ARENA - 3)
    z = clamp(player.z + math.sin(ang) * r, -ARENA + 3, ARENA - 3)
    Enemy(position=(x, 0, z), boss=boss)


def start_wave(n, boss):
    S.phase = 'combat'
    for _ in range(n):
        spawn_enemy()
    if boss:
        spawn_enemy(boss=True)
    notify(f'WAVE INCOMING: {n + boss} enemies!')


def check_wave_clear():
    if S.phase == 'combat' and not enemies:
        advance()


def advance():
    S.mission += 1
    save()
    if S.mission >= len(MISSIONS):
        S.phase = 'free'
        notify('ALL MISSIONS COMPLETE! Press T: the terminal is now a free sandbox.', 8)
    else:
        S.phase = 'code'
        notify(f'Area clear. New mission: {MISSIONS[S.mission].title}  (press T)')


# ---------------- player actions ----------------
def hurt(n):
    player.hp -= n
    hurt_overlay.color = color.rgba(1, 0, 0, .35)
    hurt_overlay.animate_color(color.rgba(1, 0, 0, 0), duration=.4)
    ursfx([(0, 1), (.05, .7), (.1, .5), (.2, .2), (.3, 0)], volume=.4, wave='square', pitch=-20, speed=3)
    if player.hp <= 0:
        player.hp = 100
        player.position = Vec3(0, 1, 0)
        notify('YOU DIED. Respawned at the center.')


def shoot():
    if not S.gun or S.reloading:
        return
    if S.ammo <= 0:
        notify('Empty! Press R to reload.', 1.5)
        return
    for k in range(S.burst):
        invoke(fire_once, delay=k * .09)


def fire_once():
    if S.ammo <= 0 or S.paused:
        return
    S.ammo -= 1
    ursfx([(0, 0), (.1, .9), (.15, .75), (.3, .14), (.6, 0)], volume=.5, wave='noise',
          pitch=random.uniform(-13, -12), pitch_change=-12, speed=3)
    gun.z = .7
    gun.animate_z(.78, .08)
    flash.enabled = True
    invoke(setattr, flash, 'enabled', False, delay=.05)
    spread = .07 if S.pellets > 1 else .004
    for _ in range(S.pellets):
        d = (camera.forward + camera.right * random.uniform(-spread, spread)
             + camera.up * random.uniform(-spread, spread)).normalized()
        hit = raycast(camera.world_position, d, distance=150, ignore=(player,))
        end = hit.world_point if hit.hit else camera.world_position + d * 150
        line = Entity(model=Mesh(vertices=[muzzle.world_position + d * .2, end], mode='line', thickness=2),
                      color=color.yellow)
        destroy(line, delay=.05)
        if hit.hit and isinstance(hit.entity, Enemy):
            hit.entity.hit(S.damage)


def reload():
    if not S.gun or S.reloading or S.ammo == S.mag:
        return
    S.reloading = True

    def done():
        S.ammo, S.reloading = S.mag, False
    invoke(done, delay=1)


def apply_reward(key):
    if key == 'hud':
        S.hud = True
    elif key == 'gun':
        S.gun = True
        gun.enabled = True
        S.ammo = S.mag = 12
    elif key == 'damage':
        S.damage = 30
    elif key == 'regen':
        S.regen = True
    elif key == 'burst':
        S.burst = 3
        S.ammo = S.mag = 30
    elif key == 'jump':
        player.jump_height = 6
    elif key == 'shotgun':
        S.pellets = 6
    elif key == 'radar':
        S.radar = True
        for e in enemies:
            e.marker.enabled = True
    health_text.enabled = ammo_text.enabled = S.hud


# ---------------- save ----------------
def save():
    with open(SAVE, 'w') as f:
        json.dump({'mission': S.mission}, f)


def load():
    try:
        with open(SAVE) as f:
            done = min(int(json.load(f)['mission']), len(MISSIONS))
    except (OSError, ValueError, KeyError):
        return
    for m in MISSIONS[:done]:
        apply_reward(m.reward)
    S.mission = done
    S.phase = 'free' if done >= len(MISSIONS) else 'code'


# ---------------- terminal ----------------
class CodeField(TextField):
    def text_input(self, key):  # no auto-closing brackets: it confuses beginners
        if not self.active:
            return
        self.delete_selected()
        self.add_text(key)
        self.render()

    def render(self):  # 1-based line numbers so they match error messages
        super().render()
        n = len(self.text.split('\n'))
        self.line_numbers.text = '\n'.join(str(i + 1).rjust(3) for i in range(min(n, self.max_lines)))


MONO = Text.default_monospace_font
term = Entity(parent=camera.ui, enabled=False, z=-1)
Entity(parent=term, model='quad', scale=(1.8, .98), color=color.rgba(.03, .04, .08, .96), z=.1)
Entity(parent=term, model='quad', scale=(.005, .9), x=-.03, color=color.dark_gray)
term_title = label(parent=term, position=(-.86, .45), scale=1.5, color=color.cyan, font=MONO)
term_info = label(parent=term, position=(-.86, .38), font=MONO, scale=.9)
label(parent=term, position=(-.86, -.44), font=MONO, scale=.8, color=color.gray,
      text='F5 / RUN = run code    Esc = close    Tab = indent')
editor = CodeField(parent=term, position=(.0, .45), max_lines=17, font=MONO)
editor.line_numbers.enabled = True
editor.bg.scale_x = .87
editor.bg.color = color.rgba(.1, .12, .18, 1)
Entity(parent=term, model='quad', origin=(-.5, .5), position=(-.01, -.06), scale=(.88, .37),
       color=color.rgba(0, 0, 0, .6), z=.05)
term_out = label(parent=term, position=(0, -.07), font=MONO, scale=.85)
Button(parent=term, text='RUN  (F5)', scale=(.18, .055), position=(.76, -.465), color=color.hsv(130, .7, .45),
       on_click=lambda: run_player_code())


def open_terminal():
    S.paused = True
    player.disable()
    term.enable()
    if S.phase == 'code':
        m = MISSIONS[S.mission]
        term_title.text = f'MISSION {m.title}'
        term_info.text = f'{m.lesson}\n\n☾yellow☽TASK:☾default☽\n{m.task}'
        if S.editor_mission != S.mission:
            S.editor_mission = S.mission
            editor.text = m.starter
            editor.cursor.position = (0, len(m.starter.split('\n')) - 1)
            editor.render()
            term_out.text = ''
            S.fails = 0
    else:
        term_title.text = 'SANDBOX CONSOLE'
        status = (f'☾orange☽{len(enemies)} enemies left. Clear them to unlock the next mission.☾default☽\n\n'
                  if S.phase == 'combat' else '')
        term_info.text = status + SANDBOX_HELP
        if S.editor_mission != 'sandbox':
            S.editor_mission = 'sandbox'
            editor.text = ''
            editor.cursor.position = (0, 0)
            editor.render()
            term_out.text = ''
    editor.active = True


def close_terminal():
    term.disable()
    player.enable()
    S.paused = False


def run_player_code():
    code = editor.text
    if S.phase == 'code':
        m = MISSIONS[S.mission]
        ok, msg = m.check(code)
        if ok:
            ursfx([(0, 0), (.1, 1), (.3, .7), (.5, .3), (.8, 0)], volume=.4, wave='sine', pitch=4, pitch_change=8, speed=2)
            printed = f'☾light_gray☽> {msg.strip()}\n\n' if msg.strip() else ''
            fight = (f'\n\n{m.wave + m.boss} enemies are coming. Press Esc and fight!' if m.wave
                     else '\n\nPress Esc, then T again for the next mission.')
            term_out.text = wrap(f'{printed}☾lime☽CORRECT!\n{m.reward_text}{fight}')
            apply_reward(m.reward)
            if m.wave:
                start_wave(m.wave, m.boss)
            else:
                advance()
        else:
            S.fails += 1
            extra = feedback_for(m, S.fails, '').strip('\n')
            colour = 'lime' if S.fails >= 3 else 'yellow'
            term_out.text = wrap(f'☾red☽Attempt {S.fails}: {msg}\n\n☾{colour}☽{extra}')
            ursfx([(0, 1), (.1, .6), (.15, .4), (.2, .2), (.3, 0)], volume=.3, wave='square', pitch=-15, speed=3)
    else:
        ns, out, err = run_code(code, sandbox_api())
        term_out.text = wrap((out[-1500:] if out else '') + (f'☾red☽{err}' if err else ('' if out else '☾lime☽ok')))


def sandbox_api():
    def _spawn_enemy(n=1):
        for _ in range(min(int(n), MAX_ENEMIES - len(enemies))):
            spawn_enemy()

    def _spawn_box(x, z, size=1, y=None):
        if len(boxes) >= MAX_BOXES:
            raise ValueError(f'box limit reached ({MAX_BOXES})')
        size = clamp(float(size), .2, 20)
        make_box(clamp(float(x), -ARENA, ARENA), clamp(float(z), -ARENA, ARENA), size,
                 None if y is None else float(y), color.hsv(random.uniform(0, 360), .6, .8))

    def _heal(n=100):
        player.hp = min(100, player.hp + float(n))

    def _set_speed(n):
        player.speed = clamp(float(n), 1, 40)

    def _set_jump(n):
        player.jump_height = clamp(float(n), 0, 30)

    def _set_gravity(g):
        player.gravity = clamp(float(g), 0, 5)

    return dict(spawn_enemy=_spawn_enemy, spawn_box=_spawn_box, heal=_heal, set_speed=_set_speed,
                set_jump=_set_jump, set_gravity=_set_gravity, enemy_count=lambda: len(enemies),
                player_pos=lambda: tuple(round(v, 1) for v in player.position))


# ---------------- loop ----------------
def game_update():
    if S.regen and not S.paused and player.hp < 50:
        player.hp = min(50, player.hp + 5 * time.dt)
    if time.time() > S.banner_until:
        banner.text = ''
    health_text.text = f'HP {int(player.hp)}'
    health_text.color = color.lime if player.hp > 50 else color.orange if player.hp > 25 else color.red
    ammo_text.text = 'RELOADING' if S.reloading else (f'AMMO {S.ammo}/{S.mag}' if S.gun else 'NO WEAPON')
    if S.phase == 'code':
        mission_text.text = f'MISSION {MISSIONS[S.mission].title}   ☾yellow☽press T to open the terminal'
    elif S.phase == 'combat':
        mission_text.text = f'☾orange☽Enemies left: {len(enemies)}☾default☽   (T = sandbox console)'
    else:
        mission_text.text = '☾lime☽SANDBOX MODE☾default☽   press T to code the world'


def game_input(key):
    if term.enabled:
        if key == 'escape':
            close_terminal()
        elif key == 'f5':
            run_player_code()
        return
    if key == 't up':  # on release, so the T never gets typed into the editor
        open_terminal()
    elif key == 'left mouse down':
        shoot()
    elif key == 'r':
        reload()


Entity(update=game_update, input=game_input)
load()
notify('Welcome, recruit. Press T to open your terminal.' if S.mission == 0
       else f'Progress loaded: mission {S.mission + 1}. Press T.', 6)

if __name__ == '__main__':
    app.run()
