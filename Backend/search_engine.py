import math
import re
import time
import unicodedata
from typing import Dict, List, Optional, Set, Tuple

try:
    import spacy
except Exception:
    spacy = None

try:
    from rapidfuzz import fuzz, process
except Exception:
    from difflib import SequenceMatcher

    class _FuzzFallback:
        @staticmethod
        def _ratio(a: str, b: str) -> float:
            return SequenceMatcher(None, a, b).ratio() * 100

        @classmethod
        def token_set_ratio(cls, a: str, b: str) -> float:
            set_a = " ".join(sorted(set(a.split())))
            set_b = " ".join(sorted(set(b.split())))
            return cls._ratio(set_a, set_b)

        @classmethod
        def partial_ratio(cls, a: str, b: str) -> float:
            if not a or not b:
                return 0.0
            short, long_text = (a, b) if len(a) <= len(b) else (b, a)
            best = 0.0
            window = len(short)
            for idx in range(0, max(1, len(long_text) - window + 1)):
                best = max(best, cls._ratio(short, long_text[idx:idx + window]))
            return best

        @classmethod
        def WRatio(cls, a: str, b: str) -> float:
            return max(cls.token_set_ratio(a, b), cls.partial_ratio(a, b))

    class _ProcessFallback:
        @staticmethod
        def extractOne(query: str, choices: List[str], scorer=None, score_cutoff: float = 0.0):
            if not choices:
                return None
            scorer_fn = scorer or _FuzzFallback.WRatio
            best_choice = None
            best_score = -1.0
            for idx, candidate in enumerate(choices):
                score = float(scorer_fn(query, candidate))
                if score > best_score:
                    best_choice = (candidate, score, idx)
                    best_score = score
            if best_choice and best_choice[1] >= score_cutoff:
                return best_choice
            return None

    fuzz = _FuzzFallback()
    process = _ProcessFallback()

from sqlalchemy import func, or_
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, joinedload

import models


STATUS_KEYWORDS = {
    "Disponible": {
        "disponible", "dispo", "libre", "available", "free", "ready", "متاح", "فارغ"
    },
    "Occupé": {
        "occupe", "occupé", "busy", "reserved", "reserve", "used", "محجوز", "مشغول"
    },
    "Panne": {
        "panne", "hs", "error", "critical", "broken", "down", "معطل", "عطل"
    },
}

TYPE_KEYWORDS = {
    "Imprimante": {
        "imprimante", "printer", "print", "impression", "imprimer", "copieur", "photocopieur",
        "paper", "papier", "feuille", "document", "documento", "impresora", "imprimir",
        "طابعة", "طباعة", "ورقة", "ورق"
    },
    "Scanner": {
        "scanner", "scan", "scanne", "sanne", "scaner", "scanear", "escaner", "numeriser",
        "numériser", "digitizer", "ماسح", "سكانر", "مسح"
    },
    "Projecteur": {
        "projecteur", "projector", "beamer", "video", "proyector", "presentation",
        "عرض", "عارض", "بروجيكتور", "عرض تقديمي"
    },
    "Écran": {
        "ecran", "écran", "screen", "display", "monitor", "pantalla", "شاشة"
    },
    "Routeur": {
        "routeur", "router", "wifi", "reseau", "réseau", "network", "networking",
        "red", "شبكة", "راوتر"
    },
}

TYPE_INTENT_PATTERNS = {
    "Imprimante": [
        r"(?:print|imprim|impression|imprimer|impresora|imprimir|طباعة|طابعة)",
        r"(?:papier|paper|feuille|document|ورقة|ورق)",
    ],
    "Scanner": [
        r"(?:scan|scanner|scanne|scaner|scanear|escaner|numeris|numéris|مسح|ماسح|سكانر)",
    ],
    "Projecteur": [
        r"(?:project|beamer|proyector|presentation|عرض|عارض|بروجيكتور)",
    ],
    "Écran": [
        r"(?:screen|display|monitor|ecran|écran|pantalla|شاشة)",
    ],
    "Routeur": [
        r"(?:router|routeur|wifi|reseau|réseau|network|red|شبكة|راوتر)",
    ],
}

