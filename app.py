import json
import os
import unicodedata
from datetime import datetime
import pytz
import requests
from flask import Flask, render_template, request, redirect, url_for, jsonify
app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0
app.config['TEMPLATES_AUTO_RELOAD'] = True
# --- CONFIGURATION ---
PICKS_FILE = 'picks.json'
HISTORY_FILE = 'history.json'
SETTINGS_FILE = 'settings.json'
SIDE_BETS_FILE = 'side_bets.json'
PLAYERS_FILE = 'players.json'
PLAYERS_PER_TEAM = 14
COUNT_BEST = 6
# Masters Tournament ID from Claude's sports data
CURRENT_TOURNAMENT_ID = "ebf84425-7ae8-491e-a128-831d175e287a"
CURRENT_TOURNAMENT_NAME = "Masters Tournament"
 
# --- MASTERS 2026 HARDCODED PICKS ---
# Draft completed April 8, 2026. Hardcoded as interim fix for picks.json persistence bug.
# Rounds 1-14 are active roster; Round 15 is the backup (alternate only if a top-6
# player withdraws after the 36-hole cut).
HARDCODED_LARRY_PICKS = [
    "Jon Rahm", "Ludvig Aberg", "Xander Schauffele", "Bryson DeChambeau",
    "Cameron Young", "Matthew Fitzpatrick", "Akshay Bhatia", "Min Woo Lee",
    "Corey Connors", "Hideki Matsuyama", "Si Woo Kim", "Shane Lowry",
    "Jake Knapp", "Russell Henley"
]
HARDCODED_LARRY_BACKUP = "Max Homa"
 
HARDCODED_ANDY_PICKS = [
    "Rory McIlroy", "Scottie Scheffler", "Brooks Koepka", "Justin Rose",
    "Tommy Fleetwood", "Viktor Hovland", "Nicolai Hojgaard", "Rasmus Hojgaard",
    "Patrick Cantlay", "Robert McIntyre", "Jordan Spieth", "Keegan Bradley",
    "Jason Day", "Harris English"
]
HARDCODED_ANDY_BACKUP = "Chris Gotterup"
 
# --- DATA MANAGEMENT ---
def load_json(filename):
    if os.path.exists(filename):
        try:
            with open(filename, 'r') as f:
                return json.load(f)
        except:
            pass
    return {}
def save_json(filename, data):
    with open(filename, 'w') as f:
        json.dump(data, f, indent=2)
def load_picks():
    data = load_json(PICKS_FILE)
    if not data:
        return {"larry": [], "andy": []}
    data['larry'] = list(set(data.get('larry', [])))
    data['andy'] = list(set(data.get('andy', [])))
    return data
def load_players():
    """Load the full 2026 Masters tournament field from players.json"""
    data = load_json(PLAYERS_FILE)
    if not data:
        return []
    return data.get('players', [])
def load_side_bets():
    """Load side bets data"""
    data = load_json(SIDE_BETS_FILE)
    if not data:
        return {
            "bet1_type": "", "bet1_larry": "", "bet1_andy": "", "bet1_winner": "",
            "bet2_type": "", "bet2_larry": "", "bet2_andy": "", "bet2_winner": "",
            "bet3_type": "", "bet3_larry": "", "bet3_andy": "", "bet3_winner": "",
            "bet4_type": "", "bet4_larry": "", "bet4_andy": "", "bet4_winner": "",
            "bet5_type": "", "bet5_larry": "", "bet5_andy": "", "bet5_winner": "",
        }
    return data
 
current_picks = load_picks()
 
# --- LIVE DATA FETCHING ---
 
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; GolfBettingApp/1.0)"}
 
def _fetch_masters_dot_com():
    """
    Try Augusta National's official JSON score feed.
    Returns (leaderboard_list, tournament_name) or raises on failure.
    """
    url = "https://www.masters.com/en_US/scores/feeds/2026/scores.json"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    resp.raise_for_status()
    data = resp.json()
 
    players = data.get("data", {}).get("player", [])
    if not players:
        raise ValueError("masters.com: empty player list")
 
    leaderboard = []
    for p in players:
        first = p.get("first_name", "")
        last  = p.get("last_name", "")
        name  = f"{first} {last}".strip()
 
        raw = p.get("topar", "E")
        if raw in ("E", "even", "", None):
            score = 0
        else:
            try:
                score = int(str(raw).replace("+", ""))
            except ValueError:
                score = 0
 
        thru = p.get("thru", "-") or "-"
        pos  = p.get("pos", "-")
 
        leaderboard.append({
            "name":     name,
            "score":    score,
            "status":   "active",
            "thru":     str(thru),
            "position": str(pos),
        })
 
    print(f"masters.com: loaded {len(leaderboard)} players")
    return leaderboard, CURRENT_TOURNAMENT_NAME
 
 
