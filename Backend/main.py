from fastapi import FastAPI, Depends, HTTPException, Request, Query, status, Body
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from database import engine as db_engine, get_db, Base
import models, schemas, auth
from fastapi.security import OAuth2PasswordRequestForm
from datetime import datetime
from search_engine import engine as search_engine
from fastapi.middleware.cors import CORSMiddleware

# Création des tables
Base.metadata.create_all(bind=db_engine)

app = FastAPI(title="SmartFind API")

# --- CONFIGURATION DU CORS (LIAISON FRONT-BACK) ---
origins = [
    "http://localhost:5173",    # L'adresse de ton React (Vite)
    "http://127.0.0.1:5173",    # Variantes possibles
    "http://localhost:3000",    # Au cas où
    "*"                         # ⚠️ Pour le dév uniquement : autorise tout le monde
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,      # Qui a le droit d'appeler ?
    allow_credentials=True,     # Autoriser les cookies/tokens ? OUI
    allow_methods=["*"],        # Autoriser GET, POST, PUT, DELETE...
    allow_headers=["*"],        # Autoriser tous les headers
)

# --- DEPENDANCES DE SECURITE ---
def get_current_admin(current_user: models.Utilisateur = Depends(auth.get_current_user)):
    if current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Privilèges Administrateur requis")
    return current_user

# ==========================================
# 1. AUTH & UTILISATEURS
# ==========================================
@app.post("/signup", response_model=schemas.UserResponse)
def create_user(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if db.query(models.Utilisateur).filter(models.Utilisateur.email == user.email).first():
        raise HTTPException(status_code=400, detail="Email déjà utilisé")
    hashed_pw = auth.get_password_hash(user.password)
    new_user = models.Utilisateur(email=user.email, hashed_password=hashed_pw, nom=user.nom, prenom=user.prenom)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user

@app.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.Utilisateur).filter(models.Utilisateur.email == form_data.username).first()
    if not user or not auth.verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Identifiants incorrects")
    access_token = auth.create_access_token(data={"sub": user.email, "role": user.role})
    return {"access_token": access_token, "token_type": "bearer"}


@app.get("/users/me", response_model=schemas.UserResponse) # Ou schemas.Utilisateur selon ton code
async def read_users_me(current_user: models.Utilisateur = Depends(auth.get_current_user)):
    """
    Renvoie les infos de l'utilisateur connecté.
    Nécessite un token valide (Depends(auth.get_current_user)).
    """
    return current_user

