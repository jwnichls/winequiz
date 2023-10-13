"""
The methods for executing scoring.

These are not a blueprint and there are no related pages. These methods
are expected to be imported in other modules where needed
"""

import random
from operator import itemgetter

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


FREE_RESPONSE_CORRECT = 10
MULTIPLE_CHOICE_CORRECT = 5


def get_stats_for_item(quiz, item):
    """
    Calculate basic counting stats for all answers to this item
    """
    answers = Answer.query.filter_by(quiz_item_id=item.id).all()
    
    stats = {
        'free_response': {
            'grapes': {},
            'countries': {},
            'vintages': {},
        },
        'multiple_choice': {
            'grapes': {},
            'countries': {},
            'vintages': {},
        }
    }
    
    count_hash = stats
    for answer in answers:
        if answer.free_response:
            count_hash = stats['free_response']
        else:
            count_hash = stats['multiple_choice']
            
        count_hash['grapes'][answer.grape_id] = count_hash['grapes'].get(answer.grape_id, 0) + 1
        count_hash['countries'][answer.country_id] = count_hash['countries'].get(answer.country_id, 0) + 1
        count_hash['vintages'][answer.vintage] = count_hash['vintages'].get(answer.vintage, 0) + 1
    
    return stats


def calculate_points_for_answer(answer, item):
    """
    Calculate the points for a single answer based on its item
    """
    if answer.quiz_item_id != item.id:
        return 0
    
    correct_points = MULTIPLE_CHOICE_CORRECT
    if answer.free_response:
        correct_points = FREE_RESPONSE_CORRECT
    
    score = 0
    if answer.grape_id == item.grape_id:
        score += correct_points
    if answer.country_id == item.country_id:
        score += correct_points
    if answer.vintage == item.vintage:
        score += correct_points
        
    return score
    

def calculate_points_for_item(quiz, item):
    """
    Calculate the points for all competitors for a single quiz item
    """
    answers = Answer.query.filter_by(quiz_item_id=item.id).all()
    
    scores = {} # hash of competitor id: score
    for competitor in quiz.competitors:
        scores[competitor.id] = 0
        
        free_response_count = 0
        multiple_choice_count = 0
        for answer in answers:
            if answer.competitor_id == competitor.id:
                if answer.free_response and free_response_count == 0:
                    free_response_count += 1
                    scores[competitor.id] += calculate_points_for_answer(answer, item)
                elif not answer.free_response and multiple_choice_count == 0:
                    multiple_choice_count += 1
                    scores[competitor.id] += calculate_points_for_answer(answer, item)
    
    return scores


def sum_score_hashes(hash1, hash2):
    """
    Sum two score hashes together
    """
    all_keys = list(hash1.keys()) + list(hash2.keys())
    
    combined_hash = {}
    for key in all_keys:
        combined_hash[key] = 0
        
    for key in combined_hash.keys():
        combined_hash[key] = hash1.get(key, 0) + hash2.get(key, 0)
        
    return combined_hash


def calculate_total_points(quiz):
    """
    Calculate points for the entire quiz
    """
    db = get_db()
    
    overall_scores = {}
    for item in quiz.items:
        item_score_hash = calculate_points_for_item(quiz, item)
        overall_scores = sum_score_hashes(overall_scores, item_score_hash)
        
    for competitor in quiz.competitors:
        competitor.score = overall_scores.get(competitor.id, 0)
        db.session.add(competitor)
        
    db.session.commit()
    
    return overall_scores


def convert_to_competitor_hash(quiz, score_hash):
    """
    Converts the basic scoring array to one with competitor names 
    which is useful for displaying a leaderboard
    """
    return sorted([{
        'id': competitor.id,
        'name': competitor.name,
        'score': score_hash.get(competitor.id, 0),
    } for competitor in quiz.competitors], key=itemgetter('score'), reverse=True)
