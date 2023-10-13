"""
The main front page route.
"""

from flask import Blueprint, render_template, request
from werkzeug.exceptions import abort

from winequiz.db import get_db, Quiz, QuizItem, QuizStateEnum

bp = Blueprint("index", __name__)


@bp.route("/")
def index():
    """
    The main index route
    """
    active_quizes = Quiz.query.filter_by(state=QuizStateEnum.LOBBY_OPEN).all()
    
    return render_template("index/index.html", quizes=active_quizes)


@bp.route("/new", methods=["GET"])
def show_new_quiz_form():
    """
    Displays the form to create a new quiz
    """
    return render_template("index/new_quiz.html", quiz=None)


@bp.route("/new", methods=["POST"])
def submit_new_quiz():
    """
    Put a new quiz in the database from the form
    """
    # Parse form data into database objects and commit
    try:
        db = get_db()
        
        name = request.form["name"]
        moderator_code = request.form["moderator_code"]
        duration_free_response = request.form["duration_free_response"]
        duration_multiple_choice = request.form["duration_multiple_choice"]
        
        max_wine_count = 0
        keys = request.form.keys()
        for key in request.form.keys():
            if key.startswith('grape_'):
                idx = int(key[6:])
                if idx > max_wine_count:
                    max_wine_count = idx
        
        quiz = Quiz(
            name=name,
            moderator_code=moderator_code,
            duration_free_response=duration_free_response,
            duration_multiple_choice=duration_multiple_choice,
        )
        
        for i in range(1,max_wine_count+1):
            item = QuizItem(
                order=i,
                grape_id=request.form[f'grape_{i}'],
                country_id=request.form[f'country_{i}'],
                vintage=request.form[f'vintage_{i}'],
                grape_alternate_one=request.form[f'alt_grape_{i}_0'],
                grape_alternate_two=request.form[f'alt_grape_{i}_1'],
                grape_alternate_three=request.form[f'alt_grape_{i}_2'],
                country_alternate_one=request.form[f'alt_country_{i}_0'],
                country_alternate_two=request.form[f'alt_country_{i}_1'],
                country_alternate_three=request.form[f'alt_country_{i}_2'],
                vintage_alternate_one=request.form[f'alt_vintage_{i}_0'],
                vintage_alternate_two=request.form[f'alt_vintage_{i}_1'],
                vintage_alternate_three=request.form[f'alt_vintage_{i}_2'],
            )
            quiz.items.append(item)
            
        db.session.add(quiz)
        db.session.commit()
        db.session.refresh(quiz)

        # Show info about the created quiz
        return render_template("index/quiz_success.html", quiz=quiz)
        
    except ValueError:
        abort(500, "Input value error")
