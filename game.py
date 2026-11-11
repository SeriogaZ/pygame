"""Syntax Siege - a first-person sandbox shooter you upgrade by writing Python.

Run:  python game.py
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

from missions import (CURRICULUM, REVIEW_NOTE, REVIEW_PENALTY, REVIEW_REWARD, SANDBOX_HELP,
                      build_mission, feedback_for, run_code)

SAVES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'saves.json')
N = len(CURRICULUM)
SLOTS = 3
ARENA = 55          # half-size of the walled arena
MAX_ENEMIES = 60
MAX_BOXES = 400
CONTROLS = ('WASD move   Mouse look   Space jump   Click shoot   R reload\n'
            'T terminal   F5 run code   Esc close / pause')

app = Ursina(title='Syntax Siege', borderless=False, development_mode=False)
window.color = color.black


def fresh_state():
    return dict(slot=None, mission=0, phase='code', current=None, fails=0, editor_mission=None,
                hud=False, gun=False, ammo=0, reserve=0, mag=12, damage=10, burst=1, pellets=1, auto=False,
                armor=1.0, regen=False, sprint=False, grenade=False, grenade_cd=0.0, turret=False, radar=False,
                reloading=False, paused=True, banner_until=0.0, fire_cd=0.0, trickle=0.0, base_speed=7.0,
                correct=0, wrong=0, confirm_delete=None)


S = SimpleNamespace(**fresh_state())
enemies, pickups, turrets, sandbox_boxes = [], [], [], []


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


def tracer(a, b, col=color.yellow):
    line = Entity(model=Mesh(vertices=[a, b], mode='line', thickness=2), color=col)
    destroy(line, delay=.05)


# ---------------- world ----------------
random.seed(7)
Sky()
sun = DirectionalLight(shadows=True)
sun.look_at(Vec3(1, -1.4, -.6))
AmbientLight(color=color.rgba(.55, .55, .6, 1))

W(model='plane', scale=ARENA * 2 + 10, texture='white_cube', texture_scale=(60, 60),
  color=color.hsv(140, .25, .55), collider='box')
for x, z, sx, sz in ((0, ARENA, ARENA * 2, 1), (0, -ARENA, ARENA * 2, 1), (ARENA, 0, 1, ARENA * 2), (-ARENA, 0, 1, ARENA * 2)):
    W(model='cube', position=(x, 3, z), scale=(sx + 1, 6, sz + 1), texture='brick',
      texture_scale=(max(sx, sz) / 2, 3), color=color.hsv(20, .3, .7), collider='box')


def make_box(x, z, size=1.0, y=None, col=None):
    return W(model='cube', position=(x, size / 2 if y is None else y, z), scale=size, texture='white_cube',
             color=col or color.hsv(30, .5, random.uniform(.45, .7)), collider='box')


for _ in range(28):
    x, z = random.uniform(-ARENA + 4, ARENA - 4), random.uniform(-ARENA + 4, ARENA - 4)
    if abs(x) < 8 and abs(z) < 8:
        continue
    s = random.choice((1.5, 2, 3))
    make_box(x, z, s)
    if random.random() < .3:
        make_box(x, z, s * .7, y=s + s * .35)
for x, z in ((25, 25), (-25, -20), (-28, 26), (30, -28)):  # platforms for the jump jets
    W(model='cube', position=(x, 2.5, z), scale=(8, 5, 8), texture='white_cube', texture_scale=(4, 4),
      color=color.hsv(210, .2, .6), collider='box')
sun.update_bounds()
random.seed()


# ---------------- player ----------------
player = FirstPersonController(position=(0, 0, 0), speed=7)
player.hp = 100.0
player.cursor.color = color.white

skin, sleeve = color.hsv(25, .45, .85), color.hsv(210, .5, .35)
for side in (-1, 1):  # you are a person: forearms + hands in view
    arm = Entity(parent=camera, position=(.33 * side, -.42, .55), rotation=(-12, -8 * side, 0))
    Entity(parent=arm, model='cube', scale=(.13, .13, .45), color=sleeve, z=-.1)
    Entity(parent=arm, model='cube', scale=(.11, .1, .14), color=skin, z=.18)

gun = Entity(parent=camera, position=(.33, -.3, .78), enabled=False)
Entity(parent=gun, model='cube', scale=(.09, .14, .42), color=color.hsv(0, 0, .2))
Entity(parent=gun, model='cube', scale=(.08, .2, .1), position=(0, -.13, -.12), color=color.hsv(0, 0, .15))
muzzle = Entity(parent=gun, model='cube', scale=(.06, .06, .25), z=.3, color=color.black)
flash = Entity(parent=gun, model='quad', z=.46, scale=.1, color=color.orange, enabled=False)


# ---------------- HUD ----------------
MONO = Text.default_monospace_font
hurt_overlay = Entity(parent=camera.ui, model='quad', scale=(3, 2), color=color.rgba(1, 0, 0, 0), z=5)
mission_text = label(position=window.top_left + Vec2(.02, -.02), scale=1.1)
health_text = label(position=window.bottom_left + Vec2(.03, .07), scale=1.8, color=color.lime, enabled=False)
ammo_text = label(position=window.bottom_right + Vec2(-.03, .07), origin=(.5, 0), scale=1.8, enabled=False)
gear_text = label(position=(0, window.bottom.y + .04), origin=(0, 0), scale=1, color=color.light_gray)
banner = label(position=(0, .32), origin=(0, 0), scale=1.6, color=color.yellow)


def notify(msg, seconds=4):
    banner.text = msg
    S.banner_until = time.time() + seconds


# ---------------- enemies ----------------
KINDS = {  # hp, speed range, size, color, damage per hit
    'grunt': (60, (2.4, 3.4), 1, color.hsv(0, .75, .65), 10),
    'runner': (30, (5.0, 6.0), .85, color.hsv(110, .7, .55), 6),
    'boss': (450, (1.8, 2.0), 1.9, color.hsv(280, .7, .5), 25),
}


class Enemy(Entity):
    # ponytail: enemies walk straight at you through crates; add pathfinding if it bothers players
    def __init__(self, position, kind='grunt'):
        hp, speeds, size, body, dmg = KINDS[kind]
        super().__init__(position=position, scale=size)
        self.kind, self.hp, self.dmg = kind, hp, dmg
        self.speed = random.uniform(*speeds) + S.mission * .05
        self.attack_cd = 0
        self.collider = BoxCollider(self, center=Vec3(0, 1, 0), size=Vec3(.9, 2, .6))
        self.legs = [W(parent=self, model='cube', scale=(.25, .8, .25), position=(s * .15, .4, 0),
                       color=color.hsv(0, 0, .2)) for s in (-1, 1)]
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
            swing = math.sin(time.time() * self.speed * 3) * 30
            self.legs[0].rotation_x, self.legs[1].rotation_x = swing, -swing
        else:
            self.attack_cd -= time.dt
            if self.attack_cd <= 0:
                self.attack_cd = 1
                hurt(self.dmg)

    def hit(self, dmg):
        if self not in enemies:
            return
        self.hp -= dmg
        self.torso.blink(color.white, duration=.08)
        self.position -= self.forward * .15
        if self.hp <= 0:
            enemies.remove(self)
            self.collider = None
            ursfx([(0, 1), (.1, .7), (.2, .3), (.35, .1), (.5, 0)], volume=.4, wave='sine', pitch=8,
                  pitch_change=-12, speed=2)
            if self.kind == 'boss' or random.random() < .35:
                Pickup(Vec3(self.x, 0, self.z))
            self.animate_scale(0, .2)
            destroy(self, delay=.25)
            check_wave_clear()


class Pickup(Entity):
    def __init__(self, position):
        super().__init__(model='cube', scale=.35, color=color.yellow, position=position + Vec3(0, .4, 0))
        pickups.append(self)

    def update(self):
        self.rotation_y += 120 * time.dt
        if S.gun and (self.position - player.position).length() < 1.8:
            S.reserve += 8
            pickups.remove(self)
            destroy(self)
            ursfx([(0, 0), (.05, 1), (.1, .6), (.15, .3), (.2, 0)], volume=.3, wave='sine', pitch=12, speed=2)
            notify('+8 ammo', 1)


def spawn_enemy(kind='grunt'):
    if len(enemies) >= MAX_ENEMIES:
        return
    ang, r = random.uniform(0, 6.283), random.uniform(22, 40)
    x = clamp(player.x + math.cos(ang) * r, -ARENA + 3, ARENA - 3)
    z = clamp(player.z + math.sin(ang) * r, -ARENA + 3, ARENA - 3)
    Enemy(position=(x, 0, z), kind=kind)


def start_wave(m):
    S.phase = 'combat'
    runners = m.wave // 3 if S.mission >= 9 else 0
    for k in range(m.wave):
        spawn_enemy('runner' if k < runners else 'grunt')
    if m.boss:
        spawn_enemy('boss')
    if S.gun:
        S.reserve += 10
    notify(f'WAVE INCOMING: {m.wave + m.boss} enemies!' + ('  BOSS!' if m.boss else ''))


def check_wave_clear():
    if S.phase == 'combat' and not enemies:
        advance()


def set_mission(i):
    S.mission = i
    S.current = build_mission(i) if i < N else None
    S.fails = 0


def advance():
    set_mission(S.mission + 1)
    if S.mission >= N:
        S.phase = 'free'
        notify('ALL MISSIONS COMPLETE! Press T: the terminal is now a free sandbox.', 8)
    else:
        S.phase = 'code'
        notify(f'Area clear. New mission: {S.current.title}  (press T)')
    save_slot()


# ---------------- player actions ----------------
def hurt(n):
    player.hp -= n * S.armor
    hurt_overlay.color = color.rgba(1, 0, 0, .35)
    hurt_overlay.animate_color(color.rgba(1, 0, 0, 0), duration=.4)
    ursfx([(0, 1), (.05, .7), (.1, .5), (.2, .2), (.3, 0)], volume=.4, wave='square', pitch=-20, speed=3)
    if player.hp <= 0:
        player.hp = 100
        player.position = Vec3(0, 0, 0)
        notify('YOU DIED. Respawned at the center.')


def shoot():
    if not S.gun or S.reloading or S.auto:  # auto fire is handled in game_update while held
        return
    if S.ammo <= 0:
        notify('Empty! Press R to reload.', 1.5)
        return
    for k in range(S.burst):
        invoke(fire_once, delay=k * .09)


def fire_once():
    if S.ammo <= 0 or S.paused or S.reloading:
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
        tracer(muzzle.world_position + d * .2, end)
        if hit.hit and isinstance(hit.entity, Enemy):
            hit.entity.hit(S.damage)


def reload():
    if not S.gun or S.reloading or S.ammo >= S.mag or S.reserve <= 0:
        return
    S.reloading = True

    def done():
        take = min(S.mag - S.ammo, S.reserve)
        S.ammo += take
        S.reserve -= take
        S.reloading = False
    invoke(done, delay=1)


class Grenade(Entity):
    def __init__(self):
        super().__init__(model='sphere', scale=.3, color=color.hsv(100, .5, .3),
                         position=camera.world_position + camera.forward * .8)
        self.vel = camera.forward * 20 + Vec3(0, 4, 0)
        self.life = 2.2

    def update(self):
        if S.paused:
            return
        self.vel += Vec3(0, -25 * time.dt, 0)
        self.position += self.vel * time.dt
        self.life -= time.dt
        if self.y <= .15 or self.life <= 0:
            explode(self.position)
            destroy(self)


def explode(pos):
    fx = Entity(model='sphere', position=pos, scale=1, color=color.rgba(1, .6, .1, .8))
    fx.animate_scale(12, .25)
    fx.fade_out(duration=.35)
    destroy(fx, delay=.4)
    ursfx([(0, 1), (.1, .9), (.3, .5), (.6, .2), (1, 0)], volume=.7, wave='noise', pitch=-30, speed=1.5)
    for e in enemies[:]:
        if (e.position - pos).length() < 6:
            e.hit(150)


def throw_grenade():
    if S.grenade and S.grenade_cd <= 0:
        S.grenade_cd = 4
        Grenade()


class Turret(Entity):
    def __init__(self, position):
        super().__init__(position=position)
        W(parent=self, model='cube', scale=(.8, .6, .8), y=.3, color=color.hsv(200, .3, .4))
        self.head = W(parent=self, model='cube', scale=(.45, .35, .9), y=.85, color=color.hsv(200, .6, .7))
        self.cd = 0

    def update(self):
        if S.paused or not enemies:
            return
        target = min(enemies, key=lambda e: (e.position - self.position).length())
        if (target.position - self.position).length() > 28:
            return
        aim = target.world_position + Vec3(0, target.scale_y, 0)
        self.head.look_at(aim)
        self.cd -= time.dt
        if self.cd <= 0:
            self.cd = .5
            tracer(self.head.world_position, aim, color.cyan)
            target.hit(12)


def place_turret():
    if not S.turret:
        return
    for t in turrets:
        destroy(t)
    turrets.clear()
    turrets.append(Turret(position=player.position + player.forward * 2))


def apply_reward(key):
    if key == 'hud':
        S.hud = True
    elif key == 'gun':
        S.gun = True
        S.ammo, S.reserve = S.mag, 24
    elif key == 'ammo':
        S.reserve += REVIEW_REWARD
    elif key == 'damage':
        S.damage = 30
    elif key == 'armor':
        S.armor = .7
    elif key == 'regen':
        S.regen = True
    elif key == 'sprint':
        S.sprint = True
    elif key == 'burst':
        S.burst = 3
        S.mag = 30
    elif key == 'grenade':
        S.grenade = True
    elif key == 'jump':
        player.jump_height = 6
    elif key == 'turret':
        S.turret = True
    elif key == 'shotgun':
        S.pellets = 6
    elif key == 'mag':
        S.mag = 50
    elif key == 'radar':
        S.radar = True
        for e in enemies:
            e.marker.enabled = True
    elif key == 'auto':
        S.auto = True
    gun.enabled = S.gun
    health_text.enabled = ammo_text.enabled = S.hud


# ---------------- save slots ----------------
def read_saves():
    try:
        with open(SAVES) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def write_saves(data):
    with open(SAVES, 'w') as f:
        json.dump(data, f, indent=1)


def save_slot():
    if S.slot is None:
        return
    data = read_saves()
    data[str(S.slot)] = dict(mission=S.mission, phase=S.phase, ammo=S.ammo, reserve=S.reserve,
                             correct=S.correct, wrong=S.wrong, saved=time.strftime('%d %b %H:%M'))
    write_saves(data)


def reset_world():
    for e in enemies + pickups + turrets + sandbox_boxes:
        destroy(e)
    for lst in (enemies, pickups, turrets, sandbox_boxes):
        lst.clear()
    S.__dict__.update(fresh_state())
    player.position, player.rotation = Vec3(0, 0, 0), Vec3(0, 0, 0)
    player.hp, player.speed, player.jump_height, player.gravity = 100.0, 7, 2, 1
    apply_reward(None)  # syncs gun/HUD visibility with the fresh state
    term_out.text = ''


def start_slot(i):
    reset_world()
    S.slot = i
    data = read_saves().get(str(i))
    if data:
        done = min(int(data.get('mission', 0)), N)
        combat = data.get('phase') == 'combat' and done < N
        for k in range(done + combat):
            apply_reward(build_mission(k).reward)
        S.ammo, S.reserve = data.get('ammo', S.ammo), data.get('reserve', S.reserve)
        S.correct, S.wrong = data.get('correct', 0), data.get('wrong', 0)
        set_mission(done)
        if done >= N:
            S.phase = 'free'
        elif combat:
            start_wave(S.current)
        notify(f'Slot {i} loaded. Mission {min(done + 1, N)}/{N}. Press T.', 5)
    else:
        set_mission(0)
        save_slot()
        notify('Welcome, recruit. Press T to open your terminal.', 6)
    title.disable()
    set_ui(False)


def delete_slot(i):
    if S.confirm_delete != i:
        S.confirm_delete = i
        del_buttons[i - 1].text = 'Sure?'
        return
    data = read_saves()
    data.pop(str(i), None)
    write_saves(data)
    refresh_title()


def set_ui(is_open):
    S.paused = is_open
    player.enabled = not is_open  # the controller unlocks the mouse when disabled


# ---------------- title + pause menus ----------------
title = Entity(parent=camera.ui, z=-3)
Entity(parent=title, model='quad', scale=(4, 2), color=color.rgba(.02, .03, .06, .94))
label(parent=title, text='SYNTAX SIEGE', origin=(0, 0), y=.33, scale=4, color=color.cyan, font=MONO)
label(parent=title, text='Learn Python. Upgrade your gear. Survive.', origin=(0, 0), y=.24, scale=1.2,
      color=color.light_gray)
label(parent=title, text='Choose a save slot', origin=(0, 0), y=.15, scale=1, color=color.gray)
slot_buttons, del_buttons = [], []
for i in range(1, SLOTS + 1):
    y = .07 - (i - 1) * .11
    slot_buttons.append(Button(parent=title, scale=(.86, .085), position=(-.08, y), color=color.hsv(210, .5, .3),
                               on_click=lambda i=i: start_slot(i)))
    del_buttons.append(Button(parent=title, text='Delete', scale=(.14, .085), position=(.45, y),
                              color=color.hsv(0, .6, .4), on_click=lambda i=i: delete_slot(i)))
Button(parent=title, text='Quit', scale=(.2, .065), y=-.3, color=color.hsv(0, 0, .25), on_click=application.quit)
label(parent=title, text=CONTROLS, origin=(0, 0), y=-.42, scale=.9, color=color.gray, font=MONO)


def refresh_title():
    saves = read_saves()
    for i, (b, d) in enumerate(zip(slot_buttons, del_buttons), 1):
        s = saves.get(str(i))
        if s:
            m = min(int(s.get('mission', 0)), N)
            where = 'COMPLETE (sandbox)' if m >= N else f'Mission {m + 1}/{N}: {build_mission(m).title}'
            b.text = f'Slot {i}   {where}   [{s.get("saved", "")}]'
        else:
            b.text = f'Slot {i}   - empty -   New game'
        d.enabled = bool(s)
        d.text = 'Delete'
    S.confirm_delete = None


def show_title():
    refresh_title()
    title.enable()
    set_ui(True)


pause = Entity(parent=camera.ui, z=-3, enabled=False)
Entity(parent=pause, model='quad', scale=(4, 2), color=color.rgba(0, 0, 0, .75))
label(parent=pause, text='PAUSED', origin=(0, 0), y=.25, scale=3, color=color.cyan, font=MONO)
pause_info = label(parent=pause, origin=(0, 0), y=.17, color=color.lime)


def resume():
    pause.disable()
    set_ui(False)


def pause_save():
    save_slot()
    pause_info.text = f'Saved to slot {S.slot}.'


def quit_to_title():
    save_slot()
    pause.disable()
    reset_world()
    show_title()


def save_and_exit():
    save_slot()
    application.quit()


for k, (txt, fn) in enumerate((('Resume', resume), ('Save game', pause_save),
                               ('Save & quit to title', quit_to_title), ('Save & exit game', save_and_exit))):
    Button(parent=pause, text=txt, scale=(.42, .075), y=.07 - k * .1, color=color.hsv(210, .5, .3), on_click=fn)


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


term = Entity(parent=camera.ui, enabled=False, z=-1)
Entity(parent=term, model='quad', scale=(1.8, .98), color=color.rgba(.03, .04, .08, .96), z=.1)
Entity(parent=term, model='quad', scale=(.005, .9), x=-.03, color=color.dark_gray)
term_title = label(parent=term, position=(-.86, .45), scale=1.3, color=color.cyan, font=MONO)
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


def set_editor(text, key):
    if S.editor_mission != key:
        S.editor_mission = key
        editor.text = text
        editor.cursor.position = (0, len(text.split('\n')) - 1)
        editor.render()
        term_out.text = ''


def open_terminal():
    set_ui(True)
    term.enable()
    if S.phase == 'code':
        m = S.current
        term_title.text = f'MISSION {S.mission + 1}/{N}: {m.title}'
        note = f'☾orange☽{REVIEW_NOTE}☾default☽\n\n' if m.review else ''
        term_info.text = wrap(f'{note}{m.lesson}\n\n☾yellow☽TASK:☾default☽\n{m.task}', 52)
        set_editor(m.starter, S.mission)
    else:
        term_title.text = 'SANDBOX CONSOLE'
        status = (f'☾orange☽{len(enemies)} enemies left. Clear them to unlock the next mission.☾default☽\n\n'
                  if S.phase == 'combat' else f'☾lime☽Score: {S.correct} correct, {S.wrong} wrong.☾default☽\n\n')
        term_info.text = status + SANDBOX_HELP
        set_editor('', 'sandbox')
    editor.active = True


def close_terminal():
    term.disable()
    set_ui(False)


def run_player_code():
    code = editor.text
    if S.phase != 'code':
        ns, out, err = run_code(code, sandbox_api())
        term_out.text = wrap((out[-1500:] if out else '') + (f'☾red☽{err}' if err else ('' if out else '☾lime☽ok')))
        return
    m = S.current
    ok, msg = m.check(code)
    if ok:
        S.correct += 1
        ursfx([(0, 0), (.1, 1), (.3, .7), (.5, .3), (.8, 0)], volume=.4, wave='sine', pitch=4, pitch_change=8, speed=2)
        printed = f'☾light_gray☽> {msg.strip()}\n\n' if msg.strip() else ''
        bonus = ''
        if m.review and S.fails == 0:
            S.reserve += 10
            bonus = '\nPerfect, first try: +10 bonus ammo!'
        fight = (f'\n\n{m.wave + m.boss} enemies are coming. Press Esc and fight!' if m.wave
                 else '\n\nPress Esc, then T again for the next mission.')
        term_out.text = wrap(f'{printed}☾lime☽CORRECT!\n{m.reward_text}{bonus}{fight}')
        apply_reward(m.reward)
        if m.wave:
            start_wave(m)
            save_slot()
        else:
            advance()
        return
    S.fails += 1
    S.wrong += 1
    penalty = ''
    if m.review and S.gun:
        lost = min(REVIEW_PENALTY, S.reserve + S.ammo)
        from_reserve = min(lost, S.reserve)
        S.reserve -= from_reserve
        S.ammo -= lost - from_reserve
        if lost:
            penalty = f'\n\n☾orange☽-{lost} AMMO (review penalty)'
    extra = feedback_for(m, S.fails, '').strip('\n')
    colour = 'lime' if S.fails >= 3 else 'yellow'
    term_out.text = wrap(f'☾red☽Attempt {S.fails}: {msg}\n\n☾{colour}☽{extra}{penalty}')
    ursfx([(0, 1), (.1, .6), (.15, .4), (.2, .2), (.3, 0)], volume=.3, wave='square', pitch=-15, speed=3)


def sandbox_api():
    def _spawn_enemy(n=1):
        for _ in range(min(int(n), MAX_ENEMIES - len(enemies))):
            spawn_enemy()

    def _spawn_box(x, z, size=1, y=None):
        if len(sandbox_boxes) >= MAX_BOXES:
            raise ValueError(f'box limit reached ({MAX_BOXES})')
        size = clamp(float(size), .2, 20)
        sandbox_boxes.append(make_box(clamp(float(x), -ARENA, ARENA), clamp(float(z), -ARENA, ARENA), size,
                                      None if y is None else float(y), color.hsv(random.uniform(0, 360), .6, .8)))

    def _heal(n=100):
        player.hp = min(100, player.hp + float(n))

    def _set_speed(n):
        S.base_speed = clamp(float(n), 1, 40)

    def _set_jump(n):
        player.jump_height = clamp(float(n), 0, 30)

    def _set_gravity(g):
        player.gravity = clamp(float(g), 0, 5)

    return dict(spawn_enemy=_spawn_enemy, spawn_box=_spawn_box, heal=_heal, set_speed=_set_speed,
                set_jump=_set_jump, set_gravity=_set_gravity, enemy_count=lambda: len(enemies),
                player_pos=lambda: tuple(round(v, 1) for v in player.position))


# ---------------- loop ----------------
def game_update():
    if time.time() > S.banner_until:
        banner.text = ''
    if S.slot is None:
        mission_text.text = ''
        gear_text.text = ''
        return
    S.reserve = min(S.reserve, S.mag * 4)  # cap keeps the review penalty meaningful
    if player.y < 0:  # a long frame (e.g. a wave spawning) can push the controller through the floor
        player.y = 0
        player.air_time = 0
    if not S.paused:
        if S.regen and player.hp < 50:
            player.hp = min(50, player.hp + 5 * time.dt)
        S.grenade_cd -= time.dt
        player.speed = S.base_speed * (1.7 if S.sprint and held_keys['shift'] else 1)
        if S.auto and mouse.left and not S.reloading:
            S.fire_cd -= time.dt
            if S.fire_cd <= 0:
                S.fire_cd = .1
                fire_once()
        if S.gun and S.ammo == 0 and S.reserve == 0 and not S.reloading:  # never fully stuck without ammo
            S.trickle += time.dt
            if S.trickle >= 1.5:
                S.trickle, S.ammo = 0, 1
    health_text.text = f'HP {int(player.hp)}'
    health_text.color = color.lime if player.hp > 50 else color.orange if player.hp > 25 else color.red
    if S.reloading:
        ammo_text.text = 'RELOADING'
    elif not S.gun:
        ammo_text.text = 'NO WEAPON'
    else:
        ammo_text.text = f'AMMO {S.ammo} | {S.reserve}' + ('  (emergency charge)' if S.ammo + S.reserve <= 1 else '')
    gear = []
    if S.sprint:
        gear.append('Shift sprint')
    if S.grenade:
        gear.append('G grenade' + ('' if S.grenade_cd <= 0 else f' ({math.ceil(S.grenade_cd)}s)'))
    if S.turret:
        gear.append('Q turret')
    gear_text.text = '    '.join(gear)
    if S.phase == 'code':
        tag = 'REVIEW ' if S.current.review else ''
        mission_text.text = f'{tag}MISSION {S.mission + 1}/{N}: {S.current.title}   ☾yellow☽press T to open the terminal'
    elif S.phase == 'combat':
        mission_text.text = f'☾orange☽Enemies left: {len(enemies)}☾default☽   (T = sandbox console, Esc = pause)'
    else:
        mission_text.text = '☾lime☽SANDBOX MODE☾default☽   press T to code the world'


def game_input(key):
    if title.enabled:
        return
    if pause.enabled:
        if key == 'escape':
            resume()
        return
    if term.enabled:
        if key == 'escape':
            close_terminal()
        elif key == 'f5':
            run_player_code()
        return
    if key == 'escape':
        pause_info.text = ''
        pause.enable()
        set_ui(True)
    elif key == 't up':  # on release, so the T never gets typed into the editor
        open_terminal()
    elif key == 'left mouse down':
        shoot()
    elif key == 'r':
        reload()
    elif key == 'g':
        throw_grenade()
    elif key == 'q':
        place_turret()


Entity(update=game_update, input=game_input)
show_title()

if __name__ == '__main__':
    app.run()