def _fetch_espn():
    """
    Try ESPN's undocumented public golf scoreboard API.
    Returns (leaderboard_list, tournament_name) or raises on failure.
    """
    # Try both known ESPN golf endpoint formats
    urls = [
        "https://site.api.espn.com/apis/site/v2/sports/golf/leaderboard",
        "https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard",
    ]
 
    data = None
    used_url = None
    for url in urls:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            used_url = url
            break
        except Exception as e:
            print(f"ESPN endpoint {url} failed: {e}")
 
    if not data:
        raise ValueError("All ESPN endpoints failed")
 
    events = data.get("events", [])
    target = None
    for event in events:
        name = event.get("name", "").lower()
        if "masters" in name or "augusta" in name:
            target = event
            break
    if not target and events:
        target = events[0]
    if not target:
        raise ValueError("ESPN: no events in response")
 
    tournament_name = target.get("name", CURRENT_TOURNAMENT_NAME)
    leaderboard = []
    competitions = target.get("competitions", [])
    if competitions:
        for comp in competitions[0].get("competitors", []):
            athlete   = comp.get("athlete", {})
            full_name = athlete.get("displayName", "")
 
            raw_score = comp.get("score", "E")
            if raw_score in ("E", "even", "", None):
                score = 0
            else:
                try:
                    score = int(str(raw_score).replace("+", ""))
                except ValueError:
                    score = 0
 
            status_obj = comp.get("status", {})
            thru = status_obj.get("type", {}).get("shortDetail", "-")
 
            leaderboard.append({
                "name":     full_name,
                "score":    score,
                "status":   "active",
                "thru":     thru,
                "position": str(comp.get("place", "-")),
            })
 
    print(f"ESPN ({used_url}): loaded {len(leaderboard)} players for '{tournament_name}'")
    if not leaderboard:
        raise ValueError("ESPN: empty competitor list")
    return leaderboard, tournament_name
 
 
def get_live_data():
    """
    Fetch live leaderboard. Tries sources in order:
      1. masters.com official JSON feed
      2. ESPN public API (two endpoint variants)
      3. Static players.json fallback
    """
    sources = [
        ("masters.com", _fetch_masters_dot_com),
        ("ESPN",        _fetch_espn),
    ]
    for name, fn in sources:
        try:
            leaderboard, tournament_name = fn()
            if leaderboard:
                return leaderboard, tournament_name
        except Exception as e:
            print(f"[get_live_data] {name} failed: {e}")
 
    # Final fallback — static data, all scores will be 0/E
    print("[get_live_data] All live sources failed. Using players.json fallback.")
    all_players = load_players()
    return (all_players if all_players else []), CURRENT_TOURNAMENT_NAME
 
def normalize_name(name):
    """
    Normalize a player name for fuzzy matching.
    Strips accents (Åberg → Aberg, Højgaard → Hojgaard) and lowercases.
    This lets us match ESPN's accented names against our ASCII pick list.
    """
    nfkd = unicodedata.normalize('NFKD', str(name))
    return ''.join(c for c in nfkd if not unicodedata.combining(c)).lower().strip()
 
def parse_score(score_val):
    """Parse a golf score value to integer for sorting/summing."""
    if isinstance(score_val, (int, float)):
        return int(score_val)
    if isinstance(score_val, str):
        s = score_val.strip()
        if s in ('E', 'even', '-', ''):
            return 0
        try:
            return int(s.replace('+', ''))
        except:
            return 100
    return 100
 
