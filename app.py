import json
import os
from datetime import datetime
import pytz
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

PLAYERS_PER_TEAM = 14
COUNT_BEST = 6

# Masters Tournament ID from Claude's sports data
CURRENT_TOURNAMENT_ID = "ebf84425-7ae8-491e-a128-831d175e287a"
CURRENT_TOURNAMENT_NAME = "Masters Tournament"

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

def load_side_bets():
    data = load_json(SIDE_BETS_FILE)
    if not data:
        return {
            "props": [],  # List of prop bets
            "active": True
        }
    return data

current_picks = load_picks()

# --- LIVE DATA FETCHING ---
def get_live_data():
    """
    Fetch live golf data from Claude's sports data API.
    
    NOTE: This function is designed to work when run through Claude.
    For local testing without Claude's API, it will use fallback sample data.
    """
    formatted_leaderboard = []
    tournament_name = CURRENT_TOURNAMENT_NAME
    
    try:
        # In production with Claude, this would call the fetch_sports_data tool
        # For now, we'll use sample data that matches the expected format
        
        # When deployed with Claude's sports API, replace this with:
        # sports_data = fetch_sports_data(data_type="scores", league="golf")
        # Then parse sports_data['games'] to find current tournament
        
        # SAMPLE DATA for local testing
        sample_players = [
            {"name": "Scottie Scheffler", "score": -8, "status": "active", "thru": "F", "position": "1"},
            {"name": "Rory McIlroy", "score": -6, "status": "active", "thru": "16", "position": "T2"},
            {"name": "Jon Rahm", "score": -6, "status": "active", "thru": "17", "position": "T2"},
            {"name": "Viktor Hovland", "score": -5, "status": "active", "thru": "F", "position": "4"},
            {"name": "Brooks Koepka", "score": -4, "status": "active", "thru": "15", "position": "5"},
            {"name": "Jordan Spieth", "score": -3, "status": "active", "thru": "14", "position": "T6"},
            {"name": "Patrick Cantlay", "score": -3, "status": "active", "thru": "16", "position": "T6"},
            {"name": "Xander Schauffele", "score": -2, "status": "active", "thru": "F", "position": "8"},
            {"name": "Collin Morikawa", "score": -1, "status": "active", "thru": "13", "position": "9"},
            {"name": "Max Homa", "score": 0, "status": "active", "thru": "12", "position": "T10"},
            {"name": "Dustin Johnson", "score": 0, "status": "active", "thru": "14", "position": "T10"},
            {"name": "Justin Thomas", "score": 1, "status": "CUT", "thru": "F", "position": "MC"},
            {"name": "Tiger Woods", "score": 3, "status": "WD", "thru": "9", "position": "WD"},
            # Add more players for realistic testing
            {"name": "Cameron Smith", "score": -2, "status": "active", "thru": "15", "position": "T8"},
            {"name": "Will Zalatoris", "score": -1, "status": "active", "thru": "16", "position": "T9"},
            {"name": "Tony Finau", "score": 0, "status": "active", "thru": "14", "position": "T10"},
            {"name": "Sam Burns", "score": 1, "status": "active", "thru": "12", "position": "T13"},
            {"name": "Tommy Fleetwood", "score": 1, "status": "active", "thru": "13", "position": "T13"},
            {"name": "Hideki Matsuyama", "score": 2, "status": "active", "thru": "F", "position": "T15"},
            {"name": "Matt Fitzpatrick", "score": 2, "status": "active", "thru": "17", "position": "T15"},
        ]
        
        formatted_leaderboard = sample_players
        
    except Exception as e:
        print(f"Error fetching live data: {e}")
        # Return empty leaderboard on error
        formatted_leaderboard = []
    
    return formatted_leaderboard, tournament_name

def calculate_team_score(picks, leaderboard):
    """Calculate team score - matches Larry's existing logic"""
    team_data = []
    unique_picks = list(set(picks))
    
    for player_name in unique_picks:
        player_stats = next(
            (p for p in leaderboard if p["name"].lower() == player_name.lower()), 
            None
        )
        if player_stats:
            team_data.append(player_stats)
        else:
            # Player not found in leaderboard (hasn't started yet)
            team_data.append({
                "name": player_name,
                "score": 0,
                "status": "active",
                "thru": "-",
                "position": "-"
            })
    
    # Sort by score (lowest is best in golf)
    team_data.sort(key=lambda x: int(x['score']) if isinstance(x['score'], int) else 100)
    top_6_players = team_data[:COUNT_BEST]
    total_score = sum(int(p['score']) for p in top_6_players)
    
    return {
        "total": total_score,
        "all_players": team_data,
        "top_6": top_6_players
    }

# --- ROUTES ---

@app.route('/')
def dashboard():
    """Main dashboard - shows current tournament standings"""
    global current_picks
    current_picks = load_picks()
    leaderboard, tournament_name = get_live_data()
    
    # Load stakes
    settings = load_json(SETTINGS_FILE)
    stakes = settings.get('stakes', 'Bragging Rights')
    
    # Calculate scores
    larry_results = calculate_team_score(current_picks['larry'], leaderboard)
    andy_results = calculate_team_score(current_picks['andy'], leaderboard)
    
    # Get current time
    try:
        est = pytz.timezone('US/Eastern')
        current_time = datetime.now(est).strftime("%I:%M %p ET")
    except:
        current_time = datetime.now().strftime("%I:%M %p")
    
    # Load side bets
    side_bets = load_side_bets()
    
    return render_template('index.html',
                         larry=larry_results,
                         andy=andy_results,
                         tournament_name=tournament_name,
                         stakes=stakes,
                         side_bets=side_bets,
                         last_updated=current_time)

