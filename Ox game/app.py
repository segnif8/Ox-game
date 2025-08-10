from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_socketio import SocketIO, join_room, leave_room, emit
import random
import string
from datetime import timedelta
import time
from collections import defaultdict

app = Flask(__name__)
app.secret_key = 'your_secret_key_here'  # change this in production
app.permanent_session_lifetime = timedelta(minutes=30)

# Socket.IO setup
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', ping_timeout=60, ping_interval=25)

# Game data storage
games = {}
chat_messages = defaultdict(list)
player_stats = defaultdict(lambda: {'wins': 0, 'losses': 0, 'ties': 0, 'games_played': 0})
active_players = set()

def generate_game_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))

def check_winner(board):
    # Check rows
    for row in range(3):
        if board[row][0] == board[row][1] == board[row][2] and board[row][0] != ' ':
            return board[row][0], [(row, 0), (row, 1), (row, 2)]
    
    # Check columns
    for col in range(3):
        if board[0][col] == board[1][col] == board[2][col] and board[0][col] != ' ':
            return board[0][col], [(0, col), (1, col), (2, col)]
    
    # Check diagonals
    if board[0][0] == board[1][1] == board[2][2] and board[0][0] != ' ':
        return board[0][0], [(0, 0), (1, 1), (2, 2)]
    if board[0][2] == board[1][1] == board[2][0] and board[0][2] != ' ':
        return board[0][2], [(0, 2), (1, 1), (2, 0)]
    
    # Check for tie
    if all(cell != ' ' for row in board for cell in row):
        return 'Tie', []
    
    return None, []

def reset_game(game_id):
    if game_id in games:
        games[game_id]['board'] = [[' ', ' ', ' '] for _ in range(3)]
        games[game_id]['current_player'] = 'X'
        games[game_id]['winner'] = None
        games[game_id]['winning_cells'] = []
        games[game_id]['move_history'] = []
        games[game_id]['last_move_time'] = time.time()

def _pack_game(game):
    return {
        'board': game['board'],
        'players': game['players'],
        'current_player': game['current_player'],
        'winner': game['winner'],
        'scores': game.get('scores', {'X': 0, 'O': 0}),
        'winning_cells': game.get('winning_cells', []),
        'move_history': game.get('move_history', []),
        'game_start_time': game.get('game_start_time', time.time()),
        'time_controls': game.get('time_controls', None),
        'theme': game.get('theme', 'classic'),
        'game_mode': game.get('game_mode', 'standard'),
        'player_names': game.get('player_names', {'X': 'Player X', 'O': 'Player O'})
    }

