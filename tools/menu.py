"""Genera il menù giorno per giorno del blocco.

Scrive due cose:
  - menu.ics: il calendario con i pasti e i promemoria (scongela, pranzo, cena, palestra);
  - in index.html, tra /* MENU:START */ e /* MENU:END */, la costante MENU usata dalla scheda Dieta.

Uso, dalla cartella del sito:  python tools/menu.py
Va rilanciato ogni volta che si cambiano le regole qui sotto.
"""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
START = date(2026, 11, 16)            # lunedì della settimana 1 (uguale a BLOCK.start nell'app)
WEEKS = 16
DELOADS = {6, 12}
SITE = 'https://stefanosurian.github.io/ripartenza/'

# Orari (pranzo 12, cena 19, palestra alle 3 della notte dopo)
T_THAW = (8, 0)        # scongela per la cena
T_LUNCH = (12, 0)
T_DINNER = (19, 0)
T_TOMORROW = (19, 45)  # dopo cena: cosa preparare per domani
T_FREEZER = (16, 0)    # domenica: si cucina per il freezer
ALERT_BEFORE_MEAL = 30  # minuti

DOW = ['Lunedì', 'Martedì', 'Mercoledì', 'Giovedì', 'Venerdì', 'Sabato', 'Domenica']
MONTHS = ['gennaio', 'febbraio', 'marzo', 'aprile', 'maggio', 'giugno', 'luglio',
          'agosto', 'settembre', 'ottobre', 'novembre', 'dicembre']

# Ricette (nomi uguali a RECIPES / FREEZER nell'app)
PASTA_POLLO = 'Pasta, pollo e zucchine'
WOK = 'Riso saltato stile wok'
PASTA_TONNO = 'Pasta al pomodoro, tonno e capperi'
INSALATA = 'Insalata fredda di riso e tonno'
RAGU = 'Pasta al ragù magro'
RISO_PISELLI = 'Riso, piselli e pollo'
PATATE_TONNO = 'Insalata di patate, fagiolini e tonno'
MERLUZZO = 'Merluzzo al forno con patate croccanti'
PIZZAIOLA = 'Merluzzo alla pizzaiola con patate'
SALMONE = 'Salmone in padella'
POLLO_LIMONE = 'Pollo al limone con verdure in teglia'
POLLO_VERZA = 'Pollo e verza al vino bianco'
BURGER = 'Burger di manzo, patate, peperoni e cipolla'
FRITTATA = 'Frittata di zucchine o spinaci al forno'
TACCHINO = 'Tacchino alla piastra con minestrone'
FREEZER = ['Spezzatino di pollo, peperoni e cipolla', 'Polpette di manzo al sugo',
           'Burger pronti, da cuocere da congelati', 'Pollo e verza, in dose da 4']
FREEZER_SHORT = ['spezzatino di pollo', 'polpette al sugo', 'burger pronti', 'pollo e verza']

ON_RECIPES = {PASTA_POLLO, WOK, RAGU, RISO_PISELLI, MERLUZZO, PIZZAIOLA, SALMONE, POLLO_LIMONE, POLLO_VERZA}

# Pranzi freddi da preparare la sera prima, anche per più giorni
COLD = {INSALATA: "l'insalata fredda di riso", PATATE_TONNO: "l'insalata di patate, fagiolini e tonno"}

# Cosa tirare fuori dal freezer (None = niente da scongelare)
THAW = {
    PASTA_POLLO: 'il pollo da 150 g', WOK: 'il pollo da 150 g', RISO_PISELLI: 'il pollo da 150 g',
    RAGU: "il macinato da 130 g (o 1 contenitore di ragù, se l'hai congelato)",
    PIZZAIOLA: 'il merluzzo, se è surgelato',
    POLLO_LIMONE: 'il pollo da 200 g', POLLO_VERZA: 'il pollo da 200 g',
    MERLUZZO: 'il merluzzo, se è surgelato', SALMONE: 'il salmone, se è surgelato',
    BURGER: 'il macinato da 200 g, se è surgelato',
    FREEZER[0]: '1 contenitore di spezzatino', FREEZER[1]: '1 contenitore di polpette',
    FREEZER[3]: '1 contenitore di pollo e verza',
}

