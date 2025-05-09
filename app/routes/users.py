# app/routes/users.py
from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity, get_jwt, create_access_token
from app.utils.db import execute_query
from app.utils.auth import authenticate_user, hash_password

bp = Blueprint('users', __name__, url_prefix='/api/users')

@bp.route('/register', methods=['POST'])
@jwt_required()
def register():
    """
    Création d'un nouvel utilisateur (admin uniquement)
    """
    # Vérifier que l'utilisateur est un administrateur
    jwt_data = get_jwt()
    if jwt_data['role'] != 'admin':
        return jsonify({"error": "Accès non autorisé"}), 403
    
    data = request.get_json()
    
    # Valider les données
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Données incomplètes"}), 400
    
    email = data['email']
    password = data['password']
    role = data.get('role', 'user')  # Par défaut, le rôle est 'user'
    id_groupe = data.get('id_groupe')  # Optionnel

    # Vérifier si l'utilisateur existe déjà
    check_query = "SELECT id_utilisateur FROM utilisateur WHERE email = %s"
    existing_user = execute_query(check_query, (email,))
    
    if existing_user:
        return jsonify({"error": "Cet email est déjà utilisé"}), 409
    
    # Valider le rôle
    if role not in ['admin', 'user']:
        return jsonify({"error": "Rôle invalide"}), 400
    
    # Hacher le mot de passe
    hashed_password = hash_password(password)
    
    # Créer l'utilisateur dans la base de données
    if id_groupe is not None:
        query = """
        INSERT INTO utilisateur (email, password, role, id_groupe)
        VALUES (%s, %s, %s, %s)
        RETURNING id_utilisateur
        """
        params = (email, hashed_password, role, id_groupe)
    else:
        query = """
        INSERT INTO utilisateur (email, password, role)
        VALUES (%s, %s, %s)
        RETURNING id_utilisateur
        """
        params = (email, hashed_password, role)
    
    try:
        result = execute_query(query, params)
        new_user_id = result[0]['id_utilisateur']
        
        return jsonify({
            "message": "Utilisateur créé avec succès",
            "id": new_user_id,
            "email": email,
            "role": role
        }), 201
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/login', methods=['POST'])
def login():
    """
    Authentification d'un utilisateur et génération du token JWT
    """
    data = request.get_json()
    
    if not data or not data.get('email') or not data.get('password'):
        return jsonify({"error": "Email et mot de passe requis"}), 400
    
    user_data = authenticate_user(data['email'], data['password'])
    
    if not user_data:
        return jsonify({"error": "Email ou mot de passe incorrect"}), 401
    
    return jsonify(user_data), 200

@bp.route('/', methods=['GET'])
@jwt_required()
def get_users():
    """
    Récupérer la liste des utilisateurs (admin uniquement)
    """
    jwt_data = get_jwt()
    if jwt_data['role'] != 'admin':
        return jsonify({"error": "Accès non autorisé"}), 403
    
    query = """
    SELECT u.id_utilisateur, u.email, u.role, g.id_groupe, g.nom_groupe
    FROM utilisateur u
    LEFT JOIN groupe g ON u.id_groupe = g.id_groupe
    ORDER BY u.id_utilisateur
    """
    
    try:
        users = execute_query(query)
        return jsonify(users), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/<int:user_id>', methods=['GET'])
@jwt_required()
def get_user(user_id):
    """
    Récupérer les informations d'un utilisateur spécifique
    """
    jwt_data = get_jwt()
    current_user_id = get_jwt_identity()
    
    # Seul l'admin ou l'utilisateur lui-même peut voir ses informations
    if jwt_data['role'] != 'admin' and current_user_id != user_id:
        return jsonify({"error": "Accès non autorisé"}), 403
    
    query = """
    SELECT u.id_utilisateur, u.email, u.role, g.id_groupe, g.nom_groupe
    FROM utilisateur u
    LEFT JOIN groupe g ON u.id_groupe = g.id_groupe
    WHERE u.id_utilisateur = %s
    """
    
    try:
        user = execute_query(query, (user_id,))
        
        if not user:
            return jsonify({"error": "Utilisateur non trouvé"}), 404
        
        return jsonify(user[0]), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/<int:user_id>', methods=['PUT'])