@app.route('/')
def home():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
      <title>Segni OX Game</title>
      <style>
        :root {
          --primary: #3B82F6;
          --secondary: #9333EA;
          --accent: #F59E0B;
          --text: #fff;
          --bg: #111;
          --panel-bg: rgba(255, 255, 255, 0.08);
          --x-color: #FF6B6B;
          --o-color: #4ECDC4;
          --success: #10B981;
          --danger: #EF4444;
          --warning: #F59E0B;
          --info: #3B82F6;
        }
        
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }
        
        body {
          font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
          margin: 0;
          padding: 0;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: var(--bg);
          color: var(--text);
          background: linear-gradient(135deg, var(--primary), var(--secondary));
          background-attachment: fixed;
          line-height: 1.5;
        }
        
        .container {
          width: 100%;
          max-width: 1200px;
          padding: 20px;
          display: flex;
          flex-direction: column;
          align-items: center;
        }
        
        .card {
          width: 100%;
          max-width: 500px;
          padding: 24px;
          border-radius: 16px;
          background: var(--panel-bg);
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
          text-align: center;
          backdrop-filter: blur(10px);
          margin-bottom: 20px;
        }
        
        h1 {
          margin: 0 0 16px 0;
          font-size: 28px;
          font-weight: 700;
          background: linear-gradient(to right, var(--x-color), var(--o-color));
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }
        
        .subtitle {
          margin-bottom: 20px;
          opacity: 0.9;
          font-size: 16px;
        }
        
        .tabs {
          display: flex;
          margin-bottom: 20px;
          border-bottom: 1px solid rgba(255, 255, 255, 0.1);
          width: 100%;
        }
        
        .tab {
          padding: 10px 16px;
          cursor: pointer;
          border-bottom: 2px solid transparent;
          transition: all 0.2s;
          font-weight: 600;
        }
        
        .tab.active {
          border-bottom: 2px solid var(--accent);
          color: var(--accent);
        }
        
        .tab-content {
          display: none;
          width: 100%;
        }
        
        .tab-content.active {
          display: flex;
          flex-direction: column;
          gap: 16px;
        }
        
        .form-group {
          display: flex;
          flex-direction: column;
          gap: 8px;
          margin-bottom: 12px;
          text-align: left;
        }
        
        label {
          font-size: 14px;
          font-weight: 500;
          opacity: 0.9;
        }
        
        input, select {
          padding: 12px 16px;
          border-radius: 8px;
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: var(--text);
          font-size: 16px;
          width: 100%;
          transition: all 0.2s;
        }
        
        input:focus, select:focus {
          outline: none;
          box-shadow: 0 0 0 2px var(--accent);
          background: rgba(255, 255, 255, 0.2);
        }
        
        .btn {
          padding: 12px 24px;
          border-radius: 8px;
          border: none;
          cursor: pointer;
          font-weight: 600;
          font-size: 16px;
          transition: all 0.2s;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          gap: 8px;
        }
        
        .btn-primary {
          background: var(--accent);
          color: #111;
        }
        
        .btn-primary:hover {
          background: #E67E22;
          transform: translateY(-2px);
        }
        
        .btn-secondary {
          background: rgba(255, 255, 255, 0.1);
          color: var(--text);
        }
        
        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.2);
        }
        
        .btn-icon {
          width: 40px;
          height: 40px;
          padding: 0;
          border-radius: 50%;
          font-size: 20px;
        }
        
        .btn-group {
          display: flex;
          gap: 12px;
          width: 100%;
        }
        
        .btn-group .btn {
          flex: 1;
        }
        
        .divider {
          height: 1px;
          background: rgba(255, 255, 255, 0.1);
          margin: 20px 0;
          width: 100%;
        }
        
        .features {
          display: grid;
          grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
          gap: 12px;
          width: 100%;
          margin-top: 20px;
        }
        
        .feature {
          background: rgba(255, 255, 255, 0.05);
          padding: 16px;
          border-radius: 8px;
          text-align: left;
          transition: all 0.2s;
        }
        
        .feature:hover {
          background: rgba(255, 255, 255, 0.1);
          transform: translateY(-2px);
        }
        
        .feature-icon {
          font-size: 24px;
          margin-bottom: 8px;
          color: var(--accent);
        }
        
        .feature-title {
          font-weight: 600;
          margin-bottom: 4px;
        }
        
        .feature-desc {
          font-size: 14px;
          opacity: 0.8;
        }
        
        .online-count {
          position: fixed;
          bottom: 20px;
          right: 20px;
          background: var(--panel-bg);
          padding: 8px 16px;
          border-radius: 20px;
          font-size: 14px;
          display: flex;
          align-items: center;
          gap: 8px;
          box-shadow: 0 4px 12px rgba(0, 0, 0, 0.2);
        }
        
        .online-dot {
          width: 10px;
          height: 10px;
          border-radius: 50%;
          background: var(--success);
          animation: pulse 2s infinite;
        }
        
        @keyframes pulse {
          0% { opacity: 1; }
          50% { opacity: 0.5; }
          100% { opacity: 1; }
        }
        
        .how-to-play {
          text-align: left;
          width: 100%;
          margin-top: 20px;
        }
        
        .how-to-play h3 {
          margin-bottom: 12px;
        }
        
        .how-to-play ol {
          padding-left: 20px;
        }
        
        .how-to-play li {
          margin-bottom: 8px;
        }
        
        @media (max-width: 600px) {
          .card {
            padding: 16px;
            border-radius: 12px;
          }
          
          h1 {
            font-size: 24px;
          }
          
          .features {
            grid-template-columns: 1fr;
          }
          
          .btn {
            padding: 10px 16px;
          }
        }
        
        /* Animation classes */
        .shake {
          animation: shake 0.5s ease;
        }
        
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
          20%, 40%, 60%, 80% { transform: translateX(5px); }
        }
        
        .pulse {
          animation: pulse 2s infinite;
        }
        
        .floating {
          animation: floating 3s ease-in-out infinite;
        }
        
        @keyframes floating {
          0%, 100% { transform: translateY(0); }
          50% { transform: translateY(-10px); }
        }
      </style>
      <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
      <div class="container">
        <div class="card floating">
          <h1><i class="fas fa-gamepad"></i> Segni OX Game</h1>
          <p class="subtitle">The most advanced Tic-Tac-Toe experience online</p>
          
          <div class="tabs">
            <div class="tab active" onclick="switchTab('play')">Play Game</div>
            <div class="tab" onclick="switchTab('how-to')">How to Play</div>
            <div class="tab" onclick="switchTab('features')">Features</div>
          </div>
          
          <div id="play" class="tab-content active">
            <form action="/create" method="post" id="createForm">
              <div class="form-group">
                <label for="player_name">Your Name</label>
                <input type="text" id="player_name" name="player_name" placeholder="Enter your name" required>
              </div>
              
              <div class="form-group">
                <label for="game_mode">Game Mode</label>
                <select id="game_mode" name="game_mode">
                  <option value="standard">Standard</option>
                  <option value="timed">Timed (60s per move)</option>
                  <option value="blitz">Blitz (10s per move)</option>
                  <option value="ultimate">Ultimate (3D 4x4x4)</option>
                </select>
              </div>
              
              <div class="form-group">
                <label for="theme">Theme</label>
                <select id="theme" name="theme">
                  <option value="classic">Classic</option>
                  <option value="dark">Dark Mode</option>
                  <option value="neon">Neon</option>
                  <option value="nature">Nature</option>
                  <option value="retro">Retro</option>
                </select>
              </div>
              
              <button type="submit" class="btn btn-primary">
                <i class="fas fa-plus"></i> Create New Game
              </button>
            </form>
            
            <div class="divider">OR</div>
            
            <form action="/join" method="post" id="joinForm">
              <div class="form-group">
                <label for="join_player_name">Your Name</label>
                <input type="text" id="join_player_name" name="player_name" placeholder="Enter your name" required>
              </div>
              
              <div class="form-group">
                <label for="game_id">Game ID</label>
                <input type="text" id="game_id" name="game_id" placeholder="Enter Game ID" required>
              </div>
              
              <button type="submit" class="btn btn-secondary">
                <i class="fas fa-sign-in-alt"></i> Join Existing Game
              </button>
            </form>
          </div>
          
          <div id="how-to" class="tab-content">
            <div class="how-to-play">
              <h3><i class="fas fa-question-circle"></i> How to Play OX (Tic-Tac-Toe)</h3>
              <ol>
                <li>Create a new game or join an existing one using a Game ID</li>
                <li>Player X always goes first</li>
                <li>Take turns placing your symbol (X or O) on the 3x3 grid</li>
                <li>The first player to get 3 of their symbols in a row (horizontally, vertically or diagonally) wins</li>
                <li>If all squares are filled without a winner, the game is a tie</li>
                <li>Use the chat to communicate with your opponent</li>
                <li>Try different game modes and themes for varied gameplay</li>
              </ol>
            </div>
            
            <div class="divider"></div>
            
            <h3><i class="fas fa-trophy"></i> Advanced Features</h3>
            <ul>
              <li><strong>Timed Mode:</strong> Each player has limited time per move</li>
              <li><strong>Blitz Mode:</strong> Ultra-fast gameplay with 10 seconds per move</li>
              <li><strong>Ultimate Mode:</strong> 3D 4x4x4 grid for advanced players</li>
              <li><strong>Player Stats:</strong> Track your wins, losses, and performance</li>
              <li><strong>Spectator Mode:</strong> Watch ongoing games</li>
            </ul>
          </div>
          
          <div id="features" class="tab-content">
            <h3><i class="fas fa-star"></i> Game Features</h3>
            <div class="features">
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-users"></i></div>
                <div class="feature-title">Multiplayer</div>
                <div class="feature-desc">Play with friends or random opponents online in real-time</div>
              </div>
              
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-comments"></i></div>
                <div class="feature-title">In-Game Chat</div>
                <div class="feature-desc">Communicate with your opponent during the game</div>
              </div>
              
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-stopwatch"></i></div>
                <div class="feature-title">Timed Games</div>
                <div class="feature-desc">Multiple time control options for different play styles</div>
              </div>
              
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-palette"></i></div>
                <div class="feature-title">Custom Themes</div>
                <div class="feature-desc">Choose from multiple visual themes to personalize your experience</div>
              </div>
              
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-undo"></i></div>
                <div class="feature-title">Move History</div>
                <div class="feature-desc">Review all moves made during the game</div>
              </div>
              
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-chart-line"></i></div>
                <div class="feature-title">Player Stats</div>
                <div class="feature-desc">Track your wins, losses, and performance over time</div>
              </div>
              
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-mobile-alt"></i></div>
                <div class="feature-title">Mobile Friendly</div>
                <div class="feature-desc">Fully responsive design works on all devices</div>
              </div>
              
              <div class="feature">
                <div class="feature-icon"><i class="fas fa-eye"></i></div>
                <div class="feature-title">Spectator Mode</div>
                <div class="feature-desc">Watch ongoing games between other players</div>
              </div>
            </div>
          </div>
        </div>
        
        <div class="online-count">
          <div class="online-dot"></div>
          <span id="onlineCount">Loading...</span> players online
        </div>
      </div>
      
      <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
      <script>
        const socket = io();
        
        // Switch between tabs
        function switchTab(tabId) {
          document.querySelectorAll('.tab').forEach(tab => {
            tab.classList.remove('active');
          });
          document.querySelectorAll('.tab-content').forEach(content => {
            content.classList.remove('active');
          });
          
          document.querySelector(`.tab[onclick="switchTab('${tabId}')"]`).classList.add('active');
          document.getElementById(tabId).classList.add('active');
        }
        
        // Get online player count
        socket.on('player_count', (count) => {
          document.getElementById('onlineCount').textContent = count;
        });
        
        // Form validation
        document.getElementById('createForm').addEventListener('submit', (e) => {
          const name = document.getElementById('player_name').value.trim();
          if (!name) {
            e.preventDefault();
            alert('Please enter your name');
            return false;
          }
          return true;
        });
        
        document.getElementById('joinForm').addEventListener('submit', (e) => {
          const name = document.getElementById('join_player_name').value.trim();
          const gameId = document.getElementById('game_id').value.trim();
          
          if (!name || !gameId) {
            e.preventDefault();
            alert('Please enter your name and game ID');
            return false;
          }
          return true;
        });
        
        // Show loading state on buttons
        document.querySelectorAll('form').forEach(form => {
          form.addEventListener('submit', () => {
            const button = form.querySelector('button[type="submit"]');
            button.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Loading...';
            button.disabled = true;
          });
        });
      </script>
    </body>
    </html>
    ''')

@app.route('/create', methods=['POST'])
def create_game():
    game_id = generate_game_id()
    player_name = request.form.get('player_name', 'Player X').strip() or 'Player X'
    game_mode = request.form.get('game_mode', 'standard')
    theme = request.form.get('theme', 'classic')
    
    time_controls = None
    if game_mode == 'timed':
        time_controls = {'per_move': 60, 'remaining': {'X': 60, 'O': 60}}
    elif game_mode == 'blitz':
        time_controls = {'per_move': 10, 'remaining': {'X': 10, 'O': 10}}
    
    games[game_id] = {
        'board': [[' ', ' ', ' '] for _ in range(3)],
        'players': ['X'],
        'player_names': {'X': player_name},
        'current_player': 'X',
        'winner': None,
        'winning_cells': [],
        'scores': {'X': 0, 'O': 0},
        'move_history': [],
        'game_start_time': time.time(),
        'last_move_time': time.time(),
        'time_controls': time_controls,
        'theme': theme,
        'game_mode': game_mode,
        'spectators': []
    }
    
    chat_messages[game_id] = []
    session['game_id'] = game_id
    session['player'] = 'X'
    session['player_name'] = player_name
    return redirect(url_for('game', game_id=game_id))

@app.route('/join', methods=['POST'])
def join_game():
    game_id = request.form['game_id'].upper().strip()
    player_name = request.form.get('player_name', 'Player O').strip() or 'Player O'
    
    if game_id in games and len(games[game_id]['players']) < 2:
        session['game_id'] = game_id
        session['player'] = 'O'
        session['player_name'] = player_name
        games[game_id]['players'].append('O')
        games[game_id]['player_names']['O'] = player_name
        return redirect(url_for('game', game_id=game_id))
    
    # Check if game exists but is full - offer to spectate
    if game_id in games:
        session['game_id'] = game_id
        session['player'] = 'spectator'
        session['player_name'] = player_name
        games[game_id]['spectators'].append(player_name)
        return redirect(url_for('game', game_id=game_id))
    
    return render_template_string('''
      <!doctype html>
      <html><head><meta charset="utf-8"><title>Game Not Found</title>
      <style>body{font-family:sans-serif;background:#111;color:#fff;display:flex;align-items:center;justify-content:center;height:100vh}a{color:#0af}</style>
      </head>
      <body>
        <div style="text-align:center;padding:20px;">
          <h2>Game Not Found</h2>
          <p>The game ID you entered doesn't exist or may have expired.</p>
          <p style="margin-top:20px;">
            <a href="/" style="display:inline-block;padding:10px 20px;background:#F59E0B;color:#111;border-radius:8px;text-decoration:none;font-weight:bold;">
              <i class="fas fa-arrow-left"></i> Return Home
            </a>
          </p>
        </div>
        <script src="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/js/all.min.js"></script>
      </body>
      </html>
    '''), 404

@app.route('/game/<game_id>')
def game(game_id):
    if game_id not in games or 'player' not in session or session.get('game_id') != game_id:
        return redirect(url_for('home'))
    
    game_data = games[game_id]
    player = session['player']
    player_name = session.get('player_name', f'Player {player}')
    theme = game_data.get('theme', 'classic')
    
    # Theme-specific variables
    theme_styles = {
        'classic': {
            'bg1': '#3B82F6',
            'bg2': '#9333EA',
            'x_color': '#FF6B6B',
            'o_color': '#4ECDC4',
            'panel_bg': 'rgba(255,255,255,0.08)'
        },
        'dark': {
            'bg1': '#111',
            'bg2': '#222',
            'x_color': '#FF5252',
            'o_color': '#4CAF50',
            'panel_bg': 'rgba(0,0,0,0.4)'
        },
        'neon': {
            'bg1': '#0F0',
            'bg2': '#F0F',
            'x_color': '#FF0',
            'o_color': '#0FF',
            'panel_bg': 'rgba(0,0,0,0.7)'
        },
        'nature': {
            'bg1': '#4CAF50',
            'bg2': '#8BC34A',
            'x_color': '#FF5722',
            'o_color': '#2196F3',
            'panel_bg': 'rgba(255,255,255,0.1)'
        },
        'retro': {
            'bg1': '#FF9800',
            'bg2': '#9C27B0',
            'x_color': '#E91E63',
            'o_color': '#00BCD4',
            'panel_bg': 'rgba(0,0,0,0.5)'
        }
    }
    
    current_theme = theme_styles.get(theme, theme_styles['classic'])
    
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
      <meta charset="utf-8" />
      <title>Game {{game_id}} - Segni OX</title>
      <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no" />
      <style>
        :root {
          --bg1: {{ current_theme.bg1 }};
          --bg2: {{ current_theme.bg2 }};
          --panel-bg: {{ current_theme.panel_bg }};
          --x-color: {{ current_theme.x_color }};
          --o-color: {{ current_theme.o_color }};
          --accent: #F59E0B;
          --text: #fff;
          --success: #10B981;
          --danger: #EF4444;
          --warning: #F59E0B;
          --info: #3B82F6;
          --border-radius: 12px;
        }
        
        * {
          box-sizing: border-box;
          margin: 0;
          padding: 0;
        }
        
        body {
          font-family: 'Segoe UI', system-ui, -apple-system, sans-serif;
          margin: 0;
          padding: 0;
          min-height: 100vh;
          display: flex;
          align-items: center;
          justify-content: center;
          background: linear-gradient(135deg, var(--bg1), var(--bg2));
          background-attachment: fixed;
          color: var(--text);
          line-height: 1.5;
        }
        
        .game-container {
          width: 100%;
          max-width: 800px;
          padding: 20px;
          display: flex;
          flex-direction: column;
          gap: 20px;
        }
        
        .panel {
          width: 100%;
          padding: 20px;
          border-radius: var(--border-radius);
          background: var(--panel-bg);
          box-shadow: 0 10px 30px rgba(0, 0, 0, 0.3);
          backdrop-filter: blur(10px);
        }
        
        .header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 16px;
          flex-wrap: wrap;
          gap: 12px;
        }
        
        h1 {
          font-size: 24px;
          font-weight: 700;
          margin: 0;
          background: linear-gradient(to right, var(--x-color), var(--o-color));
          -webkit-background-clip: text;
          background-clip: text;
          color: transparent;
        }
        
        .game-id {
          font-family: monospace;
          background: rgba(0, 0, 0, 0.2);
          padding: 6px 12px;
          border-radius: 20px;
          font-size: 14px;
        }
        
        .player-info {
          display: flex;
          gap: 12px;
          align-items: center;
          background: rgba(0, 0, 0, 0.2);
          padding: 8px 16px;
          border-radius: 20px;
        }
        
        .player-badge {
          font-weight: 600;
        }
        
        .player-badge.you {
          color: var(--accent);
        }
        
        .status-container {
          margin: 16px 0;
          text-align: center;
        }
        
        .status {
          font-size: 18px;
          font-weight: 700;
          padding: 12px 20px;
          border-radius: var(--border-radius);
          background: rgba(0, 0, 0, 0.2);
          display: inline-block;
          margin-bottom: 12px;
        }
        
        .timer {
          font-family: monospace;
          font-size: 16px;
          background: rgba(0, 0, 0, 0.3);
          padding: 6px 12px;
          border-radius: 20px;
          display: inline-block;
        }
        
        .timer.warning {
          color: var(--warning);
          animation: pulse 1s infinite;
        }
        
        .timer.danger {
          color: var(--danger);
          animation: pulse 0.5s infinite;
        }
        
        .board-container {
          display: flex;
          justify-content: center;
          margin: 20px 0;
        }
        
        .board {
          display: grid;
          grid-template-columns: repeat(3, 1fr);
          gap: 10px;
          max-width: 400px;
          width: 100%;
          aspect-ratio: 1/1;
        }
        
        .cell {
          background: rgba(255, 255, 255, 0.1);
          border-radius: var(--border-radius);
          display: flex;
          align-items: center;
          justify-content: center;
          font-size: min(15vw, 80px);
          font-weight: 800;
          cursor: pointer;
          user-select: none;
          transition: all 0.2s ease;
          position: relative;
          overflow: hidden;
        }
        
        .cell.x-symbol {
          color: var(--x-color);
        }
        
        .cell.o-symbol {
          color: var(--o-color);
        }
        
        .cell.winner-cell {
          animation: rainbowBorder 2s linear infinite, pulseScale 1.5s ease infinite;
        }
        
        .cell:not(.x-symbol):not(.o-symbol):hover {
          background: rgba(255, 255, 255, 0.2);
          }
        
        .cell.disabled {
          cursor: not-allowed;
          opacity: 0.7;
        }
        
        @keyframes rainbowBorder {
          0% { box-shadow: 0 0 0 3px #FF0000; }
          14% { box-shadow: 0 0 0 3px #FF7F00; }
          28% { box-shadow: 0 0 0 3px #FFFF00; }
          42% { box-shadow: 0 0 0 3px #00FF00; }
          57% { box-shadow: 0 0 0 3px #0000FF; }
          71% { box-shadow: 0 0 0 3px #4B0082; }
          85% { box-shadow: 0 0 0 3px #9400D3; }
          100% { box-shadow: 0 0 0 3px #FF0000; }
        }
        
        @keyframes pulseScale {
  0% { transform: none; }
  50% { transform: none; }
  100% { transform: none; }
}
          50% { transform: scale(1.1); }
          100% { transform: scale(1); }
        }
        
        @keyframes pulse {
          0%, 100% { opacity: 1; }
          50% { opacity: 0.5; }
        }
        
        .score-board {
          display: flex;
          justify-content: center;
          gap: 20px;
          margin: 10px 0;
        }
        
        .score {
          padding: 8px 20px;
          border-radius: 20px;
          background: rgba(0, 0, 0, 0.2);
          font-weight: 600;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .score.active {
          background: rgba(255, 255, 255, 0.2);
        }
        
        .score-x {
          color: var(--x-color);
        }
        
        .score-o {
          color: var(--o-color);
        }
        
        .controls {
          display: flex;
          gap: 12px;
          justify-content: center;
          margin-top: 20px;
          flex-wrap: wrap;
        }
        
        .btn {
          padding: 10px 20px;
          border-radius: var(--border-radius);
          border: none;
          cursor: pointer;
          font-weight: 600;
          transition: all 0.2s;
          display: inline-flex;
          align-items: center;
          gap: 8px;
          font-size: 14px;
        }
        
        .btn-primary {
          background: var(--accent);
          color: #111;
        }
        
        .btn-primary:hover {
          background: #E67E22;
          transform: translateY(-2px);
        }
        
        .btn-secondary {
          background: rgba(255, 255, 255, 0.1);
          color: var(--text);
        }
        
        .btn-secondary:hover {
          background: rgba(255, 255, 255, 0.2);
        }
        
        .btn-danger {
          background: var(--danger);
          color: white;
        }
        
        .btn-danger:hover {
          background: #DC2626;
        }
        
        .chat-container {
          margin-top: 20px;
        }
        
        .chat-header {
          display: flex;
          justify-content: space-between;
          align-items: center;
          margin-bottom: 12px;
        }
        
        .chat-messages {
          height: 200px;
          overflow-y: auto;
          background: rgba(0, 0, 0, 0.2);
          border-radius: var(--border-radius);
          padding: 12px;
          margin-bottom: 12px;
          display: flex;
          flex-direction: column;
          gap: 8px;
        }
        
        .chat-message {
          word-break: break-word;
          line-height: 1.4;
        }
        
        .chat-message strong {
          color: var(--accent);
        }
        
        .chat-message.system {
          opacity: 0.8;
          font-style: italic;
        }
        
        .chat-input-container {
          display: flex;
          gap: 8px;
        }
        
        .chat-input {
          flex: 1;
          padding: 12px;
          border-radius: var(--border-radius);
          border: none;
          background: rgba(255, 255, 255, 0.1);
          color: var(--text);
          font-size: 14px;
        }
        
        .chat-input:focus {
          outline: none;
          background: rgba(255, 255, 255, 0.2);
        }
        
        .btn-send {
          padding: 0 16px;
          border-radius: var(--border-radius);
          background: var(--accent);
          color: #111;
          border: none;
          cursor: pointer;
          font-weight: 600;
        }
        
        .move-history {
          margin-top: 20px;
        }
        
        .move-history-title {
          margin-bottom: 8px;
          font-weight: 600;
        }
        
        .moves-list {
          display: flex;
          flex-wrap: wrap;
          gap: 8px;
        }
        
        .move {
          background: rgba(0, 0, 0, 0.2);
          padding: 6px 10px;
          border-radius: 20px;
          font-size: 12px;
        }
        
        .confetti-container {
          position: fixed;
          top: 0;
          left: 0;
          width: 100%;
          height: 100%;
          pointer-events: none;
          z-index: 1000;
          overflow: hidden;
        }
        
        .confetti {
          position: absolute;
          width: 10px;
          height: 10px;
          opacity: 0;
        }
        
        .spectator-notice {
          background: rgba(255, 255, 255, 0.1);
          padding: 12px;
          border-radius: var(--border-radius);
          text-align: center;
          margin-bottom: 16px;
        }
        
        .player-list {
          display: flex;
          gap: 12px;
          justify-content: center;
          flex-wrap: wrap;
          margin-bottom: 16px;
        }
        
        .player-item {
          background: rgba(0, 0, 0, 0.2);
          padding: 8px 16px;
          border-radius: 20px;
          display: flex;
          align-items: center;
          gap: 8px;
        }
        
        .player-item.you::after {
          content: "(You)";
          font-size: 12px;
          opacity: 0.8;
        }
        
        .player-item.x {
          color: var(--x-color);
        }
        
        .player-item.o {
          color: var(--o-color);
        }
        
        .player-item.spectator {
          color: var(--text);
          opacity: 0.8;
        }
        
        /* Animations */
        @keyframes celebrate {
  0% { transform: none; color: #fff; }
  25% { transform: none; color: #FFD700; }
  50% { transform: none; color: #FF6B6B; }
  75% { transform: none; color: #4ECDC4; }
  100% { transform: none; color: #fff; }
}
          25% { transform: scale(1.2); color: #FFD700; }
          50% { transform: scale(1); color: #FF6B6B; }
          75% { transform: scale(1.2); color: #4ECDC4; }
          100% { transform: scale(1); color: #fff; }
        }
        
        .celebrate {
          animation: celebrate 1s ease infinite;
        }
        
        @keyframes sad {
          0% { opacity: 1; }
          50% { opacity: 0.5; color: #888; }
          100% { opacity: 1; }
        }
        
        .sad {
          animation: sad 1.5s ease infinite;
        }
        
        @keyframes shake {
          0%, 100% { transform: translateX(0); }
          10%, 30%, 50%, 70%, 90% { transform: translateX(-5px); }
          20%, 40%, 60%, 80% { transform: translateX(5px); }
        }
        
        .shake {
          animation: shake 0.5s ease;
        }
        
        /* Responsive styles */
        @media (max-width: 600px) {
          .panel {
            padding: 16px;
          }
          
          .header {
            flex-direction: column;
            align-items: center;
            gap: 8px;
          }
          
          .player-info {
            order: 1;
          }
          
          .board {
            aspect-ratio: 1/1;
            max-width: 100%;
          }
          
          .cell {
            font-size: 20vw;
          }
          
          .controls {
            flex-direction: column;
            align-items: center;
          }
          
          .btn {
            width: 100%;
            justify-content: center;
          }
          
          .chat-messages {
            height: 150px;
          }
        }
      </style>
      <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    </head>
    <body>
      <div class="confetti-container" id="confetti-container"></div>
      
      <div class="game-container">
        <div class="panel">
          <div class="header">
            <h1><i class="fas fa-gamepad"></i> Segni OX Game</h1>
            <div class="game-id">Game ID: <strong>{{ game_id }}</strong></div>
            <div class="player-info">
              <div class="player-badge {% if player != 'spectator' %}you{% endif %}">
                <i class="fas fa-user"></i> {{ player_name }} {% if player != 'spectator' %}({{ player }}){% endif %}
              </div>
            </div>
          </div>
          
          {% if player == 'spectator' %}
            <div class="spectator-notice">
              <i class="fas fa-eye"></i> You are spectating this game
            </div>
          {% endif %}
          
          <div class="player-list">
            {% if 'player_names' in game_data %}
              <div class="player-item x {% if player == 'X' %}you{% endif %}">
                <i class="fas fa-times"></i> {{ game_data['player_names']['X'] }}
              </div>
              {% if 'O' in game_data['player_names'] %}
                <div class="player-item o {% if player == 'O' %}you{% endif %}">
                  <i class="far fa-circle"></i> {{ game_data['player_names']['O'] }}
                </div>
              {% endif %}
              {% for spec in game_data.get('spectators', []) %}
                <div class="player-item spectator {% if player == 'spectator' and player_name == spec %}you{% endif %}">
                  <i class="fas fa-eye"></i> {{ spec }}
                </div>
              {% endfor %}
            {% endif %}
          </div>
          
          <div class="status-container">
            <div id="status" class="status">Loading game...</div>
            {% if game_data.get('time_controls') %}
              <div id="timer" class="timer">X: {{ game_data['time_controls']['remaining']['X'] }}s | O: {{ game_data['time_controls']['remaining']['O'] }}s</div>
            {% endif %}
          </div>
          
          <div class="score-board">
            <div id="score-x" class="score score-x">
              <i class="fas fa-times"></i> <span id="score-x-value">{{ game_data['scores']['X'] }}</span>
            </div>
            <div id="score-o" class="score score-o">
              <i class="far fa-circle"></i> <span id="score-o-value">{{ game_data['scores']['O'] }}</span>
            </div>
          </div>
          
          <div class="board-container">
            <div id="board" class="board">
              {% for r in range(3) %}
                {% for c in range(3) %}
                  <div class="cell" data-row="{{ r }}" data-col="{{ c }}"></div>
                {% endfor %}
              {% endfor %}
            </div>
          </div>
          
          <div class="controls">
            <button id="btnRematch" class="btn btn-primary">
              <i class="fas fa-redo"></i> Rematch
            </button>
            <button id="btnNewGame" class="btn btn-secondary">
              <i class="fas fa-plus"></i> New Game
            </button>
            <button id="btnLeave" class="btn btn-danger">
              <i class="fas fa-sign-out-alt"></i> Leave
            </button>
          </div>
        </div>
        
        <div class="panel">
          <div class="chat-container">
            <div class="chat-header">
              <h2><i class="fas fa-comments"></i> Game Chat</h2>
            </div>
            <div id="chat-messages" class="chat-messages">
              {% for msg in chat_messages %}
                <div class="chat-message">
                  <strong>{{ msg['player'] }}:</strong> {{ msg['message'] }}
                </div>
              {% endfor %}
            </div>
            <div class="chat-input-container">
              <input type="text" id="chat-input" class="chat-input" placeholder="Type your message..." {% if player == 'spectator' %}disabled placeholder="Spectators cannot chat"{% endif %} />
              <button id="btnSend" class="btn-send" {% if player == 'spectator' %}disabled{% endif %}>
                <i class="fas fa-paper-plane"></i>
              </button>
            </div>
          </div>
          
          {% if game_data.get('move_history') %}
            <div class="move-history">
              <div class="move-history-title"><i class="fas fa-history"></i> Move History</div>
              <div class="moves-list">
                {% for move in game_data['move_history'] %}
                  <div class="move">{{ move['player'] }}: ({{ move['row'] }}, {{ move['col'] }})</div>
                {% endfor %}
              </div>
            </div>
          {% endif %}
        </div>
      </div>
      
      <script src="https://cdn.socket.io/4.5.4/socket.io.min.js"></script>
      <script>
        const socket = io();
        const gameId = "{{ game_id }}";
        const player = "{{ player }}";
        const playerName = "{{ player_name }}";
        
        // DOM elements
        const statusEl = document.getElementById('status');
        const boardEl = document.getElementById('board');
        const chatMessagesEl = document.getElementById('chat-messages');
        const chatInputEl = document.getElementById('chat-input');
        const btnSend = document.getElementById('btnSend');
        const scoreXEl = document.getElementById('score-x');
        const scoreOEl = document.getElementById('score-o');
        const scoreXValue = document.getElementById('score-x-value');
        const scoreOValue = document.getElementById('score-o-value');
        const timerEl = document.getElementById('timer');
        const confettiContainer = document.getElementById('confetti-container');
        const btnRematch = document.getElementById('btnRematch');
        const btnNewGame = document.getElementById('btnNewGame');
        const btnLeave = document.getElementById('btnLeave');
        
        // Join game and request initial state
        socket.emit('join_game', {
          game_id: gameId, 
          player: player,
          player_name: playerName
        });
        
        socket.emit('request_state', {game_id: gameId});
        
        // Game state updates
        socket.on('game_update', (data) => {
          renderBoard(data.board, data.winning_cells);
          updateScores(data.scores);
          
          // Highlight current player
          scoreXEl.classList.toggle('active', data.current_player === 'X');
          scoreOEl.classList.toggle('active', data.current_player === 'O');
          
          // Update timer if available
          if (data.time_controls) {
            updateTimer(data.time_controls.remaining, data.current_player);
          }
          
          if (data.players.length < 2) {
            statusEl.textContent = "Waiting for another player to join...";
            statusEl.className = 'status';
          } else if (data.winner) {
            if (data.winner === 'Tie') {
              statusEl.textContent = "Game ended in a tie! 🤝";
              statusEl.className = 'status shake';
              document.querySelectorAll('.cell').forEach(cell => {
                cell.classList.add('shake');
                setTimeout(() => cell.classList.remove('shake'), 500);
              });
            } else {
              const winnerName = data.player_names[data.winner] || `Player ${data.winner}`;
              statusEl.textContent = data.winner === player 
                ? `You win! 🏆🎉 (${winnerName})` 
                : `You lose! 😢 (${winnerName} wins)`;
              
              if (data.winner === player) {
                statusEl.className = 'status celebrate';
                createConfetti();
              } else {
                statusEl.className = 'status sad';
              }
            }
            
            // Auto-reset after 5 seconds
            setTimeout(() => {
              socket.emit('request_reset', {game_id: gameId});
            }, 5000);
          } else {
            const currentPlayerName = data.player_names[data.current_player] || `Player ${data.current_player}`;
            statusEl.textContent = `Current turn: ${currentPlayerName}` + 
              (data.current_player === player ? " — Your move" : "");
            statusEl.className = 'status';
          }
        });
        
        // Create confetti effect
        function createConfetti() {
          confettiContainer.innerHTML = '';
          
          for (let i = 0; i < 150; i++) {
            const confetti = document.createElement('div');
            confetti.className = 'confetti';
            
            const colors = ['#FF5252', '#FFD700', '#4CAF50', '#2196F3', '#9C27B0'];
            const shapes = ['circle', 'square', 'triangle'];
            
            confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
            confetti.style.left = Math.random() * 100 + 'vw';
            confetti.style.top = -10 + 'px';
            confetti.style.width = Math.random() * 10 + 5 + 'px';
            confetti.style.height = Math.random() * 10 + 5 + 'px';
            confetti.style.opacity = Math.random();
            confetti.style.transform = `rotate(${Math.random() * 360}deg)`;
            
            if (Math.random() > 0.5) {
              confetti.style.borderRadius = '50%';
            }
            
            const animationDuration = Math.random() * 3 + 2;
            confetti.style.animation = `fall ${animationDuration}s linear forwards`;
            
            const keyframes = `
              @keyframes fall {
                to {
                  transform: translateY(100vh) rotate(${Math.random() * 360}deg);
                  opacity: 0;
                }
              }
            `;
            const style = document.createElement('style');
            style.innerHTML = keyframes;
            document.head.appendChild(style);
            
            confettiContainer.appendChild(confetti);
            
            setTimeout(() => {
              confetti.remove();
            }, animationDuration * 1000);
          }
        }
        
        // Update timer display
        function updateTimer(times, currentPlayer) {
          if (!timerEl) return;
          
          timerEl.textContent = `X: ${times.X}s | O: ${times.O}s`;
          
          // Highlight current player's time
          if (times[currentPlayer] <= 5) {
            timerEl.classList.add('danger');
            timerEl.classList.remove('warning');
          } else if (times[currentPlayer] <= 15) {
            timerEl.classList.add('warning');
            timerEl.classList.remove('danger');
          } else {
            timerEl.classList.remove('warning', 'danger');
          }
        }
        
        // Player left the game
        socket.on('player_left', (data) => {
          const playerName = data.player_name || `Player ${data.player}`;
          statusEl.textContent = `${playerName} has left the game`;
          statusEl.className = 'status shake';
          
          // Add system message to chat
          const msgEl = document.createElement('div');
          msgEl.className = 'chat-message system';
          msgEl.textContent = `System: ${playerName} has left the game`;
          chatMessagesEl.appendChild(msgEl);
          chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
          
          setTimeout(() => {
            socket.emit('request_state', {game_id: gameId});
          }, 2000);
        });
        
        // Player joined the game
        socket.on('player_joined', (data) => {
          const playerName = data.player_name || `Player ${data.player}`;
          const msgEl = document.createElement('div');
          msgEl.className = 'chat-message system';
          msgEl.textContent = `System: ${playerName} has joined the game`;
          chatMessagesEl.appendChild(msgEl);
          chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
        });
        
        // Spectator joined
        socket.on('spectator_joined', (data) => {
          const msgEl = document.createElement('div');
          msgEl.className = 'chat-message system';
          msgEl.textContent = `System: ${data.player_name} is now spectating`;
          chatMessagesEl.appendChild(msgEl);
          chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
        });
        
        // Invalid move attempt
        socket.on('invalid_move', (data) => {
          const prev = statusEl.textContent;
          const prevClass = statusEl.className;
          statusEl.textContent = "Invalid: " + (data.message || "not allowed");
          statusEl.className = 'status shake';
          setTimeout(() => {
            statusEl.textContent = prev;
            statusEl.className = prevClass;
          }, 1400);
        });
        
        // Chat message received
        socket.on('chat_message', (data) => {
          const msgEl = document.createElement('div');
          msgEl.className = 'chat-message';
          msgEl.innerHTML = `<strong>${data.player_name || data.player}:</strong> ${data.message}`;
          chatMessagesEl.appendChild(msgEl);
          chatMessagesEl.scrollTop = chatMessagesEl.scrollHeight;
        });
        
        // Render the game board
        function renderBoard(board, winningCells) {
          // Clear winner classes first
          document.querySelectorAll('.cell').forEach(cell => {
            cell.classList.remove('winner-cell', 'x-symbol', 'o-symbol', 'disabled');
          });
          
          for (let r = 0; r < 3; r++) {
            for (let c = 0; c < 3; c++) {
              const selector = `.cell[data-row="${r}"][data-col="${c}"]`;
              const cell = document.querySelector(selector);
              cell.textContent = board[r][c] === ' ' ? '' : board[r][c];
              
              // Add symbol class
              if (board[r][c] === 'X') cell.classList.add('x-symbol');
              if (board[r][c] === 'O') cell.classList.add('o-symbol');
              
              // Disable filled cells
              if (board[r][c] !== ' ') {
                cell.classList.add('disabled');
              }
            }
          }
          
          // Highlight winning cells
          winningCells.forEach(([r, c]) => {
            const selector = `.cell[data-row="${r}"][data-col="${c}"]`;
            const cell = document.querySelector(selector);
            if (cell) cell.classList.add('winner-cell');
          });
        }
        
        // Update scores display
        function updateScores(scores) {
          scoreXValue.textContent = scores.X;
          scoreOValue.textContent = scores.O;
        }
        
        // Board click handler
        boardEl.addEventListener('click', (ev) => {
          if (player === 'spectator') return;
          
          const cell = ev.target.closest('.cell');
          if (!cell || cell.classList.contains('disabled')) return;
          
          const row = parseInt(cell.dataset.row);
          const col = parseInt(cell.dataset.col);
          
          socket.emit('make_move', {
            game_id: gameId, 
            player: player, 
            row: row, 
            col: col
          });
        });
        
        // Chat handlers
        chatInputEl.addEventListener('keypress', (e) => {
          if (e.key === 'Enter' && chatInputEl.value.trim()) {
            sendMessage();
          }
        });
        
        btnSend.addEventListener('click', () => {
          if (chatInputEl.value.trim()) sendMessage();
        });
        
        function sendMessage() {
          socket.emit('send_chat', {
            game_id: gameId,
            player: player,
            player_name: playerName,
            message: chatInputEl.value.trim()
          });
          chatInputEl.value = '';
        }
        
        // Button handlers
        btnRematch.addEventListener('click', () => {
          socket.emit('request_reset', {game_id: gameId});
        });
        
        btnNewGame.addEventListener('click', () => {
          window.location.href = '/';
        });
        
        btnLeave.addEventListener('click', () => {
          socket.emit('leave_game', {
            game_id: gameId, 
            player: player,
            player_name: playerName
          });
          window.location.href = '/';
        });
        
        // Cleanup on page leave
        window.addEventListener('beforeunload', () => {
          socket.emit('leave_game', {
            game_id: gameId, 
            player: player,
            player_name: playerName
          });
        });
        
        // Focus chat input when clicking anywhere on chat messages
        chatMessagesEl.addEventListener('click', () => {
          chatInputEl.focus();
        });
      </script>
    </body>
    </html>
    ''', game_id=game_id, player=player, player_name=player_name, 
        game_data=game_data, current_theme=current_theme,
        chat_messages=chat_messages.get(game_id, []))