# Settimana tipo: dispari (1, 3, 5…) e pari (2, 4…). 'FRZ' = cena dal freezer (dalla settimana 2).
# Il venerdì ha due versioni: OFF (settimane 1–2) e ON (dalla 3ª, quando diventa giorno di palestra).
# Settimana 1: quella già iniziata, con le ricette di prima.
WEEK1 = {
    0: (PASTA_POLLO, POLLO_LIMONE),
    1: (INSALATA, ('FRZ', TACCHINO)),
    2: (WOK, MERLUZZO),
    3: (INSALATA, ('FRZ', FRITTATA)),
    4: {'off': (PASTA_TONNO, BURGER), 'on': (PASTA_POLLO, SALMONE)},
    5: (WOK, 'LIBERO'),
    6: (PASTA_POLLO, POLLO_VERZA),
}
ODD = {
    0: (PASTA_POLLO, POLLO_LIMONE),
    1: (INSALATA, ('FRZ', TACCHINO)),
    2: (WOK, MERLUZZO),
    3: (INSALATA, ('FRZ', FRITTATA)),
    4: {'off': (PASTA_TONNO, BURGER), 'on': (RAGU, SALMONE)},
    5: (RISO_PISELLI, 'LIBERO'),
    6: (PASTA_TONNO, POLLO_VERZA),
}
EVEN = {
    0: (WOK, SALMONE),
    1: (PATATE_TONNO, ('FRZ', TACCHINO)),
    2: (PASTA_POLLO, PIZZAIOLA),
    3: (PATATE_TONNO, ('FRZ', FRITTATA)),
    4: {'off': (RISO_PISELLI, TACCHINO), 'on': (RISO_PISELLI, POLLO_VERZA)},
    5: (RAGU, 'LIBERO'),
    6: (PASTA_TONNO, FRITTATA),
}

# Eccezioni a date precise: (pranzo, cena), None = segui la settimana tipo
FEAST = ('FESTA', 'Pasto delle feste: libero, senza sensi di colpa')
OVERRIDES = {
    date(2026, 11, 17): ((PASTA_TONNO, ''), (POLLO_LIMONE, "dose OFF: patate 200 g · pollo 150 g a cubetti, + 100 g di albume se ce l'hai")),
    date(2026, 12, 24): (None, FEAST),
    date(2026, 12, 25): (FEAST, None),
    date(2026, 12, 26): (FEAST, None),
    date(2026, 12, 31): (None, FEAST),
    date(2027, 1, 1): (FEAST, None),
}


def week_of(d):
    return (d - START).days // 7 + 1


# Giorni spostati rispetto alla regola (palestra la notte dopo questi giorni)
FORCE_ON = {date(2026, 11, 18), date(2026, 11, 20)}   # settimana 1: mercoledì e venerdì
FORCE_OFF = {date(2026, 11, 16)}                        # settimana 1: lunedì saltato


def is_on(d):
    if d in FORCE_ON:
        return True
    if d in FORCE_OFF:
        return False
    w, k = week_of(d), d.weekday()
    return k in (0, 2) or (w >= 3 and k == 4)


def workout(d):
    """Full A / Full B: settimane dispari A-B-A, pari B-A-B (nelle sett. 1–2 solo le prime due)."""
    w = week_of(d)
    mon = d - timedelta(days=d.weekday())
    n = [k for k in range(7) if is_on(mon + timedelta(days=k))].index(d.weekday())
    return 'Full ' + ('ABA' if w % 2 else 'BAB')[n]


def freezer_for(w):
    """Ricetta da freezer mangiata nella settimana w (cucinata la domenica della settimana dispari prima)."""
    return (w - 2) // 2 % 4


def carbs_note(slot, recipe, on):
    if slot == 'l':
        if not on and recipe in ON_RECIPES:
            return 'dose OFF: ' + {WOK: 'riso 70 g', RISO_PISELLI: 'riso 40 g, piselli sempre 150 g'}.get(recipe, 'pasta 70 g')
        return ''
    if recipe in FREEZER:
        return 'con pane 90 g o patate 300 g' if on else 'con pane 60 g o patate 200 g'
    if not on and recipe in ON_RECIPES:
        return 'giorno OFF: pane 60 g o patate 200 g'
    return ''


