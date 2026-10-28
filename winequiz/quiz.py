"""
The quiz pages
"""

from operator import attrgetter
import random

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_socketio import emit
from werkzeug.exceptions import abort

from winequiz.db import (
    get_db, 
    Answer,
    Competitor, 
    Country, 
    Grape, 
    Quiz, 
    QuizItem, 
    QuizStateEnum
)
from winequiz.scoring import (
    calculate_points_for_item, 
    calculate_total_points,
    convert_to_competitor_hash,
    get_stats_for_item,
    FREE_RESPONSE_CORRECT,
    MULTIPLE_CHOICE_CORRECT,
)

from . import socketio

random.seed()

bp = Blueprint("quiz", __name__, url_prefix="/quiz")


WINE_QUIZ_COOKIE_NAME = 'WineQuizCompetitorCookie'


def advance_quiz_state(quiz):
    """
    Advances the quiz to the next state
    """
    # This method is key to the operation of the entire game
    # It sends the current state and any relevant data when the state changes
    # This data is in turn used to display the current screen for players, the moderator and displays
    db = get_db()
    
    if quiz.state == QuizStateEnum.NOT_STARTED:
        quiz.state = QuizStateEnum.LOBBY_OPEN
    elif quiz.state == QuizStateEnum.LOBBY_OPEN:
        quiz.current_item = 0
        if len(quiz.items) == 0:
            quiz.state = QuizStateEnum.QUIZ_RECAP
        else:
            quiz.state = QuizStateEnum.FREE_RESPONSE
    elif quiz.state == QuizStateEnum.FREE_RESPONSE:
        quiz.state = QuizStateEnum.MULTIPLE_CHOICE
    elif quiz.state == QuizStateEnum.MULTIPLE_CHOICE:
        quiz.state = QuizStateEnum.QUESTION_RECAP
    elif quiz.state == QuizStateEnum.QUESTION_RECAP:
        quiz.current_item = quiz.current_item + 1
        if quiz.current_item >= len(quiz.items):
            quiz.state = QuizStateEnum.QUIZ_RECAP
        else:
            quiz.state = QuizStateEnum.FREE_RESPONSE
    elif quiz.state == QuizStateEnum.QUIZ_RECAP:
        # Nothing to do in this case
        pass

    db.session.add(quiz)
    db.session.commit()
    db.session.refresh(quiz)

    room_name = f"quiz{quiz.id}"

    json_state = get_quiz_state(quiz)
    emit("quiz_state_changed", json_state, room=room_name)
    
    
def reverse_quiz_state(quiz):
    """
    Returns to the previous quiz state (only happens due to moderator)
    """
    db = get_db()
    
    # Same as above, but in reverse
    if quiz.state == QuizStateEnum.NOT_STARTED:
        # Nothing to do in this case
        pass
    elif quiz.state == QuizStateEnum.LOBBY_OPEN:
        quiz.state = QuizStateEnum.NOT_STARTED
    elif quiz.state == QuizStateEnum.FREE_RESPONSE:
        quiz.current_item = quiz.current_item - 1
        if quiz.current_item < 0:
            quiz.current_item = 0
            quiz.state = QuizStateEnum.LOBBY_OPEN
        else:
            quiz.state = QuizStateEnum.QUESTION_RECAP
    elif quiz.state == QuizStateEnum.MULTIPLE_CHOICE:
        quiz.state = QuizStateEnum.FREE_RESPONSE
    elif quiz.state == QuizStateEnum.QUESTION_RECAP:
        quiz.state = QuizStateEnum.MULTIPLE_CHOICE
    elif quiz.state == QuizStateEnum.QUIZ_RECAP:
        if len(quiz.items) == 0:
            quiz.state = QuizStateEnum.LOBBY_OPEN
            quiz.current_item = 0
        else:
            quiz.state = QuizStateEnum.QUESTION_RECAP
            quiz.current_item = len(quiz.items)-1

    db.session.add(quiz)
    db.session.commit()
    db.session.refresh(quiz)

    room_name = f"quiz{quiz.id}"

    json_state = get_quiz_state(quiz)
    emit("quiz_state_changed", json_state, room=room_name)
    
    
