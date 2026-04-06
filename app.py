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
PLAYERS_FILE = 'players.json'

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

def load_players():
    """Load the full 2026 Masters tournament field from players.json"""
    data = load_json(PLAYERS_FILE)
    if not data:
        # Fallback to empty list if file doesn't exist
        return []
    return data.get('players', [])

def load_side_bets():
    """Load side bets data"""
    data = load_json(SIDE_BETS_FILE)
    if not data:
        return {
            "bet1_type": "",
            "bet1_larry": "",
            "bet1_andy": "",
            "bet1_winner": "",
            "bet2_type": "",
            "bet2_larry": "",
            "bet2_andy": "",
            "bet2_winner": "",
            "bet3_type": "",
            "bet3_larry": "",
            "bet3_andy": "",
            "bet3_winner": "",
            "bet4_type": "",
            "bet4_larry": "",
            "bet4_andy": "",
            "bet4_winner": "",
            "bet5_type": "",
            "bet5_larry": "",
            "bet5_andy": "",
            "bet5_winner": "",
        }
    return data

current_picks = load_picks()

# --- LIVE DATA FETCHING ---
def get_live_data():
    """
    Fetch live golf data from Claude's sports data API.
    
    NOTE: This function is designed to work when run through Claude.
    For local testing without Claude's API, it will use the players.json field with sample scores.
    """
    formatted_leaderboard = []
    tournament_name = CURRENT_TOURNAMENT_NAME
    
    try:
        # Load all players from the Masters field
        all_players = load_players()
        
        # In production with Claude, this would call the fetch_sports_data tool
        # For now, we'll use the players.json data with sample scores for testing
        
        # When deployed with Claude's sports API, replace this with:
        # sports_data = fetch_sports_data(data_type="scores", league="golf")
        # Then parse sports_data['games'] to find current tournament and update scores
        
        # For now, add sample scores to the loaded players for testing
        # In production, these scores would come from the live API
        if all_players:
            formatted_leaderboard = all_players
        else:
            # Ultimate fallback if players.json doesn't exist
            formatted_leaderboard = [
                {"name": "Scottie Scheffler", "score": 0, "status": "active", "thru": "-", "position": "-"},
                {"name": "Rory McIlroy", "score": 0, "status": "active", "thru": "-", "position": "-"},
            ]
        
    except Exception as e:
        print(f"Error fetching live data: {e}")
        # Return empty leaderboard on error
        formatted_leaderboard = []
    
    return formatted_leaderboard, tournament_name

def calculate_team_score(picks, leaderboard):
    """Calculate team score - top 6 of 14 players count"""
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

def get_available_players_for_side_bets():
    """Get players NOT selected in main draft (available for side bets)"""
    current_picks = load_picks()
    all_players = load_players()
    
    # Get all drafted players
    drafted = set(current_picks['larry'] + current_picks['andy'])
    
    # Filter out drafted players
    available = [p for p in all_players if p['name'] not in drafted]
    
    return available

# --- ROUTES ---

@app.route('/')
def dashboard():
    """Main dashboard - shows current tournament standings"""
    global current_picks
    current_picks = load_picks()
    leaderboard, tournament_name = get_live_data()
    
    # Load settings
    settings = load_json(SETTINGS_FILE)
    stakes = settings.get('stakes', 'Bragging Rights')
    tournament_name_custom = settings.get('tournament_name', tournament_name)
    
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
                         tournament_name=tournament_name_custom,
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
    """Admin panel - configure tournament settings only"""
    global current_picks
    
    # Load current settings
    settings = load_json(SETTINGS_FILE)
    current_stakes = settings.get('stakes', 'Bragging Rights')
    current_tournament_name = settings.get('tournament_name', 'The Masters Tournament')
    
    if request.method == 'POST':
        # Check if archiving
        if 'archive_week' in request.form:
            return redirect(url_for('archive_week'))
        
        # Check if this is a draft save (coming from draft page)
        if 'larry_picks' in request.form or 'andy_picks' in request.form:
            larry_picks = request.form.getlist('larry_picks')
            andy_picks = request.form.getlist('andy_picks')
            
            # Save the picks
            picks_data = {
                'larry': larry_picks,
                'andy': andy_picks
            }
            save_json(PICKS_FILE, picks_data)
            current_picks = picks_data
            
            # Also save stakes if provided
            if 'stakes' in request.form:
                new_settings = {
                    'stakes': request.form.get('stakes', 'Bragging Rights'),
                    'tournament_name': settings.get('tournament_name', 'The Masters Tournament')
                }
                save_json(SETTINGS_FILE, new_settings)
            
            return redirect(url_for('dashboard'))
        
        # Otherwise, just save settings
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
    
    return render_template('draft.html',
                         players=all_players_sorted)

@app.route('/side_bets', methods=['GET', 'POST'])
def side_bets():
    """Manage side bets - 5 bets, $2 each, 36-hole format"""
    if request.method == 'POST':
        # Save all 5 side bets
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
        
        # TODO: After Friday, calculate winners here based on 36-hole scores
        # For now, just save the picks
        
        save_json(SIDE_BETS_FILE, bet_data)
        return redirect(url_for('side_bets'))
    
    # GET request - show side bets page
    side_bets_data = load_side_bets()
    available_players = get_available_players_for_side_bets()
    
    # TODO: Set show_results=True after Friday's round is complete
    show_results = False
    larry_wins = 0
    andy_wins = 0
    
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
    current_picks = load_picks()
    leaderboard, tournament_name = get_live_data()
    
    # Load custom tournament name if set
    settings = load_json(SETTINGS_FILE)
    tournament_name = settings.get('tournament_name', tournament_name)
    
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
    save_json(SETTINGS_FILE, {'stakes': 'Bragging Rights', 'tournament_name': 'The Masters Tournament'})
    
    # Clear side bets
    save_json(SIDE_BETS_FILE, {
        "bet1_type": "", "bet1_larry": "", "bet1_andy": "", "bet1_winner": "",
        "bet2_type": "", "bet2_larry": "", "bet2_andy": "", "bet2_winner": "",
        "bet3_type": "", "bet3_larry": "", "bet3_andy": "", "bet3_winner": "",
        "bet4_type": "", "bet4_larry": "", "bet4_andy": "", "bet4_winner": "",
        "bet5_type": "", "bet5_larry": "", "bet5_andy": "", "bet5_winner": "",
    })
    
    return redirect(url_for('history'))

if __name__ == '__main__':
    # Initialize data files if they don't exist
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