@app.route('/api/refresh')
def api_refresh():
    """API endpoint for auto-refresh - returns JSON data"""
    global current_picks
    current_picks = load_picks()
    leaderboard, tournament_name = get_live_data()
    
    larry_results = calculate_team_score(current_picks['larry'], leaderboard)
    andy_results = calculate_team_score(current_picks['andy'], leaderboard)
    
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

@app.route('/history')
def history():
    """Tournament history page"""
    history_data = load_json(HISTORY_FILE)
    if not isinstance(history_data, list):
        history_data = []
    
    larry_wins = sum(1 for h in history_data if h['winner'] == 'Larry')
    andy_wins = sum(1 for h in history_data if h['winner'] == 'Andy')
    ties = sum(1 for h in history_data if h['winner'] == 'Tie')
    
    return render_template('history.html',
                         history=history_data,
                         larry_wins=larry_wins,
                         andy_wins=andy_wins,
                         ties=ties)

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    """Admin panel - pick players and set stakes"""
    global current_picks
    leaderboard, _ = get_live_data()
    all_players_sorted = sorted(leaderboard, key=lambda x: x['name'])
    
    # Load current settings
    settings = load_json(SETTINGS_FILE)
    current_stakes = settings.get('stakes', '')
    
    if request.method == 'POST':
        # Check if archiving
        if 'archive_week' in request.form:
            return redirect(url_for('archive_week'))
        
        # Save stakes
        new_stakes = request.form.get('stakes', '')
        save_json(SETTINGS_FILE, {'stakes': new_stakes})
        
        # Save picks
        new_picks = {
            "larry": request.form.getlist('larry_picks'),
            "andy": request.form.getlist('andy_picks')
        }
        save_json(PICKS_FILE, new_picks)
        current_picks = load_picks()
        
        return redirect(url_for('dashboard'))
    
    return render_template('admin.html',
                         players=all_players_sorted,
                         current=current_picks,
                         stakes=current_stakes)

@app.route('/draft')
def draft():
    """New draft interface - snake draft style"""
    leaderboard, _ = get_live_data()
    all_players_sorted = sorted(leaderboard, key=lambda x: x['name'])
    
    return render_template('draft.html',
                         players=all_players_sorted)

@app.route('/side_bets', methods=['GET', 'POST'])
def side_bets():
    """Manage side bets"""
    if request.method == 'POST':
        # Handle side bet updates
        bet_data = request.get_json()
        side_bets_current = load_side_bets()
        
        if 'add_bet' in bet_data:
            new_bet = {
                'id': len(side_bets_current.get('props', [])) + 1,
                'type': bet_data['type'],
                'description': bet_data['description'],
                'stake': bet_data['stake'],
                'larry_pick': bet_data.get('larry_pick'),
                'andy_pick': bet_data.get('andy_pick'),
                'status': 'active'
            }
            side_bets_current.setdefault('props', []).append(new_bet)
            save_json(SIDE_BETS_FILE, side_bets_current)
            return jsonify({'success': True, 'bet': new_bet})
        
        return jsonify({'success': False})
    
    # GET request - show side bets page
    side_bets_data = load_side_bets()
    return render_template('side_bets.html', side_bets=side_bets_data)

@app.route('/archive_week')
def archive_week():
    """Archive current tournament results"""
    global current_picks
    current_picks = load_picks()
    leaderboard, tournament_name = get_live_data()
    
    larry = calculate_team_score(current_picks['larry'], leaderboard)
    andy = calculate_team_score(current_picks['andy'], leaderboard)
    
    if larry['total'] < andy['total']:
        winner = "Larry"
    elif andy['total'] < larry['total']:
        winner = "Andy"
    else:
        winner = "Tie"
    
    new_record = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "tournament": tournament_name,
        "larry_score": larry['total'],
        "andy_score": andy['total'],
        "winner": winner
    }
    
    history_data = load_json(HISTORY_FILE)
    if not isinstance(history_data, list):
        history_data = []
    history_data.insert(0, new_record)
    save_json(HISTORY_FILE, history_data)
    
    # Clear picks and settings
    save_json(PICKS_FILE, {"larry": [], "andy": []})
    current_picks = {"larry": [], "andy": []}
    save_json(SETTINGS_FILE, {'stakes': 'Bragging Rights'})
    
    # Archive side bets
    side_bets_data = load_side_bets()
    side_bets_data['active'] = False
    save_json(SIDE_BETS_FILE, side_bets_data)
    
    return redirect(url_for('history'))

if __name__ == '__main__':
    # Initialize data files if they don't exist
    if not os.path.exists(PICKS_FILE):
        save_json(PICKS_FILE, {"larry": [], "andy": []})
    if not os.path.exists(HISTORY_FILE):
        save_json(HISTORY_FILE, [])
    if not os.path.exists(SETTINGS_FILE):
        save_json(SETTINGS_FILE, {'stakes': 'Bragging Rights'})
    if not os.path.exists(SIDE_BETS_FILE):
        save_json(SIDE_BETS_FILE, {'props': [], 'active': True})
    
    app.run(debug=True, host='0.0.0.0', port=5000)
