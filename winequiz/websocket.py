"""
Collection of methods that use SocketIO to keep the
game in sync efficiently across multiple devices
"""

from collections import defaultdict

from flask import request, session
from flask_socketio import emit, join_room

from winequiz.db import get_db, Competitor, Quiz, QuizItem
from winequiz.quiz import advance_quiz_state, reverse_quiz_state, get_quiz_state

from . import socketio


# The socket ids each competitor has joined with, so we can tell when their
# last connection goes away. This is per process, which is fine as long as
# the app runs a single worker (see Procfile).
competitor_sockets = defaultdict(set)


@socketio.on('connect')
def on_connect():
    emit('after_connect', {'data': 'Connected!'})


@socketio.on('join')
def on_join(data):
    room_name = data['room']
    competitor_id = data['competitor']
    if room_name.startswith('quiz'):
        quiz_id = int(room_name[4:])
        quiz = Quiz.query.filter_by(id=quiz_id).first()

        competitor = None
        if competitor_id > 0:
            competitor = Competitor.query.filter_by(id=competitor_id).first()
        
        if quiz is not None and (competitor is None or competitor.quiz_id == quiz.id):
            join_room(room_name)
            json_data = get_quiz_state(quiz)
            emit('quiz_state_changed', json_data, room=room_name)
            
            if competitor is not None:
                session['competitor_id'] = competitor.id
                competitor_sockets[competitor.id].add(request.sid)
                emit('competitor_joined', {'id': competitor.id, 'name': competitor.name}, room=room_name)
        else:
            print("Not allowing user to join")


@socketio.on('advance_quiz_state')
def next_state(data, room_name):
    if room_name.startswith('quiz'):
        quiz_id = int(room_name[4:])
        quiz = Quiz.query.filter_by(id=quiz_id).first()
        moderator_code = data['moderator_code']
        
        if quiz is not None and moderator_code == quiz.moderator_code:
            advance_quiz_state(quiz)


@socketio.on('reverse_quiz_state')
def previous_state(data, room_name):
    if room_name.startswith('quiz'):
        quiz_id = int(room_name[4:])
        quiz = Quiz.query.filter_by(id=quiz_id).first()
        moderator_code = data['moderator_code']
        
        if quiz is not None and moderator_code == quiz.moderator_code:
            reverse_quiz_state(quiz)


def announce_competitor_left(competitor_id):
    competitor = Competitor.query.filter_by(id=competitor_id).first()
    if competitor is not None:
        quiz_id = competitor.quiz_id
        room_name = f'quiz{quiz_id}'
        emit('competitor_left', {'id': competitor_id, 'name': competitor.name}, room=room_name)


@socketio.on('disconnect')
def on_disconnect(reason=None):
    competitor_id = session.get('competitor_id')
    if competitor_id is None:
        return

    sockets = competitor_sockets[competitor_id]
    sockets.discard(request.sid)
    if not sockets:
        del competitor_sockets[competitor_id]
        announce_competitor_left(competitor_id)


@socketio.on('competitor_left')
def competitor_left(data, room_name=None):
    announce_competitor_left(data['competitor_id'])


@socketio.on('who_is_here')
def who_is_here(data):
    emit('who_is_here', {}, room='quiz1')