def calculate_team_score(picks, leaderboard, backup=None):
    """
    Calculate team score — top 6 of 14 active players count.
    The backup (15th) is kept entirely separate and pinned to the bottom of the list.
    Returns:
        total       — sum of top-6 scores
        all_players — list of 14, sorted best-to-worst, each with a 'counting' flag
        backup      — the 15th player dict (or None), never mixed into scoring
    """
    team_data = []
    for player_name in picks:
        # Use normalize_name() so accented API names (Åberg, Højgaard) match
        # our ASCII pick strings (Aberg, Hojgaard)
        player_stats = next(
            (p for p in leaderboard
             if normalize_name(p["name"]) == normalize_name(player_name)),
            None
        )
        if player_stats:
            team_data.append(dict(player_stats))
        else:
            team_data.append({
                "name": player_name,
                "score": 0,
                "status": "active",
                "thru": "-",
                "position": "-"
            })
 
    # Sort by score (lowest = best in golf)
    team_data.sort(key=lambda x: parse_score(x['score']))
 
    # Mark top COUNT_BEST as counting
    for i, player in enumerate(team_data):
        player['counting'] = (i < COUNT_BEST)
 
    total_score = sum(parse_score(p['score']) for p in team_data[:COUNT_BEST])
 
    # Handle backup player (15th — always separate, never scored)
    backup_data = None
    if backup:
        backup_stats = next(
            (p for p in leaderboard
             if normalize_name(p["name"]) == normalize_name(backup)),
            None
        )
        if backup_stats:
            backup_data = dict(backup_stats)
        else:
            backup_data = {
                "name": backup,
                "score": 0,
                "status": "active",
                "thru": "-",
                "position": "-"
            }
        backup_data['counting'] = False
        backup_data['is_backup'] = True
 
    return {
        "total": total_score,
        "all_players": team_data,
        "backup": backup_data
    }
 
def get_available_players_for_side_bets():
    """Get players NOT selected in main draft (available for side bets)"""
    all_players = load_players()
    drafted = set(HARDCODED_LARRY_PICKS + [HARDCODED_LARRY_BACKUP] +
                  HARDCODED_ANDY_PICKS + [HARDCODED_ANDY_BACKUP])
    return [p for p in all_players if p['name'] not in drafted]
 
# --- ROUTES ---
@app.route('/')
def dashboard():
    """Main dashboard - shows current tournament standings"""
    leaderboard, tournament_name = get_live_data()
 
    settings = load_json(SETTINGS_FILE)
    stakes = settings.get('stakes', 'Bragging Rights')
    tournament_name_custom = settings.get('tournament_name', tournament_name)
 
    larry_results = calculate_team_score(HARDCODED_LARRY_PICKS, leaderboard, HARDCODED_LARRY_BACKUP)
    andy_results  = calculate_team_score(HARDCODED_ANDY_PICKS,  leaderboard, HARDCODED_ANDY_BACKUP)
 
    try:
        est = pytz.timezone('US/Eastern')
        current_time = datetime.now(est).strftime("%I:%M %p ET")
    except:
        current_time = datetime.now().strftime("%I:%M %p")
 
    side_bets = load_side_bets()
 
    return render_template('index.html',
                           larry=larry_results,
                           andy=andy_results,
                           tournament_name=tournament_name_custom,
                           stakes=stakes,
                           side_bets=side_bets,
                           last_updated=current_time)
 
@app.route('/api/refresh')
def api_refresh():
    """API endpoint for auto-refresh - returns JSON data"""
    leaderboard, tournament_name = get_live_data()
 
    larry_results = calculate_team_score(HARDCODED_LARRY_PICKS, leaderboard, HARDCODED_LARRY_BACKUP)
    andy_results  = calculate_team_score(HARDCODED_ANDY_PICKS,  leaderboard, HARDCODED_ANDY_BACKUP)
 
    try:
        est = pytz.timezone('US/Eastern')
        current_time = datetime.now(est).strftime("%I:%M %p ET")
    except:
        current_time = datetime.now().strftime("%I:%M %p")
 
    return jsonify({
        'larry': larry_results,
        'andy': andy_results,
        'tournament_name': tournament_name,
        'last_updated': current_time
    })
 
@app.route('/api/debug')
def api_debug():
    """
    Diagnostic endpoint — visit /api/debug in your browser to see exactly
    what each data source returns. Useful for troubleshooting live scoring.
    """
    results = {}
 
    # Expose raw masters.com JSON for first 2 players so we can see exact field names
    try:
        url = "https://www.masters.com/en_US/scores/feeds/2026/scores.json"
        resp = requests.get(url, headers=HEADERS, timeout=10)
        raw_data = resp.json()
        raw_players = raw_data.get("data", {}).get("player", [])
        results["masters_com_raw_fields"] = raw_players[:2]  # show full raw dict for first 2 players
    except Exception as e:
        results["masters_com_raw_fields"] = {"error": str(e)}
 
    # Test masters.com (parsed)
    try:
        lb, name = _fetch_masters_dot_com()
        results["masters_com"] = {
            "status": "OK",
            "player_count": len(lb),
            "sample": lb[:3],
        }
    except Exception as e:
        results["masters_com"] = {"status": "FAILED", "error": str(e)}
 
    # Test ESPN
    try:
        lb, name = _fetch_espn()
        results["espn"] = {
            "status": "OK",
            "player_count": len(lb),
            "sample": lb[:3],
        }
    except Exception as e:
        results["espn"] = {"status": "FAILED", "error": str(e)}
 
    # Show what get_live_data() actually used
    try:
        lb, name = get_live_data()
        results["get_live_data"] = {
            "status": "OK",
            "source_used": name,
            "player_count": len(lb),
            "sample": lb[:5],
        }
    except Exception as e:
        results["get_live_data"] = {"status": "FAILED", "error": str(e)}
 
    # Check whether our picks are matching anything
    lb, _ = get_live_data()
    pick_check = {}
    for pick in HARDCODED_LARRY_PICKS[:3] + HARDCODED_ANDY_PICKS[:3]:
        match = next((p for p in lb if normalize_name(p["name"]) == normalize_name(pick)), None)
        pick_check[pick] = match["name"] if match else "NO MATCH"
    results["pick_name_matching"] = pick_check
 
    return jsonify(results)
 