def get_quiz_state(quiz):
    """
    Gets the current quiz state in a JSON format suitable for sending via socket or web request
    """
    json_data = {
        'id': quiz.id,
        'name': quiz.name,
        'state': quiz.state,
        'state_string': str(quiz.state),
    }
    
    if quiz.state == QuizStateEnum.FREE_RESPONSE:
        # send grape color
        grape = Grape.query.filter_by(id=quiz.items[quiz.current_item].grape_id).first()
        json_data['grape_color'] = grape.color
    elif quiz.state == QuizStateEnum.MULTIPLE_CHOICE:
        item = quiz.items[quiz.current_item]
        grapes = [item.grape_id, item.grape_alternate_one, item.grape_alternate_two, item.grape_alternate_three]
        countries = [item.country_id, item.country_alternate_one, item.country_alternate_two, item.country_alternate_three]
        vintages = [item.vintage, item.vintage_alternate_one, item.vintage_alternate_two, item.vintage_alternate_three]
        grapes.sort()
        countries.sort()
        vintages.sort()
        json_data['grapes'] = grapes
        json_data['countries'] = countries
        json_data['vintages'] = vintages
    elif quiz.state == QuizStateEnum.QUESTION_RECAP:
        item = quiz.items[quiz.current_item]
        json_data['correct_grape'] = item.grape_id
        json_data['correct_country'] = item.country_id
        json_data['correct_vintage'] = item.vintage
        json_data['scores'] = convert_to_competitor_hash(
            quiz, 
            calculate_points_for_item(quiz, item),
        )
        json_data['stats'] = get_stats_for_item(quiz, item)
    elif quiz.state == QuizStateEnum.QUIZ_RECAP:
        json_data['final_scores'] = convert_to_competitor_hash(
            quiz, 
            calculate_total_points(quiz),
        )
    
    return json_data


@bp.route("/<int:id>", methods=["GET"])
def show_quiz(id):
    """
    Show basic quiz data
    """
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'Quiz does not exist')
    
    return render_template("quiz/index.html", quiz=quiz)


@bp.route("/<int:id>/join", methods=["GET"])
def join_quiz(id):
    """
    Show the interface to join the quiz
    """
    competitor_id = request.cookies.get(WINE_QUIZ_COOKIE_NAME, type=int)
    if competitor_id is not None:
        competitor = Competitor.query.filter_by(id=competitor_id).first()
        if competitor is not None and competitor.quiz_id == id:
            return redirect(url_for('quiz.start_player', id=id))
    
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'Quiz does not exist')
    
    return render_template("quiz/join.html", quiz=quiz)


def check_name(quiz, proposed_name):
    """
    The name check used by several methods
    """
    if proposed_name is not None:
        competitor = Competitor.query.filter_by(quiz_id=quiz.id, name=proposed_name).first()
        return (competitor is None)
        
    return False
    

@bp.route("/<int:id>/checkname", methods=["POST"])
def check_player_name(id):
    """
    Check whether a name is in use
    """
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'Quiz does not exist')
    
    if not request.is_json:
        abort(415, 'Expected a JSON request')
        
    json_data = request.get_json()
    proposed_name = json_data.get("name")
    
    return {'success': True, 'valid': check_name(quiz, proposed_name)}


@bp.route("/<int:id>/createplayer", methods=["POST"])
def create_player(id):
    """
    Create a player for this account, using the provided name
    """
    db = get_db()
    
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'Quiz does not exist')
    proposed_name = request.form.get("competitor_name")

    if not check_name(quiz, proposed_name):
        flash('Player name is already used...sorry!')
        return redirect(url_for('quiz.join_quiz', id=id))
        
    # Create the competitor and set cookie
    competitor = Competitor(quiz_id=id, name=proposed_name)
    db.session.add(competitor)
    db.session.commit()
    db.session.refresh(competitor)
    
    response = redirect(url_for('quiz.start_player', id=id))
    response.set_cookie(WINE_QUIZ_COOKIE_NAME, str(competitor.id))
    return response


