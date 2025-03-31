import discord
import pandas as pd
from discord.ext import commands
from discord import app_commands
import os
import logging
import re
import textwrap
import requests
import json
import time
import threading

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()]
)

TOKEN = os.getenv("DISCORD_BOT_TOKEN")
GUILD_ID = int(os.getenv("DISCORD_GUILD_ID", "0"))
EXCEL_FILE = "/documents/mes_donnees.xlsx"
TRANSLATIONS_CACHE_FILE = "/documents/pokemon_translations.json"
TRANSLATIONS_CACHE = {}
UNDEFINED_TRANSLATIONS = {}  # Pour stocker les traductions qui retournent undefined
REVERSE_TRANSLATIONS = {}  # Pour rechercher par nom dans chaque langue

# Codes de langue pour PokeAPI
LANGUAGES = {
    "en": "en",    # anglais
    "fr": "fr",    # français
    "de": "de",    # allemand
    "ja": "roomaji" # japonais (romaji)
}

# Commandes par langue
COMMANDS = {
    "en": "where",
    "fr": "tesou",
    "de": "wobistdu",
    "ja": "doko"
}

# Descriptions des commandes par langue
COMMAND_DESCRIPTIONS = {
    "en": "Shows spawn information for a Pokémon",
    "fr": "Affiche les conditions de spawn d'un Pokémon",
    "de": "Zeigt Spawn-Informationen für ein Pokémon",
    "ja": "ポケモンのスポーン情報を表示"
}

# Formes régionales: correspondance anglais-translations
REGIONAL_FORMS = {
    "alolan": {
        "en": "Alolan",
        "fr": "d'Alola",
        "de": "von Alola",
        "ja": "Alolan"
    },
    "paldean": {
        "en": "Paldean",
        "fr": "de Paldea",
        "de": "von Paldea",
        "ja": "Paldean"
    },
    "galarian": {
        "en": "Galarian",
        "fr": "de Galar",
        "de": "von Galar",
        "ja": "Galarian"
    },
    "hisuian": {
        "en": "Hisuian",
        "fr": "de Hisui",
        "de": "von Hisui",
        "ja": "Hisuian"
    }
}

if GUILD_ID == 0:
    logging.error("❌ DISCORD_GUILD_ID n'est pas défini. Vérifie tes variables d'environnement.")
    exit(1)

spawn_data = []