def plan_day(d):
    w, k, on = week_of(d), d.weekday(), is_on(d)
    tpl = (WEEK1 if w == 1 else ODD if w % 2 else EVEN)[k]
    if isinstance(tpl, dict):
        tpl = tpl['on' if on else 'off']
    lunch, dinner = tpl
    if isinstance(dinner, tuple):
        dinner = FREEZER[freezer_for(w)] if w >= 2 else dinner[1]
    meals = {}
    for slot, r in (('l', lunch), ('d', dinner)):
        if r == 'LIBERO':
            meals[slot] = {'free': 'Pasto libero: pizza, sushi o quello che ti va'}
        else:
            meals[slot] = {'r': r, 'n': carbs_note(slot, r, on)}
    ov = OVERRIDES.get(d)
    if ov:
        for slot, x in zip(('l', 'd'), ov):
            if x is None:
                continue
            meals[slot] = {'free': x[1]} if x[0] == 'FESTA' else {'r': x[0], 'n': x[1]}
    return {
        'd': d.isoformat(), 'w': w, 't': 'on' if on else 'off',
        'b': 'Dolce' if on or k not in (1, 3, 6) else 'Salata',
        'l': meals['l'], 'dn': meals['d'],
        'gym': workout(d) if on else '',
        'light': w in DELOADS,
    }


def build():
    days = [plan_day(START + timedelta(days=i)) for i in range(WEEKS * 7)]
    by = {x['d']: x for x in days}
    covered = set()  # pranzi di insalata già preparati in un giorno precedente
    for x in days:
        d = date.fromisoformat(x['d'])
        x['todo'] = []
        # mattina: scongela per la cena
        dn = x['dn']
        if dn.get('r') in THAW and not (d in OVERRIDES and OVERRIDES[d][1]):
            x['todo'].append(['08:00', f"Scongela {THAW[dn['r']]}: dal freezer al frigo, è per la cena"])
        if dn.get('r') == FREEZER[2]:
            x['todo'].append(['08:00', 'Stasera burger pronti: non serve scongelarli, si cuociono da congelati'])
        # sera: cosa preparare per domani
        nxt = by.get((d + timedelta(days=1)).isoformat())
        if nxt:
            tl = nxt['l'].get('r')
            if tl in THAW:
                x['todo'].append(['19:45', f"Per il pranzo di domani tira fuori {THAW[tl]} e mettilo in frigo"])
            if tl in COLD and nxt['d'] not in covered:
                later = [y for y in (by.get((d + timedelta(days=j)).isoformat()) for j in (2, 3)) if y and y['l'].get('r') == tl][:1]
                covered.update(y['d'] for y in later)
                n = 1 + len(later)
                when = f" (l'altra è per {DOW[date.fromisoformat(later[0]['d']).weekday()].lower()})" if later else ''
                x['todo'].append(['19:45', f"Prepara {COLD[tl]} per domani: {n} porzion{'i' if n > 1 else 'e'}{when}, da condire al momento"])
        # sabato prima: controlla di avere gli ingredienti
        if d.weekday() == 5 and x['w'] % 2 and x['w'] < WEEKS:
            x['todo'].append(['10:00', f"Domani si cucina per il freezer: {FREEZER_SHORT[freezer_for(x['w'] + 1)]}. Controlla di avere gli ingredienti (Ricette → Da congelare)"])
        # domenica delle settimane dispari: si cucina per il freezer
        if d.weekday() == 6 and x['w'] % 2 and x['w'] < WEEKS:
            i = freezer_for(x['w'] + 1)
            x['cook'] = FREEZER[i]
            x['todo'].append(['16:00', f"Oggi si cucina per il freezer: {FREEZER_SHORT[i]}, 4 porzioni (ricetta in Ricette → Da congelare)"])
        x['todo'].sort()
    return days


# ---------- iCalendar ----------
def ics_text(s):
    return s.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')


def fold(line):
    out, b = [], line.encode('utf-8')
    while len(b) > 75:
        cut = 75 if not out else 74
        while (b[cut] & 0xC0) == 0x80:  # non spezzare un carattere UTF-8
            cut -= 1
        out.append(b[:cut].decode('utf-8'))
        b = b[cut:]
    out.append(b.decode('utf-8'))
    return '\r\n '.join(out)


def dt(d, hm):
    return f"{d.strftime('%Y%m%d')}T{hm[0]:02d}{hm[1]:02d}00"