@app.put("/users/me", response_model=schemas.UserResponse)
def update_profile(user_update: schemas.UserUpdate, current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    if user_update.nom:
        current_user.nom = user_update.nom
    if user_update.prenom:
        current_user.prenom = user_update.prenom

    if user_update.password:
        if not user_update.current_password:
            raise HTTPException(status_code=400, detail="Mot de passe actuel requis")
        if not auth.verify_password(user_update.current_password, current_user.hashed_password):
            raise HTTPException(status_code=400, detail="Mot de passe actuel incorrect")
        if len(user_update.password) < 6:
            raise HTTPException(status_code=400, detail="Le nouveau mot de passe doit contenir au moins 6 caractères")
        current_user.hashed_password = auth.get_password_hash(user_update.password)

    db.commit()
    db.refresh(current_user)
    return current_user

@app.get("/users/me/history", response_model=List[schemas.HistoriqueResponse])
def get_history(current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Historique)\
        .filter(models.Historique.id_utilisateur == current_user.id_utilisateur)\
        .order_by(models.Historique.date_his.desc())\
        .all()

@app.get("/users/me/reservations", response_model=List[schemas.ReservationResponse])
def get_reservations(current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    return db.query(models.Reservation)\
        .filter(models.Reservation.id_utilisateur == current_user.id_utilisateur)\
        .order_by(models.Reservation.date_reservation.desc())\
        .all()

# ==========================================
# 2. GESTION OBJETS (ADMIN)
# ==========================================
# ==========================================
# 2. GESTION OBJETS (ADMIN) - Version Corrigée
# ==========================================

# 1. CRÉATION D'OBJET (Sécurisé Admin + Champs complets)
@app.post("/objets", response_model=schemas.ObjetResponse)
def create_objet(
    objet: schemas.ObjetCreate, 
    current_user: models.Utilisateur = Depends(get_current_admin), # Sécurité Admin
    db: Session = Depends(get_db)
):
    # On crée l'objet avec TOUS les champs (y compris statut et description si présents dans le schema)
    # Note : Assure-toi que ton schemas.ObjetCreate contient bien 'statut' et 'description' si tu veux les passer
    db_objet = models.Objet(
        nom_model=objet.nom_model, 
        nom_marque=objet.nom_marque,
        type_objet=objet.type_objet, 
        id_salle=objet.id_salle, 
        mac_adresse=objet.mac_adresse,
        # Si ton formulaire envoie un statut (ex: "Panne"), on le prend, sinon "Disponible" par défaut
        statut="Disponible" 
    )
    
    # Gestion des fonctionnalités (ex: Wifi, Scanner...)
    for nom_fonc in objet.fonctionnalites:
        nom_clean = nom_fonc.capitalize()
        fonc = db.query(models.Fonctionnalite).filter_by(nom=nom_clean).first()
        if not fonc: 
            fonc = models.Fonctionnalite(nom=nom_clean)
        db_objet.fonctionnalites.append(fonc)

    db.add(db_objet)
    db.commit()
    db.refresh(db_objet)
    return db_objet

# 2. LECTURE D'UN OBJET
@app.get("/objets/{objet_id}", response_model=schemas.ObjetResponse)
def get_objet(objet_id: int, db: Session = Depends(get_db), current_user: models.Utilisateur = Depends(auth.get_current_user)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet:
        raise HTTPException(404, "Objet introuvable")
    return objet

# 3. MODIFICATION D'OBJET
@app.put("/objets/{objet_id}", response_model=schemas.ObjetResponse)
def update_objet(objet_id: int, update_data: schemas.ObjetUpdate, current_user: models.Utilisateur = Depends(get_current_admin), db: Session = Depends(get_db)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    
    if update_data.statut: objet.statut = update_data.statut
    if update_data.nom_model: objet.nom_model = update_data.nom_model
    if update_data.description: objet.description = update_data.description
    
    db.commit()
    db.refresh(objet)
    return objet

# 3. SUPPRESSION D'OBJET
@app.delete("/objets/{objet_id}")
def delete_objet(objet_id: int, current_user: models.Utilisateur = Depends(get_current_admin), db: Session = Depends(get_db)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    db.delete(objet)
    db.commit()
    return {"message": "Objet supprimé avec succès"}
# ==========================================
# 3. RECHERCHE & CONSULTATION
# ==========================================
@app.get("/search", response_model=List[schemas.ObjetResponse])
def search_global(
    q: Optional[str] = None,
    etage: Optional[int] = None, salle: Optional[int] = None,
    type: Optional[str] = None, marque: Optional[str] = None,
    statut: Optional[str] = None, fonction: Optional[str] = None,
    distance: bool = False,
    distance_max: Optional[float] = None,
    save_history: bool = False,
    db: Session = Depends(get_db),
    current_user: Optional[models.Utilisateur] = Depends(auth.get_current_user_optional)
):
    # Save history once for explicit search click; ignore accidental duplicate requests.
    if current_user and save_history and q and q.strip():
        query_text = q.strip()
        last_entry = db.query(models.Historique)\
            .filter(
                models.Historique.id_utilisateur == current_user.id_utilisateur,
                models.Historique.requete_search == query_text
            )\
            .order_by(models.Historique.date_his.desc())\
            .first()

        should_insert = True
        if last_entry and last_entry.date_his:
            should_insert = (datetime.utcnow() - last_entry.date_his).total_seconds() > 2

        if should_insert:
            hist = models.Historique(requete_search=query_text, id_utilisateur=current_user.id_utilisateur)
            db.add(hist)
            db.commit()

    return search_engine.search(
        db=db,
        query=q,
        filtre_etage_id=etage,
        filtre_salle_id=salle,
        filtre_type=type,
        filtre_marque=marque,
        filtre_statut=statut,
        filtre_fonction=fonction,
        sort_by_distance=distance,
        max_distance=distance_max,
    )


@app.get("/search/suggest")
def search_suggest(
    q: str = Query(..., min_length=1),
    limit: int = Query(8, ge=1, le=20),
    db: Session = Depends(get_db),
):
    return {
        "suggestions": search_engine.suggest(
            db=db,
            query=q,
            limit=limit,
        )
    }


@app.get("/search/filters")
def get_search_filters(db: Session = Depends(get_db)):
    types = [
        row[0]
        for row in db.query(models.Objet.type_objet)\
            .filter(models.Objet.type_objet.isnot(None))\
            .distinct()\
            .order_by(models.Objet.type_objet.asc())\
            .all()
        if row[0]
    ]

    marques = [
        row[0]
        for row in db.query(models.Objet.nom_marque)\
            .filter(models.Objet.nom_marque.isnot(None))\
            .distinct()\
            .order_by(models.Objet.nom_marque.asc())\
            .all()
        if row[0]
    ]

    statuts = [
        row[0]
        for row in db.query(models.Objet.statut)\
            .filter(models.Objet.statut.isnot(None))\
            .distinct()\
            .order_by(models.Objet.statut.asc())\
            .all()
        if row[0]
    ]

    fonctionnalites = [
        row[0]
        for row in db.query(models.Fonctionnalite.nom)\
            .filter(models.Fonctionnalite.nom.isnot(None))\
            .distinct()\
            .order_by(models.Fonctionnalite.nom.asc())\
            .all()
        if row[0]
    ]

    etages = [
        row[0]
        for row in db.query(models.Etage.num_etage)\
            .distinct()\
            .order_by(models.Etage.num_etage.asc())\
            .all()
        if row[0] is not None
    ]

    salles = db.query(models.Salle)\
        .order_by(models.Salle.num_etage.asc(), models.Salle.nom_salle.asc())\
        .all()

    return {
        "types": types,
        "marques": marques,
        "statuts": statuts,
        "fonctionnalites": fonctionnalites,
        "etages": etages,
        "salles": [
            {
                "id_salle": s.id_salle,
                "nom_salle": s.nom_salle,
                "num_etage": s.num_etage,
                "coord_x": s.coord_x,
                "coord_y": s.coord_y,
            }
            for s in salles
        ],
    }

# ==========================================
# 4. ACTIONS UTILISATEUR (Réserver, Actionner, Signaler)
# ==========================================
@app.post("/objets/{objet_id}/reserve")
def reserve_objet(objet_id: int, current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    payload = schemas.ReservationCreateRequest(
        object_id=objet_id,
        user_id=current_user.id_utilisateur,
    )
    return create_reservation(payload=payload, db=db, current_user=current_user)

@app.post("/objets/{objet_id}/action")
def actionner_objet(objet_id: int, action: str = Query(..., description="imprimer, scanner..."), current_user: models.Utilisateur = Depends(auth.get_current_user), db: Session = Depends(get_db)):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    
    # Vérification simple : l'utilisateur a-t-il réservé l'objet ?
    reservation = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == objet_id,
            models.Reservation.id_utilisateur == current_user.id_utilisateur,
            models.Reservation.statut_reservation.in_(["Active", "ACTIVE"])
        )
        .first()
    )
    
    # On autorise l'action SI (objet est libre) OU (utilisateur a réservé)
    if objet.statut == "Occupé" and not reservation:
        raise HTTPException(403, "Cet objet est utilisé par quelqu'un d'autre")
    
    if objet.statut == "Panne":
        raise HTTPException(400, "Objet en panne, impossible d'actionner")

    return {"message": f"Action '{action}' envoyée à {objet.nom_model} (IP: {objet.ip_adress})"}



# ==========================================
# GESTION DES ALERTES (ADMIN)
# ==========================================

# 1. Consulter les alertes (Tableau de bord Admin)
@app.get("/admin/alertes", response_model=List[schemas.AlerteResponse])
def get_alertes(resolved: bool = False, db: Session = Depends(get_db), current_user: models.Utilisateur = Depends(get_current_admin)):
    """
    Récupère toutes les alertes (par défaut seulement les non résolues).
    """
    alertes = db.query(models.Alerte).filter(models.Alerte.est_resolu == resolved).all()
    
    # Mapping manuel pour faciliter l'affichage Frontend
    response = []
    for a in alertes:
        signaleur = "IoT Automatique"
        if a.id_utilisateur and a.utilisateur:
            signaleur = f"{a.utilisateur.nom} {a.utilisateur.prenom}"
            
        response.append({
            "id_alerte": a.id_alerte,
            "message": a.message,
            "niveau": a.niveau,
            "source": a.source,
            "date_alerte": a.date_alerte,
            "est_resolu": a.est_resolu,
            "nom_objet": f"{a.objet.type_objet} {a.objet.nom_model} ({a.objet.salle.nom_salle})",
            "nom_signaleur": signaleur
        })
    return response

# 2. Résoudre une alerte (L'admin clique sur "Traité")
@app.put("/admin/alertes/{alerte_id}/resolve")
def resolve_alerte(
    alerte_id: int, 
    nouveau_statut_objet: str = Body(..., embed=True), # L'admin choisit le verdict : "Disponible" ou "Panne"
    db: Session = Depends(get_db), 
    current_user: models.Utilisateur = Depends(get_current_admin)
):
    """
    L'admin traite l'alerte et décide du sort de l'objet.
    Exemple de body JSON : { "nouveau_statut_objet": "Disponible" } (Fausse alerte)
    Exemple de body JSON : { "nouveau_statut_objet": "Panne" } (Vraie panne confirmée)
    """
    alerte = db.query(models.Alerte).filter(models.Alerte.id_alerte == alerte_id).first()
    if not alerte: raise HTTPException(404, "Alerte introuvable")
    
    # 1. On marque l'alerte comme traitée
    alerte.est_resolu = True
    
    # 2. On applique la décision de l'admin sur l'objet
    if alerte.objet:
        alerte.objet.statut = nouveau_statut_objet
        
        # Si l'admin remet l'objet en "Disponible", on peut ajouter une trace dans la description
        if nouveau_statut_objet == "Disponible":
             # On nettoie l'ancienne description de panne si besoin
             pass 
        elif nouveau_statut_objet == "Panne":
             alerte.objet.description = f"EN PANNE (Confirmé par Admin via alerte #{alerte_id})"

    db.commit()
    return {"message": f"Alerte résolue. L'objet est maintenant '{nouveau_statut_objet}'"}


@app.post("/objets/{objet_id}/report")
def signaler_probleme(
    objet_id: int, 
    description: str, 
    current_user: models.Utilisateur = Depends(auth.get_current_user), 
    db: Session = Depends(get_db)
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == objet_id).first()
    if not objet: raise HTTPException(404, "Objet introuvable")
    
    # LOGIQUE CORRIGÉE :
    # On ne met PAS "Panne" direct. On met un statut d'avertissement.
    if objet.statut != "Panne": # Si déjà en panne, on ne change rien
        objet.statut = "Signalé" 
    
    # Création de l'alerte pour l'admin
    new_alerte = models.Alerte(
        message=description,
        niveau="Warning",
        source="Utilisateur",
        id_objet=objet_id,
        id_utilisateur=current_user.id_utilisateur
    )
    
    db.add(new_alerte)
    db.commit()
    
    return {"message": "Problème signalé. L'objet est en attente de vérification."}
# ==========================================
# 5. IoT HEARTBEAT
# ==========================================
@app.post("/iot/heartbeat")
def receive_heartbeat(
    heartbeat: schemas.HeartbeatSchema, 
    request: Request, 
    db: Session = Depends(get_db)
):
    """
    Reçoit le signal de vie des objets connectés.
    Gère intelligemment les pannes et les rétablissements.
    """
    # 1. Identifier l'objet
    objet = db.query(models.Objet).filter(models.Objet.mac_adresse == heartbeat.mac_adresse).first()
    if not objet: 
        raise HTTPException(404, "Objet inconnu (MAC non reconnue)")
    
    # 2. Mise à jour technique (IP et Date)
    objet.ip_adress = request.client.host
    objet.last_heartbeat = datetime.utcnow()

    # 3. INTELLIGENCE DES STATUTS
    # On définit des listes de mots-clés que l'IoT pourrait envoyer
    status_critique = ["Critical", "Panne", "Erreur", "Surchauffe", "Error"]
    status_warning = ["Warning", "Low Battery", "Papier Bas", "Maintenance"]
    status_ok = ["OK", "Available", "Ready", "Disponible"]

    # CAS A : PROBLÈME GRAVE (Le capteur ne ment pas -> On met en Panne direct)
    if heartbeat.statut in status_critique:
        objet.statut = "Panne"
        
        # Création d'alerte si pas déjà existante
        alerte_existante = db.query(models.Alerte).filter(
            models.Alerte.id_objet == objet.id_objet,
            models.Alerte.est_resolu == False,
            models.Alerte.source == "IoT"
        ).first()
        
        if not alerte_existante:
            new_alerte = models.Alerte(
                message=f"ALERTE CRITIQUE AUTO : {heartbeat.statut}",
                niveau="Critical",
                source="IoT",
                id_objet=objet.id_objet
            )
            db.add(new_alerte)

    # CAS B : AVERTISSEMENT (On met en Signalé/Orange)
    elif heartbeat.statut in status_warning:
        # On ne change le statut que s'il n'est pas déjà en Panne
        if objet.statut != "Panne":
            objet.statut = "Signalé"
            
        # On crée une alerte de niveau Warning
        alerte_existante = db.query(models.Alerte).filter(
            models.Alerte.id_objet == objet.id_objet,
            models.Alerte.message.contains("Warning"), # Simple vérif pour éviter doublon
            models.Alerte.est_resolu == False
        ).first()

        if not alerte_existante:
            new_alerte = models.Alerte(
                message=f"Maintenance requise : {heartbeat.statut}",
                niveau="Warning",
                source="IoT",
                id_objet=objet.id_objet
            )
            db.add(new_alerte)

    # CAS C : TOUT VA BIEN (Auto-Réparation)
    elif heartbeat.statut in status_ok:
        # Si l'objet était en Panne ou Signalé, on le remet en Disponible
        if objet.statut in ["Panne", "Signalé"]:
            objet.statut = "Disponible"
            # (Optionnel : On pourrait aussi clore les alertes automatiquement ici)
        
        # NOTE IMPORTANTE : Si le statut est "Occupé" (Réservé), ON NE TOUCHE PAS.
        # Ce n'est pas parce que l'imprimante marche qu'elle n'est pas réservée.

    db.commit()
    return {"status": "ok", "message": f"Heartbeat traité. Statut actuel : {objet.statut}"}
# ==========================================
# ENDPOINT CATEGORIES (Pour le Menu)
# ==========================================
@app.get("/categories", response_model=List[schemas.CategoryResponse])
def get_categories(db: Session = Depends(get_db)):
    """
    Retourne les categories a partir de type_objet (table Objet)
    avec le nombre d'objets par type.
    """
    results = db.query(
        models.Objet.type_objet,
        func.count(models.Objet.id_objet)
    ).filter(models.Objet.type_objet.isnot(None))\
     .group_by(models.Objet.type_objet)\
     .order_by(models.Objet.type_objet.asc())\
     .all()

    return [
        {"nom": type_name, "count": int(count or 0)}
        for type_name, count in results
        if type_name
    ]

@app.get("/salles")
def get_all_salles(db: Session = Depends(get_db)):
    """
    Récupère la liste de toutes les salles pour le menu déroulant.
    """
    return db.query(models.Salle).all()
# ==========================================
# 6. EQUIPMENT DETAILS + RESERVATION QUEUE (NO MODEL CHANGE)
# ==========================================
ACTIVE_RESERVATION_STATUSES = ["ACTIVE", "Active"]
WAITING_RESERVATION_STATUSES = ["WAITING", "Waiting"]
OPEN_RESERVATION_STATUSES = ACTIVE_RESERVATION_STATUSES + WAITING_RESERVATION_STATUSES


def _create_notification(
    db: Session,
    user_id: int,
    message: str,
    type_notification: str = "INFO",
    object_id: Optional[int] = None,
    reservation_id: Optional[int] = None,
):
    notif = models.Notification(
        id_utilisateur=user_id,
        message=message,
        type_notification=type_notification,
        id_objet=object_id,
        id_reservation=reservation_id,
    )
    db.add(notif)
    return notif


def _count_unread_notifications(db: Session, user_id: int) -> int:
    return int(
        db.query(func.count(models.Notification.id_notification))
        .filter(
            models.Notification.id_utilisateur == user_id,
            models.Notification.est_lu == False,  # noqa: E712
        )
        .scalar()
        or 0
    )


def _count_waiting(db: Session, object_id: int) -> int:
    return int(
        db.query(func.count(models.Reservation.id))
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.statut_reservation.in_(WAITING_RESERVATION_STATUSES),
        )
        .scalar()
        or 0
    )


def _get_active_reservation(db: Session, object_id: int):
    return (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.statut_reservation.in_(ACTIVE_RESERVATION_STATUSES),
        )
        .order_by(models.Reservation.date_reservation.asc())
        .first()
    )


def _get_oldest_waiting_reservation(db: Session, object_id: int):
    return (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.statut_reservation.in_(WAITING_RESERVATION_STATUSES),
        )
        .order_by(models.Reservation.date_reservation.asc())
        .first()
    )


def _get_my_open_reservation(db: Session, object_id: int, user_id: int):
    return (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.id_utilisateur == user_id,
            models.Reservation.statut_reservation.in_(OPEN_RESERVATION_STATUSES),
        )
        .order_by(models.Reservation.date_reservation.desc())
        .first()
    )


