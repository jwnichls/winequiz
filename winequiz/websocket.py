"""
Collection of methods that use SocketIO to keep the
game in sync efficiently across multiple devices
"""

from flask_socketio import emit

from . import socketio


# default values for sliders
values = {
    'slider1': 25,
    'slider2': 0,
}

@socketio.on('connect')
def on_connect():
    emit('after_connect', {'data': 'Connected!'})
    for slider_id, val in values.items():
        emit('update_value', {
            'who': slider_id,
            'data': val,
        })


@socketio.on('value_changed')
def value_changed(message):
    values[message['who']] = message['data']
    emit('update_value', message, broadcast=True)