@bp.route("/<int:id>/display", methods=["GET"])
def start_display(id):
    """
    Show the large display interface for a quiz
    """
    quiz = Quiz.query.filter_by(id=id).first()    
    if quiz is None:
        abort(404, 'Quiz does not exist')
    
    return render_template("quiz/display.html", quiz=quiz)


@bp.route("/<int:id>/player", methods=["GET"])
def start_player(id):
    """
    Show the interface to join the quiz
    """
    competitor_id = request.cookies.get(WINE_QUIZ_COOKIE_NAME, type=int)
    if competitor_id is None:
        return redirect(url_for('quiz.join_quiz', id=id))
    
    competitor = Competitor.query.filter_by(id=competitor_id).first()
    if competitor is None or competitor.quiz_id != id:
        return redirect(url_for('quiz.join_quiz', id=id))

    quiz = Quiz.query.filter_by(id=id).first()    
    
    return render_template("quiz/player.html", quiz=quiz, competitor=competitor)


def submit_answer(competitor, quiz, json_data, free_response=True):
    """
    Submit answer to any type of question
    """
    db = get_db()
    
    grape_id = json_data.get('grape')
    country_id = json_data.get('country')
    vintage = json_data.get('vintage')

    item = quiz.items[quiz.current_item]
    answer = Answer.query.filter_by(
        competitor_id=competitor.id,
        quiz_id=quiz.id,
        quiz_item_id=item.id,
        free_response=free_response,
    ).first()
    if answer is None:
        answer = Answer(
            quiz_id=quiz.id,
            quiz_item_id=item.id,
            competitor_id=competitor.id,
            free_response=free_response,
            grape_id=grape_id,
            country_id=country_id,
            vintage=vintage,
        )
    else:
        answer.grape_id = grape_id
        answer.country_id = country_id
        answer.vintage = vintage
    
    db.session.add(answer)
    db.session.commit()
    
    if grape_id is not None and country_id is not None and vintage is not None:
        socketio.emit('full_answer_received', {'id': competitor.id, 'name': competitor.name}, room=f'quiz{quiz.id}')
    
    return {'success': True}


@bp.route("/<int:id>/submit_free_response", methods=["POST"])
def submit_free_response(id):
    """
    Submit free response answer
    """    
    competitor_id = request.cookies.get(WINE_QUIZ_COOKIE_NAME, type=int)
    if competitor_id is None:
        abort(403, 'Not a competitor')
    
    competitor = Competitor.query.filter_by(id=competitor_id).first()
    if competitor is None or competitor.quiz_id != id:
        abort(403, 'Not a competitor in this quiz')

    quiz = Quiz.query.filter_by(id=id).first()
    
    if not request.is_json:
        abort(415, 'Expected a JSON request')
        
    if quiz.state != QuizStateEnum.FREE_RESPONSE:
        abort(409, 'Free response answers are closed')

    json_data = request.get_json()
    return submit_answer(competitor, quiz, json_data, free_response=True)
    


@bp.route("/<int:id>/submit_multiple_choice", methods=["POST"])
def submit_multiple_choice(id):
    """
    Submit multiple choice answer
    """
    competitor_id = request.cookies.get(WINE_QUIZ_COOKIE_NAME, type=int)
    if competitor_id is None:
        abort(403, 'Not a competitor')
    
    competitor = Competitor.query.filter_by(id=competitor_id).first()
    if competitor is None or competitor.quiz_id != id:
        abort(403, 'Not a competitor in this quiz')

    quiz = Quiz.query.filter_by(id=id).first()
    
    if not request.is_json:
        abort(415, 'Expected a JSON request')
        
    if quiz.state != QuizStateEnum.MULTIPLE_CHOICE:
        abort(409, 'Multiple choice answers are closed')

    json_data = request.get_json()
    return submit_answer(competitor, quiz, json_data, free_response=False)