def _compute_distance_m(objet: models.Objet):
    if not objet.salle:
        return None

    x = objet.salle.coord_x
    y = objet.salle.coord_y
    if x is None or y is None:
        return None

    return round(((x ** 2) + (y ** 2)) ** 0.5, 2)


def _serialize_equipment_details(objet: models.Objet, current_user: models.Utilisateur, db: Session):
    salle = objet.salle
    etage = salle.etage if salle else None

    active_reservation = _get_active_reservation(db, objet.id_objet)
    my_reservation = _get_my_open_reservation(db, objet.id_objet, current_user.id_utilisateur)

    return {
        "id": objet.id_objet,
        "name": objet.nom_model,
        "type": objet.type_objet,
        "marque": objet.nom_marque,
        "status": objet.statut,
        "localisation": {
            "building": etage.nom_building if etage else None,
            "floor": salle.num_etage if salle else None,
            "room": salle.nom_salle if salle else None,
        },
        "distance_m": _compute_distance_m(objet),
        "description": objet.description,
        "fonctionnalites": [f.nom for f in (objet.fonctionnalites or []) if f and f.nom],
        "queue_count": _count_waiting(db, objet.id_objet),
        "active_reservation_id": active_reservation.id if active_reservation else None,
        "my_reservation_id": my_reservation.id if my_reservation else None,
        "my_reservation_status": my_reservation.statut_reservation if my_reservation else None,
    }