# ----- Socket.IO event handlers -----
@socketio.on('connect')
def handle_connect():
    active_players.add(request.sid)
    emit('player_count', len(active_players), broadcast=True)

@socketio.on('disconnect')
def handle_disconnect():
    if request.sid in active_players:
        active_players.remove(request.sid)
    emit('player_count', len(active_players), broadcast=True)

@socketio.on('join_game')
def handle_join(data):
    game_id = data.get('game_id')
    player = data.get('player')
    player_name = data.get('player_name', f'Player {player}')
    
    if not game_id or game_id not in games:
        emit('invalid_move', {'message': 'Game not found'})
        return
    
    join_room(game_id)
    
    if player == 'spectator':
        games[game_id]['spectators'].append(player_name)
        emit('spectator_joined', {
            'player_name': player_name
        }, room=game_id)
    else:
        # Update player name if provided
        if 'player_names' not in games[game_id]:
            games[game_id]['player_names'] = {}
        games[game_id]['player_names'][player] = player_name
        
        emit('player_joined', {
            'player': player,
            'player_name': player_name
        }, room=game_id)
    
    emit('game_update', _pack_game(games[game_id]), room=game_id)
    
    # Send chat history
    for msg in chat_messages.get(game_id, [])[-50:]:
        emit('chat_message', msg, room=request.sid)