@bp.route("/<int:id>/answer", methods=["GET"])
def get_answer(id):
    """
    Return the values from an answer for this competitor, if one exists
    """
    competitor_id = request.cookies.get(WINE_QUIZ_COOKIE_NAME, type=int)
    if competitor_id is None:
        abort(403, 'Not a competitor')
    
    competitor = Competitor.query.filter_by(id=competitor_id).first()
    if competitor is None or competitor.quiz_id != id:
        abort(403, 'Not a competitor in this quiz')

    quiz = Quiz.query.filter_by(id=id).first()
    if quiz.state != QuizStateEnum.FREE_RESPONSE and quiz.state != QuizStateEnum.MULTIPLE_CHOICE:
        abort(409, 'Answer can only be returned in an answering phase')

    item = quiz.items[quiz.current_item]
    answer = Answer.query.filter_by(
        competitor_id=competitor.id,
        quiz_id=quiz.id,
        quiz_item_id=item.id,
        free_response=(quiz.state == QuizStateEnum.FREE_RESPONSE),
    ).first()
    
    if answer is None:
        return {'success': True}
        
    return {'success': True, 'answer': answer.as_dict()}        
    

@bp.route("/<int:id>/join_as_mod", methods=["GET"])
def join_as_moderator(id):
    """
    Display the page that allows joining as a moderator
    """
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'Quiz does not exist')
    return render_template("quiz/join_as_mod.html", quiz=quiz)


@bp.route("/<int:id>/moderator", methods=["GET", "POST"])
def start_moderator(id):
    """
    Show the screen to display moderator interface
    """
    supplied_code = request.form.get('moderator_code', request.args.get('modcode'))
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'Quiz does not exist')
    if supplied_code is None or quiz.moderator_code != supplied_code:
        abort(401, 'Unauthorized')
    
    return render_template("quiz/moderator.html", quiz=quiz)


@bp.route("/<int:id>/leaderboard", methods=["GET"])
def show_leaderboard(id):
    """
    Show the leaderboard
    """
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'Quiz does not exist')

    leaders = sorted(quiz.competitors, key=attrgetter('points'), reverse=True)
    
    return render_template("quiz/leaderboard.html", quiz=quiz, competitors=leaders)


@bp.route("/<int:id>/merge/<int:c_dup_id>/to/<int:c_main_id>", methods=["GET"])
def merge_competitors(id, c_dup_id, c_main_id):
    """
    Show the leaderboard
    """
    db = get_db()
    
    quiz = Quiz.query.filter_by(id=id).first()
    main_competitor = Competitor.query.filter_by(id=c_main_id).first()
    merging_competitor = Competitor.query.filter_by(id=c_dup_id).first()
    
    if quiz is None or main_competitor is None or merging_competitor is None:
        abort(404, 'Quiz or competitors do not exist')
    if main_competitor.quiz_id != quiz.id or merging_competitor.quiz_id != quiz.id:
        abort(404, 'Competitors are not in this quiz')
    if main_competitor.id == merging_competitor.id:
        abort(400, 'Cannot merge a competitor into itself')
    
    answers_to_merge = Answer.query.filter_by(competitor_id=c_dup_id).all()
    for answer in answers_to_merge:
        answer.competitor_id = main_competitor.id
        db.session.add(answer)
    
    db.session.delete(merging_competitor)
    db.session.commit()
    
    return redirect(url_for('quiz.show_leaderboard', id=quiz.id))


@bp.route("/<int:id>/rescore", methods=["GET"])
def rescore(id):
    """
    Rescore the quiz
    """
    quiz = Quiz.query.filter_by(id=id).first()
    if quiz is None:
        abort(404, 'No such quiz')
        
    calculate_total_points(quiz)
    
    return redirect(url_for('quiz.show_leaderboard', id=quiz.id))
    

