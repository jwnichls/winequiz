"""
Collection of methods that use SocketIO to keep the
game in sync efficiently across multiple devices
"""

from flask_socketio import emit, join_room

from winequiz.db import get_db, Competitor, Quiz, QuizItem
from winequiz.quiz import advance_quiz_state, reverse_quiz_state, get_quiz_state

from . import socketio


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


@socketio.on('competitor_left')
def competitor_left(data):
    # leave_room()
    competitor_id = data['competitor_id']
    competitor = Competitor.query.filter_by(id=competitor_id).first()
    print(f"competitor left! {competitor_id}")
    if competitor is not None:
        quiz_id = competitor.quiz_id
        room_name = f'quiz{quiz_id}'
        emit('competitor_left', {'id': competitor_id, 'name': competitor.name}, room=room_name)


@socketio.on('who_is_here')
def who_is_here(data):
    emit('who_is_here', {}, room='quiz1')