@jwt_required()
def update_user(user_id):
    """
    Mettre à jour les informations d'un utilisateur
    """
    jwt_data = get_jwt()
    current_user_id = get_jwt_identity()
    
    # Seul l'admin ou l'utilisateur lui-même peut modifier ses informations
    if jwt_data['role'] != 'admin' and current_user_id != user_id:
        return jsonify({"error": "Accès non autorisé"}), 403
    
    data = request.get_json()
    
    if not data:
        return jsonify({"error": "Aucune donnée fournie"}), 400
    
    # Vérifier si l'utilisateur existe
    check_query = "SELECT id_utilisateur, role FROM utilisateur WHERE id_utilisateur = %s"
    user = execute_query(check_query, (user_id,))
    
    if not user:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    
    # Préparation des champs à mettre à jour
    updates = []
    params = []
    
    if 'email' in data:
        updates.append("email = %s")
        params.append(data['email'])
    
    if 'password' in data:
        updates.append("password = %s")
        params.append(hash_password(data['password']))
    
    # Seul l'admin peut changer le rôle ou le groupe
    if jwt_data['role'] == 'admin':
        if 'role' in data:
            if data['role'] not in ['admin', 'user']:
                return jsonify({"error": "Rôle invalide"}), 400
            updates.append("role = %s")
            params.append(data['role'])
        
        if 'id_groupe' in data:
            updates.append("id_groupe = %s")
            params.append(data['id_groupe'] if data['id_groupe'] else None)
    
    if not updates:
        return jsonify({"message": "Aucune mise à jour effectuée"}), 200
    
    # Construire la requête
    query = f"""
    UPDATE utilisateur
    SET {', '.join(updates)}
    WHERE id_utilisateur = %s
    RETURNING id_utilisateur, email, role, id_groupe
    """
    
    params.append(user_id)
    
    try:
        result = execute_query(query, tuple(params))
        return jsonify({
            "message": "Utilisateur mis à jour avec succès",
            "user": result[0]
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/<int:user_id>', methods=['DELETE'])
@jwt_required()
def delete_user(user_id):
    """
    Supprimer un utilisateur (admin uniquement)
    """
    jwt_data = get_jwt()
    if jwt_data['role'] != 'admin':
        return jsonify({"error": "Accès non autorisé"}), 403
    
    # Vérifier si l'utilisateur existe
    check_query = "SELECT id_utilisateur FROM utilisateur WHERE id_utilisateur = %s"
    user = execute_query(check_query, (user_id,))
    
    if not user:
        return jsonify({"error": "Utilisateur non trouvé"}), 404
    
    # Supprimer l'utilisateur
    query = "DELETE FROM utilisateur WHERE id_utilisateur = %s"
    
    try:
        execute_query(query, (user_id,), fetch=False)
        return jsonify({"message": "Utilisateur supprimé avec succès"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@bp.route('/group/<int:group_id>', methods=['GET'])
@jwt_required()
def get_users_by_group(group_id):
    """
    Récupérer tous les utilisateurs d'un groupe spécifique
    """
    jwt_data = get_jwt()
    
    # Seul l'admin peut voir tous les utilisateurs d'un groupe
    if jwt_data['role'] != 'admin':
        return jsonify({"error": "Accès non autorisé"}), 403
    
    query = """
    SELECT id_utilisateur, email, role
    FROM utilisateur
    WHERE id_groupe = %s
    ORDER BY id_utilisateur
    """
    
    try:
        users = execute_query(query, (group_id,))
        return jsonify(users), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500