def load_translations_cache():
    """Charge le cache des traductions existant ou crée un nouveau fichier"""
    global TRANSLATIONS_CACHE, UNDEFINED_TRANSLATIONS, REVERSE_TRANSLATIONS
    try:
        if os.path.exists(TRANSLATIONS_CACHE_FILE):
            with open(TRANSLATIONS_CACHE_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
                # Charger les traductions standard
                if isinstance(data, dict):
                    if "translations" in data:
                        # Nouveau format multi-langues
                        TRANSLATIONS_CACHE = data.get("translations", {})
                        UNDEFINED_TRANSLATIONS = data.get("undefined_translations", {})
                    else:
                        # Conversion de l'ancien format (français uniquement) vers le nouveau format
                        new_translations = {}
                        for key, value in data.items():
                            new_translations[key] = {"fr": value}
                        TRANSLATIONS_CACHE = new_translations
                        UNDEFINED_TRANSLATIONS = {}
                
            # Initialiser le dictionnaire inverse pour chaque langue
            REVERSE_TRANSLATIONS = {lang: {} for lang in LANGUAGES.keys()}
            for key, translations in TRANSLATIONS_CACHE.items():
                for lang, name in translations.items():
                    if name is not None and lang in REVERSE_TRANSLATIONS:
                        REVERSE_TRANSLATIONS[lang][name.lower()] = key
            
            logging.info(f"Cache de traductions chargé: {len(TRANSLATIONS_CACHE)} entrées standard, {len(UNDEFINED_TRANSLATIONS)} entrées undefined")
        else:
            logging.info("Aucun cache de traductions existant, un nouveau sera créé")
            # Initialiser des dictionnaires vides
            TRANSLATIONS_CACHE = {}
            UNDEFINED_TRANSLATIONS = {}
            REVERSE_TRANSLATIONS = {lang: {} for lang in LANGUAGES.keys()}
    except Exception as e:
        logging.error(f"Erreur lors du chargement du cache de traductions: {e}")
        # En cas d'erreur, initialiser des dictionnaires vides
        TRANSLATIONS_CACHE = {}
        UNDEFINED_TRANSLATIONS = {}
        REVERSE_TRANSLATIONS = {lang: {} for lang in LANGUAGES.keys()}

def save_translations_cache():
    """Sauvegarde le cache des traductions dans un fichier JSON"""
    try:
        # Préparer les données dans le format multi-langues
        cache_data = {
            "translations": TRANSLATIONS_CACHE,
            "undefined_translations": UNDEFINED_TRANSLATIONS
        }
        
        with open(TRANSLATIONS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        logging.info(f"Cache de traductions sauvegardé: {len(TRANSLATIONS_CACHE)} entrées standard, {len(UNDEFINED_TRANSLATIONS)} entrées undefined")
    except Exception as e:
        logging.error(f"Erreur lors de la sauvegarde du cache de traductions: {e}")

def normalize_pokemon_name(name):
    """Extrait le nom de base du Pokémon et les features"""
    if not name:
        return (name, None)
    
    # Stocker la version originale pour référence
    original_name = name
    
    # Extraire les features (tout ce qui suit un espace + caractère spécial)
    features = ""
    feature_match = re.search(r'\s+[^a-zA-Z0-9\s]', name)
    if feature_match:
        features = name[feature_match.start():].strip()
        name = name[:feature_match.start()].strip()
    
    # Cas 1: Traiter les formes régionales (forme régionale en fin de nom)
    for form in REGIONAL_FORMS.keys():
        if name.lower().endswith(f" {form}"):
            base_name = name[:-len(form)-1].strip()
            return (base_name, form)
    
    # Cas 2: Traiter les formes régionales (forme régionale en début de nom)
    parts = name.split()
    if len(parts) > 1 and parts[0].lower() in REGIONAL_FORMS:
        regional_form = parts[0].lower()
        pokemon_name = ' '.join(parts[1:])
        return (pokemon_name, regional_form)
    
    # Cas par défaut: retourner le nom sans modifications
    return (name, None)

def get_pokemon_name(pokemon_name, lang="fr", max_retries=3, force_save=False):
    """Obtient le nom du Pokémon dans la langue spécifiée"""
    if not pokemon_name:
        return pokemon_name
    
    # Conserver le nom original exact pour la mise en cache
    original_name = pokemon_name
    
    # Récupérer les features pour les afficher plus tard
    features = ""
    feature_match = re.search(r'\s+[^a-zA-Z0-9\s]', pokemon_name)
    if feature_match:
        features = pokemon_name[feature_match.start():].strip()
    
    # Normaliser le nom du Pokémon
    normalized_name, regional_form = normalize_pokemon_name(pokemon_name)
    
    # Format spécifique pour l'API
    api_name = normalized_name.lower().replace(' ', '-').replace("'", "")
    
    # Vérifier le cache pour ce Pokémon avec le nom original
    if original_name in TRANSLATIONS_CACHE and lang in TRANSLATIONS_CACHE[original_name]:
        translated_name = TRANSLATIONS_CACHE[original_name][lang]
        
        # Construire le nom complet avec forme régionale et/ou features
        result_name = translated_name
        if regional_form:
            result_name = f"{result_name} {REGIONAL_FORMS[regional_form][lang]}"
        if features:
            result_name = f"{result_name} ({features})"
        
        return result_name
    
    # Vérifier si déjà essayé et ne donnant pas de résultat
    if original_name in UNDEFINED_TRANSLATIONS:
        if lang in UNDEFINED_TRANSLATIONS[original_name] and UNDEFINED_TRANSLATIONS[original_name][lang] is not None:
            # Si une traduction manuelle a été fournie, l'utiliser
            translated_name = UNDEFINED_TRANSLATIONS[original_name][lang]
            result_name = translated_name
            if regional_form:
                result_name = f"{result_name} {REGIONAL_FORMS[regional_form][lang]}"
            if features:
                result_name = f"{result_name} ({features})"
            return result_name
        
        # Sinon utiliser le nom original
        logging.info(f"Utilisant le nom original pour {original_name} (précédemment undefined)")
        result_name = normalized_name
        if regional_form:
            result_name = f"{result_name} {REGIONAL_FORMS[regional_form][lang]}"
        if features:
            result_name = f"{result_name} ({features})"
        
        return result_name
    
    # Essayer l'API avec le nom tel quel
    translations = try_api_request(api_name, max_retries)
    if translations:
        # Initialiser l'entrée dans le cache si elle n'existe pas
        if original_name not in TRANSLATIONS_CACHE:
            TRANSLATIONS_CACHE[original_name] = {}
        
        # Stocker toutes les traductions obtenues
        for language, name in translations.items():
            TRANSLATIONS_CACHE[original_name][language] = name
            
            # Mettre à jour les dictionnaires inverses
            if name is not None and language in REVERSE_TRANSLATIONS:
                REVERSE_TRANSLATIONS[language][name.lower()] = original_name
        
        if force_save:
            save_translations_cache()  # Forcer la sauvegarde immédiate
        
        # Construire le nom complet dans la langue demandée
        if lang in translations and translations[lang]:
            result_name = translations[lang]
            if regional_form:
                result_name = f"{result_name} {REGIONAL_FORMS[regional_form][lang]}"
            if features:
                result_name = f"{result_name} ({features})"
            return result_name
    
    # STRATÉGIE 1: Essayer d'insérer un tiret à différentes positions
    if "-" not in api_name and len(api_name) > 3:
        for i in range(1, len(api_name)):
            test_name = f"{api_name[:i]}-{api_name[i:]}"
            translations = try_api_request(test_name, 1)
            if translations:
                logging.info(f"Nom trouvé avec tiret: {test_name}")
                
                # Initialiser l'entrée dans le cache si elle n'existe pas
                if original_name not in TRANSLATIONS_CACHE:
                    TRANSLATIONS_CACHE[original_name] = {}
                
                # Stocker toutes les traductions obtenues
                for language, name in translations.items():
                    TRANSLATIONS_CACHE[original_name][language] = name
                    
                    # Mettre à jour les dictionnaires inverses
                    if name is not None and language in REVERSE_TRANSLATIONS:
                        REVERSE_TRANSLATIONS[language][name.lower()] = original_name
                
                if force_save:
                    save_translations_cache()  # Forcer la sauvegarde immédiate
                
                # Construire le nom complet dans la langue demandée
                if lang in translations and translations[lang]:
                    result_name = translations[lang]
                    if regional_form:
                        result_name = f"{result_name} {REGIONAL_FORMS[regional_form][lang]}"
                    if features:
                        result_name = f"{result_name} ({features})"
                    return result_name
    
    # STRATÉGIE 2: Essayer avec seulement la première partie (exemple : pichu-spiky, garder pichu seulement)
    if "-" in api_name:
        base_part = api_name.split("-")[0]
        translations = try_api_request(base_part, max_retries)
        if translations:
            logging.info(f"Nom trouvé avec partie de base: {base_part}")
            
            # Initialiser l'entrée dans le cache si elle n'existe pas
            if original_name not in TRANSLATIONS_CACHE:
                TRANSLATIONS_CACHE[original_name] = {}
            
            # Stocker toutes les traductions obtenues
            for language, name in translations.items():
                TRANSLATIONS_CACHE[original_name][language] = name
                
                # Mettre à jour les dictionnaires inverses
                if name is not None and language in REVERSE_TRANSLATIONS:
                    REVERSE_TRANSLATIONS[language][name.lower()] = original_name
            
            if force_save:
                save_translations_cache()  # Forcer la sauvegarde immédiate
            
            # Construire le nom complet dans la langue demandée
            if lang in translations and translations[lang]:
                result_name = translations[lang]
                if regional_form:
                    result_name = f"{result_name} {REGIONAL_FORMS[regional_form][lang]}"
                if features:
                    result_name = f"{result_name} ({features})"
                else:
                    extra_part = "-".join(api_name.split("-")[1:])
                    if extra_part:
                        result_name = f"{result_name} ({extra_part})"
                return result_name
    
    # Si tout échoue, marquer comme undefined et utiliser le nom original
    logging.warning(f"Impossible de trouver une traduction pour {original_name}")
    if original_name not in UNDEFINED_TRANSLATIONS:
        UNDEFINED_TRANSLATIONS[original_name] = {}
    UNDEFINED_TRANSLATIONS[original_name][lang] = None
    
    if force_save:
        save_translations_cache()  # Forcer la sauvegarde immédiate
    
    # Construire le nom complet avec features même si pas de traduction
    result_name = normalized_name
    if regional_form:
        result_name = f"{result_name} {REGIONAL_FORMS[regional_form][lang]}"
    if features:
        result_name = f"{result_name} ({features})"
    
    return result_name

def try_api_request(api_name, max_tries=3):
    """Fonction utilitaire pour essayer une requête API avec différentes tentatives"""
    for attempt in range(max_tries):
        try:
            response = requests.get(f"https://pokeapi.co/api/v2/pokemon-species/{api_name}")
            
            if response.status_code == 200:
                data = response.json()
                # Extraire les noms dans toutes les langues demandées
                translations = {}
                for entry in data["names"]:
                    lang_code = entry["language"]["name"]
                    # Convertir les codes de langue de l'API en nos codes
                    for our_lang, api_lang in LANGUAGES.items():
                        if lang_code == api_lang:
                            translations[our_lang] = entry["name"]
                return translations
            elif response.status_code == 404:
                return None  # Pokémon non trouvé
            else:
                # Autre erreur HTTP, attendre et réessayer
                time.sleep(1)
        except Exception as e:
            time.sleep(1)
    
    return None  # Échec après toutes les tentatives

def preload_all_pokemon_translations():
    """Précharge toutes les traductions des Pokémon présents dans les données"""
    logging.info("Préchargement des traductions de tous les Pokémon...")
    
    # Récupérer tous les noms uniques de Pokémon
    pokemon_to_translate = []
    total_unique = 0
    
    for entry in spawn_data:
        pokemon_name = safe_field(entry.get("Pokemon"))
        if pokemon_name != "∅":
            normalized_name, _ = normalize_pokemon_name(pokemon_name)
            api_name = normalized_name.lower().replace(' ', '-').replace("'", "")
            total_unique += 1
            
            # Vérifier si déjà dans le cache pour toutes les langues
            need_translation = False
            for lang in LANGUAGES.keys():
                if api_name not in TRANSLATIONS_CACHE or lang not in TRANSLATIONS_CACHE[api_name]:
                    if api_name not in UNDEFINED_TRANSLATIONS or lang not in UNDEFINED_TRANSLATIONS[api_name]:
                        need_translation = True
                        break
            
            if need_translation:
                pokemon_to_translate.append(pokemon_name)
    
    total = len(pokemon_to_translate)
    processed = 0
    logging.info(f"Nombre total de Pokémon uniques: {total_unique}, à traduire: {total}")
    
    # Sortir immédiatement si tous les Pokémon sont déjà dans le cache
    if total == 0:
        logging.info("Tous les Pokémon sont déjà traduits dans le cache, aucun appel API nécessaire.")
        return
    
    # Précharger les traductions uniquement pour ceux qui ne sont pas dans le cache
    for pokemon_name in pokemon_to_translate:
        try:
            # On lance une traduction pour la langue française, mais ça récupérera toutes les langues
            translations = get_pokemon_name(pokemon_name, "fr")
            processed += 1
            
            if processed % 10 == 0:
                save_translations_cache()
                logging.info(f"Traduction {processed}/{total} : {pokemon_name} (cache sauvegardé)")
            elif processed % 5 == 0 or processed == total:
                logging.info(f"Traduction {processed}/{total} : {pokemon_name}")
            
            # Délai entre les requêtes
            time.sleep(1.0)
        except Exception as e:
            logging.error(f"Erreur lors de la traduction de {pokemon_name}: {e}")
            time.sleep(5.0)  # Attendre plus longtemps en cas d'erreur
    
    # Sauvegarde finale
    save_translations_cache()
    logging.info(f"Préchargement terminé. {len(TRANSLATIONS_CACHE)} traductions disponibles, {len(UNDEFINED_TRANSLATIONS)} non définies.")

def async_preload_translations():
    """Lance le préchargement des traductions dans un thread séparé pour ne pas bloquer Discord"""
    threading.Thread(target=preload_all_pokemon_translations, daemon=True).start()
    logging.info("Préchargement des traductions lancé en arrière-plan")

def load_spawn_data_from_excel():
    global spawn_data
    try:
        df = pd.read_excel(EXCEL_FILE)
        spawn_data = df.to_dict(orient="records")
        logging.info(f"Données chargées depuis {EXCEL_FILE}. {len(spawn_data)} entrées disponibles.")
    except Exception as e:
        logging.error(f"Erreur lors du chargement du fichier Excel: {e}")
        spawn_data = []

def safe_field(val):
    try:
        if pd.isna(val):
            return "∅"
    except Exception:
        pass
    if isinstance(val, bool):
        return str(val).lower()
    val_str = str(val)
    if val_str.strip() == "" or val_str.lower() == "nan":
        return "∅"
    return val_str

def split_long_field(label, emoji, value, max_length=1700):
    """Divise un champ trop long en plusieurs parties."""
    if len(value) <= max_length:
        return [f"{emoji} **{label}** : {value}"]
    
    items = [item.strip() for item in value.split('|') if item.strip()]
    
    parts = []
    current_part = []
    current_length = 0
    base_prefix = f"{emoji} **{label}** : "
    cont_prefix = f"{emoji} **{label} (suite)** : "
    
    for item in items:
        prefix = base_prefix if not current_part else cont_prefix
        item_length = len(item) + 3
        
        if current_part and (current_length + item_length + len(prefix) > max_length):
            parts.append(prefix + " | ".join(current_part))
            current_part = [item]
            current_length = item_length
        else:
            current_part.append(item)
            current_length += item_length
    
    if current_part:
        prefix = base_prefix if not parts else cont_prefix
        parts.append(prefix + " | ".join(current_part))
    
    return parts

def prepare_message_parts(fields_output, header, max_length=1900):
    """Prépare les parties du message à envoyer."""
    message_parts = []
    current_part = header
    
    for field in fields_output:
        if len(current_part + "\n" + field) > max_length:
            message_parts.append(current_part)
            current_part = field
        else:
            if current_part == header:
                current_part += field
            else:
                current_part += "\n" + field
    
    if current_part:
        message_parts.append(current_part)
    
    return message_parts

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

def extract_regional_form(name, lang="fr"):
    """Extrait la forme régionale d'un nom de Pokémon dans une langue spécifique"""
    for form_en, forms in REGIONAL_FORMS.items():
        if forms[lang].lower() in name.lower():
            return form_en
    return None

async def pokemon_search(interaction: discord.Interaction, pokemon: str, lang: str, show_all: bool = False):
    """Fonction générique de recherche de Pokémon utilisée par toutes les commandes"""
    # Vérifier si c'est une valeur d'autocomplétion (contient un séparateur |)
    exact_pokemon_name = None
    if "|" in pokemon:
        translated_name, exact_pokemon_name = pokemon.split("|", 1)
        search_term = translated_name.lower()
        logging.info(f"Recherche exacte pour {exact_pokemon_name} (traduction: {translated_name})")
    else:
        search_term = pokemon.lower()
    
    # Vérifier si la langue existe dans le dictionnaire inverse
    if lang not in REVERSE_TRANSLATIONS:
        REVERSE_TRANSLATIONS[lang] = {}
    
    # Créer un dictionnaire inversé en minuscules pour la recherche
    reverse_translations_lower = {k.lower(): v.lower() for k, v in REVERSE_TRANSLATIONS[lang].items()}
    
    # Rechercher le Pokémon
    results = []
    for entry in spawn_data:
        pokemon_entry = safe_field(entry.get("Pokemon"))
        
        # Si nous avons un nom exact à chercher (de l'autocomplétion)
        if exact_pokemon_name and pokemon_entry == exact_pokemon_name:
            results.append(entry)
            continue
        
        # Si aucun résultat exact n'est disponible, continuez avec la recherche normale
        if not exact_pokemon_name:
            pokemon_name_lower = pokemon_entry.lower()
            
            # Recherche directe - si le terme de recherche fait partie du nom dans Excel
            if search_term in pokemon_name_lower:
                results.append(entry)
                continue
                
            # Recherche par nom traduit
            if pokemon_entry in TRANSLATIONS_CACHE and lang in TRANSLATIONS_CACHE[pokemon_entry]:
                translated_name = TRANSLATIONS_CACHE[pokemon_entry][lang].lower()
                if search_term in translated_name:
                    results.append(entry)
                    continue
                    
            # Recherche basée sur la correspondance du dictionnaire inverse
            if english_name and english_name in pokemon_name_lower:
                results.append(entry)
                continue
                
            # Pour les formes régionales
            if search_regional_form:
                # Vérifier si la forme régionale correspond
                matches_regional_form = False
                
                # 1. Vérifier si la forme régionale est au début (hisuian arcanine)
                if pokemon_name_lower.startswith(search_regional_form.lower()):
                    matches_regional_form = True
                # 2. Vérifier si la forme régionale est à la fin (arcanine hisuian)
                elif pokemon_name_lower.endswith(search_regional_form.lower()):
                    matches_regional_form = True
                # 3. Vérifier des formes spécifiques
                elif f" {search_regional_form.lower()}" in pokemon_name_lower:
                    matches_regional_form = True
                
                if matches_regional_form:
                    # Obtenir le nom traduit du Pokémon avec sa forme
                    translated_name = get_pokemon_name(pokemon_entry, lang)
                    if translated_name.lower() in search_term.lower() or search_term.lower() in translated_name.lower():
                        results.append(entry)
                        continue
    
    if not results:
        # Message d'erreur localisé selon la langue de recherche
        error_messages = {
            "en": f"❌ No information found for **{pokemon}**.",
            "fr": f"❌ Aucune information trouvée pour **{pokemon}**.",
            "de": f"❌ Keine Informationen gefunden für **{pokemon}**.",
            "ja": f"❌ **{pokemon}**の情報が見つかりませんでした。"
        }
        await interaction.response.send_message(error_messages.get(lang, error_messages["en"]), ephemeral=True)
        return
    
    # Messages de recherche localisés selon la langue
    searching_messages = {
        "en": f"Searching information for **{pokemon}**...",
        "fr": f"Recherche d'informations sur **{pokemon}**...",
        "de": f"Suche nach Informationen zu **{pokemon}**...",
        "ja": f"**{pokemon}**の情報を検索中..."
    }
    
    # Répondre d'abord pour éviter le timeout
    await interaction.response.send_message(searching_messages.get(lang, searching_messages["en"]), ephemeral=True)
    
    for entry_index, entry in enumerate(results):
        # Obtenir le nom du Pokémon avec ses features
        pokemon_name = safe_field(entry.get('Pokemon'))
        
        # Extraire les features pour l'affichage
        features = ""
        feature_match = re.search(r'\s+[^a-zA-Z0-9\s]', pokemon_name)
        if feature_match:
            features = pokemon_name[feature_match.start():].strip()
        
        # Obtenir le nom traduit avec toutes les parties
        translated_name = get_pokemon_name(pokemon_name, lang)
        
        # Messages d'information localisés
        info_header = {
            "en": f"🔍 **Information about {translated_name} (Entry {entry_index+1}/{len(results)})**\n",
            "fr": f"🔍 **Informations sur {translated_name} (Entrée {entry_index+1}/{len(results)})**\n",
            "de": f"🔍 **Informationen zu {translated_name} (Eintrag {entry_index+1}/{len(results)})**\n",
            "ja": f"🔍 **{translated_name}の情報 (エントリー {entry_index+1}/{len(results)})**\n"
        }
        
        if features:
            header = info_header.get(lang, info_header["en"])
        else:
            info_header_with_eng = {
                "en": f"🔍 **Information about {translated_name} ({pokemon_name}) (Entry {entry_index+1}/{len(results)})**\n",
                "fr": f"🔍 **Informations sur {translated_name} ({pokemon_name}) (Entrée {entry_index+1}/{len(results)})**\n",
                "de": f"🔍 **Informationen zu {translated_name} ({pokemon_name}) (Eintrag {entry_index+1}/{len(results)})**\n",
                "ja": f"🔍 **{translated_name} ({pokemon_name})の情報 (エントリー {entry_index+1}/{len(results)})**\n"
            }
            header = info_header_with_eng.get(lang, info_header_with_eng["en"])
            
        fields_output = []
        
        # Traductions des labels pour chaque langue
        field_labels = {
            "Bucket": {
                "en": "Rarity", "fr": "Rareté", 
                "de": "Seltenheit", "ja": "レアリティ"
            },
            "Dimensions": {
                "en": "Dimensions", "fr": "Dimensions",
                "de": "Dimensionen", "ja": "寸法"
            },
            "Meilleurs biomes de spawn": {
                "en": "Best spawn biomes", "fr": "Meilleurs biomes de spawn",
                "de": "Beste Spawn-Biome", "ja": "最適な出現バイオーム"
            },
            "Nombre de concurrents": {
                "en": "Number of competitors", "fr": "Nombre de concurrents",
                "de": "Anzahl der Konkurrenten", "ja": "競合数"
            },
            "Structures": {
                "en": "Structures", "fr": "Structures",
                "de": "Strukturen", "ja": "構造物"
            },
            "Moon Phase": {
                "en": "Moon Phase", "fr": "Phase de Lune",
                "de": "Mondphase", "ja": "月相"
            },
            "Can See Sky": {
                "en": "Can See Sky", "fr": "Peut voir le ciel",
                "de": "Kann den Himmel sehen", "ja": "空が見える"
            },
            "Min X": {
                "en": "Min X", "fr": "Min X",
                "de": "Min X", "ja": "最小 X"
            },
            "Min Y": {
                "en": "Min Y", "fr": "Min Y",
                "de": "Min Y", "ja": "最小 Y"
            },
            "Min Z": {
                "en": "Min Z", "fr": "Min Z",
                "de": "Min Z", "ja": "最小 Z"
            },
            "Max X": {
                "en": "Max X", "fr": "Max X",
                "de": "Max X", "ja": "最大 X"
            },
            "Max Y": {
                "en": "Max Y", "fr": "Max Y",
                "de": "Max Y", "ja": "最大 Y"
            },
            "Max Z": {
                "en": "Max Z", "fr": "Max Z", 
                "de": "Max Z", "ja": "最大 Z"
            },
            "Min Light": {
                "en": "Min Light", "fr": "Min Light", 
                "de": "Min Licht", "ja": "最小光量"
            },
            "Max Light": {
                "en": "Max Light", "fr": "Max Light",
                "de": "Max Licht", "ja": "最大光量"
            },
            "Min Sky Light": {
                "en": "Min Sky Light", "fr": "Min Sky Light",
                "de": "Min Himmelslicht", "ja": "最小空光量"
            },
            "Max Sky Light": {
                "en": "Max Sky Light", "fr": "Max Sky Light",
                "de": "Max Himmelslicht", "ja": "最大空光量"
            },
            "Time Range": {
                "en": "Time Range", "fr": "Plage Horaire",
                "de": "Zeitbereich", "ja": "時間帯"
            },
            "Is Raining": {
                "en": "Is Raining", "fr": "Il pleut",
                "de": "Es regnet", "ja": "雨が降っている"
            },
            "Is Thundering": {
                "en": "Is Thundering", "fr": "Il y a de l'orage",
                "de": "Es gewittert", "ja": "雷が鳴っている"
            },
            "Is Slime Chunk": {
                "en": "Is Slime Chunk", "fr": "Chunk de Slime",
                "de": "Ist Slime-Chunk", "ja": "スライムチャンク"
            },
            "Labels": {
                "en": "Labels", "fr": "Étiquettes",
                "de": "Labels", "ja": "ラベル"
            },
            "Label Mode": {
                "en": "Label Mode", "fr": "Mode d'Étiquette",
                "de": "Label-Modus", "ja": "ラベルモード"
            },
            "Min Width": {
                "en": "Min Width", "fr": "Largeur Min",
                "de": "Min Breite", "ja": "最小幅"
            },
            "Max Width": {
                "en": "Max Width", "fr": "Largeur Max",
                "de": "Max Breite", "ja": "最大幅"
            },
            "Min Height": {
                "en": "Min Height", "fr": "Hauteur Min",
                "de": "Min Höhe", "ja": "最小高"
            },
            "Max Height": {
                "en": "Max Height", "fr": "Hauteur Max",
                "de": "Max Höhe", "ja": "最大高"
            },
            "Needed Nearby Blocks": {
                "en": "Needed Nearby Blocks", "fr": "Blocs Nécessaires à Proximité",
                "de": "Benötigte Blöcke in der Nähe", "ja": "必要な近接ブロック"
            },
            "Needed Base Blocks": {
                "en": "Needed Base Blocks", "fr": "Blocs de Base Nécessaires",
                "de": "Benötigte Basisblöcke", "ja": "必要な基本ブロック"
            },
            "Min Depth": {
                "en": "Min Depth", "fr": "Profondeur Min",
                "de": "Min Tiefe", "ja": "最小深度"
            },
            "Max Depth": {
                "en": "Max Depth", "fr": "Profondeur Max", 
                "de": "Max Tiefe", "ja": "最大深度"
            },
            "Fluid Is Source": {
                "en": "Fluid Is Source", "fr": "Fluide Est Source",
                "de": "Flüssigkeit Ist Quelle", "ja": "流体が湧き水である"
            },
            "Fluid Block": {
                "en": "Fluid Block", "fr": "Bloc de Fluide",
                "de": "Flüssigkeitsblock", "ja": "流体ブロック"
            },
            "Fluid": {
                "en": "Fluid", "fr": "Fluide",
                "de": "Flüssigkeit", "ja": "流体"
            },
            "Contexte": {
                "en": "Context", "fr": "Contexte",
                "de": "Kontext", "ja": "コンテキスト"
            },
            "Key Item": {
                "en": "Key Item", "fr": "Objet Clé",
                "de": "Schlüsselgegenstand", "ja": "キーアイテム"
            },
            "Stone Requirements": {
                "en": "Stone Requirements", "fr": "Exigences de Pierre", 
                "de": "Steinanforderungen", "ja": "石の要件"
            },
            "Custom Pokemons In Team": {
                "en": "Custom Pokemons In Team", "fr": "Pokémons Personnalisés Dans l'Équipe",
                "de": "Benutzerdefinierte Pokémon im Team", "ja": "チーム内のカスタムポケモン"
            },
            "Biomes": {
                "en": "Biomes", "fr": "Biomes",
                "de": "Biome", "ja": "バイオーム"
            }
        }
        
        field_mapping = [
            (field_labels["Bucket"][lang], "📌", "Bucket"),
            (field_labels["Dimensions"][lang], "🌍", "Dimensions"),
            (field_labels["Meilleurs biomes de spawn"][lang], "🌟", "Meilleurs biomes de spawn"),
            (field_labels["Nombre de concurrents"][lang], "🥇", "Nombre de concurrents"),
            (field_labels["Structures"][lang], "🏰", "Structures"),
            (field_labels["Moon Phase"][lang], "🌙", "Moon Phase"),
            (field_labels["Can See Sky"][lang], "☀️", "Can See Sky"),
            (field_labels["Min X"][lang], "⬅️", "Min X"),
            (field_labels["Min Y"][lang], "⬇️", "Min Y"),
            (field_labels["Min Z"][lang], "↙️", "Min Z"),
            (field_labels["Max X"][lang], "➡️", "Max X"),
            (field_labels["Max Y"][lang], "⬆️", "Max Y"),
            (field_labels["Max Z"][lang], "↗️", "Max Z"),
            (field_labels["Min Light"][lang], "💡", "Min Light"),
            (field_labels["Max Light"][lang], "💡", "Max Light"),
            (field_labels["Min Sky Light"][lang], "🌤️", "Min Sky Light"),
            (field_labels["Max Sky Light"][lang], "🌤️", "Max Sky Light"),
            (field_labels["Time Range"][lang], "⏰", "Time Range"),
            (field_labels["Is Raining"][lang], "☔", "Is Raining"),
            (field_labels["Is Thundering"][lang], "⚡", "Is Thundering"),
            (field_labels["Is Slime Chunk"][lang], "🟢", "Is Slime Chunk"),
            (field_labels["Labels"][lang], "🏷️", "Labels"),
            (field_labels["Label Mode"][lang], "📋", "Label Mode"),
            (field_labels["Min Width"][lang], "📏", "Min Width"),
            (field_labels["Max Width"][lang], "📐", "Max Width"),
            (field_labels["Min Height"][lang], "↕️", "Min Height"),
            (field_labels["Max Height"][lang], "↕️", "Max Height"),
            (field_labels["Needed Nearby Blocks"][lang], "🧱", "Needed Nearby Blocks"),
            (field_labels["Needed Base Blocks"][lang], "🧱", "Needed Base Blocks"),
            (field_labels["Min Depth"][lang], "⚓", "Min Depth"),
            (field_labels["Max Depth"][lang], "⚓", "Max Depth"),
            (field_labels["Fluid Is Source"][lang], "🔄", "Fluid Is Source"),
            (field_labels["Fluid Block"][lang], "🌊", "Fluid Block"),
            (field_labels["Fluid"][lang], "💧", "Fluid"),
            (field_labels["Contexte"][lang], "🧭", "Contexte"),
            (field_labels["Key Item"][lang], "🔑", "Key Item"),
            (field_labels["Stone Requirements"][lang], "🪨", "Stone Requirements"),
            (field_labels["Custom Pokemons In Team"][lang], "👥", "Custom Pokemons In Team"),
        ]
        
        # Traiter tous les champs normaux
        for label, emoji, field_name in field_mapping:
            value = safe_field(entry.get(field_name))
            if show_all or (value != "∅" and value):
                # Traitement spécial pour les champs qui peuvent être longs
                if field_name in ["Meilleurs biomes de spawn"] and len(value) > 1700:
                    biomes_parts = split_long_field(label, emoji, value)
                    fields_output.extend(biomes_parts)
                else:
                    fields_output.append(f"{emoji} **{label}** : {value}")
        
        # Traiter le champ des biomes séparément car il peut être très long
        biomes_value = safe_field(entry.get("Biomes"))
        if show_all or (biomes_value != "∅" and biomes_value):
            biomes_parts = split_long_field(field_labels["Biomes"][lang], "🏞️", biomes_value)
            fields_output.extend(biomes_parts)
        
        # Si aucun champ n'a de valeur, ajouter un message par défaut
        if not fields_output:
            no_info_msg = {
                "en": "No specific information is available for this Pokémon.",
                "fr": "Aucune information spécifique n'est disponible pour ce Pokémon.",
                "de": "Keine spezifischen Informationen für dieses Pokémon verfügbar.",
                "ja": "このポケモンに関する特定の情報はありません。"
            }
            fields_output.append(no_info_msg.get(lang, no_info_msg["en"]))
        
        # Préparer les parties du message
        all_parts = prepare_message_parts(fields_output, header)
        
        # Envoyer chaque partie
        part_translations = {
            "en": "Part",
            "fr": "Partie",
            "de": "Teil",
            "ja": "パート"
        }
        
        for i, part in enumerate(all_parts):
            part_indicator = f" ({part_translations.get(lang, 'Part')} {i+1}/{len(all_parts)})" if len(all_parts) > 1 else ""
            try:
                await interaction.followup.send(part + part_indicator, ephemeral=True)
            except discord.errors.HTTPException as e:
                logging.error(f"Erreur lors de l'envoi du message (longueur: {len(part)}): {e}")
                # Si le message est encore trop long, le diviser davantage
                chunks = textwrap.wrap(part, width=1900, replace_whitespace=False, break_long_words=True)
                for j, chunk in enumerate(chunks):
                    sub_indicator = f" ({part_translations.get(lang, 'Part')} {i+1}.{j+1}/{len(all_parts)}.{len(chunks)})"
                    await interaction.followup.send(chunk + sub_indicator, ephemeral=True)

async def pokemon_autocomplete(interaction: discord.Interaction, current: str, lang: str):
    """Fonction d'autocomplétion pour les Pokémon dans la langue spécifiée"""
    current_lower = current.lower()
    
    # Utiliser un dictionnaire pour stocker les noms uniques et éviter les doublons
    unique_pokemon = {}
    
    for entry in spawn_data:
        pokemon_name = safe_field(entry.get("Pokemon"))
        if pokemon_name == "∅":
            continue
            
        # Obtenir la traduction seulement si elle existe déjà dans le cache
        translated_name = pokemon_name  # Par défaut, utiliser le nom original
        
        if pokemon_name in TRANSLATIONS_CACHE and lang in TRANSLATIONS_CACHE[pokemon_name]:
            translated_name = TRANSLATIONS_CACHE[pokemon_name][lang]
        
        # Vérifier si la recherche correspond à un des noms
        if current_lower in translated_name.lower() or current_lower in pokemon_name.lower():
            # Créer une clé unique basée sur la traduction et le nom original
            unique_key = f"{translated_name}|{pokemon_name}"
            
            # Ne pas ajouter de doublons
            if unique_key not in unique_pokemon:
                display_name = f"{translated_name} ({pokemon_name})"
                # Si la traduction est identique au nom original, ne pas dupliquer
                if translated_name.lower() == pokemon_name.lower():
                    display_name = pokemon_name
                
                # Stocker l'original et la traduction dans la valeur
                value = f"{translated_name}|{pokemon_name}"
                    
                unique_pokemon[unique_key] = app_commands.Choice(name=display_name, value=value)
    
    # Convertir le dictionnaire en liste
    choices = list(unique_pokemon.values())
    
    # Limiter à 25 résultats et trier
    return sorted(choices, key=lambda x: x.name)[:25]

# Création des commandes
@bot.tree.command(guild=discord.Object(id=GUILD_ID), name="where", description=COMMAND_DESCRIPTIONS["en"])
@app_commands.describe(pokemon="Name of the Pokémon", show_all="Show all fields (even empty ones)")
async def where(interaction: discord.Interaction, pokemon: str, show_all: bool = False):
    await pokemon_search(interaction, pokemon, "en", show_all)

@where.autocomplete("pokemon")
async def where_autocomplete(interaction: discord.Interaction, current: str):
    return await pokemon_autocomplete(interaction, current, "en")

@bot.tree.command(guild=discord.Object(id=GUILD_ID), name="tesou", description=COMMAND_DESCRIPTIONS["fr"])
@app_commands.describe(pokemon="Nom du Pokémon recherché", show_all="Afficher tous les champs (même vides)")
async def tesou(interaction: discord.Interaction, pokemon: str, show_all: bool = False):
    await pokemon_search(interaction, pokemon, "fr", show_all)

@tesou.autocomplete("pokemon")
async def tesou_autocomplete(interaction: discord.Interaction, current: str):
    return await pokemon_autocomplete(interaction, current, "fr")

@bot.tree.command(guild=discord.Object(id=GUILD_ID), name="wobistdu", description=COMMAND_DESCRIPTIONS["de"])
@app_commands.describe(pokemon="Name des Pokémon", show_all="Alle Felder anzeigen (auch leere)")
async def wobistdu(interaction: discord.Interaction, pokemon: str, show_all: bool = False):
    await pokemon_search(interaction, pokemon, "de", show_all)

@wobistdu.autocomplete("pokemon")
async def wobistdu_autocomplete(interaction: discord.Interaction, current: str):
    return await pokemon_autocomplete(interaction, current, "de")

@bot.tree.command(guild=discord.Object(id=GUILD_ID), name="doko", description=COMMAND_DESCRIPTIONS["ja"])
@app_commands.describe(pokemon="ポケモンの名前", show_all="すべてのフィールドを表示（空欄も含む）")
async def doko(interaction: discord.Interaction, pokemon: str, show_all: bool = False):
    await pokemon_search(interaction, pokemon, "ja", show_all)

@doko.autocomplete("pokemon")
async def doko_autocomplete(interaction: discord.Interaction, current: str):
    return await pokemon_autocomplete(interaction, current, "ja")

@bot.event
async def on_ready():
    load_translations_cache()
    load_spawn_data_from_excel()
    
    # Précharger toutes les traductions dans un thread séparé
    async_preload_translations()
    
    guild = discord.Object(id=GUILD_ID)
    try:
        synced = await bot.tree.sync(guild=guild)
        logging.info(f"{len(synced)} commandes synchronisées sur le serveur {guild.id}.")
    except Exception as e:
        logging.error(f"Erreur de synchronisation des commandes : {e}")
    logging.info(f"✅ Bot connecté en tant que {bot.user}")

bot.run(TOKEN)
