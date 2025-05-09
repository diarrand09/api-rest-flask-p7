# app/routes/votes.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from app.utils.db import execute_query

bp = Blueprint('votes', __name__, url_prefix='/api/votes')

@bp.route('/<int:prompt_id>', methods=['POST'])
@jwt_required()
def vote_prompt(prompt_id):
    """
    Voter pour l'activation d'un prompt en état de Rappel
    """
    current_user_id = get_jwt_identity()
    
    # Vérifier si le prompt existe et est en état de Rappel
    check_query = """
    SELECT p.id_prompt, p.statut, p.id_createur 
    FROM prompt p
    WHERE p.id_prompt = %s
    """
    
    prompt = execute_query(check_query, (prompt_id,))
    
    if not prompt:
        return jsonify({"error": "Prompt non trouvé"}), 404
    
    if prompt[0]['statut'] != 'rappel':
        return jsonify({"error": "Ce prompt n'est pas en état de Rappel"}), 400
    
    # Vérifier si c'est le créateur du prompt
    if prompt[0]['id_createur'] == current_user_id:
        return jsonify({"error": "Vous ne pouvez pas voter pour votre propre prompt"}), 403
    
    # Vérifier si l'utilisateur a déjà voté
    check_vote_query = """
    SELECT id_vote FROM vote
    WHERE id_utilisateur = %s AND id_prompt = %s
    """
    
    existing_vote = execute_query(check_vote_query, (current_user_id, prompt_id))
    
    if existing_vote:
        return jsonify({"error": "Vous avez déjà voté pour ce prompt"}), 409
    
    # Enregistrer le vote
    vote_query = """
    INSERT INTO vote (id_utilisateur, id_prompt)
    VALUES (%s, %s)
    RETURNING id_vote
    """
    
    try:
        result = execute_query(vote_query, (current_user_id, prompt_id))
        
        # Vérifier si le nombre de points est suffisant pour activer le prompt
        points_query = """
        SELECT 
            SUM(CASE 
                    WHEN u1.id_groupe = u2.id_groupe AND u1.id_groupe IS NOT NULL THEN 2
                    ELSE 1
                END) AS total_points
        FROM vote v
        JOIN utilisateur u1 ON v.id_utilisateur = u1.id_utilisateur
        JOIN prompt p ON v.id_prompt = p.id_prompt
        JOIN utilisateur u2 ON p.id_createur = u2.id_utilisateur
        WHERE v.id_prompt = %s
        """
        
        points_result = execute_query(points_query, (prompt_id,))
        total_points = points_result[0]['total_points'] if points_result[0]['total_points'] else 0
        
        # Si 6 points ou plus, activer le prompt
        if total_points >= 6:
            update_query = """
            UPDATE prompt
            SET statut = 'activer', date_derniere_modification = CURRENT_TIMESTAMP
            WHERE id_prompt = %s
            RETURNING id_prompt, statut
            """
            
            update_result = execute_query(update_query, (prompt_id,))
            
            return jsonify({
                "message": "Vote enregistré avec succès. Le prompt a été activé.",
                "vote_id": result[0]['id_vote'],
                "total_points": total_points,
                "prompt": update_result[0]
            }), 200
        else:
            return jsonify({
                "message": "Vote enregistré avec succès",
                "vote_id": result[0]['id_vote'],
                "total_points": total_points,
                "points_needed": 6 - total_points
            }), 200
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

