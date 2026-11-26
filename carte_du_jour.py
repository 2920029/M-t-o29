#!/usr/bin/env python3
"""Carte du jour surf / wing débutant, Finistère.

Sources (gratuites, sans clé) : Open-Meteo Marine (houle, niveau de la mer)
et Open-Meteo Forecast (vent). Aucune dépendance : bibliothèque standard seule.

Carte : Leaflet + OpenStreetMap / IGN (nécessite une connexion pour afficher les fonds).

Usage :
    python3 carte_du_jour.py                 -> écrit carte_du_jour.html
    python3 carte_du_jour.py sortie.html     -> chemin au choix
    python3 carte_du_jour.py --demo          -> données fictives (test hors ligne)
"""
import datetime as dt
import json
import math
import os
import sys
import time
import urllib.parse
import urllib.request

TZ = "Europe/Paris"
TIDE_REF = (48.30, -4.80)  # point en mer au large de Brest, sert de référence marée

# facing : direction vers laquelle la plage regarde (0 = N, 90 = E, 180 = S, 270 = O).
# expo   : part de la houle du large qui arrive sur la plage (0 à 1), estimée.
# lat/lon et facing fournis par Math. expo = estimation.
SPOTS = [
    dict(n="La Torche", lat=47.8435928, lon=-4.3469666, facing=270, expo=1.0),
    dict(n="Pentrez", lat=48.1910477, lon=-4.3041569, facing=270, expo=0.6),
    dict(n="Telgruc", lat=48.2137268, lon=-4.3760186, facing=225, expo=0.35),
    dict(n="Plage de l'Aber", lat=48.2322748, lon=-4.4446101, facing=202, expo=0.3),
    dict(n="Goulien", lat=48.2451792, lon=-4.5476183, facing=270, expo=0.9),
    dict(n="Moulin Blanc", lat=48.3971843, lon=-4.4300601, facing=180, expo=0.0),
    dict(n="Pen Alan", lat=48.3311132, lon=-4.3709707, facing=90, expo=0.0),
    dict(n="Porzh Gwen", lat=48.3439302, lon=-4.3497407, facing=180, expo=0.0),
    dict(n="Blanc Sablon", lat=48.3676312, lon=-4.7679242, facing=315, expo=0.8),
    dict(n="Keremma", lat=48.6535886, lon=-4.2560421, facing=0, expo=0.5),
    dict(n="Brignogan", lat=48.6521627, lon=-4.2991499, facing=90, expo=0.6),
    dict(n="Kerlouan", lat=48.6689601, lon=-4.3683898, facing=0, expo=0.6),
]

COMPASS = ["N", "NE", "E", "SE", "S", "SO", "O", "NO"]
CLS_FR = {"onshore": "onshore", "side-onshore": "side-onshore",
          "side-offshore": "side-offshore", "offshore": "offshore, vent de terre"}
TIDE_FR = {"high": "pleine mer", "rising": "marée montante",
           "falling": "marée descendante", "low": "basse mer"}


