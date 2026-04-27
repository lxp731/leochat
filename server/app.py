# client_cli.py
from flask import Flask, render_template
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app)

@app.route('/')
def index():
    return render_template('index.html')

@socketio.on('connect')
def handle_connect():
    print('Client connected')
    emit('message', {'user': 'System', 'text': 'A new user has joined the chat.'})

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')
    emit('message', {'user': 'System', 'text': 'A user has left the chat.'})

@socketio.on('send_message')
def handle_message(data):
    print(f"Received message: {data}")
    emit('message', data, broadcast=True)

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
