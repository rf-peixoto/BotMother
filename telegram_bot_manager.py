import os
import threading
import json
from flask import Flask, request, render_template, redirect, url_for, jsonify, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from telegram import Update, Bot
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext

app = Flask(__name__)
app.secret_key = 'supersecretkey'
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'
bots = {}

# User data - in a real application, this should be stored in a database
users = {
    'admin': generate_password_hash('password')
}

class BotManager:
    def __init__(self, token):
        self.token = token
        self.updater = Updater(token, use_context=True)
        self.dispatcher = self.updater.dispatcher
        self.commands = {}
        self.interactions = []

        # Add a handler to log all messages
        self.dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, self.log_interaction))

    def log_interaction(self, update: Update, context: CallbackContext):
        interaction = {
            'username': update.message.from_user.username,
            'user_id': update.message.from_user.id,
            'message': update.message.text
        }
        self.interactions.append(interaction)

    def add_command(self, command, response):
        if not command.isidentifier() or not command.islower() or ' ' in command:
            raise ValueError('Command is not a valid bot command')
        
        def command_callback(update: Update, context: CallbackContext):
            update.message.reply_text(response)
        
        self.commands[command] = response
        self.dispatcher.add_handler(CommandHandler(command, command_callback))

    def edit_command(self, command, new_response):
        self.commands[command] = new_response
        self.dispatcher.remove_handler(CommandHandler(command))
        self.add_command(command, new_response)

    def delete_command(self, command):
        if command in self.commands:
            del self.commands[command]
            self.dispatcher.remove_handler(CommandHandler(command))

    def start(self):
        self.updater.start_polling()

    def stop(self):
        self.updater.stop()

    def export_config(self):
        return {
            'token': self.token,
            'commands': self.commands,
            'interactions': self.interactions
        }

    @classmethod
    def import_config(cls, config):
        bot_manager = cls(config['token'])
        for command, response in config['commands'].items():
            bot_manager.add_command(command, response)
        bot_manager.interactions = config['interactions']
        return bot_manager

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    if user_id in users:
        return User(id=user_id)
    return None

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in users and check_password_hash(users[username], password):
            user = User(id=username)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid credentials')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    return render_template('index.html', bots=bots, get_analytics=get_analytics)

@app.route('/create_bot', methods=['POST'])
@login_required
def create_bot():
    token = request.form['token']
    bot_name = request.form['bot_name']
    bots[bot_name] = BotManager(token)
    return redirect(url_for('index'))

@app.route('/add_command/<bot_name>', methods=['POST'])
@login_required
def add_command(bot_name):
    command = request.form['command']
    response = request.form['response']
    try:
        bots[bot_name].add_command(command, response)
    except ValueError as e:
        flash(str(e))
    return redirect(url_for('index'))

@app.route('/edit_command/<bot_name>/<command>', methods=['POST'])
@login_required
def edit_command(bot_name, command):
    new_response = request.form['new_response']
    bots[bot_name].edit_command(command, new_response)
    return redirect(url_for('index'))

@app.route('/delete_command/<bot_name>/<command>', methods=['POST'])
@login_required
def delete_command(bot_name, command):
    bots[bot_name].delete_command(command)
    return redirect(url_for('index'))

@app.route('/start_bot/<bot_name>', methods=['POST'])
@login_required
def start_bot(bot_name):
    threading.Thread(target=bots[bot_name].start).start()
    return redirect(url_for('index'))

@app.route('/stop_bot/<bot_name>', methods=['POST'])
@login_required
def stop_bot(bot_name):
    bots[bot_name].stop()
    return redirect(url_for('index'))

@app.route('/export_bot/<bot_name>', methods=['GET'])
@login_required
def export_bot(bot_name):
    bot_config = bots[bot_name].export_config()
    response = jsonify(bot_config)
    response.headers['Content-Disposition'] = f'attachment; filename={bot_name}.json'
    return response

@app.route('/import_bot', methods=['POST'])
@login_required
def import_bot():
    file = request.files['bot_config']
    bot_config = json.load(file)
    bot_name = request.form['bot_name']
    bots[bot_name] = BotManager.import_config(bot_config)
    return redirect(url_for('index'))

@app.route('/export_interactions/<bot_name>', methods=['GET'])
@login_required
def export_interactions(bot_name):
    interactions = bots[bot_name].interactions
    response = jsonify(interactions)
    response.headers['Content-Disposition'] = f'attachment; filename={bot_name}_interactions.json'
    return response

def get_analytics(bot):
    interaction_count = len(bot.interactions)
    command_usage = {}
    for interaction in bot.interactions:
        if interaction['message'] in bot.commands:
            command_usage[interaction['message']] = command_usage.get(interaction['message'], 0) + 1
    return {
        'interaction_count': interaction_count,
        'most_used_command': max(command_usage, key=command_usage.get) if command_usage else 'N/A'
    }

if __name__ == '__main__':
    app.run(debug=True)