@app.route('/history')
def history():
    """Tournament history page with season tracking"""
    history_data = load_json(HISTORY_FILE)
    if not isinstance(history_data, list):
        history_data = []
 
    larry_wins = sum(1 for h in history_data if h['winner'] == 'Larry')
    andy_wins  = sum(1 for h in history_data if h['winner'] == 'Andy')
    ties       = sum(1 for h in history_data if h['winner'] == 'Tie')
 
    larry_season_strokes = 0
    andy_season_strokes  = 0
    for tournament in history_data:
        larry_diff = tournament.get('andy_score', 0) - tournament.get('larry_score', 0)
        andy_diff  = tournament.get('larry_score', 0) - tournament.get('andy_score', 0)
        if larry_diff > 0:
            larry_season_strokes += larry_diff
        elif andy_diff > 0:
            andy_season_strokes += andy_diff
 
    return render_template('history.html',
                           history=history_data,
                           larry_wins=larry_wins,
                           andy_wins=andy_wins,
                           ties=ties,
                           larry_season_strokes=larry_season_strokes,
                           andy_season_strokes=andy_season_strokes)
 
@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Admin panel - configure tournament settings only"""
    global current_picks
 
    settings = load_json(SETTINGS_FILE)
    current_stakes = settings.get('stakes', 'Bragging Rights')
    current_tournament_name = settings.get('tournament_name', 'The Masters Tournament')
 
    if request.method == 'POST':
        if 'archive_week' in request.form:
            return redirect(url_for('archive_week'))
 
        if 'larry_picks' in request.form or 'andy_picks' in request.form:
            larry_picks = request.form.getlist('larry_picks')
            andy_picks  = request.form.getlist('andy_picks')
            picks_data  = {'larry': larry_picks, 'andy': andy_picks}
            save_json(PICKS_FILE, picks_data)
            current_picks = picks_data
            if 'stakes' in request.form:
                new_settings = {
                    'stakes': request.form.get('stakes', 'Bragging Rights'),
                    'tournament_name': settings.get('tournament_name', 'The Masters Tournament')
                }
                save_json(SETTINGS_FILE, new_settings)
            return redirect(url_for('dashboard'))
 
        new_settings = {
            'stakes': request.form.get('stakes', 'Bragging Rights'),
            'tournament_name': request.form.get('tournament_name', 'The Masters Tournament')
        }
        save_json(SETTINGS_FILE, new_settings)
        return redirect(url_for('dashboard'))
 
    return render_template('admin.html',
                           stakes=current_stakes,
                           tournament_name=current_tournament_name)
 
@app.route('/draft')
def draft():
    """Snake draft interface - 14 players each"""
    leaderboard, _ = get_live_data()
    all_players_sorted = sorted(leaderboard, key=lambda x: x['name'])
    return render_template('draft.html', players=all_players_sorted)
 
@app.route('/side_bets', methods=['GET', 'POST'])
def side_bets():
    """Manage side bets - 5 bets, $2 each, 36-hole format"""
    if request.method == 'POST':
        bet_data = {
            'bet1_type': request.form.get('bet1_type', ''),
            'bet1_larry': request.form.get('bet1_larry', ''),
            'bet1_andy': request.form.get('bet1_andy', ''),
            'bet2_type': request.form.get('bet2_type', ''),
            'bet2_larry': request.form.get('bet2_larry', ''),
            'bet2_andy': request.form.get('bet2_andy', ''),
            'bet3_type': request.form.get('bet3_type', ''),
            'bet3_larry': request.form.get('bet3_larry', ''),
            'bet3_andy': request.form.get('bet3_andy', ''),
            'bet4_type': request.form.get('bet4_type', ''),
            'bet4_larry': request.form.get('bet4_larry', ''),
            'bet4_andy': request.form.get('bet4_andy', ''),
            'bet5_type': request.form.get('bet5_type', ''),
            'bet5_larry': request.form.get('bet5_larry', ''),
            'bet5_andy': request.form.get('bet5_andy', ''),
        }
        save_json(SIDE_BETS_FILE, bet_data)
        return redirect(url_for('side_bets'))
 
    side_bets_data = load_side_bets()
    available_players = get_available_players_for_side_bets()
    show_results = False
    larry_wins = 0
    andy_wins  = 0
 
    return render_template('side_bets.html',
                           side_bets=side_bets_data,
                           available_players=available_players,
                           show_results=show_results,
                           larry_wins=larry_wins,
                           andy_wins=andy_wins)
 
@app.route('/archive_week')
def archive_week():
    """Archive current tournament results"""
    global current_picks
    leaderboard, tournament_name = get_live_data()
 
    settings = load_json(SETTINGS_FILE)
    tournament_name = settings.get('tournament_name', tournament_name)
 
    larry = calculate_team_score(HARDCODED_LARRY_PICKS, leaderboard, HARDCODED_LARRY_BACKUP)
    andy  = calculate_team_score(HARDCODED_ANDY_PICKS,  leaderboard, HARDCODED_ANDY_BACKUP)
 
    if larry['total'] < andy['total']:
        winner = "Larry"
        margin = andy['total'] - larry['total']
    elif andy['total'] < larry['total']:
        winner = "Andy"
        margin = larry['total'] - andy['total']
    else:
        winner = "Tie"
        margin = 0
 
    tournament_lower = tournament_name.lower()
    if 'masters' in tournament_lower:
        major_type = 'masters'
    elif 'pga' in tournament_lower:
        major_type = 'pga'
    elif 'u.s. open' in tournament_lower or 'us open' in tournament_lower:
        major_type = 'usopen'
    elif 'open championship' in tournament_lower or 'british open' in tournament_lower or tournament_lower == 'the open':
        major_type = 'theopen'
    else:
        major_type = 'other'
 
    new_record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tournament": tournament_name,
        "major_type": major_type,
        "larry_score": larry['total'],
        "andy_score": andy['total'],
        "winner": winner,
        "margin": margin
    }
 
    history_data = load_json(HISTORY_FILE)
    if not isinstance(history_data, list):
        history_data = []
    history_data.insert(0, new_record)
    save_json(HISTORY_FILE, history_data)
 
    save_json(PICKS_FILE, {"larry": [], "andy": []})
    current_picks = {"larry": [], "andy": []}
    save_json(SETTINGS_FILE, {'stakes': 'Bragging Rights', 'tournament_name': 'The Masters Tournament'})
    save_json(SIDE_BETS_FILE, {
        "bet1_type": "", "bet1_larry": "", "bet1_andy": "", "bet1_winner": "",
        "bet2_type": "", "bet2_larry": "", "bet2_andy": "", "bet2_winner": "",
        "bet3_type": "", "bet3_larry": "", "bet3_andy": "", "bet3_winner": "",
        "bet4_type": "", "bet4_larry": "", "bet4_andy": "", "bet4_winner": "",
        "bet5_type": "", "bet5_larry": "", "bet5_andy": "", "bet5_winner": "",
    })
 
    return redirect(url_for('history'))
 
if __name__ == '__main__':
    if not os.path.exists(PICKS_FILE):
        save_json(PICKS_FILE, {"larry": [], "andy": []})
    if not os.path.exists(HISTORY_FILE):
        save_json(HISTORY_FILE, [])
    if not os.path.exists(SETTINGS_FILE):
        save_json(SETTINGS_FILE, {'stakes': 'Bragging Rights', 'tournament_name': 'The Masters Tournament'})
    if not os.path.exists(SIDE_BETS_FILE):
        save_json(SIDE_BETS_FILE, {
            "bet1_type": "", "bet1_larry": "", "bet1_andy": "", "bet1_winner": "",
            "bet2_type": "", "bet2_larry": "", "bet2_andy": "", "bet2_winner": "",
            "bet3_type": "", "bet3_larry": "", "bet3_andy": "", "bet3_winner": "",
            "bet4_type": "", "bet4_larry": "", "bet4_andy": "", "bet4_winner": "",
            "bet5_type": "", "bet5_larry": "", "bet5_andy": "", "bet5_winner": "",
        })
    app.run(debug=True, host='0.0.0.0', port=5000)