@bp.route("/<int:id>/competitor/<int:cid>/breakdown", methods=["GET"])
def show_breakdown(id, cid):
    """
    Show the leaderboard
    """
    quiz = Quiz.query.filter_by(id=id).first()
    competitor = Competitor.query.filter_by(id=cid).first()
    
    if quiz is None or competitor is None:
        abort(404, 'Quiz or competitor does not exist')
    
    answers = Answer.query.filter_by(quiz_id=quiz.id, competitor_id=competitor.id).all()
    
    wines = []
    wine_counter = 1
    for item in quiz.items:
        wine = {
            'wine_idx': wine_counter,
            'item_id': item.id,
            'grape_id': item.grape_id,
            'country_id': item.country_id,
            'vintage': item.vintage,
            'grape_points': 0,
            'country_points': 0,
            'vintage_points': 0,
        }
        wine_counter += 1

        for answer in answers:
            if answer.quiz_item_id == item.id:
                if answer.free_response == True:
                    wine['fr_grape_id'] = answer.grape_id
                    if item.grape_id == answer.grape_id:
                        wine['grape_points'] += FREE_RESPONSE_CORRECT
                    wine['fr_country_id'] = answer.country_id
                    if item.country_id == answer.country_id:
                        wine['country_points'] += FREE_RESPONSE_CORRECT
                    wine['fr_vintage'] = answer.vintage
                    if item.vintage == answer.vintage:
                        wine['vintage_points'] += FREE_RESPONSE_CORRECT
                else:
                    wine['mr_grape_id'] = answer.grape_id
                    if item.grape_id == answer.grape_id:
                        wine['grape_points'] += MULTIPLE_CHOICE_CORRECT
                    wine['mr_country_id'] = answer.country_id
                    if item.country_id == answer.country_id:
                        wine['country_points'] += MULTIPLE_CHOICE_CORRECT
                    wine['mr_vintage'] = answer.vintage
                    if item.vintage == answer.vintage:
                        wine['vintage_points'] += MULTIPLE_CHOICE_CORRECT
                    
        wines.append(wine)

    
    return render_template("quiz/breakdown.html", quiz=quiz, competitor=competitor, wines=wines)


@bp.route("/<int:id>/answer/<int:aid>/stats", methods=["GET"])
def show_answer_stats(id, aid):
    """
    Display stats for an individual answer
    """
    quiz = Quiz.query.filter_by(id=id).first()
    quiz_item = QuizItem.query.filter_by(id=aid).first()
    
    if quiz is None or quiz_item is None or quiz_item.quiz_id != quiz.id:
        abort(404, 'No such quiz or answer')
    
    stats = get_stats_for_item(quiz, quiz_item)
    
    return render_template("quiz/answerstats.html", quiz=quiz, item=quiz_item, stats=stats)


@bp.route("/<int:id>/competitors", methods=["GET"])
def get_competitors(id):
    """
    Return JSON of current competitor information
    """
    quiz = Quiz.query.filter_by(id=id).first()
    
    if quiz is None:
        abort(404, 'No such quiz')

    answers = None
    if quiz.state == QuizStateEnum.FREE_RESPONSE or quiz.state == QuizStateEnum.MULTIPLE_CHOICE:
        answers = Answer.query.filter_by(
            quiz_id=quiz.id, 
            quiz_item_id=quiz.items[quiz.current_item].id,
            free_response=(quiz.state == QuizStateEnum.FREE_RESPONSE)
        ).all()
    
    return_value = []
    for competitor in quiz.competitors:
        competitor_data = {
            'id': competitor.id,
            'name': competitor.name,
            'answered': False,
        }
        
        if answers is not None:
            for answer in answers:
                if answer.competitor_id == competitor.id:
                    competitor_data['answered'] = (
                        answer.grape_id is not None and 
                        answer.country_id is not None and 
                        answer.vintage is not None
                    )
        
        return_value.append(competitor_data)
        
    return {'success': True, 'competitors': return_value}


@bp.route("/killcookie", methods=["GET"])
def kill_cookie():
    """
    Debug feature to remove the wine quiz cookie
    """
    response = redirect(url_for('index.index'))
    response.delete_cookie(WINE_QUIZ_COOKIE_NAME)
    return response
