# app/routes/prompts.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt
from app.utils.db import execute_query
import datetime

bp = Blueprint('prompts', __name__, url_prefix='/api/prompts')

@bp.route('/', methods=['POST'])
@jwt_required()
def create_prompt():
    """
    Créer un nouveau prompt (utilisateur connecté uniquement)
    """
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    # Valider les données
    if not data or not data.get('description'):
        return jsonify({"error": "Description du prompt requise"}), 400
    
    description = data['description']
    
    # Par défaut, le prompt est en attente de validation
    query = """
    INSERT INTO prompt (description, id_createur, statut)
    VALUES (%s, %s, 'en_attente')
    RETURNING id_prompt, description, prix, statut, date_creation
    """
    
    try:
        result = execute_query(query, (description, current_user_id))
        return jsonify({
            "message": "Prompt créé avec succès",
            "prompt": result[0]
        }), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/', methods=['GET'])
def get_prompts():
    """
    Récupérer la liste des prompts (filtrable par statut)
    """
    statut = request.args.get('statut', 'activer')  # Par défaut, on montre les prompts activés
    
    # Les utilisateurs non-admin ne peuvent voir que les prompts activés
    jwt_data = get_jwt() if request.headers.get('Authorization') else None
    
    if not jwt_data or jwt_data.get('role') != 'admin':
        statut = 'activer'  # Forcer l'affichage des prompts activés uniquement
    
    query = """
    SELECT p.id_prompt, p.description, p.prix, p.statut, p.date_creation,
           u.id_utilisateur, u.email as createur_email
    FROM prompt p
    JOIN utilisateur u ON p.id_createur = u.id_utilisateur
    WHERE p.statut = %s
    ORDER BY p.date_creation DESC
    """
    
    try:
        prompts = execute_query(query, (statut,))
        return jsonify(prompts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/<int:prompt_id>', methods=['GET'])
def get_prompt(prompt_id):
    """
    Récupérer les détails d'un prompt spécifique
    """
    query = """
    SELECT p.id_prompt, p.description, p.prix, p.statut, p.date_creation,
           u.id_utilisateur, u.email as createur_email
    FROM prompt p
    JOIN utilisateur u ON p.id_createur = u.id_utilisateur
    WHERE p.id_prompt = %s
    """
    
    try:
        result = execute_query(query, (prompt_id,))
        
        if not result:
            return jsonify({"error": "Prompt non trouvé"}), 404
        
        prompt = result[0]
        
        # Si le prompt n'est pas activé, seul l'admin ou le créateur peut le voir
        jwt_data = get_jwt() if request.headers.get('Authorization') else None
        current_user_id = get_jwt_identity() if jwt_data else None
        
        if prompt['statut'] != 'activer':
            if not jwt_data or (jwt_data.get('role') != 'admin' and current_user_id != prompt['id_utilisateur']):
                return jsonify({"error": "Accès non autorisé"}), 403
        
        # Récupérer également les notes moyennes si le prompt est activé
        if prompt['statut'] == 'activer':
            note_query = """
            SELECT COALESCE(
                SUM(
                    CASE 
                        WHEN u1.id_groupe = u2.id_groupe AND u1.id_groupe IS NOT NULL THEN n.valeur * 0.6
                        ELSE n.valeur * 0.4
                    END
                ) / COUNT(*), 0
            ) AS moyenne_ponderee,
            COUNT(n.id_note) AS nombre_notes
            FROM note n
            JOIN utilisateur u1 ON n.id_utilisateur = u1.id_utilisateur
            JOIN prompt p ON n.id_prompt = p.id_prompt
            JOIN utilisateur u2 ON p.id_createur = u2.id_utilisateur
            WHERE p.id_prompt = %s
            """
            note_result = execute_query(note_query, (prompt_id,))
            prompt['notation'] = note_result[0] if note_result else {"moyenne_ponderee": 0, "nombre_notes": 0}
        
        return jsonify(prompt), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/<int:prompt_id>', methods=['PUT'])
@jwt_required()
def update_prompt_status(prompt_id):
    """
    Mettre à jour le statut d'un prompt
    - Admin: peut changer à n'importe quel statut
    - Utilisateur: peut seulement demander la suppression de ses propres prompts
    """
    jwt_data = get_jwt()
    current_user_id = get_jwt_identity()
    data = request.get_json()
    
    if not data or not data.get('statut'):
        return jsonify({"error": "Statut du prompt requis"}), 400
    
    nouveau_statut = data['statut']
    
    # Valider le statut
    statuts_valides = ['en_attente', 'activer', 'a_revoir', 'rappel', 'a_supprimer']
    if nouveau_statut not in statuts_valides:
        return jsonify({"error": "Statut invalide"}), 400
    
    # Vérifier si le prompt existe et qui en est le créateur
    check_query = """
    SELECT id_prompt, id_createur, statut
    FROM prompt
    WHERE id_prompt = %s
    """
    
    prompt = execute_query(check_query, (prompt_id,))
    
    if not prompt:
        return jsonify({"error": "Prompt non trouvé"}), 404
    
    prompt = prompt[0]
    is_creator = prompt['id_createur'] == current_user_id
    
    # Appliquer les règles d'autorisation
    if jwt_data['role'] == 'admin':
        # L'admin peut tout faire
        pass
    elif is_creator:
        # Le créateur ne peut que demander la suppression
        if nouveau_statut != 'a_supprimer':
            return jsonify({"error": "Vous ne pouvez que demander la suppression de votre prompt"}), 403
    else:
        # Les autres utilisateurs n'ont pas le droit de modifier le statut
        return jsonify({"error": "Accès non autorisé"}), 403
    
    # Mettre à jour le statut
    query = """
    UPDATE prompt
    SET statut = %s, date_derniere_modification = %s
    WHERE id_prompt = %s
    RETURNING id_prompt, description, prix, statut, date_creation, date_derniere_modification
    """
    
    try:
        result = execute_query(query, (nouveau_statut, datetime.datetime.now(), prompt_id))
        return jsonify({
            "message": "Statut du prompt mis à jour avec succès",
            "prompt": result[0]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/search', methods=['GET'])
def search_prompts():
    """
    Rechercher des prompts par mots-clés
    """
    keyword = request.args.get('q', '')
    
    if not keyword:
        return jsonify({"error": "Mot-clé de recherche requis"}), 400
    
    # On ne recherche que dans les prompts activés
    query = """
    SELECT p.id_prompt, p.description, p.prix, p.date_creation,
           u.email as createur_email
    FROM prompt p
    JOIN utilisateur u ON p.id_createur = u.id_utilisateur
    WHERE p.statut = 'activer' AND p.description ILIKE %s
    ORDER BY p.date_creation DESC
    """
    
    try:
        prompts = execute_query(query, (f'%{keyword}%',))
        return jsonify(prompts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/admin/pending', methods=['GET'])
@jwt_required()
def get_pending_prompts():
    """
    Récupérer les prompts en attente de validation (admin uniquement)
    """
    jwt_data = get_jwt()
    if jwt_data['role'] != 'admin':
        return jsonify({"error": "Accès non autorisé"}), 403
    
    query = """
    SELECT p.id_prompt, p.description, p.statut, p.date_creation, 
           u.id_utilisateur, u.email as createur_email
    FROM prompt p
    JOIN utilisateur u ON p.id_createur = u.id_utilisateur
    WHERE p.statut IN ('en_attente', 'a_revoir', 'a_supprimer', 'rappel')
    ORDER BY 
        CASE 
            WHEN p.statut = 'a_supprimer' THEN 1
            WHEN p.statut = 'rappel' THEN 2
            WHEN p.statut = 'en_attente' THEN 3
            WHEN p.statut = 'a_revoir' THEN 4
        END,
        p.date_creation ASC
    """
    
    try:
        prompts = execute_query(query)
        return jsonify(prompts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/user', methods=['GET'])
@jwt_required()
def get_user_prompts():
    """
    Récupérer les prompts créés par l'utilisateur connecté
    """
    current_user_id = get_jwt_identity()
    
    query = """
    SELECT id_prompt, description, prix, statut, date_creation
    FROM prompt
    WHERE id_createur = %s
    ORDER BY date_creation DESC
    """
    
    try:
        prompts = execute_query(query, (current_user_id,))
        return jsonify(prompts), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/update-states', methods=['POST'])
@jwt_required()
def update_prompt_states():
    """
    Exécuter la vérification et mise à jour des états des prompts (admin uniquement)
    """
    jwt_data = get_jwt()
    if jwt_data['role'] != 'admin':
        return jsonify({"error": "Accès non autorisé"}), 403
    
    query = "SELECT verifier_etat_prompts()"
    
    try:
        execute_query(query, fetch=False)
        return jsonify({"message": "États des prompts mis à jour avec succès"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/<int:prompt_id>/activate-by-vote', methods=['POST'])
@jwt_required()
def activate_prompt_by_vote(prompt_id):
    """
    Activer un prompt par vote si le minimum de points est atteint
    """
    jwt_data = get_jwt()
    if jwt_data['role'] != 'admin':
        return jsonify({"error": "Accès non autorisé"}), 403
    
    # Vérifier si le prompt est en état "rappel"
    check_query = "SELECT statut FROM prompt WHERE id_prompt = %s"
    prompt = execute_query(check_query, (prompt_id,))
    
    if not prompt or prompt[0]['statut'] != 'rappel':
        return jsonify({"error": "Ce prompt ne peut pas être activé par vote"}), 400
    
    # Calculer les points de vote
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
    
    if total_points < 6:
        return jsonify({
            "error": "Le minimum de 6 points n'est pas atteint",
            "total_points": total_points
        }), 400
    
    # Activer le prompt
    update_query = """
    UPDATE prompt
    SET statut = 'activer', date_derniere_modification = %s
    WHERE id_prompt = %s
    RETURNING id_prompt, description, statut
    """
    
    try:
        result = execute_query(update_query, (datetime.datetime.now(), prompt_id))
        return jsonify({
            "message": "Prompt activé par vote avec succès",
            "prompt": result[0],
            "total_points": total_points
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500