def _cancel_reservation_and_update_queue(
    reservation: models.Reservation,
    db: Session,
    close_status: str = "CANCELLED",
    action_word: str = "annulée",
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == reservation.id_objet).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    status_upper = (reservation.statut_reservation or "").upper()

    if status_upper == "ACTIVE":
        reservation.statut_reservation = close_status
        next_waiting = _get_oldest_waiting_reservation(db, objet.id_objet)

        if next_waiting:
            next_waiting.statut_reservation = "ACTIVE"
            objet.statut = "Occupé"
            _create_notification(
                db=db,
                user_id=next_waiting.id_utilisateur,
                message=f"Votre tour est arrivé pour {objet.nom_model}.",
                type_notification="TURN_READY",
                object_id=objet.id_objet,
                reservation_id=next_waiting.id,
            )
            message = f"Réservation {action_word}. Le prochain utilisateur est passé actif."
        else:
            objet.statut = "Disponible"
            message = f"Réservation {action_word}. L'objet est à nouveau disponible."

    elif status_upper == "WAITING":
        reservation.statut_reservation = "CANCELLED"
        message = "Retiré de la file d'attente."

    else:
        message = "Réservation déjà clôturée."

    db.commit()

    return {
        "message": message,
        "reservation_id": reservation.id,
        "reservation_status": reservation.statut_reservation,
        "queue_count": _count_waiting(db, objet.id_objet),
        "object_status": objet.statut,
    }