def compass(deg):
    return COMPASS[int((deg + 22.5) % 360 // 45)]


def adiff(a, b):
    return abs((a - b + 180) % 360 - 180)


def clamp(v, lo=0, hi=10):
    return max(lo, min(hi, v))


def get(url, params):
    q = urllib.parse.urlencode(params, safe=",")
    err = None
    for i in range(3):
        try:
            with urllib.request.urlopen(url + "?" + q, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            err = e
            time.sleep(2 * (i + 1))
    raise RuntimeError("échec de la requête %s : %s" % (url, err))


def fetch_marine(sp):
    return get("https://marine-api.open-meteo.com/v1/marine", dict(
        latitude=sp["lat"], longitude=sp["lon"], timezone=TZ, forecast_days=1,
        hourly="swell_wave_height,swell_wave_period,swell_wave_direction"))


def fetch_wind(sp):
    return get("https://api.open-meteo.com/v1/forecast", dict(
        latitude=sp["lat"], longitude=sp["lon"], timezone=TZ, forecast_days=1,
        wind_speed_unit="kn", daily="sunrise,sunset",
        hourly="wind_speed_10m,wind_gusts_10m,wind_direction_10m"))


def fetch_tide():
    d = get("https://marine-api.open-meteo.com/v1/marine", dict(
        latitude=TIDE_REF[0], longitude=TIDE_REF[1], timezone=TZ,
        past_days=1, forecast_days=2, hourly="sea_level_height_msl"))
    return d["hourly"]["time"], [v if v is not None else 0 for v in d["hourly"]["sea_level_height_msl"]]


def demo_data():
    """Données fictives réalistes pour tester le script sans réseau."""
    def day(f):
        return [f(h) for h in range(24)]
    marine = {"hourly": {
        "swell_wave_height": day(lambda h: 1.4 + 0.2 * math.sin(h / 4)),
        "swell_wave_period": day(lambda h: 11),
        "swell_wave_direction": day(lambda h: 265)}}
    wind = {"hourly": {
        "wind_speed_10m": day(lambda h: 15 - 3 * math.cos(h / 4)),
        "wind_gusts_10m": day(lambda h: 21),
        "wind_direction_10m": day(lambda h: 0)},
        "daily": {"sunrise": ["2026-11-25T08:41"], "sunset": ["2026-11-25T17:28"]}}
    today = dt.date.today()
    times, lv = [], []
    for i in range(72):
        t = dt.datetime.combine(today, dt.time()) + dt.timedelta(hours=i - 24)
        times.append(t.strftime("%Y-%m-%dT%H:00"))
        lv.append(3.0 * math.sin(2 * math.pi * (i - 24 - 5) / 12.42))
    return marine, wind, (times, lv)


def tide_phases(times, levels, today):
    """Phase de marée pour chaque heure du jour + liste des PM/BM du jour."""
    n = len(levels)
    ext = []
    for i in range(1, n - 1):
        if levels[i] >= levels[i - 1] and levels[i] > levels[i + 1]:
            ext.append((i, "HW"))
        elif levels[i] <= levels[i - 1] and levels[i] < levels[i + 1]:
            ext.append((i, "LW"))
    start = next(i for i, t in enumerate(times) if t.startswith(today))
    phases = []
    for h in range(24):
        i = start + h
        near = [(abs(i - e), k) for e, k in ext if abs(i - e) <= 1.5]
        if near:
            phases.append("high" if min(near)[1] == "HW" else "low")
            continue
        prev = [k for e, k in ext if e < i]
        phases.append("rising" if prev and prev[-1] == "LW" else "falling")
    day_ext = [(e - start, k, levels[e]) for e, k in ext if 0 <= e - start < 24]
    hws = [lv for _, k, lv in day_ext if k == "HW"]
    lws = [lv for _, k, lv in day_ext if k == "LW"]
    coef = None
    if hws and lws:
        coef = round(((max(hws) - min(lws)) / 2) / 3.05 * 100)
    return phases, day_ext, coef


def wind_class(wind_from, facing):
    d = adiff(wind_from, facing)
    if d <= 45:
        return "onshore"
    if d <= 90:
        return "side-onshore"
    if d <= 135:
        return "side-offshore"
    return "offshore"


def effective_height(swell_h, swell_dir, facing, expo):
    align = max(0.0, math.cos(math.radians(adiff(swell_dir, facing))))
    return swell_h * expo * (0.4 + 0.6 * align)


def surf_score(h, period, wk, cls):
    if h < 0.4:
        return 0
    base = 2 if h < 0.7 else 4 if h < 1.0 else 6 if h < 1.5 else 7 if h < 2.5 else 6
    base += 2 if period >= 13 else 1 if period >= 10 else -2 if period < 7 else 0
    base += {"offshore": 2 if wk <= 18 else 0, "side-offshore": 1,
             "side-onshore": -1, "onshore": -2}[cls]
    if wk > 22:
        base -= 2
    return clamp(base)


def wing_score(wk, gk, cls, tide, h):
    w = 0 if wk < 10 else 2 if wk < 12 else 4 if wk <= 18 else 3 if wk <= 22 else 1 if wk <= 26 else 0
    if gk - wk > 8:
        w -= 1
    d = {"onshore": 2, "side-onshore": 2, "side-offshore": 1, "offshore": 0}[cls]
    t = {"high": 2, "rising": 2, "falling": 0, "low": -1}[tide]
    v = 1 if h <= 0.3 else 0 if h <= 0.6 else -1 if h <= 1.0 else -2
    total = w + d + t + v
    if cls == "offshore":
        total = min(total, 2)  # vent de terre : jamais pour un débutant
    if h > 1.0:
        total = min(total, 3)  # vagues : pas pour un débutant
    elif h > 0.6:
        total = min(total, 5)
    return clamp(total)


def best_window(scores, hours):
    best = None
    for h in hours:
        if h + 1 in hours:
            avg = (scores[h] + scores[h + 1]) / 2
            if best is None or avg > best[1]:
                best = (h, avg)
    return best


def analyse(sp, marine, wind, phases, hours):
    m, w = marine["hourly"], wind["hourly"]
    z = lambda a: [v if v is not None else 0 for v in a]  # noqa: E731
    sh, sper, sdir = z(m["swell_wave_height"]), z(m["swell_wave_period"]), z(m["swell_wave_direction"])
    ws, wg, wd = z(w["wind_speed_10m"]), z(w["wind_gusts_10m"]), z(w["wind_direction_10m"])
    surf, wing, eff = [], [], []
    for h in range(24):
        he = effective_height(sh[h], sdir[h], sp["facing"], sp["expo"])
        cls = wind_class(wd[h], sp["facing"])
        eff.append(he)
        surf.append(surf_score(he, sper[h], ws[h], cls))
        wing.append(wing_score(ws[h], wg[h], cls, phases[h], he))
    hrs = []
    for h in hours:
        hrs.append(dict(h=h, surf=surf[h], wing=wing[h], wd=round(wd[h]), wk=round(ws[h]),
                        wg=round(wg[h]), he=round(eff[h], 1), per=round(sper[h]),
                        tide=phases[h], cls=wind_class(wd[h], sp["facing"])))
    best = {}
    for key, sc in (("surf", surf), ("wing", wing)):
        b = best_window(sc, hours)
        if b:
            best[key] = dict(h=b[0], score=round(b[1]), win="%dh–%dh" % (b[0], b[0] + 2))
        else:
            best[key] = dict(h=None, score=0, win="-")
    out = dict(n=sp["n"], f=sp["facing"], lat=sp["lat"], lon=sp["lon"],
               o="%s (%d°)" % (compass(sp["facing"]), sp["facing"]), hours=hrs, best=best)
    mid = hours[len(hours) // 2]
    return out, (round(sh[mid], 1), round(sper[mid]), round(ws[mid]), compass(wd[mid]))


def build(demo=False):
    try:
        from zoneinfo import ZoneInfo
        now = dt.datetime.now(ZoneInfo(TZ))
    except Exception:  # noqa: BLE001
        now = dt.datetime.now()
    today = now.date().isoformat()
    if demo:
        marine0, wind0, (times, levels) = demo_data()
    else:
        times, levels = fetch_tide()
    phases, day_ext, coef = tide_phases(times, levels, today)

    results, ref = [], None
    hours = list(range(8, 18))
    for sp in SPOTS:
        if demo:
            marine, wind = marine0, wind0
        else:
            marine, wind = fetch_marine(sp), fetch_wind(sp)
            time.sleep(0.3)
        sr = wind["daily"]["sunrise"][0][11:16]
        ss = wind["daily"]["sunset"][0][11:16]
        hours = [h for h in range(24) if int(sr[:2]) <= h <= int(ss[:2]) - 1]
        res, snap = analyse(sp, marine, wind, phases, hours)
        results.append(res)
        if sp["n"] == "La Torche":
            ref = snap
    tide_txt = " · ".join("%s %02dh" % ("PM" if k == "HW" else "BM", h) for h, k, _ in day_ext)
    meta = dict(date=today, generated=now.strftime("%Y-%m-%dT%H:%M"), sun="%s–%s" % (sr, ss),
                swell="%s m / %s s" % (ref[0], ref[1]) if ref else "-",
                wind="%s kt %s" % (ref[2], ref[3]) if ref else "-",
                tide=tide_txt + (" · coef ≈ %d" % coef if coef else ""))
    return dict(meta=meta, spots=results)


HTML = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate"><meta http-equiv="Pragma" content="no-cache">
<title>Surf et wing, Finistère</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css">
<style>
:root{--bg:#fff;--t:#1c1c1a;--t2:#5f5e5a;--card:#f1efe8;--b:#d3d1c7}
@media(prefers-color-scheme:dark){:root{--bg:#191919;--t:#efefef;--t2:#b4b2a9;--card:#2c2c2a;--b:#444441}}
body{margin:0;padding:14px;max-width:560px;margin:auto;background:var(--bg);color:var(--t);font:15px/1.5 system-ui,sans-serif}
h1{font-size:18px;font-weight:500;margin:0 0 2px}.sub{color:var(--t2);font-size:13px;margin:0 0 12px}
.g{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px}
.c{background:var(--card);border-radius:8px;padding:8px 12px}.c small{display:block;color:var(--t2);font-size:12px}.c b{font-weight:500;font-size:14px}
.tabs{display:flex;gap:8px;margin-bottom:8px}button,select{padding:8px;border:.5px solid var(--b);border-radius:8px;background:none;color:var(--t);font:inherit}
button{flex:1}select{flex:1}
#map{height:62vh;min-height:380px;border-radius:12px;border:.5px solid var(--b)}
.sp{background:none;border:none}
.lbl{background:rgba(255,255,255,.88);border:none;box-shadow:none;color:#1c1c1a;font-size:12px;padding:1px 5px}
.lbl:before{display:none}
#info{border:.5px solid var(--b);border-radius:12px;padding:12px 14px;margin-top:8px}
.lg{display:flex;gap:10px;flex-wrap:wrap;font-size:12px;color:var(--t2);margin-top:8px}
.lg i{display:inline-block;width:10px;height:10px;border-radius:50%;vertical-align:-1px}
</style></head><body>
<h1>Surf et wing débutant, Finistère</h1><p class="sub" id="sub"></p>
<div class="g" id="cards"></div>
<div class="tabs"><button id="bs">Surf</button><button id="bw">Wing débutant</button></div>
<div class="tabs"><select id="hr" aria-label="Heure"></select></div>
<div id="map"></div>
<div id="info"></div>
<div class="lg"><span><i style="background:#E24B4A"></i> 1–3</span><span><i style="background:#EF9F27"></i> 4–5</span><span><i style="background:#97C459"></i> 6–7</span><span><i style="background:#639922"></i> 8–10</span><span><i style="background:#B4B2A9"></i> sans objet</span></div>
<p class="sub" style="margin-top:6px">Trait épais = la plage, petit trait = côté mer. Touche une plage pour voir la flèche de vent. Le choix « Meilleur créneau » prend, pour chaque onglet, l'heure la plus favorable ; choisis une heure pour comparer surf et wing avec le même vent.</p>
<p class="sub">Sources : Open-Meteo (houle, vent, niveau de la mer), fonds de carte OpenStreetMap et IGN. Marée de référence : large de Brest. Notes estimées par spot selon l'orientation de la plage.</p>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
var D=__DATA__,mode="surf",sel=0,hour=null,R=Math.PI/180,mk=[],wm=null;
var CF={"onshore":"onshore","side-onshore":"side-onshore","side-offshore":"side-offshore","offshore":"offshore, vent de terre"};
var TF={high:"pleine mer",rising:"marée montante",falling:"marée descendante",low:"basse mer"};
var CP=["N","NE","E","SE","S","SO","O","NO"];
function cp(d){return CP[Math.floor(((d+22.5)%360)/45)]}
function pad(n){return (n<10?"0":"")+n}
function head(){var g=D.meta.generated||"",d=new Date(),today=d.getFullYear()+"-"+pad(d.getMonth()+1)+"-"+pad(d.getDate());
var t=g?("mis à jour le "+g.slice(8,10)+"/"+g.slice(5,7)+" à "+g.slice(11,13)+"h"+g.slice(14,16)):D.meta.date;
document.getElementById("sub").innerHTML=(D.meta.date!==today?'<b style="color:#A32D2D">Données du '+D.meta.date.slice(8,10)+'/'+D.meta.date.slice(5,7)+' : pas encore mises à jour.</b> ':"")+t+" · jour "+D.meta.sun;
document.getElementById("cards").innerHTML=[["Houle (La Torche)",D.meta.swell],["Vent (La Torche)",D.meta.wind],["Marée (Brest)",D.meta.tide],["Lever – coucher",D.meta.sun]].map(function(c){return '<div class="c"><small>'+c[0]+'</small><b>'+c[1]+'</b></div>'}).join("")}
function fillHours(){var o='<option value="best">Meilleur créneau</option>';D.spots[0].hours.forEach(function(x){o+='<option value="'+x.h+'">'+x.h+'h</option>'});var el=document.getElementById("hr");el.innerHTML=o;el.value=hour===null?"best":String(hour)}
var map=L.map("map");
var osm=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:"© les contributeurs d'OpenStreetMap"}).addTo(map);
var ign=L.tileLayer("https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}",{maxZoom:18,attribution:"© IGN"});
L.control.layers({"OpenStreetMap":osm,"Plan IGN":ign}).addTo(map);
map.fitBounds(D.spots.map(function(s){return [s.lat,s.lon]}),{padding:[24,24]});
function col(v){return v<=0?"#B4B2A9":v<=3?"#E24B4A":v<=5?"#EF9F27":v<=7?"#97C459":"#639922"}
function verdict(v){if(mode=="surf")return v==0?"Pas de houle":v>=6?"Correct à bon":v>=4?"Moyen":"Faible";return v>=7?"Bon pour débuter":v>=5?"Jouable, avec réserves":v>=3?"Peu adapté":"À éviter"}
function view(s){var e,score,win;
if(hour===null){var b=s.best[mode];score=b.score;win=b.win;e=s.hours.filter(function(x){return x.h===b.h})[0]}
else{e=s.hours.filter(function(x){return x.h===hour})[0];score=e?e[mode]:0;win=hour+"h"}
return {score:score,win:win,e:e}}
function spIcon(s,c,on){var o=on?'<line x1="-14" y1="0" x2="14" y2="0" stroke="#1c1c1a" stroke-width="13" stroke-linecap="round"/>':'';
return L.divIcon({className:"sp",iconSize:[44,44],iconAnchor:[22,22],html:'<svg width="44" height="44" viewBox="-22 -22 44 44"><g transform="rotate('+s.f+')">'+o+'<line x1="-12" y1="0" x2="12" y2="0" stroke="#fff" stroke-width="10" stroke-linecap="round"/><line x1="-12" y1="0" x2="12" y2="0" stroke="'+c+'" stroke-width="7" stroke-linecap="round"/><line x1="0" y1="-5" x2="0" y2="-14" stroke="'+c+'" stroke-width="2.5" stroke-linecap="round"/></g></svg>'})}
function windIcon(deg,kt,label){var to=deg+180,len=24+kt*2,hy=-len/2,tx=-Math.sin(to*R)*(len/2+16),ty=Math.cos(to*R)*(len/2+16)+4;
return L.divIcon({className:"sp",iconSize:[200,200],iconAnchor:[100,100],html:'<svg width="200" height="200" viewBox="-100 -100 200 200"><g transform="rotate('+to+')"><line x1="0" y1="'+(len/2)+'" x2="0" y2="'+hy+'" stroke="#fff" stroke-width="7" stroke-linecap="round"/><line x1="0" y1="'+(len/2)+'" x2="0" y2="'+hy+'" stroke="#185FA5" stroke-width="3" stroke-linecap="round"/><polygon points="0,'+(hy-2)+' -6,'+(hy+9)+' 6,'+(hy+9)+'" fill="#185FA5" stroke="#fff" stroke-width="1.5" stroke-linejoin="round"/></g><text x="'+tx+'" y="'+ty+'" text-anchor="middle" style="font:500 12px system-ui;fill:#185FA5;paint-order:stroke;stroke:#fff;stroke-width:3px">'+kt+' kt · '+label+'</text></svg>'})}
D.spots.forEach(function(s,i){var m=L.marker([s.lat,s.lon],{icon:spIcon(s,"#B4B2A9",false)}).addTo(map);
m.bindTooltip(s.n,{permanent:true,direction:"right",offset:[14,0],className:"lbl"});m.on("click",function(){pick(i)});mk.push(m)});
function draw(){D.spots.forEach(function(s,i){var v=view(s).score;mk[i].setIcon(spIcon(s,col(v),i==sel));mk[i].setTooltipContent(s.n+" <b>"+(v==0?"–":v)+"</b>");mk[i].setZIndexOffset(i==sel?500:0)});
var s=D.spots[sel],r=view(s),e=r.e;if(wm){map.removeLayer(wm);wm=null}
var hl=hour===null?r.win.split("–")[0]:hour+"h";
if(e&&e.wk>0){wm=L.marker([s.lat,s.lon],{icon:windIcon(e.wd,e.wk,hl),interactive:false,zIndexOffset:1000}).addTo(map)}
var txt=e?((e.he>=0.2?"Houle "+String(e.he).replace(".",",")+" m / "+e.per+" s · ":"Pas de houle · ")+"Vent "+e.wk+" kt "+cp(e.wd)+" (rafales "+e.wg+" kt, "+CF[e.cls]+") · "+TF[e.tide]):"Pas de données à cette heure (nuit).";
document.getElementById("info").innerHTML='<div style="display:flex;justify-content:space-between"><b>'+s.n+'</b><span style="color:var(--t2);font-size:13px">'+(r.score==0?"–":r.score+"/10")+' · '+verdict(r.score)+'</span></div><div style="color:var(--t2);font-size:12px;margin:2px 0 6px">Orientation : '+s.o+' · '+(hour===null?"meilleur créneau : ":"à ")+r.win+'</div><div style="font-size:13px">'+txt+'</div>';
document.getElementById("bs").style.background=mode=="surf"?"var(--card)":"none";document.getElementById("bw").style.background=mode=="wing"?"var(--card)":"none"}
function pick(i){sel=i;draw()}
document.getElementById("bs").onclick=function(){mode="surf";draw()};document.getElementById("bw").onclick=function(){mode="wing";draw()};
document.getElementById("hr").onchange=function(){hour=this.value=="best"?null:parseInt(this.value,10);draw()};
head();fillHours();draw();
try{fetch("data.json?t="+Date.now(),{cache:"no-store"}).then(function(r){return r.ok?r.json():null}).then(function(j){
if(j&&j.meta&&j.spots&&j.spots.length==D.spots.length&&(j.meta.generated||"")>(D.meta.generated||"")){D=j;head();fillHours();draw()}}).catch(function(){})}catch(e){}
</script></body></html>"""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    out = args[0] if args else "carte_du_jour.html"
    data = build(demo="--demo" in sys.argv)
    blob = json.dumps(data, ensure_ascii=False)
    with open(out, "w", encoding="utf-8") as f:
        f.write(HTML.replace("__DATA__", blob))
    # data.json : la page le recharge à chaque ouverture, même si le raccourci garde l'ancienne page en cache
    with open(os.path.join(os.path.dirname(os.path.abspath(out)), "data.json"), "w", encoding="utf-8") as f:
        f.write(blob)
    print("Carte écrite dans", out)


if __name__ == "__main__":
    main()