NOISE_TERMS = {
    # English
    "i", "want", "need", "find", "show", "me", "please", "for", "to", "a", "an", "the",
    "with", "without", "and", "or", "in", "on", "at", "of", "my", "your",
    # French
    "je", "veux", "vieux", "cherche", "chercher", "recherche", "montre", "moi", "svp",
    "sil", "te", "plait", "un", "une", "des", "de", "du", "la", "le", "les", "dans",
    "avec", "sans", "et", "ou", "pour", "mon", "ma", "mes",
    # Spanish
    "yo", "quiero", "buscar", "busca", "mostrar", "muestrame", "porfavor",
    "el", "la", "los", "las", "de", "del", "con", "sin", "y", "o", "para",
    # Darija / Arabizi
    "ana", "nheb", "bghit", "bdit", "3tini", "arid", "law", "smahli",
    # Arabic
    "اريد", "أريد", "ابحث", "بحث", "ابغي", "بغيت", "شي", "من", "في", "على", "الى", "إلى",
    "لو", "سمحت", "رجاء",
    # technical/noise words
    "disponible", "dispo", "libre", "occupe", "occup", "occupé", "panne",
    "etage", "étage", "niveau", "floor", "salle", "room", "distance", "proche",
    "loin", "metre", "metres", "meter", "m",
    "batiment", "bâtiment", "objet", "objets",
}

WAITING_STATUSES = {"WAITING", "EN ATTENTE"}
CANCELLED_STATUSES = {"CANCELLED", "ANNULEE", "ANNULÉE", "DONE", "TERMINE", "TERMINÉ"}