def event(uid, d, hm, minutes, summary, desc='', alarm=None, allday=False):
    lines = ['BEGIN:VEVENT', f'UID:{uid}@palestroxa', f'DTSTAMP:{STAMP}']
    if allday:
        lines += [f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}",
                  'TRANSP:TRANSPARENT']
    else:
        start = datetime(d.year, d.month, d.day, *hm)
        end = start + timedelta(minutes=minutes)
        lines += [f'DTSTART:{dt(start, (start.hour, start.minute))}', f'DTEND:{dt(end, (end.hour, end.minute))}']
    lines += [f'SUMMARY:{ics_text(summary)}']
    if desc:
        lines.append(f'DESCRIPTION:{ics_text(desc)}')
    if alarm is not None:
        trig = f'-PT{alarm}M' if alarm > 0 else 'PT0M'
        lines += ['BEGIN:VALARM', 'ACTION:DISPLAY', f'DESCRIPTION:{ics_text(summary)}', f'TRIGGER:{trig}', 'END:VALARM']
    lines.append('END:VEVENT')
    return lines


def meal_name(m):
    return m['r'] + (f" ({m['n']})" if m.get('n') else '') if m.get('r') else m['free']


def write_ics(days):
    L = ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//Palestroxa//Menu//IT', 'CALSCALE:GREGORIAN', 'METHOD:PUBLISH',
         'X-WR-CALNAME:Palestroxa', 'X-WR-TIMEZONE:Europe/Rome', 'X-WR-CALDESC:Menù e promemoria della dieta',
         'REFRESH-INTERVAL;VALUE=DURATION:PT12H', 'X-PUBLISHED-TTL:PT12H']
    for x in days:
        d = date.fromisoformat(x['d'])
        key = d.strftime('%Y%m%d')
        snack = 'di notte, attorno alla palestra' if x['t'] == 'on' else 'pomeriggio: yogurt, frutta e mandorle'
        overview = '\n'.join([
            f"Colazione: {x['b'].lower()}", f"Pranzo (12:00): {meal_name(x['l'])}",
            f"Spuntino: {snack}", f"Cena (19:00): {meal_name(x['dn'])}", '', 'Ricette e dosi nell\'app: ' + SITE])
        title = 'Giorno ON · palestra stanotte' if x['t'] == 'on' else 'Giorno OFF'
        L += event(f'{key}-day', d, None, 0, title, overview, allday=True)
        for slot, label, hm in (('l', 'Pranzo', T_LUNCH), ('dn', 'Cena', T_DINNER)):
            m = x[slot]
            if m.get('r'):
                desc = (m['n'] + '\n' if m.get('n') else '') + 'Ricetta: app → Dieta → Menù'
                L += event(f'{key}-{slot}', d, hm, 45, f"{label}: {m['r']}", desc, alarm=ALERT_BEFORE_MEAL)
            else:
                L += event(f'{key}-{slot}', d, hm, 60, f"{label}: {m['free']}", alarm=ALERT_BEFORE_MEAL)
        for i, (hm, text) in enumerate(x['todo']):
            h, mi = map(int, hm.split(':'))
            L += event(f'{key}-todo{i}', d, (h, mi), 10, text, alarm=0)
        if x['gym']:
            night = d + timedelta(days=1)
            extra = ' · settimana leggera: 2 serie per esercizio' if x['light'] else ''
            desc = f"Spuntino: banana appena sveglio, panino con bresaola al rientro.{extra}\nScheda e timer: app → Allenamento"
            # l'avviso arriva alle 20:00 della sera prima (7 ore prima delle 3)
            L += event(f'{key}-gym', night, (3, 0), 75, f"Palestra · {x['gym']}", desc, alarm=7 * 60)
    L.append('END:VCALENDAR')
    (ROOT / 'menu.ics').write_text('\r\n'.join(fold(l) for l in L) + '\r\n', encoding='utf-8', newline='')


def write_app(days):
    p = ROOT / 'index.html'
    s = p.read_text(encoding='utf-8')
    data = json.dumps(days, ensure_ascii=False, separators=(',', ':'))
    block = f'/* MENU:START (generato da tools/menu.py: non modificare a mano) */\nconst MENU = {data};\n/* MENU:END */'
    new, n = re.subn(r'/\* MENU:START.*?/\* MENU:END \*/', lambda _: block, s, flags=re.S)
    assert n == 1, 'segnaposto MENU non trovato in index.html'
    p.write_text(new, encoding='utf-8', newline='')


STAMP = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

if __name__ == '__main__':
    days = build()
    write_ics(days)
    write_app(days)
    print(f"ok: {len(days)} giorni, {sum(len(x['todo']) for x in days)} promemoria")