@socketio.on('leave_game')
def handle_leave(data):
    game_id = data.get('game_id')
    player = data.get('player')
    player_name = data.get('player_name', f'Player {player}')
    
    if game_id and game_id in games:
        leave_room(game_id)
        
        if player == 'spectator':
            if player_name in games[game_id]['spectators']:
                games[game_id]['spectators'].remove(player_name)
        elif player in games[game_id]['players']:
            games[game_id]['players'].remove(player)
            
            # Notify remaining players
            emit('player_left', {
                'player': player,
                'player_name': player_name
            }, room=game_id)
            
            emit('chat_message', {
                'player': 'System',
                'player_name': 'System',
                'message': f'{player_name} has left the game'
            }, room=game_id)
            
            # If no players left, clean up the game after a delay
            if not games[game_id]['players']:
                def cleanup():
                    if game_id in games:
                        del games[game_id]
                    if game_id in chat_messages:
                        del chat_messages[game_id]
                socketio.start_background_task(lambda: socketio.sleep(60) or cleanup())

@socketio.on('request_state')
def handle_request_state(data):
    game_id = data.get('game_id')
    if game_id in games:
        emit('game_update', _pack_game(games[game_id]))

@socketio.on('request_reset')
def handle_request_reset(data):
    game_id = data.get('game_id')
    if game_id in games and games[game_id]['winner']:
        reset_game(game_id)
        emit('game_update', _pack_game(games[game_id]), room=game_id)
        emit('chat_message', {
            'player': 'System',
            'player_name': 'System',
            'message': 'Game has been reset!'
        }, room=game_id)