# Regex helpers for natural-language filters
REGEX_FLOOR_1 = re.compile(r"(?:etage|étage|niveau|floor|طابق|الطابق)\s*(\d+)", re.IGNORECASE)
REGEX_FLOOR_2 = re.compile(r"(\d+)\s*(?:er|e|eme)?\s*(?:etage|étage|niveau|floor)", re.IGNORECASE)
REGEX_ROOM = re.compile(r"(?:salle|room|قاعة|غرفة)\s*([\w\-]+)", re.IGNORECASE)
REGEX_IP = re.compile(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$")
REGEX_MAC = re.compile(r"^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$")


def _strip_accents(value: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return _strip_accents(str(value)).lower().strip()


def _split_words(value: str) -> List[str]:
    return [
        w
        for w in re.findall(r"[a-z0-9؀-ۿ]+", _normalize_text(value), flags=re.UNICODE)
        if w
    ]


def _clean_noise_terms(terms: List[str]) -> List[str]:
    cleaned: List[str] = []
    seen: Set[str] = set()

    for term in terms:
        normalized = _normalize_text(term)
        if not normalized:
            continue
        if normalized in NOISE_TERMS:
            continue
        if len(normalized) < 2 and not normalized.isdigit():
            continue
        if normalized in seen:
            continue

        seen.add(normalized)
        cleaned.append(normalized)

    return cleaned


class SmartSearchEngine:
    def __init__(self):
        print("⚡ Chargement du Moteur de Recherche (NLP + Hybrid Ranking)...")
        self.nlp = None

        if spacy is not None:
            try:
                self.nlp = spacy.load("fr_core_news_sm")
            except Exception:
                print("⚠️ Modèle spaCy fr_core_news_sm non trouvé. NLP avancé partiellement désactivé.")
        else:
            print("⚠️ spaCy non installé. NLP avancé désactivé.")

        self.type_alias_to_canonical: Dict[str, str] = {}
        for canonical, aliases in TYPE_KEYWORDS.items():
            self.type_alias_to_canonical[_normalize_text(canonical)] = canonical
            for alias in aliases:
                self.type_alias_to_canonical[_normalize_text(alias)] = canonical

        self.intent_patterns: Dict[str, List[re.Pattern]] = {
            canonical: [re.compile(pattern, re.IGNORECASE) for pattern in patterns]
            for canonical, patterns in TYPE_INTENT_PATTERNS.items()
        }

        self._vocab_cache_at = 0.0
        self._vocab_cache_terms: List[str] = []

    def _extract_tokens(self, query: str) -> List[str]:
        query = (query or "").strip()
        if not query:
            return []

        if self.nlp:
            doc = self.nlp(query)
            terms: List[str] = []
            for token in doc:
                if token.is_space or token.is_punct:
                    continue

                if token.like_num:
                    terms.append(token.text.lower())
                    continue

                if token.is_stop:
                    continue

                lemma = (token.lemma_ or token.text).lower().strip()
                if not lemma:
                    continue

                chunks = _split_words(lemma)
                if chunks:
                    terms.extend(chunks)
                else:
                    terms.append(_normalize_text(lemma))

            if terms:
                return terms

        return _split_words(query)

    def _load_available_types(self, db: Session) -> List[str]:
        rows = (
            db.query(models.Objet.type_objet)
            .filter(models.Objet.type_objet.isnot(None))
            .distinct()
            .all()
        )
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def _load_available_marques(self, db: Session) -> List[str]:
        rows = (
            db.query(models.Objet.nom_marque)
            .filter(models.Objet.nom_marque.isnot(None))
            .distinct()
            .all()
        )
        return [str(row[0]).strip() for row in rows if row and row[0]]

    def _load_available_fonctions(self, db: Session) -> List[str]:
        rows = (
            db.query(models.Fonctionnalite.nom)
            .filter(models.Fonctionnalite.nom.isnot(None))
            .distinct()
            .all()
        )
        return [str(row[0]).strip() for row in rows if row and row[0]]

    @staticmethod
    def _best_value_from_query(
        terms: List[str],
        normalized_query: str,
        values: List[str],
        score_cutoff: float = 88.0,
    ) -> Optional[str]:
        if not values:
            return None

        normalized_map = {
            _normalize_text(value): value
            for value in values
            if _normalize_text(value)
        }

        if not normalized_map:
            return None

        for normalized_value, original_value in normalized_map.items():
            if len(normalized_value) >= 3 and normalized_value in normalized_query:
                return original_value

        best_value = None
        best_score = 0.0

        for term in terms:
            normalized_term = _normalize_text(term)
            if not normalized_term or normalized_term in NOISE_TERMS:
                continue

            # Exact match first (important for short brands like HP)
            if normalized_term in normalized_map:
                return normalized_map[normalized_term]

            if normalized_term.isdigit() or len(normalized_term) < 3:
                continue

            best = process.extractOne(
                normalized_term,
                list(normalized_map.keys()),
                scorer=fuzz.WRatio,
                score_cutoff=score_cutoff,
            )
            if best and float(best[1]) > best_score:
                best_score = float(best[1])
                best_value = normalized_map.get(best[0])

        return best_value

    @staticmethod
    def _resolve_to_available_type(canonical_type: str, available_types: List[str]) -> str:
        if not canonical_type or not available_types:
            return canonical_type

        normalized_map = {_normalize_text(t): t for t in available_types}
        target = _normalize_text(canonical_type)

        if target in normalized_map:
            return normalized_map[target]

        for normalized_value, original_value in normalized_map.items():
            if target and (target in normalized_value or normalized_value in target):
                return original_value

        best = process.extractOne(
            target,
            list(normalized_map.keys()),
            scorer=fuzz.WRatio,
            score_cutoff=80,
        )
        if best:
            return normalized_map[best[0]]

        return canonical_type

    def _infer_type_from_intent_patterns(
        self,
        normalized_query: str,
        available_types: List[str],
    ) -> Optional[str]:
        if not normalized_query:
            return None

        for canonical, patterns in self.intent_patterns.items():
            if patterns and any(pattern.search(normalized_query) for pattern in patterns):
                return self._resolve_to_available_type(canonical, available_types)

        return None

    def _infer_type_from_terms(
        self,
        terms: List[str],
        available_types: List[str],
        normalized_query: str,
    ) -> Optional[str]:
        # Direct alias phrase hit in full query (example: "i want print")
        for alias, canonical in self.type_alias_to_canonical.items():
            if alias and alias in normalized_query:
                return self._resolve_to_available_type(canonical, available_types)

        normalized_available_map = {_normalize_text(t): t for t in available_types}

        best_type = None
        best_score = 0.0

        for term in terms:
            n_term = _normalize_text(term)
            if not n_term or n_term in NOISE_TERMS:
                continue

            if n_term in self.type_alias_to_canonical:
                canonical = self.type_alias_to_canonical[n_term]
                return self._resolve_to_available_type(canonical, available_types)

            if n_term in normalized_available_map:
                return normalized_available_map[n_term]

            best = process.extractOne(
                n_term,
                list(normalized_available_map.keys()),
                scorer=fuzz.WRatio,
                score_cutoff=86,
            )
            if best and best[1] > best_score:
                best_score = float(best[1])
                best_type = normalized_available_map.get(best[0])

        return best_type

    def _extract_filters(
        self,
        query: str,
        tokens: List[str],
        available_types: List[str],
        available_marques: List[str],
        available_fonctions: List[str],
    ) -> Tuple[Dict[str, object], List[str]]:
        filters: Dict[str, object] = {}
        normalized_query = _normalize_text(query)

        normalized_tokens = [_normalize_text(t) for t in tokens if _normalize_text(t)]
        token_set: Set[str] = set(normalized_tokens)

        for canonical_status, keywords in STATUS_KEYWORDS.items():
            if any(kw in normalized_query for kw in keywords) or any(kw in token_set for kw in keywords):
                filters["statut"] = canonical_status
                break

        floor_match = REGEX_FLOOR_1.search(query) or REGEX_FLOOR_2.search(query)
        if floor_match:
            try:
                filters["num_etage"] = int(floor_match.group(1))
            except (TypeError, ValueError):
                pass

        room_match = REGEX_ROOM.search(query)
        if room_match and room_match.group(1):
            filters["salle_text"] = room_match.group(1).strip()

        cleaned_terms = _clean_noise_terms(normalized_tokens)

        inferred_type = self._infer_type_from_intent_patterns(normalized_query, available_types)
        if not inferred_type:
            inferred_type = self._infer_type_from_terms(cleaned_terms or normalized_tokens, available_types, normalized_query)
        if inferred_type:
            filters["type_objet"] = inferred_type

        inferred_marque = self._best_value_from_query(
            cleaned_terms or normalized_tokens,
            normalized_query,
            available_marques,
            score_cutoff=90,
        )
        if inferred_marque:
            filters["nom_marque"] = inferred_marque

        inferred_fonction = self._best_value_from_query(
            cleaned_terms or normalized_tokens,
            normalized_query,
            available_fonctions,
            score_cutoff=90,
        )
        if inferred_fonction:
            filters["fonction"] = inferred_fonction

        return filters, cleaned_terms

    def _load_domain_vocabulary(self, db: Session) -> List[str]:
        now = time.time()
        if self._vocab_cache_terms and (now - self._vocab_cache_at) < 45:
            return self._vocab_cache_terms

        terms: Set[str] = set()

        def add_term(value: Optional[str]):
            normalized = _normalize_text(value)
            if not normalized:
                return
            if len(normalized) >= 2:
                terms.add(normalized)
            for chunk in _split_words(normalized):
                if len(chunk) >= 3:
                    terms.add(chunk)

        distinct_columns = [
            models.Objet.type_objet,
            models.Objet.nom_marque,
            models.Objet.nom_model,
            models.Objet.description,
        ]

        for column in distinct_columns:
            rows = (
                db.query(column)
                .filter(column.isnot(None))
                .distinct()
                .limit(400)
                .all()
            )
            for row in rows:
                add_term(row[0] if row else None)

        salle_rows = (
            db.query(models.Salle.nom_salle)
            .filter(models.Salle.nom_salle.isnot(None))
            .distinct()
            .limit(200)
            .all()
        )
        for row in salle_rows:
            add_term(row[0] if row else None)

        fonction_rows = (
            db.query(models.Fonctionnalite.nom)
            .filter(models.Fonctionnalite.nom.isnot(None))
            .distinct()
            .limit(200)
            .all()
        )
        for row in fonction_rows:
            add_term(row[0] if row else None)

        for alias in self.type_alias_to_canonical.keys():
            if alias and len(alias) >= 3:
                terms.add(alias)

        self._vocab_cache_terms = sorted(terms)
        self._vocab_cache_at = now
        return self._vocab_cache_terms

    def _autocorrect_terms(self, terms: List[str], vocabulary: List[str]) -> Tuple[List[str], Dict[str, str]]:
        if not terms or not vocabulary:
            return terms, {}

        corrected_terms: List[str] = []
        corrections: Dict[str, str] = {}

        for term in terms:
            normalized = _normalize_text(term)
            if not normalized:
                continue

            if normalized in NOISE_TERMS or normalized.isdigit() or len(normalized) < 3:
                corrected_terms.append(normalized)
                continue

            if normalized in vocabulary:
                corrected_terms.append(normalized)
                continue

            best = process.extractOne(
                normalized,
                vocabulary,
                scorer=fuzz.WRatio,
                score_cutoff=84,
            )

            if best:
                candidate = _normalize_text(best[0])
                if candidate and abs(len(candidate) - len(normalized)) <= 6:
                    corrections[normalized] = candidate
                    corrected_terms.append(candidate)
                    continue

            corrected_terms.append(normalized)

        return corrected_terms, corrections

    def _expand_terms(self, terms: List[str]) -> List[str]:
        expanded: List[str] = []
        seen: Set[str] = set()

        def push(value: Optional[str]):
            normalized = _normalize_text(value)
            if not normalized or normalized in seen:
                return
            seen.add(normalized)
            expanded.append(normalized)

        for term in terms:
            push(term)
            canonical = self.type_alias_to_canonical.get(_normalize_text(term))
            if canonical:
                push(canonical)

        return expanded

    @staticmethod
    def _distance_from_user(obj) -> float:
        salle = getattr(obj, "salle", None)
        if not salle:
            return float("inf")

        x = getattr(salle, "coord_x", None)
        y = getattr(salle, "coord_y", None)
        if x is None or y is None:
            return float("inf")

        origin_x = 0.0
        origin_y = 0.0

        return math.sqrt(((float(x) - origin_x) ** 2) + ((float(y) - origin_y) ** 2))

    @staticmethod
    def _availability_score(status: Optional[str]) -> float:
        normalized = _normalize_text(status)
        if "dispon" in normalized or normalized == "available":
            return 100.0
        if "occup" in normalized or "reserve" in normalized or "busy" in normalized:
            return 45.0
        if "panne" in normalized or "signal" in normalized or "error" in normalized:
            return 10.0
        return 30.0

    @staticmethod
    def _distance_score(distance_value: float) -> float:
        if not math.isfinite(distance_value):
            return 0.0
        return max(0.0, 100.0 - (min(distance_value, 5000.0) / 50.0))

    @staticmethod
    def _build_haystack(obj: models.Objet) -> str:
        fonctionnalites = " ".join([f.nom for f in (obj.fonctionnalites or []) if f and f.nom])
        salle_nom = obj.salle.nom_salle if obj.salle and obj.salle.nom_salle else ""
        return (
            f"{obj.type_objet or ''} "
            f"{obj.nom_marque or ''} "
            f"{obj.nom_model or ''} "
            f"{obj.description or ''} "
            f"{salle_nom} "
            f"{fonctionnalites}"
        ).lower().strip()

    def _load_waiting_counts(self, db: Session, object_ids: List[int]) -> Dict[int, int]:
        if not object_ids:
            return {}

        status_upper = func.upper(func.coalesce(models.Reservation.statut_reservation, ""))
        rows = (
            db.query(models.Reservation.id_objet, func.count(models.Reservation.id))
            .filter(
                models.Reservation.id_objet.in_(object_ids),
                status_upper.in_(list(WAITING_STATUSES)),
            )
            .group_by(models.Reservation.id_objet)
            .all()
        )
        return {int(object_id): int(count or 0) for object_id, count in rows}

    def _load_popularity_counts(self, db: Session, object_ids: List[int]) -> Dict[int, int]:
        if not object_ids:
            return {}

        status_upper = func.upper(func.coalesce(models.Reservation.statut_reservation, ""))
        rows = (
            db.query(models.Reservation.id_objet, func.count(models.Reservation.id))
            .filter(
                models.Reservation.id_objet.in_(object_ids),
                ~status_upper.in_(list(CANCELLED_STATUSES)),
            )
            .group_by(models.Reservation.id_objet)
            .all()
        )
        return {int(object_id): int(count or 0) for object_id, count in rows}

    def _load_postgres_text_ranks(self, db: Session, object_ids: List[int], query_clean: str) -> Dict[int, float]:
        if not object_ids or not query_clean:
            return {}

        engine = db.get_bind()
        if not engine or engine.dialect.name != "postgresql":
            return {}

        document = func.concat_ws(
            " ",
            func.coalesce(models.Objet.nom_model, ""),
            func.coalesce(models.Objet.type_objet, ""),
            func.coalesce(models.Objet.nom_marque, ""),
            func.coalesce(models.Objet.description, ""),
        )

        ts_rank = func.ts_rank_cd(
            func.to_tsvector("simple", document),
            func.plainto_tsquery("simple", query_clean),
        ).label("text_rank")

        try:
            rows = (
                db.query(models.Objet.id_objet, ts_rank)
                .filter(models.Objet.id_objet.in_(object_ids))
                .all()
            )
            return {int(object_id): float(rank or 0.0) for object_id, rank in rows}
        except SQLAlchemyError:
            return {}

    def search(
        self,
        db: Session,
        query: str = None,
        filtre_etage_id: int = None,
        filtre_salle_id: int = None,
        filtre_type: str = None,
        filtre_marque: str = None,
        filtre_statut: str = None,
        filtre_fonction: str = None,
        sort_by_distance: bool = False,
        max_distance: float = None,
    ):
        raw_query = (query or "").strip()

        if raw_query:
            if REGEX_IP.match(raw_query):
                return db.query(models.Objet).filter(models.Objet.ip_adress == raw_query).all()
            if REGEX_MAC.match(raw_query):
                return db.query(models.Objet).filter(models.Objet.mac_adresse == raw_query).all()

        tokens = self._extract_tokens(raw_query)
        available_types = self._load_available_types(db)
        available_marques = self._load_available_marques(db)
        available_fonctions = self._load_available_fonctions(db)

        nlp_filters, cleaned_terms = self._extract_filters(
            raw_query,
            tokens,
            available_types,
            available_marques,
            available_fonctions,
        )
        vocabulary = self._load_domain_vocabulary(db)

        corrected_terms, corrections = self._autocorrect_terms(cleaned_terms, vocabulary)
        expanded_terms = self._expand_terms(corrected_terms)

        normalized_query = _normalize_text(raw_query)
        if not expanded_terms and normalized_query:
            expanded_terms = self._expand_terms(_clean_noise_terms(_split_words(normalized_query)))

        if not filtre_type and not nlp_filters.get("type_objet"):
            inferred_type = self._infer_type_from_terms(expanded_terms or tokens, available_types, normalized_query)
            if inferred_type:
                nlp_filters["type_objet"] = inferred_type

        query_clean = " ".join([term for term in expanded_terms if len(term) >= 2]).strip()

        sql = (
            db.query(models.Objet)
            .options(joinedload(models.Objet.salle), joinedload(models.Objet.fonctionnalites))
        )

        target_etage = filtre_etage_id if filtre_etage_id is not None else nlp_filters.get("num_etage")
        target_statut = filtre_statut if filtre_statut is not None else nlp_filters.get("statut")
        target_type = filtre_type if filtre_type else nlp_filters.get("type_objet")
        target_marque = filtre_marque if filtre_marque else nlp_filters.get("nom_marque")
        target_fonction = filtre_fonction if filtre_fonction else nlp_filters.get("fonction")
        target_salle_text = nlp_filters.get("salle_text")

        joined_salle = False
        joined_fonction = False

        if (
            target_etage is not None
            or filtre_salle_id is not None
            or sort_by_distance
            or max_distance is not None
            or target_salle_text
        ):
            sql = sql.join(models.Salle)
            joined_salle = True

        if target_fonction:
            sql = sql.join(models.Objet.fonctionnalites)
            joined_fonction = True

        if target_etage is not None:
            sql = sql.filter(models.Salle.num_etage == int(target_etage))
        if filtre_salle_id is not None:
            sql = sql.filter(models.Salle.id_salle == filtre_salle_id)
        if target_salle_text and not filtre_salle_id:
            sql = sql.filter(models.Salle.nom_salle.ilike(f"%{target_salle_text}%"))

        if target_statut:
            sql = sql.filter(func.lower(models.Objet.statut) == str(target_statut).lower())
        if target_type:
            sql = sql.filter(func.lower(models.Objet.type_objet) == str(target_type).lower())
        if target_marque:
            sql = sql.filter(func.lower(models.Objet.nom_marque) == str(target_marque).lower())
        if target_fonction:
            sql = sql.filter(func.lower(models.Fonctionnalite.nom) == str(target_fonction).lower())

        base_sql = sql

        if query_clean:
            if not joined_salle:
                sql = sql.outerjoin(models.Salle)
                joined_salle = True

            if not joined_fonction:
                sql = sql.outerjoin(models.Objet.fonctionnalites)
                joined_fonction = True

            terms_for_like = [query_clean] + expanded_terms[:12]
            like_conditions = []

            for term in terms_for_like:
                token = _normalize_text(term)
                if len(token) < 2:
                    continue
                token_like = f"%{token}%"
                like_conditions.extend([
                    models.Objet.nom_model.ilike(token_like),
                    models.Objet.type_objet.ilike(token_like),
                    models.Objet.nom_marque.ilike(token_like),
                    models.Objet.description.ilike(token_like),
                    models.Salle.nom_salle.ilike(token_like),
                    models.Fonctionnalite.nom.ilike(token_like),
                ])

            if like_conditions:
                sql = sql.filter(or_(*like_conditions))

        candidates = sql.distinct().limit(420).all()

        if query_clean and not candidates:
            # Fallback pool: let fuzzy rank recover typo-heavy inputs (e.g. "sanne")
            candidates = base_sql.distinct().limit(520).all()

        if not candidates:
            return []

        object_ids = [obj.id_objet for obj in candidates]
        waiting_count_map = self._load_waiting_counts(db, object_ids)
        popularity_count_map = self._load_popularity_counts(db, object_ids)
        pg_rank_map = self._load_postgres_text_ranks(db, object_ids, query_clean)

        distance_map: Dict[int, float] = {
            obj.id_objet: self._distance_from_user(obj)
            for obj in candidates
        }

        if max_distance is not None and max_distance >= 0:
            candidates = [
                obj for obj in candidates
                if distance_map.get(obj.id_objet, float("inf")) <= max_distance
            ]

        if not candidates:
            return []

        max_popularity = max(popularity_count_map.values(), default=0)
        max_waiting = max(waiting_count_map.values(), default=0)

        if query_clean:
            weights = {
                "text": 0.45 if sort_by_distance else 0.60,
                "availability": 0.18 if sort_by_distance else 0.20,
                "distance": 0.22 if sort_by_distance else 0.05,
                "popularity": 0.09 if sort_by_distance else 0.10,
                "waiting": 0.06 if sort_by_distance else 0.05,
            }
        else:
            weights = {
                "text": 0.0,
                "availability": 0.55,
                "distance": 0.25 if sort_by_distance else 0.10,
                "popularity": 0.12,
                "waiting": 0.08,
            }

        ranked = []

        for obj in candidates:
            haystack = self._build_haystack(obj)
            waiting_count = waiting_count_map.get(obj.id_objet, 0)
            popularity_count = popularity_count_map.get(obj.id_objet, 0)
            distance_value = distance_map.get(obj.id_objet, float("inf"))

            if query_clean:
                token_score = float(fuzz.token_set_ratio(query_clean, haystack))
                partial_score = float(fuzz.partial_ratio(query_clean, haystack))

                coverage_hits = sum(1 for term in expanded_terms if term and term in haystack)
                coverage_score = (coverage_hits / max(1, len(expanded_terms))) * 100.0

                postgres_rank_score = min(100.0, pg_rank_map.get(obj.id_objet, 0.0) * 125.0)

                correction_bonus = 0.0
                for corrected in corrections.values():
                    if corrected and corrected in haystack:
                        correction_bonus += 4.0

                text_score = (
                    token_score * 0.40
                    + partial_score * 0.25
                    + coverage_score * 0.20
                    + postgres_rank_score * 0.15
                    + correction_bonus
                )
            else:
                text_score = 0.0

            availability_score = self._availability_score(obj.statut)
            distance_score = self._distance_score(distance_value)
            popularity_score = (popularity_count / max_popularity * 100.0) if max_popularity > 0 else 0.0
            waiting_score = 100.0 - ((waiting_count / max_waiting) * 100.0) if max_waiting > 0 else 100.0

            final_score = (
                text_score * weights["text"]
                + availability_score * weights["availability"]
                + distance_score * weights["distance"]
                + popularity_score * weights["popularity"]
                + waiting_score * weights["waiting"]
            )

            if target_type and _normalize_text(obj.type_objet) == _normalize_text(str(target_type)):
                final_score += 8.0
            if target_statut and _normalize_text(obj.statut) == _normalize_text(str(target_statut)):
                final_score += 6.0
            if target_marque and _normalize_text(obj.nom_marque) == _normalize_text(str(target_marque)):
                final_score += 5.0
            if target_fonction and any(_normalize_text(f.nom) == _normalize_text(str(target_fonction)) for f in (obj.fonctionnalites or []) if f and f.nom):
                final_score += 4.0
            if target_etage is not None and obj.salle and obj.salle.num_etage == int(target_etage):
                final_score += 5.0

            if query_clean and text_score < 18.0 and not (target_type or target_marque or target_fonction or target_statut or target_etage):
                continue

            obj.distance_m = None if not math.isfinite(distance_value) else round(distance_value, 2)
            obj.waiting_count = int(waiting_count)
            obj.popularity_score = round(popularity_score, 2)
            obj.relevance_score = round(final_score, 2)

            ranked.append((final_score, distance_value, availability_score, obj))

        if not ranked:
            return []

        if sort_by_distance:
            ranked.sort(key=lambda item: (-item[0], item[1], -item[2]))
        else:
            ranked.sort(key=lambda item: (-item[0], -item[2], item[1]))

        return [item[3] for item in ranked]

    def suggest(self, db: Session, query: str, limit: int = 8) -> List[str]:
        raw_query = (query or "").strip()
        if not raw_query:
            return []

        q_norm = _normalize_text(raw_query)
        if not q_norm:
            return []

        cleaned_q_tokens = _clean_noise_terms(_split_words(q_norm))
        q_for_matching = " ".join(cleaned_q_tokens).strip() or q_norm

        candidates: List[Tuple[float, str, str]] = []

        def add_candidate(label: Optional[str], base_score: float):
            if not label:
                return
            clean_label = str(label).strip()
            norm_label = _normalize_text(clean_label)
            if not norm_label:
                return

            if norm_label.startswith(q_for_matching):
                score = 120.0
            elif q_for_matching in norm_label:
                score = 98.0
            else:
                score = float(fuzz.WRatio(q_for_matching, norm_label))
                if score < 70.0:
                    return

            token_hits = sum(1 for token in q_for_matching.split() if token and token in norm_label)
            score = score + base_score + (token_hits * 2.0)

            candidates.append((score, clean_label, norm_label))

        # Dynamic values from database
        models_rows = (
            db.query(models.Objet.nom_model)
            .filter(models.Objet.nom_model.isnot(None))
            .distinct()
            .limit(120)
            .all()
        )
        for row in models_rows:
            add_candidate(row[0] if row else None, 16.0)

        types_rows = (
            db.query(models.Objet.type_objet)
            .filter(models.Objet.type_objet.isnot(None))
            .distinct()
            .limit(80)
            .all()
        )
        for row in types_rows:
            add_candidate(row[0] if row else None, 18.0)

        marques_rows = (
            db.query(models.Objet.nom_marque)
            .filter(models.Objet.nom_marque.isnot(None))
            .distinct()
            .limit(80)
            .all()
        )
        for row in marques_rows:
            add_candidate(row[0] if row else None, 8.0)

        salle_rows = (
            db.query(models.Salle.nom_salle)
            .filter(models.Salle.nom_salle.isnot(None))
            .distinct()
            .limit(80)
            .all()
        )
        for row in salle_rows:
            add_candidate(row[0] if row else None, 7.0)

        fonction_rows = (
            db.query(models.Fonctionnalite.nom)
            .filter(models.Fonctionnalite.nom.isnot(None))
            .distinct()
            .limit(80)
            .all()
        )
        for row in fonction_rows:
            add_candidate(row[0] if row else None, 7.0)

        # If query hints a known type via intent/synonyms, boost canonical suggestion
        available_types = self._load_available_types(db)
        inferred_type = self._infer_type_from_intent_patterns(q_for_matching, available_types)
        if not inferred_type:
            inferred_type = self._infer_type_from_terms(cleaned_q_tokens or _split_words(q_norm), available_types, q_norm)
        if inferred_type:
            add_candidate(inferred_type, 24.0)

        # Typo correction suggestion (ex: "sanne" -> "scanner")
        vocabulary = self._load_domain_vocabulary(db)
        corrected_terms, _ = self._autocorrect_terms(cleaned_q_tokens or _split_words(q_norm), vocabulary)
        corrected_phrase = " ".join(corrected_terms).strip()
        if corrected_phrase and corrected_phrase != q_for_matching:
            add_candidate(corrected_phrase, 22.0)
            inferred_from_corrected = self._infer_type_from_terms(
                corrected_terms,
                available_types,
                corrected_phrase,
            )
            if inferred_from_corrected:
                add_candidate(inferred_from_corrected, 30.0)

        # Floor helper suggestions
        if any(keyword in q_norm for keyword in ["etage", "étage", "floor", "طابق"]):
            etage_rows = (
                db.query(models.Salle.num_etage)
                .filter(models.Salle.num_etage.isnot(None))
                .distinct()
                .order_by(models.Salle.num_etage.asc())
                .limit(10)
                .all()
            )
            for row in etage_rows:
                if row and row[0] is not None:
                    add_candidate(f"Étage {row[0]}", 12.0)

        # Deduplicate by normalized label, keep highest score
        best_by_label: Dict[str, Tuple[float, str]] = {}
        for score, label, norm in candidates:
            if norm not in best_by_label or score > best_by_label[norm][0]:
                best_by_label[norm] = (score, label)

        ordered = sorted(
            best_by_label.values(),
            key=lambda item: (-item[0], len(item[1]))
        )

        return [label for _, label in ordered[: max(1, min(limit, 20))]]


engine = SmartSearchEngine()