@app.get("/objects/{object_id}", response_model=schemas.EquipmentDetailsResponse)
def get_object_details(
    object_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == object_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    return _serialize_equipment_details(objet, current_user, db)


@app.get("/objects/{object_id}/queue", response_model=schemas.QueueInfoResponse)
def get_object_queue(
    object_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    objet = db.query(models.Objet).filter(models.Objet.id_objet == object_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    active_reservation = _get_active_reservation(db, object_id)

    return {
        "object_id": object_id,
        "waiting_count": _count_waiting(db, object_id),
        "active_reservation_id": active_reservation.id if active_reservation else None,
    }


@app.post("/reservations", response_model=schemas.ReservationActionResponse)
def create_reservation(
    payload: schemas.ReservationCreateRequest,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    user_id = payload.user_id or current_user.id_utilisateur

    if payload.user_id and payload.user_id != current_user.id_utilisateur and current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Non autorisé")

    objet = db.query(models.Objet).filter(models.Objet.id_objet == payload.object_id).first()
    if not objet:
        raise HTTPException(status_code=404, detail="Objet introuvable")

    if objet.statut == "Panne":
        raise HTTPException(status_code=400, detail="Objet en panne, réservation impossible")

    existing = _get_my_open_reservation(db, payload.object_id, user_id)
    if existing:
        return {
            "message": "Vous avez déjà une réservation en cours pour cet objet.",
            "reservation_id": existing.id,
            "reservation_status": existing.statut_reservation,
            "queue_count": _count_waiting(db, payload.object_id),
            "object_status": objet.statut,
        }

    active_reservation = _get_active_reservation(db, payload.object_id)

    if active_reservation is None and objet.statut != "Occupé":
        reservation_status = "ACTIVE"
        objet.statut = "Occupé"
        message = "Réservation confirmée"
    else:
        reservation_status = "WAITING"
        if objet.statut == "Disponible":
            objet.statut = "Occupé"
        message = "Ajouté à la file d'attente"

    reservation = models.Reservation(
        id_utilisateur=user_id,
        id_objet=payload.object_id,
        statut_reservation=reservation_status,
    )

    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    return {
        "message": message,
        "reservation_id": reservation.id,
        "reservation_status": reservation.statut_reservation,
        "queue_count": _count_waiting(db, payload.object_id),
        "object_status": objet.statut,
    }


@app.delete("/reservations/{reservation_id}", response_model=schemas.ReservationActionResponse)
def cancel_reservation_by_id(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation introuvable")

    if reservation.id_utilisateur != current_user.id_utilisateur and current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Non autorisé")

    return _cancel_reservation_and_update_queue(reservation, db)


@app.post("/reservations/{reservation_id}/complete", response_model=schemas.ReservationActionResponse)
def complete_reservation_by_id(
    reservation_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    reservation = db.query(models.Reservation).filter(models.Reservation.id == reservation_id).first()
    if not reservation:
        raise HTTPException(status_code=404, detail="Réservation introuvable")

    if reservation.id_utilisateur != current_user.id_utilisateur and current_user.role != "Admin":
        raise HTTPException(status_code=403, detail="Non autorisé")

    status_upper = (reservation.statut_reservation or "").upper()
    if status_upper != "ACTIVE":
        raise HTTPException(status_code=400, detail="Seule une réservation active peut être terminée")

    return _cancel_reservation_and_update_queue(
        reservation=reservation,
        db=db,
        close_status="DONE",
        action_word="terminée",
    )


@app.get("/users/me/notifications", response_model=schemas.NotificationListResponse)
def get_my_notifications(
    limit: int = Query(10, ge=1, le=100),
    unread_only: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    query = db.query(models.Notification).filter(
        models.Notification.id_utilisateur == current_user.id_utilisateur
    )

    if unread_only:
        query = query.filter(models.Notification.est_lu == False)  # noqa: E712

    items = query.order_by(models.Notification.date_notification.desc()).limit(limit).all()
    unread_count = _count_unread_notifications(db, current_user.id_utilisateur)

    return {
        "items": items,
        "unread_count": unread_count,
    }


@app.post("/users/me/notifications/{notification_id}/read", response_model=schemas.NotificationUpdateResponse)
def mark_notification_read(
    notification_id: int,
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    notif = (
        db.query(models.Notification)
        .filter(
            models.Notification.id_notification == notification_id,
            models.Notification.id_utilisateur == current_user.id_utilisateur,
        )
        .first()
    )

    if not notif:
        raise HTTPException(status_code=404, detail="Notification introuvable")

    if not notif.est_lu:
        notif.est_lu = True
        db.commit()

    return {
        "message": "Notification marquée comme lue.",
        "unread_count": _count_unread_notifications(db, current_user.id_utilisateur),
    }


@app.post("/users/me/notifications/read-all", response_model=schemas.NotificationUpdateResponse)
def mark_all_notifications_read(
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    (
        db.query(models.Notification)
        .filter(
            models.Notification.id_utilisateur == current_user.id_utilisateur,
            models.Notification.est_lu == False,  # noqa: E712
        )
        .update({models.Notification.est_lu: True}, synchronize_session=False)
    )
    db.commit()

    return {
        "message": "Toutes les notifications sont marquées comme lues.",
        "unread_count": 0,
    }


@app.delete("/reservations", response_model=schemas.ReservationActionResponse)
def cancel_my_reservation_for_object(
    object_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: models.Utilisateur = Depends(auth.get_current_user),
):
    reservation = (
        db.query(models.Reservation)
        .filter(
            models.Reservation.id_objet == object_id,
            models.Reservation.id_utilisateur == current_user.id_utilisateur,
            models.Reservation.statut_reservation.in_(OPEN_RESERVATION_STATUSES),
        )
        .order_by(models.Reservation.date_reservation.desc())
        .first()
    )

    if not reservation:
        raise HTTPException(status_code=404, detail="Aucune réservation active/en attente pour cet objet")

    return _cancel_reservation_and_update_queue(reservation, db)