@socketio.on('make_move')
def handle_make_move(data):
    game_id = data.get('game_id')
    player = data.get('player')
    row = data.get('row')
    col = data.get('col')
    
    if not game_id or game_id not in games:
        emit('invalid_move', {'message': 'Game not found'})
        return

    game = games[game_id]

    # Validations
    if len(game['players']) < 2:
        emit('invalid_move', {'message': 'Waiting for another player'})
        return
    if game['winner']:
        emit('invalid_move', {'message': 'Game already ended'})
        return
    if game['current_player'] != player:
        emit('invalid_move', {'message': 'Not your turn'})
        return
    try:
        r = int(row); c = int(col)
    except:
        emit('invalid_move', {'message': 'Invalid coordinates'})
        return
    if r < 0 or r > 2 or c < 0 or c > 2:
        emit('invalid_move', {'message': 'Out of bounds'})
        return
    if game['board'][r][c] != ' ':
        emit('invalid_move', {'message': 'Cell already taken'})
        return

    # Apply move
    game['board'][r][c] = player
    game['last_move_time'] = time.time()
    
    # Add to move history
    move_record = {
        'player': player,
        'row': r,
        'col': c,
        'timestamp': time.time()
    }
    game['move_history'].append(move_record)
    
    # Check for winner
    winner, winning_cells = check_winner(game['board'])
    
    if winner:
        game['winner'] = winner
        game['winning_cells'] = winning_cells
        if winner != 'Tie':
            game['scores'][winner] += 1
            
            # Update player stats
            winner_name = game['player_names'].get(winner, f'Player {winner}')
            loser_name = game['player_names'].get('O' if winner == 'X' else 'X', f'Player {'O' if winner == 'X' else 'X'}')
            
            # This would be more robust with a proper database
            player_stats[winner_name]['wins'] += 1
            player_stats[winner_name]['games_played'] += 1
            player_stats[loser_name]['losses'] += 1
            player_stats[loser_name]['games_played'] += 1
        else:
            # Update tie stats
            x_name = game['player_names'].get('X', 'Player X')
            o_name = game['player_names'].get('O', 'Player O')
            player_stats[x_name]['ties'] += 1
            player_stats[x_name]['games_played'] += 1
            player_stats[o_name]['ties'] += 1
            player_stats[o_name]['games_played'] += 1
    else:
        game['current_player'] = 'O' if player == 'X' else 'X'
    
    # Update time controls if applicable
    if game.get('time_controls'):
        move_time = time.time() - game['last_move_time']
        game['time_controls']['remaining'][player] = max(0, game['time_controls']['remaining'][player] - move_time)
        
        # Check for time forfeit
        if game['time_controls']['remaining'][player] <= 0:
            game['winner'] = 'O' if player == 'X' else 'X'
            game['scores'][game['winner']] += 1
    
    # Broadcast updated game to everyone in the room
    emit('game_update', _pack_game(game), room=game_id)

@socketio.on('send_chat')
def handle_send_chat(data):
    game_id = data.get('game_id')
    player = data.get('player')
    player_name = data.get('player_name', f'Player {player}')
    message = data.get('message').strip()
    
    if not message:
        return
    
    if game_id and game_id in games:
        # Store message (limit to 100 messages per game)
        chat_record = {
            'player': player,
            'player_name': player_name,
            'message': message,
            'timestamp': time.time()
        }
        chat_messages[game_id].append(chat_record)
        chat_messages[game_id] = chat_messages[game_id][-100:]
        
        # Broadcast to all in the room
        emit('chat_message', chat_record, room=game_id)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
